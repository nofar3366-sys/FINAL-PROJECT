from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from models import (
    Booking,
    Member,
    MembershipPurchase,
    Trainer,
    User,
    WorkoutSession,
    db,
)
from models.seed import seed_demo_data
from services.booking_service import BookingError, book_session, cancel_booking
from skills.availability import get_class_availability_skill
from skills.scheduling import schedule_class_skill, schedule_recurring_sessions_skill


def _login(client, email, password="Demo123!"):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def test_booking_capacity_and_credit_refund(app):
    seed_demo_data()
    trainer = db.session.scalar(select(Trainer).where(Trainer.is_active.is_(True)))
    workout_session = WorkoutSession(
        trainer=trainer,
        title="Capacity Test",
        starts_at=datetime.now() + timedelta(days=10),
        duration_minutes=45,
        max_capacity=1,
        status="scheduled",
    )
    db.session.add(workout_session)
    db.session.commit()

    alice = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "alice@fitness.local")
    )
    cara = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "cara@fitness.local")
    )
    ben = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "ben@fitness.local")
    )
    with pytest.raises(BookingError, match="inactive or expired"):
        book_session(cara.id, workout_session.id)

    cara.membership_expires_on = date.today() + timedelta(days=30)
    starting_credits = alice.credit_balance
    db.session.commit()

    with pytest.raises(BookingError, match="credits"):
        book_session(ben.id, workout_session.id)
    book_session(alice.id, workout_session.id)
    assert alice.credit_balance == starting_credits - 1
    with pytest.raises(BookingError, match="full"):
        book_session(cara.id, workout_session.id)

    booking = db.session.scalar(
        select(Booking).where(
            Booking.member_id == alice.id,
            Booking.workout_session_id == workout_session.id,
        )
    )
    cancel_booking(alice.id, booking.id)
    assert alice.credit_balance == starting_credits
    with pytest.raises(BookingError, match="already cancelled"):
        cancel_booking(alice.id, booking.id)


def test_demo_purchase_renews_membership_and_logs_receipt(app):
    seed_demo_data()
    client = app.test_client()
    _login(client, "alice@fitness.local")

    alice = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "alice@fitness.local")
    )
    old_expiry = alice.membership_expires_on
    old_credits = alice.credit_balance
    response = client.post(
        "/member/membership/purchase",
        data={"plan_code": "punch_10"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Demo purchase completed" in response.data
    db.session.refresh(alice)
    assert alice.credit_balance == old_credits + 10
    assert alice.membership_expires_on > old_expiry
    purchase = db.session.scalar(select(MembershipPurchase))
    assert purchase.receipt_status == "mocked"


def test_manager_schedule_report_subscription_and_ai_skill(app):
    seed_demo_data()
    client = app.test_client()
    _login(client, "manager@fitness.local")

    trainer = db.session.scalar(select(Trainer).where(Trainer.is_active.is_(True)))
    response = client.post(
        "/manager/sessions/new",
        data={
            "title": "Manual Pilates",
            "trainer_id": str(trainer.id),
            "starts_at": (datetime.now() + timedelta(days=20)).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "duration_minutes": "50",
            "max_capacity": "12",
        },
        follow_redirects=True,
    )
    assert b"Workout session created" in response.data

    weekday = (date.today() + timedelta(days=1)).strftime("%A")
    result = schedule_recurring_sessions_skill(
        trainer_name=trainer.full_name,
        title="AI Mobility",
        weekday=weekday,
        start_time="23:30",
        max_capacity=10,
        occurrences=4,
    )
    assert result["created_count"] == 4

    alice = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "alice@fitness.local")
    )
    response = client.post(
        f"/manager/subscriptions/{alice.id}/suspended",
        follow_redirects=True,
    )
    assert b"Subscription marked suspended" in response.data
    assert alice.subscription.status == "suspended"

    report = client.get("/manager/reports.csv")
    assert report.status_code == 200
    assert report.mimetype == "text/csv"
    assert b"Attendance and Capacity" in report.data


def test_explicit_ai_skills_query_and_create_sessions(app):
    seed_demo_data()
    yoga_session = db.session.scalar(
        select(WorkoutSession)
        .join(WorkoutSession.trainer)
        .where(Trainer.specialty.ilike("%Yoga%"))
    )
    availability = get_class_availability_skill(
        yoga_session.starts_at.date().isoformat(), "Yoga"
    )
    assert availability["classes"]
    assert "remaining_capacity" in availability["classes"][0]

    trainer = db.session.scalar(select(Trainer).where(Trainer.is_active.is_(True)))
    result = schedule_class_skill(
        trainer.id,
        (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%dT21:15"),
        11,
    )
    assert result["status"] == "created"
    assert result["capacity"] == 11
