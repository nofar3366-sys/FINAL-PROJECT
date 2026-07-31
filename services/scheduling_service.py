from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from models import Booking, Member, Trainer, WorkoutSession, db
from models.time_utils import combine_utc, ensure_utc, utc_now
from services.db_transactions import begin_write_transaction


class SchedulingError(ValueError):
    pass


def validate_schedule_payload(
    payload: object, trainers: list[Trainer]
) -> dict[str, object]:
    """Normalize untrusted LLM output into bounded scheduling arguments."""

    if not isinstance(payload, dict):
        raise SchedulingError("AI response must be a JSON object.")
    if not trainers:
        raise SchedulingError("No active trainers are available.")

    trainer_name = " ".join(str(payload.get("trainer_name", "")).split())
    matches = [
        trainer
        for trainer in trainers
        if trainer.full_name.casefold() == trainer_name.casefold()
    ]
    if len(matches) != 1:
        raise SchedulingError("AI response did not select one active trainer.")

    title = " ".join(str(payload.get("title", "")).split())
    if not title:
        raise SchedulingError("AI response did not include a class title.")
    title = title[:150]

    weekday = str(payload.get("weekday", "")).strip().lower()
    valid_weekdays = {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }
    if weekday not in valid_weekdays:
        raise SchedulingError("AI response contained an invalid weekday.")

    try:
        parsed_time = time.fromisoformat(str(payload.get("start_time", "")).strip())
        max_capacity = int(payload.get("max_capacity", 0))
        occurrences = int(payload.get("occurrences", 4))
        duration_minutes = int(payload.get("duration_minutes", 60))
    except (TypeError, ValueError) as exc:
        raise SchedulingError("AI response contained invalid numeric/time values.") from exc

    if not 1 <= max_capacity <= 100:
        raise SchedulingError("Capacity must be between 1 and 100.")
    if not 1 <= occurrences <= 12:
        raise SchedulingError("Occurrences must be between 1 and 12.")
    if not 15 <= duration_minutes <= 240:
        raise SchedulingError("Duration must be between 15 and 240 minutes.")

    return {
        "trainer_name": matches[0].full_name,
        "title": title,
        "weekday": weekday.title(),
        "start_time": parsed_time.strftime("%H:%M"),
        "max_capacity": max_capacity,
        "occurrences": occurrences,
        "duration_minutes": duration_minutes,
    }


def create_fallback_workout_sessions(
    trainer_id: int, *, occurrences: int = 4
) -> list[int]:
    """Persist realistic sessions when the external AI service is unavailable."""

    titles = (
        "Functional Fitness",
        "Mobility & Core",
        "Strength Circuit",
        "Cardio Conditioning",
    )
    now = utc_now()
    created: list[WorkoutSession] = []
    try:
        begin_write_transaction()
        trainer = db.session.get(Trainer, trainer_id, with_for_update=True)
        if trainer is None or not trainer.is_active:
            raise SchedulingError(
                "No active trainer is available for fallback workouts."
            )
        for index in range(max(1, min(occurrences, len(titles)))):
            candidate_date = (now + timedelta(days=index + 2)).date()
            candidate = combine_utc(candidate_date, time(hour=18 + (index % 2)))
            # Move forward until this trainer has a free slot.
            for _ in range(14):
                try:
                    _check_trainer_conflict(trainer.id, candidate, 60)
                    break
                except SchedulingError:
                    candidate += timedelta(days=1)
            else:
                raise SchedulingError("Could not find free fallback workout slots.")

            workout = WorkoutSession(
                trainer=trainer,
                title=titles[index],
                starts_at=candidate,
                duration_minutes=60,
                max_capacity=12,
                status="scheduled",
            )
            db.session.add(workout)
            created.append(workout)

        db.session.commit()
        return [workout.id for workout in created]
    except Exception:
        db.session.rollback()
        raise


def create_session(
    *,
    trainer_id: int,
    title: str,
    starts_at: datetime,
    duration_minutes: int,
    max_capacity: int,
) -> WorkoutSession:
    if not title.strip():
        raise SchedulingError("Session title is required.")
    starts_at = ensure_utc(starts_at)
    if starts_at <= utc_now():
        raise SchedulingError("Session must start in the future.")
    if duration_minutes <= 0 or max_capacity <= 0:
        raise SchedulingError("Duration and capacity must be positive.")

    try:
        begin_write_transaction()
        # Serializes all schedule writes for one trainer.
        trainer = db.session.get(Trainer, trainer_id, with_for_update=True)
        if trainer is None or not trainer.is_active:
            raise SchedulingError("Select an active trainer.")
        _check_trainer_conflict(trainer_id, starts_at, duration_minutes)

        workout_session = WorkoutSession(
            trainer=trainer,
            title=title.strip()[:150],
            starts_at=starts_at,
            duration_minutes=duration_minutes,
            max_capacity=max_capacity,
            status="scheduled",
        )
        db.session.add(workout_session)
        db.session.commit()
        return workout_session
    except Exception:
        db.session.rollback()
        raise


def cancel_session(workout_session_id: int) -> None:
    """Cancel a session and refund every active booking once."""

    try:
        begin_write_transaction()
        workout_session = db.session.get(
            WorkoutSession, workout_session_id, with_for_update=True
        )
        if workout_session is None:
            raise SchedulingError("Session was not found.")
        if workout_session.status != "scheduled":
            raise SchedulingError("Only scheduled sessions can be cancelled.")
        if ensure_utc(workout_session.starts_at) <= utc_now():
            raise SchedulingError("Started sessions cannot be cancelled.")

        bookings = db.session.scalars(
            select(Booking)
            .where(
                Booking.workout_session_id == workout_session_id,
                Booking.status == "booked",
            )
            .order_by(Booking.id)
            .with_for_update()
        ).all()
        member_ids = sorted({booking.member_id for booking in bookings})
        members = {
            member.id: member
            for member in db.session.scalars(
                select(Member)
                .where(Member.id.in_(member_ids))
                .order_by(Member.id)
                .with_for_update()
            ).all()
        } if member_ids else {}

        workout_session.status = "cancelled"
        for booking in bookings:
            booking.status = "cancelled"
            booking.cancelled_at = utc_now()
            if booking.credit_consumed and not booking.credit_refunded:
                member = members.get(booking.member_id)
                if member is None:
                    raise SchedulingError("A booked member could not be locked.")
                member.credit_balance += 1
                booking.credit_refunded = True
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise


def create_recurring_sessions(
    *,
    trainer_name: str,
    title: str,
    weekday: str,
    start_time: str,
    max_capacity: int,
    occurrences: int = 4,
    duration_minutes: int = 60,
) -> list[int]:
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    weekday_number = weekdays.get(weekday.strip().lower())
    if weekday_number is None:
        raise SchedulingError("AI response contained an invalid weekday.")
    if occurrences < 1 or occurrences > 12:
        raise SchedulingError("Occurrences must be between 1 and 12.")
    try:
        parsed_time = time.fromisoformat(start_time)
    except ValueError as exc:
        raise SchedulingError("AI response contained an invalid time.") from exc
    if max_capacity <= 0 or duration_minutes <= 0:
        raise SchedulingError("Capacity and duration must be positive.")

    today = date.today()
    days_ahead = (weekday_number - today.weekday()) % 7
    first_start = combine_utc(today + timedelta(days=days_ahead), parsed_time)
    if first_start <= utc_now():
        first_start += timedelta(days=7)

    try:
        begin_write_transaction()
        requested_name = " ".join(trainer_name.split()).casefold()
        trainers = [
            trainer
            for trainer in db.session.scalars(
                select(Trainer)
                .where(Trainer.is_active.is_(True))
                .with_for_update()
            ).all()
            if trainer.full_name.casefold() == requested_name
        ]
        if len(trainers) != 1:
            raise SchedulingError("The trainer name must match one active trainer.")
        trainer = trainers[0]

        starts = [first_start + timedelta(weeks=index) for index in range(occurrences)]
        for starts_at in starts:
            _check_trainer_conflict(trainer.id, starts_at, duration_minutes)

        created = [
            WorkoutSession(
                trainer=trainer,
                title=title.strip()[:150],
                starts_at=starts_at,
                duration_minutes=duration_minutes,
                max_capacity=max_capacity,
                status="scheduled",
            )
            for starts_at in starts
        ]
        db.session.add_all(created)
        db.session.commit()
        return [workout_session.id for workout_session in created]
    except Exception:
        db.session.rollback()
        raise


def _check_trainer_conflict(
    trainer_id: int, starts_at: datetime, duration_minutes: int
) -> None:
    starts_at = ensure_utc(starts_at)
    proposed_end = starts_at + timedelta(minutes=duration_minutes)
    existing_sessions = db.session.scalars(
        select(WorkoutSession).where(
            WorkoutSession.trainer_id == trainer_id,
            WorkoutSession.status == "scheduled",
        )
    ).all()
    for existing in existing_sessions:
        existing_start = ensure_utc(existing.starts_at)
        existing_end = ensure_utc(existing.ends_at)
        if starts_at < existing_end and proposed_end > existing_start:
            raise SchedulingError(
                f"Trainer already has a session at {existing_start:%Y-%m-%d %H:%M}."
            )
