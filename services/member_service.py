from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload

from models import Booking, Member, MembershipPurchase, WorkoutSession, db
from models.time_utils import ensure_utc, utc_now
from services.ai_service import AIServiceError, KnowledgeDocument


WEEK_DAYS = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)


class MemberServiceError(RuntimeError):
    pass


def build_dashboard_context(member: Member) -> tuple[dict, bool]:
    """Build template-safe primitives so Jinja never touches fragile ORM graphs."""

    member_name = (
        f"{getattr(member, 'first_name', '') or ''} "
        f"{getattr(member, 'last_name', '') or ''}".strip()
        or "Member"
    )
    try:
        credit_balance = int(getattr(member, "credit_balance", 0) or 0)
    except (TypeError, ValueError):
        credit_balance = 0
    membership_expires_on = getattr(member, "membership_expires_on", None)
    try:
        membership_active = bool(member.has_active_membership())
    except Exception:
        membership_active = bool(
            getattr(member, "status", None) == "active"
            and membership_expires_on is not None
            and membership_expires_on >= date.today()
        )

    upcoming_items: list[dict] = []
    used_credits = 0
    query_failed = False
    try:
        now = utc_now()
        bookings = (
            db.session.scalars(
                select(Booking)
                .options(
                    joinedload(Booking.workout_session).joinedload(
                        WorkoutSession.trainer
                    )
                )
                .where(
                    Booking.member_id == member.id,
                    Booking.status == "booked",
                )
            )
            .unique()
            .all()
        )
        for booking in bookings:
            workout_session = booking.workout_session
            if (
                workout_session is None
                or getattr(workout_session, "starts_at", None) is None
            ):
                continue
            try:
                starts = ensure_utc(workout_session.starts_at)
            except Exception:
                continue
            if starts <= now:
                continue
            trainer = getattr(workout_session, "trainer", None)
            try:
                trainer_name = (
                    trainer.full_name if trainer is not None else "Trainer"
                )
            except Exception:
                trainer_name = "Trainer"
            upcoming_items.append(
                {
                    "day": starts.strftime("%d"),
                    "month": starts.strftime("%b"),
                    "title": getattr(workout_session, "title", None) or "Workout",
                    "when": starts.strftime("%A at %H:%M"),
                    "trainer": trainer_name,
                    "starts_at": starts,
                }
            )
        upcoming_items.sort(key=lambda item: item["starts_at"])
        used_credits = int(
            db.session.scalar(
                select(func.count(Booking.id)).where(
                    Booking.member_id == member.id,
                    Booking.status == "booked",
                    Booking.credit_consumed.is_(True),
                    Booking.credit_refunded.is_(False),
                )
            )
            or 0
        )
    except Exception:
        upcoming_items = []
        used_credits = 0
        query_failed = True

    return {
        "member": member,
        "member_name": member_name,
        "membership_active": membership_active,
        "credit_balance": credit_balance,
        "membership_expires_on": membership_expires_on,
        "used_credits": used_credits,
        "upcoming_bookings": upcoming_items,
    }, query_failed


def build_schedule_context(member: Member) -> dict:
    sessions = (
        db.session.scalars(
            select(WorkoutSession)
            .where(
                WorkoutSession.status == "scheduled",
                WorkoutSession.starts_at > utc_now(),
            )
            .order_by(WorkoutSession.starts_at)
        )
        .unique()
        .all()
    )
    bookings = db.session.scalars(
        select(Booking)
        .options(joinedload(Booking.workout_session))
        .where(Booking.member_id == member.id)
        .order_by(Booking.booked_at.desc())
    ).all()
    booked_session_ids = {
        booking.workout_session_id
        for booking in bookings
        if booking.status == "booked"
    }
    workouts_by_day = {day: [] for day in WEEK_DAYS}
    for workout_session in sessions:
        day_index = (workout_session.starts_at.weekday() + 1) % 7
        workout_type = _workout_type(
            workout_session.title, workout_session.trainer.specialty
        )
        workouts_by_day[WEEK_DAYS[day_index]].append(
            {
                "id": workout_session.id,
                "time": workout_session.starts_at.strftime("%H:%M"),
                "date": workout_session.starts_at.strftime("%d %b"),
                "title": workout_session.title,
                "trainer": workout_session.trainer.full_name,
                "specialty": workout_session.trainer.specialty,
                "type": workout_type,
                "type_label": workout_type.title(),
                "status": workout_session.status,
                "remaining_capacity": workout_session.remaining_capacity,
                "duration_minutes": workout_session.duration_minutes,
                "is_booked": workout_session.id in booked_session_ids,
            }
        )
    return {
        "member": member,
        "bookings": bookings,
        "week_days": WEEK_DAYS,
        "workouts_by_day": workouts_by_day,
    }


def answer_schedule_question(question: str, ai_service) -> str:
    if not question:
        raise ValueError("Please enter a question.")
    sessions = db.session.scalars(
        select(WorkoutSession)
        .options(
            joinedload(WorkoutSession.trainer),
            selectinload(WorkoutSession.bookings),
        )
        .where(
            WorkoutSession.status == "scheduled",
            WorkoutSession.starts_at > utc_now(),
        )
        .order_by(WorkoutSession.starts_at)
        .limit(12)
    ).all()
    schedule_text = "\n".join(
        f"{item.title} with {item.trainer.full_name} on "
        f"{item.starts_at:%Y-%m-%d at %H:%M}; "
        f"{item.remaining_capacity} places remaining."
        for item in sessions
    )
    answer = ai_service.ask(
        question,
        (
            KnowledgeDocument(
                key="live-schedule",
                title="Current training schedule",
                content=schedule_text or "No upcoming sessions are scheduled.",
            ),
        ),
    )
    if not isinstance(answer, str) or not answer.strip():
        raise AIServiceError("The AI service returned an empty response.")
    return answer


def recommend_workout(member: Member, goal: str, ai_service) -> str:
    upcoming = db.session.scalars(
        select(WorkoutSession)
        .options(
            joinedload(WorkoutSession.trainer),
            selectinload(WorkoutSession.bookings),
        )
        .where(
            WorkoutSession.status == "scheduled",
            WorkoutSession.starts_at > utc_now(),
        )
        .order_by(WorkoutSession.starts_at)
        .limit(20)
    ).all()
    available_classes = [
        {
            "title": item.title,
            "specialty": item.trainer.specialty,
            "starts_at": item.starts_at.strftime("%A, %d %B at %H:%M"),
            "remaining_capacity": item.remaining_capacity,
        }
        for item in upcoming
        if item.remaining_capacity > 0
    ]
    recent_bookings = db.session.scalars(
        select(Booking)
        .options(joinedload(Booking.workout_session))
        .where(
            Booking.member_id == member.id,
            Booking.status == "booked",
        )
        .order_by(Booking.booked_at.desc())
        .limit(3)
    ).all()
    return ai_service.recommend_workout(
        goal,
        {
            "name": member.full_name,
            "credits": member.credit_balance,
            "membership_active": member.has_active_membership(),
            "recent_workouts": ", ".join(
                booking.workout_session.title for booking in recent_bookings
            ),
        },
        available_classes,
    )


def finalize_purchase_receipt(
    purchase_id: int, member: Member, receipt_email
) -> str:
    purchase_record = db.session.get(MembershipPurchase, purchase_id)
    if purchase_record is None:
        raise MemberServiceError(
            f"Committed purchase {purchase_id} could not be reloaded"
        )
    result = receipt_email.send_receipt(
        to_email=member.user.email,
        member_name=member.full_name,
        plan_name=purchase_record.plan.name,
        amount_cents=purchase_record.amount_paid_cents,
        credits=purchase_record.plan.credits,
        expires_on=member.membership_expires_on.isoformat(),
    )
    purchase_record.receipt_status = result.status
    purchase_record.receipt_reference = result.reference
    db.session.commit()
    return result.status


def _workout_type(title: str, specialty: str) -> str:
    value = f"{title} {specialty}".lower()
    if "strength" in value or "functional" in value:
        return "strength"
    if "cardio" in value or "hiit" in value:
        return "cardio"
    if "pilates" in value:
        return "pilates"
    if "yoga" in value or "mobility" in value:
        return "yoga"
    return "general"
