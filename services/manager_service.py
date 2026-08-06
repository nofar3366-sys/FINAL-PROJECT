import csv
from datetime import datetime
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from models import (
    Booking,
    Member,
    MembershipPurchase,
    MembershipSubscription,
    Trainer,
    User,
    WorkoutSession,
    db,
)
from services.scheduling_service import (
    create_fallback_workout_sessions,
    validate_schedule_payload,
)
from skills.scheduling import schedule_recurring_sessions_skill


class ManagerServiceError(ValueError):
    pass


def get_dashboard_context() -> dict:
    return {
        "counts": {
            "members": db.session.scalar(select(func.count(Member.id))),
            "trainers": db.session.scalar(select(func.count(Trainer.id))),
            "sessions": db.session.scalar(select(func.count(WorkoutSession.id))),
            "bookings": db.session.scalar(
                select(func.count(Booking.id)).where(Booking.status == "booked")
            ),
            "revenue_cents": db.session.scalar(
                select(
                    func.coalesce(func.sum(MembershipPurchase.amount_paid_cents), 0)
                )
            ),
        },
        "members": db.session.scalars(
            select(Member).order_by(Member.created_at.desc()).limit(5)
        ).all(),
        "trainers": db.session.scalars(
            select(Trainer).order_by(Trainer.created_at.desc()).limit(5)
        ).all(),
    }


def create_member(values: dict) -> Member:
    if _email_in_use(values["email"]):
        raise ManagerServiceError("An account with this email already exists.")
    user = User(
        email=values["email"], role="member", is_active=values["is_active"]
    )
    user.set_password(values["password"])
    member = Member(
        user=user,
        first_name=values["first_name"],
        last_name=values["last_name"],
        phone=values["phone"],
        membership_expires_on=values["expiry"],
        credit_balance=values["credits"],
        status=values["status"],
    )
    db.session.add(member)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ManagerServiceError("The member could not be created.") from exc
    return member


def update_member(member: Member, values: dict) -> None:
    if _email_in_use(values["email"], excluding_user_id=member.user_id):
        raise ManagerServiceError("An account with this email already exists.")
    member.user.email = values["email"]
    member.user.is_active = values["is_active"]
    member.first_name = values["first_name"]
    member.last_name = values["last_name"]
    member.phone = values["phone"]
    member.membership_expires_on = values["expiry"]
    member.credit_balance = values["credits"]
    member.status = values["status"]
    db.session.commit()


def set_member_active(member: Member, active: bool) -> None:
    member.status = "active" if active else "inactive"
    member.user.is_active = active
    db.session.commit()


def create_trainer(values: dict, password: str) -> Trainer:
    if _email_in_use(values["email"]):
        raise ManagerServiceError("A trainer with this email already exists.")
    user = User(email=values["email"], role="trainer", is_active=values["is_active"])
    user.set_password(password)
    trainer = Trainer(user=user, **values)
    db.session.add(trainer)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ManagerServiceError("A trainer with this email already exists.") from exc
    return trainer


def update_trainer(trainer: Trainer, values: dict, password: str) -> None:
    if _email_in_use(values["email"], excluding_user_id=trainer.user_id or 0):
        raise ManagerServiceError("A trainer with this email already exists.")
    for field, value in values.items():
        setattr(trainer, field, value)
    if trainer.user is None:
        trainer.user = User(
            email=values["email"],
            role="trainer",
            is_active=values["is_active"],
        )
        trainer.user.set_password(password)
    else:
        trainer.user.email = values["email"]
        trainer.user.is_active = values["is_active"]
        if password:
            trainer.user.set_password(password)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ManagerServiceError("A trainer with this email already exists.") from exc


def set_trainer_active(trainer: Trainer, active: bool) -> None:
    trainer.is_active = active
    if trainer.user:
        trainer.user.is_active = active
    db.session.commit()


def get_active_trainers() -> list[Trainer]:
    return db.session.scalars(
        select(Trainer)
        .where(Trainer.is_active.is_(True))
        .order_by(Trainer.first_name, Trainer.last_name)
    ).all()


def get_sessions_context() -> dict:
    return {
        "sessions": db.session.scalars(
            select(WorkoutSession)
            .options(
                joinedload(WorkoutSession.trainer),
                selectinload(WorkoutSession.bookings),
            )
            .order_by(WorkoutSession.starts_at)
        ).all(),
        "trainers": get_active_trainers(),
    }


def get_subscription_members() -> list[Member]:
    return db.session.scalars(
        select(Member)
        .options(
            joinedload(Member.user),
            joinedload(Member.subscription).joinedload(
                MembershipSubscription.plan
            ),
        )
        .order_by(Member.first_name, Member.last_name)
    ).all()


def generate_ai_schedule(prompt: str, ai_service) -> tuple[str, str]:
    trainers = get_active_trainers()
    if not trainers:
        return "danger", "AI scheduling requires at least one active trainer."

    try:
        parsed = ai_service.parse_schedule_command(
            prompt, [trainer.full_name for trainer in trainers]
        )
        schedule = validate_schedule_payload(parsed, trainers)
        result = schedule_recurring_sessions_skill(
            trainer_name=str(schedule["trainer_name"]),
            title=str(schedule["title"]),
            weekday=str(schedule["weekday"]),
            start_time=str(schedule["start_time"]),
            max_capacity=int(schedule["max_capacity"]),
            occurrences=int(schedule["occurrences"]),
            duration_minutes=int(schedule["duration_minutes"]),
        )
    except Exception:
        db.session.rollback()
        try:
            session_ids = create_fallback_workout_sessions(trainers[0].id)
        except Exception as fallback_exc:
            db.session.rollback()
            raise ManagerServiceError(
                f"Could not generate workouts: {fallback_exc}"
            ) from fallback_exc
        return (
            "warning",
            "The AI service was unavailable, so "
            f"{len(session_ids)} realistic demo workouts were created instead.",
        )
    return (
        "success",
        f"AI scheduling created {result['created_count']} weekly sessions.",
    )


def generate_operational_report(generated_at: datetime | None = None) -> str:
    output = StringIO()
    writer = csv.writer(output)
    purchases = db.session.scalars(
        select(MembershipPurchase)
        .options(
            joinedload(MembershipPurchase.member),
            joinedload(MembershipPurchase.plan),
        )
        .order_by(MembershipPurchase.purchased_at)
    ).all()
    workout_sessions = db.session.scalars(
        select(WorkoutSession)
        .options(
            joinedload(WorkoutSession.trainer),
            selectinload(WorkoutSession.bookings),
        )
        .order_by(WorkoutSession.starts_at)
    ).all()

    writer.writerow(["Fitness Studio Operational Report"])
    writer.writerow(
        ["Generated", (generated_at or datetime.now()).isoformat(timespec="seconds")]
    )
    writer.writerow([])
    writer.writerow(["Revenue"])
    writer.writerow(["Purchase ID", "Member", "Plan", "Amount", "Purchased"])
    for purchase in purchases:
        writer.writerow(
            [
                purchase.id,
                purchase.member.full_name,
                purchase.plan.name,
                f"{purchase.amount_paid_cents / 100:.2f}",
                purchase.purchased_at.isoformat(),
            ]
        )
    writer.writerow([])
    writer.writerow(["Attendance and Capacity"])
    writer.writerow(
        ["Session ID", "Title", "Trainer", "Starts", "Status", "Booked", "Capacity"]
    )
    for workout_session in workout_sessions:
        writer.writerow(
            [
                workout_session.id,
                workout_session.title,
                workout_session.trainer.full_name,
                workout_session.starts_at.isoformat(),
                workout_session.status,
                workout_session.active_booking_count,
                workout_session.max_capacity,
            ]
        )
    return output.getvalue()


def _email_in_use(email: str, excluding_user_id: int | None = None) -> bool:
    query = select(User.id).where(func.lower(User.email) == email)
    if excluding_user_id is not None:
        query = query.where(User.id != excluding_user_id)
    return db.session.scalar(query) is not None
