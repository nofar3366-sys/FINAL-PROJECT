from datetime import date as date_type
from datetime import datetime, time, timedelta

from sqlalchemy import func, select

from models import Booking, Trainer, WorkoutSession, db


def get_class_availability_skill(
    date: str, specialty: str
) -> dict[str, object]:
    """Query classes by ISO date and trainer specialty with live capacity.

    This is a read-only AI tool. Controllers must authenticate the caller before
    execution; the skill returns no private member information.
    """

    try:
        requested_date = date_type.fromisoformat(date)
    except ValueError as exc:
        raise ValueError("Date must use YYYY-MM-DD format.") from exc
    specialty = specialty.strip()
    if not specialty:
        raise ValueError("Specialty is required.")

    day_start = datetime.combine(requested_date, time.min)
    day_end = day_start + timedelta(days=1)
    sessions = db.session.scalars(
        select(WorkoutSession)
        .join(WorkoutSession.trainer)
        .where(
            WorkoutSession.starts_at >= day_start,
            WorkoutSession.starts_at < day_end,
            WorkoutSession.status == "scheduled",
            Trainer.specialty.ilike(f"%{specialty}%"),
        )
        .order_by(WorkoutSession.starts_at)
    ).all()
    return {
        "date": requested_date.isoformat(),
        "specialty": specialty,
        "classes": [
            {
                "session_id": workout_session.id,
                "title": workout_session.title,
                "trainer": workout_session.trainer.full_name,
                "starts_at": workout_session.starts_at.isoformat(),
                "remaining_capacity": workout_session.remaining_capacity,
                "status": (
                    "full"
                    if workout_session.remaining_capacity == 0
                    else "available"
                ),
            }
            for workout_session in sessions
        ],
    }


def check_class_availability_skill(session_id: int) -> dict[str, object]:
    """Return authoritative read-only capacity information for one class."""

    workout_session = db.session.get(WorkoutSession, session_id)
    if workout_session is None:
        return {"found": False, "session_id": session_id}

    active_bookings = db.session.scalar(
        select(func.count(Booking.id)).where(
            Booking.workout_session_id == session_id,
            Booking.status == "booked",
        )
    )
    remaining = max(0, workout_session.max_capacity - int(active_bookings or 0))
    return {
        "found": True,
        "session_id": workout_session.id,
        "title": workout_session.title,
        "starts_at": workout_session.starts_at.isoformat(),
        "status": workout_session.status,
        "max_capacity": workout_session.max_capacity,
        "active_bookings": int(active_bookings or 0),
        "remaining_capacity": remaining,
        "is_available": workout_session.status == "scheduled" and remaining > 0,
    }
