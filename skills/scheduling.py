from datetime import datetime

from models import Trainer, db
from services.scheduling_service import create_recurring_sessions, create_session


def schedule_class_skill(
    trainer_id: int, date_time: str, capacity: int
) -> dict[str, object]:
    """Create one validated class from AI-extracted manager instructions.

    The manager controller is responsible for authorization. The skill validates
    the active trainer, future ISO date/time, positive capacity, and schedule
    conflicts through the shared scheduling service.
    """

    trainer = db.session.get(Trainer, trainer_id)
    if trainer is None:
        raise ValueError("Trainer was not found.")
    try:
        starts_at = datetime.fromisoformat(date_time)
    except ValueError as exc:
        raise ValueError("Date/time must use ISO format.") from exc

    workout_session = create_session(
        trainer_id=trainer.id,
        title=f"{trainer.specialty} Class",
        starts_at=starts_at,
        duration_minutes=60,
        max_capacity=int(capacity),
    )
    return {
        "session_id": workout_session.id,
        "title": workout_session.title,
        "trainer": trainer.full_name,
        "starts_at": workout_session.starts_at.isoformat(),
        "capacity": workout_session.max_capacity,
        "status": "created",
    }


def schedule_recurring_sessions_skill(
    *,
    trainer_name: str,
    title: str,
    weekday: str,
    start_time: str,
    max_capacity: int,
    occurrences: int = 4,
    duration_minutes: int = 60,
) -> dict[str, object]:
    """Create validated weekly sessions after a manager authorizes the tool call."""

    session_ids = create_recurring_sessions(
        trainer_name=trainer_name,
        title=title,
        weekday=weekday,
        start_time=start_time,
        max_capacity=max_capacity,
        occurrences=occurrences,
        duration_minutes=duration_minutes,
    )
    return {
        "created_count": len(session_ids),
        "session_ids": session_ids,
    }
