from pathlib import Path

import click
from flask import Flask
from sqlalchemy import func, select, text

from controllers.auth import auth_bp
from controllers.core import core_bp
from controllers.manager import manager_bp
from controllers.member import member_bp
from controllers.trainer import trainer_bp
from models import User, db
from models.seed import seed_demo_command, seed_demo_data
from services.ai_service import GroqAIService
from services.cloud_service import CloudService
from services.email_service import ReceiptEmailService
from services.membership_service import ensure_default_plans
from services.schema_service import upgrade_trainer_accounts

from .config import Config, is_vercel_runtime, sqlalchemy_engine_options


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

    # On Vercel (or any empty cloud DB), create schema and demo rows once.
    if is_vercel_runtime() and test_config is None:
        with app.app_context():
            _bootstrap_database()

    return app


def _bootstrap_database() -> None:
    """Ensure schema exists and seed demo data when the database is empty."""

    db.create_all()
    ensure_default_plans()
    if db.engine.dialect.name == "sqlite":
        try:
            db.session.execute(text("PRAGMA journal_mode=DELETE"))
            db.session.commit()
        except Exception:
            db.session.rollback()

    user_count = db.session.scalar(select(func.count(User.id))) or 0
    if user_count == 0:
        try:
            seed_demo_data()
        except click.ClickException:
            db.session.rollback()


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
