from datetime import date
from pathlib import Path

import click
import pytest
from sqlalchemy import func, select

from models import Booking, Member, Trainer, User, WorkoutSession, db
from models.seed import seed_demo_data
from services.ai_service import GroqAIService, LightweightRetriever
from services.cloud_service import CloudService

def test_schema_and_health_endpoint(app):
    assert db.engine.dialect.name == "sqlite"
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

    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json()["database"] == "ok"


def test_all_page_templates_extend_base(app):
    template_directory = Path(app.root_path) / "templates"
    child_templates = [
        path for path in template_directory.glob("*.html") if path.name != "base.html"
    ]
    assert child_templates
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
    assert any(member.credit_balance == 0 for member in members)
    assert any(
        member.membership_expires_on < date.today() for member in members
    )
    assert any(member.status == "inactive" for member in members)

    sessions = db.session.scalars(select(WorkoutSession)).all()
    assert any(session.status == "cancelled" for session in sessions)
    assert any(session.remaining_capacity == 0 for session in sessions)
    assert db.session.scalar(select(func.count(Booking.id))) > 0

    with pytest.raises(click.ClickException):
        seed_demo_data()


def test_optional_services_are_safe_by_default(app, tmp_path):
    cloud = CloudService(simulation_directory=tmp_path / "cloud")
    result = cloud.health_check()
    assert result.status == "simulated"
    backup = cloud.backup_database(db.engine.url.database)
    assert backup.status == "simulated"
    assert backup.reference.startswith("cloud-sim-")
    assert Path(backup.readable_artifact_path).is_file()
    assert (tmp_path / "cloud").exists()

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


def test_cloudinary_backup_uploads_raw_asset(app, tmp_path, monkeypatch):
    seed_demo_data()
    captured = []

    def fake_upload(self, snapshot, public_id):
        captured.append((snapshot, public_id))
        return {
            "secure_url": f"https://res.cloudinary.com/demo/raw/upload/{public_id}",
            "public_id": f"fitness_studio_backups/{public_id}",
        }

    monkeypatch.setattr(CloudService, "_cloudinary_upload", fake_upload)
    cloud = CloudService(
        cloudinary_url="cloudinary://key:secret@demo",
        simulation_directory=tmp_path / "cloudinary",
    )
    result = cloud.backup_database(db.engine.url.database)

    assert result.status == "uploaded"
    assert result.secure_url.startswith("https://res.cloudinary.com/")
    assert result.readable_url.endswith(".html")
    assert [snapshot.suffix for snapshot, _ in captured] == [".db", ".html"]
    assert captured[0][1].endswith(".db")
    assert captured[1][1].endswith(".html")
    html_report = Path(result.readable_artifact_path).read_text(encoding="utf-8")
    assert "Alice Active" in html_report
    assert "[REDACTED]" in html_report
