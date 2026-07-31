from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from fitness_studio import create_app
from fitness_studio.config import resolve_runtime_database_uri
from models import Member, Trainer, User, WorkoutSession, db
from models.seed import seed_demo_data
from services.booking_service import book_session


def _login(client, email: str):
    return client.post(
        "/auth/login",
        data={"email": email, "password": "Demo123!"},
        follow_redirects=True,
    )


def test_vercel_requires_postgres_and_never_falls_back(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PROJECT_REF", raising=False)
    monkeypatch.delenv("SUPABASE_DB_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        resolve_runtime_database_uri()

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://postgres.example:secret@pooler.example.com:6543/postgres",
    )
    uri, source = resolve_runtime_database_uri()
    assert source == "postgres"
    assert uri.startswith("postgresql+psycopg://")
    assert not uri.startswith("sqlite")


def test_registration_survives_a_new_app_instance(tmp_path):
    database_path = tmp_path / "persistent.db"
    config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        "SECRET_KEY": "test-only",
        "CSRF_ENABLED": False,
        "GROQ_API_KEY": "",
    }

    first_app = create_app(config)
    with first_app.app_context():
        db.create_all()
        response = first_app.test_client().post(
            "/auth/register",
            data={
                "first_name": "Persistent",
                "last_name": "Member",
                "email": "persistent@example.com",
                "phone": "050-123-4567",
                "password": "secret7",
                "confirm_password": "secret7",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Registration complete" in response.data
        db.session.remove()

    second_app = create_app(config)
    with second_app.app_context():
        user = db.session.scalar(
            select(User).where(User.email == "persistent@example.com")
        )
        assert user is not None
        assert user.member is not None
        assert user.member.first_name == "Persistent"
        assert user.member.last_name == "Member"
        assert user.member.membership_expires_on == date.today()


def test_manager_ai_failure_creates_fallback_without_logout(app, monkeypatch):
    seed_demo_data()
    client = app.test_client()
    _login(client, "manager@fitness.local")
    before = db.session.scalar(select(func.count(WorkoutSession.id))) or 0

    def fail_ai(*_args, **_kwargs):
        raise TimeoutError("LLM timed out")

    monkeypatch.setattr(
        app.extensions["ai_service"], "parse_schedule_command", fail_ai
    )
    response = client.post(
        "/manager/sessions/ai-schedule",
        data={"prompt": "Create a realistic weekly plan"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"realistic demo workouts were created instead" in response.data
    after = db.session.scalar(select(func.count(WorkoutSession.id))) or 0
    assert after == before + 4

    dashboard = client.get("/manager/dashboard")
    assert dashboard.status_code == 200
    assert b"Manager dashboard" in dashboard.data


def test_role_routes_and_schedule_alias_do_not_500(app):
    seed_demo_data()
    client = app.test_client()

    cases = (
        ("manager@fitness.local", "/manager/dashboard"),
        ("alice@fitness.local", "/member/dashboard"),
        ("maya@fitness.local", "/trainer/dashboard"),
    )
    for email, route in cases:
        _login(client, email)
        response = client.get(route)
        assert response.status_code == 200
        assert b"Internal Server Error" not in response.data
        alias = client.get("/schedule", follow_redirects=True)
        assert alias.status_code == 200
        assert b"Internal Server Error" not in alias.data
        client.post("/auth/logout", follow_redirects=True)


def test_booking_create_alias_persists_booking(app):
    seed_demo_data()
    client = app.test_client()
    _login(client, "alice@fitness.local")
    alice = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "alice@fitness.local")
    )
    trainer = db.session.scalar(select(Trainer).where(Trainer.is_active.is_(True)))
    session = WorkoutSession(
        trainer=trainer,
        title="Booking Alias Test",
        starts_at=datetime.now() + timedelta(days=60),
        duration_minutes=45,
        max_capacity=10,
        status="scheduled",
    )
    db.session.add(session)
    db.session.commit()
    starting_credits = alice.credit_balance
    response = client.post(
        "/booking/create",
        data={"session_id": str(session.id)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    db.session.refresh(alice)
    assert alice.credit_balance == starting_credits - 1


def test_receipt_failure_keeps_purchase_and_member_session(app, monkeypatch):
    seed_demo_data()
    client = app.test_client()
    _login(client, "alice@fitness.local")
    alice = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "alice@fitness.local")
    )
    starting_credits = alice.credit_balance

    def fail_receipt(**_kwargs):
        raise TimeoutError("receipt provider unavailable")

    monkeypatch.setattr(
        app.extensions["receipt_email"], "send_receipt", fail_receipt
    )
    response = client.post(
        "/member/membership/purchase",
        data={"plan_code": "punch_10"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"receipt will need to be retried" in response.data
    db.session.refresh(alice)
    assert alice.credit_balance == starting_credits + 10
    assert client.get("/member/dashboard").status_code == 200


def test_manager_cancel_refunds_bookings_once(app):
    seed_demo_data()
    alice = db.session.scalar(
        select(Member).join(Member.user).where(User.email == "alice@fitness.local")
    )
    trainer = db.session.scalar(select(Trainer).where(Trainer.is_active.is_(True)))
    workout = WorkoutSession(
        trainer=trainer,
        title="Cancellation Lock Test",
        starts_at=datetime.now() + timedelta(days=80),
        duration_minutes=45,
        max_capacity=10,
        status="scheduled",
    )
    db.session.add(workout)
    db.session.commit()
    starting_credits = alice.credit_balance
    book_session(alice.id, workout.id)
    assert alice.credit_balance == starting_credits - 1

    client = app.test_client()
    _login(client, "manager@fitness.local")
    response = client.post(
        f"/manager/sessions/{workout.id}/cancel",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"credits refunded" in response.data
    db.session.refresh(alice)
    assert alice.credit_balance == starting_credits

    second = client.post(
        f"/manager/sessions/{workout.id}/cancel",
        follow_redirects=True,
    )
    assert b"Only scheduled sessions can be cancelled" in second.data
    db.session.refresh(alice)
    assert alice.credit_balance == starting_credits


def test_manager_duplicate_email_check_is_case_insensitive(app):
    seed_demo_data()
    mixed = User(email="Mixed.Case@Example.com", role="member", is_active=True)
    mixed.set_password("secret7")
    db.session.add(mixed)
    db.session.commit()

    client = app.test_client()
    _login(client, "manager@fitness.local")
    response = client.post(
        "/manager/members/new",
        data={
            "first_name": "Duplicate",
            "last_name": "Person",
            "email": "mixed.case@example.com",
            "password": "secret7",
            "membership_expires_on": (date.today() + timedelta(days=30)).isoformat(),
            "credit_balance": "2",
            "status": "active",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"already exists" in response.data
    assert (
        db.session.scalar(
            select(func.count(User.id)).where(
                func.lower(User.email) == "mixed.case@example.com"
            )
        )
        == 1
    )
