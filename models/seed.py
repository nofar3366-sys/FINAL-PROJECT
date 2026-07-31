from datetime import date, datetime, time, timedelta, timezone

import click
from flask.cli import with_appcontext
from sqlalchemy import func, select

from . import (
    AuditLog,
    Booking,
    Member,
    MembershipRenewal,
    Trainer,
    User,
    WorkoutSession,
    db,
)


DEMO_PASSWORD = "Demo123!"


def _future_at(days: int, hour: int) -> datetime:
    target_date = date.today() + timedelta(days=days)
    return datetime.combine(target_date, time(hour=hour), tzinfo=timezone.utc)


def _new_user(email: str, role: str = "member") -> User:
    user = User(email=User.normalize_email(email), role=role, is_active=True)
    user.set_password(DEMO_PASSWORD)
    return user


def database_has_demo_data() -> bool:
    """True when core demo tables already contain at least one row."""

    populated_models = (User, Trainer, WorkoutSession, Booking)
    return any(
        (db.session.scalar(select(func.count(model.id))) or 0) > 0
        for model in populated_models
    )


def ensure_demo_data() -> bool:
    """Seed demo rows only when the database is empty. Safe for app startup."""

    if database_has_demo_data():
        return False
    try:
        seed_demo_data()
    except click.ClickException:
        db.session.rollback()
        return False
    except Exception:
        db.session.rollback()
        # Concurrent startup on Vercel may race; treat existing rows as success.
        if database_has_demo_data():
            return False
        raise
    return True


def ensure_presentation_seed() -> dict[str, object]:
    """Idempotent demo catalog: plans, trainers, and upcoming classes.

    Safe to run on every cold start (including Vercel SQLite). Unlike
    ``seed_demo_data``, this does not require an empty database — demo
    accounts may already exist from ``ensure_demo_accounts``.
    """

    from services.membership_service import ensure_default_plans
    from services.schema_service import ensure_demo_accounts

    report: dict[str, object] = {
        "plans": False,
        "accounts": {},
        "trainers_added": 0,
        "sessions_added": 0,
    }

    ensure_default_plans()
    report["plans"] = True

    report["accounts"] = ensure_demo_accounts()

    # Extra trainers beyond Maya so managers can schedule varied classes.
    extra_trainers = (
        ("noam@fitness.local", "Noam", "Levi", "Strength Training"),
        ("rina@fitness.local", "Rina", "Azulay", "Cardio and HIIT"),
    )
    for email, first_name, last_name, specialty in extra_trainers:
        created = _ensure_trainer_login(
            email, first_name=first_name, last_name=last_name, specialty=specialty
        )
        if created:
            report["trainers_added"] = int(report["trainers_added"]) + 1

    # Ben: active member with 0 credits (shows renewal UX).
    ben_user = db.session.scalar(
        select(User).where(User.email == "ben@fitness.local")
    )
    if ben_user is None:
        ben_user = _new_user("ben@fitness.local")
        db.session.add(ben_user)
        db.session.flush()
    if ben_user.member is None:
        db.session.add(
            Member(
                user=ben_user,
                first_name="Ben",
                last_name="Zero Credit",
                phone="050-555-0102",
                membership_expires_on=date.today() + timedelta(days=60),
                credit_balance=0,
                status="active",
            )
        )

    session_count = db.session.scalar(select(func.count(WorkoutSession.id))) or 0
    if session_count == 0:
        report["sessions_added"] = _seed_upcoming_sessions()

    db.session.commit()
    return report


def _ensure_trainer_login(
    email: str,
    *,
    first_name: str,
    last_name: str,
    specialty: str,
) -> bool:
    """Create trainer user+profile if missing. Returns True when newly created."""

    normalized = User.normalize_email(email)
    user = db.session.scalar(select(User).where(User.email == normalized))
    created = False
    if user is None:
        user = _new_user(normalized, role="trainer")
        db.session.add(user)
        db.session.flush()
        created = True
    else:
        user.role = "trainer"
        user.is_active = True

    if user.trainer is None:
        db.session.add(
            Trainer(
                user=user,
                first_name=first_name,
                last_name=last_name,
                specialty=specialty,
                email=normalized,
                phone="",
                is_active=True,
            )
        )
        db.session.flush()
        created = True
    else:
        trainer = user.trainer
        trainer.is_active = True
        if not (trainer.first_name or "").strip():
            trainer.first_name = first_name
        if not (trainer.last_name or "").strip():
            trainer.last_name = last_name
        trainer.specialty = specialty or trainer.specialty
    return created


def _seed_upcoming_sessions() -> int:
    """Insert a small set of bookable demo classes. Returns rows added."""

    trainers = {
        t.email: t
        for t in db.session.scalars(select(Trainer).where(Trainer.is_active.is_(True)))
        if t.email
    }
    yoga = trainers.get("maya@fitness.local")
    strength = trainers.get("noam@fitness.local")
    cardio = trainers.get("rina@fitness.local")
    if yoga is None and trainers:
        yoga = next(iter(trainers.values()))
    if strength is None:
        strength = yoga
    if cardio is None:
        cardio = yoga
    if yoga is None:
        return 0

    sessions = [
        WorkoutSession(
            trainer=yoga,
            title="Morning Yoga",
            starts_at=_future_at(2, 8),
            duration_minutes=60,
            max_capacity=12,
            status="scheduled",
        ),
        WorkoutSession(
            trainer=strength,
            title="Functional Strength",
            starts_at=_future_at(3, 18),
            duration_minutes=50,
            max_capacity=10,
            status="scheduled",
        ),
        WorkoutSession(
            trainer=cardio,
            title="HIIT Express",
            starts_at=_future_at(4, 17),
            duration_minutes=40,
            max_capacity=14,
            status="scheduled",
        ),
        WorkoutSession(
            trainer=yoga,
            title="Evening Mobility",
            starts_at=_future_at(5, 19),
            duration_minutes=45,
            max_capacity=15,
            status="scheduled",
        ),
    ]
    db.session.add_all(sessions)
    db.session.flush()
    return len(sessions)


def seed_demo_data() -> None:
    """Insert deterministic demo states into an otherwise empty database."""

    from services.membership_service import ensure_default_plans

    if database_has_demo_data():
        raise click.ClickException(
            "Demo seed aborted: the database already contains application data."
        )

    ensure_default_plans()
    today = date.today()
    manager = _new_user("manager@fitness.local", role="manager")

    alice_user = _new_user("alice@fitness.local")
    ben_user = _new_user("ben@fitness.local")
    cara_user = _new_user("cara@fitness.local")
    dan_user = _new_user("dan@fitness.local")
    dan_user.is_active = False

    alice = Member(
        user=alice_user,
        first_name="Alice",
        last_name="Active",
        phone="050-555-0101",
        membership_expires_on=today + timedelta(days=120),
        credit_balance=7,
        status="active",
    )
    ben = Member(
        user=ben_user,
        first_name="Ben",
        last_name="Zero Credit",
        phone="050-555-0102",
        membership_expires_on=today + timedelta(days=60),
        credit_balance=0,
        status="active",
    )
    cara = Member(
        user=cara_user,
        first_name="Cara",
        last_name="Expired",
        phone="050-555-0103",
        membership_expires_on=today - timedelta(days=10),
        credit_balance=4,
        status="active",
    )
    dan = Member(
        user=dan_user,
        first_name="Dan",
        last_name="Inactive",
        phone="050-555-0104",
        membership_expires_on=today + timedelta(days=90),
        credit_balance=5,
        status="inactive",
    )

    yoga = Trainer(
        user=_new_user("maya@fitness.local", role="trainer"),
        first_name="Maya",
        last_name="Cohen",
        specialty="Yoga and Mobility",
        email="maya@fitness.local",
        phone="050-555-0201",
    )
    strength = Trainer(
        user=_new_user("noam@fitness.local", role="trainer"),
        first_name="Noam",
        last_name="Levi",
        specialty="Strength Training",
        email="noam@fitness.local",
        phone="050-555-0202",
    )
    cardio = Trainer(
        user=_new_user("rina@fitness.local", role="trainer"),
        first_name="Rina",
        last_name="Azulay",
        specialty="Cardio and HIIT",
        email="rina@fitness.local",
        phone="050-555-0203",
    )

    open_session = WorkoutSession(
        trainer=yoga,
        title="Morning Yoga",
        starts_at=_future_at(2, 8),
        duration_minutes=60,
        max_capacity=5,
        status="scheduled",
    )
    nearly_full_session = WorkoutSession(
        trainer=strength,
        title="Functional Strength",
        starts_at=_future_at(3, 18),
        duration_minutes=50,
        max_capacity=3,
        status="scheduled",
    )
    full_session = WorkoutSession(
        trainer=cardio,
        title="HIIT Express",
        starts_at=_future_at(4, 17),
        duration_minutes=40,
        max_capacity=2,
        status="scheduled",
    )
    cancelled_session = WorkoutSession(
        trainer=yoga,
        title="Cancelled Mobility Lab",
        starts_at=_future_at(5, 10),
        duration_minutes=45,
        max_capacity=8,
        status="cancelled",
    )

    db.session.add_all(
        [
            manager,
            alice,
            ben,
            cara,
            dan,
            yoga,
            strength,
            cardio,
            open_session,
            nearly_full_session,
            full_session,
            cancelled_session,
        ]
    )
    db.session.flush()

    db.session.add_all(
        [
            Booking(member=alice, workout_session=open_session),
            Booking(member=alice, workout_session=nearly_full_session),
            Booking(member=ben, workout_session=nearly_full_session),
            Booking(member=alice, workout_session=full_session),
            Booking(member=ben, workout_session=full_session),
            Booking(
                member=alice,
                workout_session=cancelled_session,
                status="cancelled",
                credit_consumed=True,
                credit_refunded=True,
                cancelled_at=datetime.now(timezone.utc),
            ),
            MembershipRenewal(
                member=alice,
                processed_by=manager,
                previous_expiry=today + timedelta(days=30),
                new_expiry=today + timedelta(days=120),
                credits_added=10,
                notes="Demonstration renewal",
            ),
            AuditLog(
                actor=manager,
                action="seed_demo",
                entity_type="database",
                entity_id=0,
                details_json='{"source":"flask seed-demo"}',
            ),
        ]
    )
    db.session.commit()


@click.command("seed-demo")
@with_appcontext
def seed_demo_command() -> None:
    """Populate a fresh database with presentation-ready demonstration data."""

    try:
        from services.schema_service import repair_database

        repair_database()
        seed_demo_data()
        repair_database()
    except Exception:
        db.session.rollback()
        raise

    click.echo("Demo data created.")
    click.echo("Manager: manager@fitness.local / Demo123!")
    click.echo("Members: alice@fitness.local, ben@fitness.local / Demo123!")
    click.echo("Trainer: maya@fitness.local / Demo123!")
    click.echo("These credentials are development-only.")
