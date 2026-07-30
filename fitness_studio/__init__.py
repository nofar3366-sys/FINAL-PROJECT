from pathlib import Path

import click
from flask import Flask
from sqlalchemy import text

from controllers.auth import auth_bp
from controllers.core import core_bp
from controllers.manager import manager_bp
from controllers.member import member_bp
from controllers.trainer import trainer_bp
from models import db
from models.seed import seed_demo_command
from services.ai_service import GroqAIService
from services.cloud_service import CloudService
from services.email_service import ReceiptEmailService
from services.membership_service import ensure_default_plans
from services.schema_service import upgrade_trainer_accounts

from .config import Config


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

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

    return app


@click.command("init-db")
@click.option("--drop", is_flag=True, help="Drop existing tables before creation.")
def init_db_command(drop: bool) -> None:
    """Create the normalized schema in instance/fitness_studio.db."""

    if drop and click.confirm("Drop all existing local tables?"):
        db.drop_all()
    elif drop:
        raise click.Abort()
    db.create_all()
    ensure_default_plans()
    db.session.execute(text("PRAGMA journal_mode=WAL"))
    db.session.commit()
    click.echo("Initialized local database: instance/fitness_studio.db")


@click.command("upgrade-db")
def upgrade_db_command() -> None:
    """Add trainer user accounts to an existing SQLite database."""

    created = upgrade_trainer_accounts()
    click.echo(f"Database upgraded. Trainer logins created: {created}.")
