from datetime import date, datetime, time, timedelta

from sqlalchemy import select, text

from models import Trainer, WorkoutSession, db


class SchedulingError(ValueError):
    pass


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
    if starts_at <= datetime.now():
        raise SchedulingError("Session must start in the future.")
    if duration_minutes <= 0 or max_capacity <= 0:
        raise SchedulingError("Duration and capacity must be positive.")

    trainer = db.session.get(Trainer, trainer_id)
    if trainer is None or not trainer.is_active:
        raise SchedulingError("Select an active trainer.")
    _check_trainer_conflict(trainer_id, starts_at, duration_minutes)

    workout_session = WorkoutSession(
        trainer=trainer,
        title=title.strip(),
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        max_capacity=max_capacity,
        status="scheduled",
    )
    db.session.add(workout_session)
    db.session.commit()
    return workout_session


def cancel_session(workout_session_id: int) -> None:
    """Cancel a session and refund every active booking once."""

    db.session.rollback()
    try:
        db.session.execute(text("BEGIN IMMEDIATE"))
        workout_session = db.session.get(WorkoutSession, workout_session_id)
        if workout_session is None:
            raise SchedulingError("Session was not found.")
        if workout_session.status != "scheduled":
            raise SchedulingError("Only scheduled sessions can be cancelled.")
        if workout_session.starts_at <= datetime.now():
            raise SchedulingError("Started sessions cannot be cancelled.")

        workout_session.status = "cancelled"
        for booking in workout_session.bookings:
            if booking.status != "booked":
                continue
            booking.status = "cancelled"
            booking.cancelled_at = datetime.now()
            if booking.credit_consumed and not booking.credit_refunded:
                booking.member.credit_balance += 1
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

    trainers = db.session.scalars(
        select(Trainer).where(
            Trainer.full_name.ilike(f"%{trainer_name.strip()}%"),
            Trainer.is_active.is_(True),
        )
    ).all()
    if len(trainers) != 1:
        raise SchedulingError("The trainer name must match one active trainer.")
    trainer = trainers[0]

    today = date.today()
    days_ahead = (weekday_number - today.weekday()) % 7
    first_start = datetime.combine(today + timedelta(days=days_ahead), parsed_time)
    if first_start <= datetime.now():
        first_start += timedelta(days=7)

    starts = [first_start + timedelta(weeks=index) for index in range(occurrences)]
    for starts_at in starts:
        _check_trainer_conflict(trainer.id, starts_at, duration_minutes)

    created = [
        WorkoutSession(
            trainer=trainer,
            title=title.strip(),
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


def _check_trainer_conflict(
    trainer_id: int, starts_at: datetime, duration_minutes: int
) -> None:
    proposed_end = starts_at + timedelta(minutes=duration_minutes)
    existing_sessions = db.session.scalars(
        select(WorkoutSession).where(
            WorkoutSession.trainer_id == trainer_id,
            WorkoutSession.status == "scheduled",
        )
    ).all()
    for existing in existing_sessions:
        if starts_at < existing.ends_at and proposed_end > existing.starts_at:
            raise SchedulingError(
                f"Trainer already has a session at {existing.starts_at:%Y-%m-%d %H:%M}."
            )
