from pathlib import Path

import click
from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

# Import the models package so every table is registered on db.Model.metadata
# before db.create_all() runs.
import models  # noqa: F401
from controllers.auth import auth_bp
from controllers.core import core_bp
from controllers.manager import manager_bp
from controllers.member import member_bp
from controllers.trainer import trainer_bp
from models import db
from models.seed import ensure_demo_data, seed_demo_command
from services.ai_service import GroqAIService
from services.cloud_service import CloudService
from services.email_service import ReceiptEmailService
from services.membership_service import ensure_default_plans
from services.schema_service import upgrade_trainer_accounts

from .config import Config, sqlalchemy_engine_options


def create_app(test_config: dict | None = None) -> Flask:
    package_dir = Path(__file__).resolve().parent
    project_root = package_dir.parent
    instance_path = (project_root / "instance").resolve()
    instance_path.mkdir(parents=True, exist_ok=True)

    app = Flask(
        __name__,
        instance_path=str(instance_path),
        instance_relative_config=True,
        template_folder=str(package_dir / "templates"),
        static_folder=str(package_dir / "static"),
        static_url_path="/static",
    )
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = sqlalchemy_engine_options(str(uri))

    db.init_app(app)
    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(member_bp)
    app.register_blueprint(trainer_bp)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(upgrade_db_command)

    app.extensions["ai_service"] = GroqAIService.from_config(app.config)
    app.extensions["cloud_service"] = CloudService.from_config(
        app.config, Path(app.instance_path) / "cloud_backups"
    )
    app.extensions["receipt_email"] = ReceiptEmailService(
        app.config["RESEND_API_KEY"], app.config["RECEIPT_FROM_EMAIL"]
    )

    # Local + Vercel: create missing tables and seed empty databases.
    # Skipped only for the pytest fixture (test_config is provided).
    if test_config is None:
        with app.app_context():
            _bootstrap_database(app)

    return app


def _bootstrap_database(app: Flask) -> None:
    """Create schema and seed demo data when the connected database is empty."""

    try:
        db.create_all()
        ensure_default_plans()
        if db.engine.dialect.name == "sqlite":
            try:
                db.session.execute(text("PRAGMA journal_mode=DELETE"))
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()

        seeded = ensure_demo_data()
        app.logger.info(
            "Database bootstrap complete (%s). Demo seed %s.",
            db.engine.dialect.name,
            "applied" if seeded else "skipped (already populated)",
        )
    except Exception:
        db.session.rollback()
        app.logger.exception(
            "Database bootstrap failed. Check DATABASE_URL / Supabase connectivity."
        )


@click.command("init-db")
@click.option("--drop", is_flag=True, help="Drop existing tables before creation.")
def init_db_command(drop: bool) -> None:
    """Create the application schema in SQLite or PostgreSQL."""

    if drop and click.confirm("Drop all existing tables?"):
        db.drop_all()
    elif drop:
        raise click.Abort()
    db.create_all()
    ensure_default_plans()
    if db.engine.dialect.name == "sqlite":
        db.session.execute(text("PRAGMA journal_mode=WAL"))
        db.session.commit()
    click.echo(f"Initialized database ({db.engine.dialect.name}).")


@click.command("upgrade-db")
def upgrade_db_command() -> None:
    """Ensure trainer user accounts exist for trainer profiles."""

    created = upgrade_trainer_accounts()
    click.echo(f"Database upgraded. Trainer logins created: {created}.")
