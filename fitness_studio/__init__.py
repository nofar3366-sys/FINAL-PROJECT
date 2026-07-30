import tempfile
from pathlib import Path

import click
from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix

# Register every model on db.Model.metadata before create_all().
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

from .config import Config, is_vercel_runtime, sqlalchemy_engine_options


def _writable_instance_path(project_root: Path) -> Path:
    """Return a writable absolute instance directory.

    Vercel's deployment filesystem is read-only except the OS temp dir, so
    creating project_root/instance there raises PermissionError and prevents
    `app.py` from importing.
    """

    candidates = []
    if is_vercel_runtime():
        candidates.append(Path(tempfile.gettempdir()).resolve() / "fitness_studio_instance")
    candidates.append((project_root / "instance").resolve())
    candidates.append(Path(tempfile.gettempdir()).resolve() / "fitness_studio_instance")

    last_error: OSError | None = None
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return path
        except OSError as exc:
            last_error = exc
            continue
    raise RuntimeError(
        f"Could not create a writable Flask instance path. Last error: {last_error}"
    )


def create_app(test_config: dict | None = None) -> Flask:
    package_dir = Path(__file__).resolve().parent
    project_root = package_dir.parent
    instance_path = _writable_instance_path(project_root)

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

    # Vercel terminates TLS at the edge; trust X-Forwarded-* for cookies/URLs.
    if is_vercel_runtime():
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

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
        try:
            db.session.rollback()
        except Exception:
            pass
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
