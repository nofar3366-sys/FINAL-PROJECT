"""Presentation seed must fill plans/trainers/sessions even when users exist."""

from sqlalchemy import func, select

from models import MembershipPlan, Trainer, User, WorkoutSession, db
from models.seed import ensure_presentation_seed
from services.schema_service import ensure_demo_accounts


def test_presentation_seed_after_demo_accounts(app):
    ensure_demo_accounts()
    assert db.session.scalar(select(func.count(User.id))) >= 1

    report = ensure_presentation_seed()
    assert report["plans"] is True

    plans = db.session.scalars(select(MembershipPlan)).all()
    assert len(plans) >= 2
    assert {p.code for p in plans} >= {"punch_10", "monthly_30"}

    trainers = db.session.scalars(select(Trainer).where(Trainer.is_active.is_(True))).all()
    assert len(trainers) >= 1
    assert any((t.email or "").startswith("maya@") for t in trainers)

    sessions = db.session.scalars(select(WorkoutSession)).all()
    assert len(sessions) >= 3

    # Idempotent: second call does not duplicate sessions.
    before = db.session.scalar(select(func.count(WorkoutSession.id)))
    ensure_presentation_seed()
    after = db.session.scalar(select(func.count(WorkoutSession.id)))
    assert before == after


def test_renewal_page_shows_plans_after_seed(app):
    ensure_presentation_seed()
    client = app.test_client()
    client.post(
        "/auth/login",
        data={"email": "alice@fitness.local", "password": "Demo123!"},
        follow_redirects=True,
    )
    response = client.get("/member/renewal")
    assert response.status_code == 200
    assert b"10-Class Punch Card" in response.data
    assert b"Monthly Pass" in response.data
    assert b"Purchase plan" in response.data
