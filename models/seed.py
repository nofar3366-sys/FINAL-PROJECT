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
