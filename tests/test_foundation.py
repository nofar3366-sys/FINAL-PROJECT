from datetime import date
from pathlib import Path

import click
import pytest
from sqlalchemy import func, select

from models import Booking, Member, Trainer, User, WorkoutSession, db
from models.seed import seed_demo_data
from services.ai_service import GroqAIService, LightweightRetriever


def test_schema_and_health_endpoint(app):
    assert db.engine.dialect.name in {"sqlite", "postgresql"}
    inspector = db.inspect(db.engine)
    assert {
        "users",
        "members",
        "trainers",
        "workout_sessions",
        "bookings",
        "membership_renewals",
        "audit_logs",
    }.issubset(inspector.get_table_names())

    member_columns = {column["name"] for column in inspector.get_columns("members")}
    trainer_columns = {column["name"] for column in inspector.get_columns("trainers")}
    assert {"first_name", "last_name"}.issubset(member_columns)
    assert {"first_name", "last_name"}.issubset(trainer_columns)
    assert "full_name" not in member_columns
    assert "full_name" not in trainer_columns

    response = app.test_client().get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["database"] == "ok"
    assert "cloud_service" not in payload
    assert "cloudinary" not in str(payload).lower()


def test_all_page_templates_extend_base(app):
    template_directory = Path(app.root_path) / "templates"
    child_templates = [
        path for path in template_directory.rglob("*.html") if path.name != "base.html"
    ]
    assert child_templates
    assert {path.parent.name for path in child_templates} == {
        "auth",
        "manager",
        "member",
        "trainer",
    }
    for template in child_templates:
        source = template.read_text(encoding="utf-8")
        assert source.lstrip().startswith('{% extends "base.html" %}')
        assert "{% block content %}" in source


def test_demo_seed_covers_required_states(app):
    seed_demo_data()

    assert db.session.scalar(select(func.count(User.id))) == 8
    assert db.session.scalar(select(func.count(Trainer.id))) == 3
    assert all(trainer.user.role == "trainer" for trainer in db.session.scalars(select(Trainer)))
    assert db.session.scalar(select(func.count(Member.id))) == 4

    members = db.session.scalars(select(Member)).all()
    assert all(member.first_name and member.last_name for member in members)
    assert any(member.full_name == "Alice Active" for member in members)
    assert any(member.credit_balance == 0 for member in members)
    assert any(
        member.membership_expires_on < date.today() for member in members
    )
    assert any(member.status == "inactive" for member in members)

    trainers = db.session.scalars(select(Trainer)).all()
    assert any(
        trainer.first_name == "Maya" and trainer.last_name == "Cohen"
        for trainer in trainers
    )

    sessions = db.session.scalars(select(WorkoutSession)).all()
    assert any(session.status == "cancelled" for session in sessions)
    assert any(session.remaining_capacity == 0 for session in sessions)
    assert db.session.scalar(select(func.count(Booking.id))) > 0

    with pytest.raises(click.ClickException):
        seed_demo_data()


def test_optional_services_are_safe_by_default(app):
    matches = LightweightRetriever().retrieve("Can I book with no credits?")
    assert matches
    assert matches[0].key == "booking-policy"

    ai = GroqAIService(api_key="", model="test")
    assert ai.ask("Can I book without credits?").startswith("Demo assistant response")
    command = ai.parse_schedule_command(
        "Schedule Pilates with Maya Cohen every Tuesday at 18:00 with capacity 15",
        ["Maya Cohen"],
    )
    assert command["trainer_name"] == "Maya Cohen"
    assert command["title"] == "Pilates"
    assert command["max_capacity"] == 15
