import tempfile
from pathlib import Path

import click
from flask import Flask, flash, redirect, url_for
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix

# Register every model on db.Model.metadata before create_all().
import models  # noqa: F401
from controllers.auth import auth_bp
from controllers.core import core_bp
from controllers.manager import manager_bp
from controllers.member import member_bp
from controllers.trainer import trainer_bp
from models import db
from models.seed import (
    ensure_demo_data,
    ensure_presentation_seed,
    seed_demo_command,
)
from services.ai_service import GroqAIService
from services.email_service import ReceiptEmailService
from services.membership_service import ensure_default_plans
from services.schema_service import (
    ensure_demo_accounts,
    ensure_name_columns,
    repair_database,
    upgrade_trainer_accounts,
)

from .config import (
    Config,
    is_vercel_runtime,
    resolve_runtime_database_uri,
    sqlalchemy_engine_options,
)


def _writable_instance_path(project_root: Path) -> Path:
    """Return a writable absolute instance directory for Flask + SQLite."""

    candidates = []
    if is_vercel_runtime():
        candidates.append(
            Path(tempfile.gettempdir()).resolve() / "fitness_studio_instance"
        )
    candidates.append((project_root / "instance").resolve())
    candidates.append(
        Path(tempfile.gettempdir()).resolve() / "fitness_studio_instance"
    )

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
    try:
        instance_path = _writable_instance_path(project_root)
    except Exception:
        # Never fail app construction over instance-path issues (esp. Vercel).
        instance_path = Path(tempfile.gettempdir()).resolve() / "fitness_studio_instance"
        try:
            instance_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            instance_path = Path(tempfile.gettempdir()).resolve()

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
        uri = str(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = sqlalchemy_engine_options(uri)
        app.config["DATABASE_SOURCE"] = (
            "sqlite" if uri.startswith("sqlite") else "postgres"
        )
    else:
        # Production is strict: a missing/bad DATABASE_URL must never redirect
        # writes into Vercel's ephemeral filesystem.
        uri, source = resolve_runtime_database_uri(instance_path)
        app.config["SQLALCHEMY_DATABASE_URI"] = uri
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = sqlalchemy_engine_options(uri)
        app.config["DATABASE_SOURCE"] = source

    if is_vercel_runtime():
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)

    # Validate the production connection on the first request, not at import.
    # Schema provisioning is an explicit deployment operation, so every cold
    # start does not run DDL or demo writes against Supabase.
    if test_config is None and is_vercel_runtime():

        @app.before_request
        def _vercel_bootstrap_once():
            if app.config.get("_db_bootstrapped"):
                return None
            try:
                _bootstrap_database(app)
            except Exception:
                app.logger.exception("Vercel lazy bootstrap failed")
            app.config["_db_bootstrapped"] = True
            return None

    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(manager_bp)
    app.register_blueprint(member_bp)
    app.register_blueprint(trainer_bp)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
    app.cli.add_command(upgrade_db_command)
    _register_error_handlers(app)

    try:
        app.extensions["ai_service"] = GroqAIService.from_config(app.config)
    except Exception:
        app.logger.exception("AI service init failed")
        app.extensions["ai_service"] = GroqAIService.from_config(
            {"GROQ_API_KEY": "", "GROQ_MODEL": "", "GROQ_TIMEOUT_SECONDS": 1}
        )
    try:
        app.extensions["receipt_email"] = ReceiptEmailService(
            app.config.get("RESEND_API_KEY", ""),
            app.config.get("RECEIPT_FROM_EMAIL", "Fitness Studio <onboarding@resend.dev>"),
        )
    except Exception:
        app.logger.exception("Email service init failed")
        app.extensions["receipt_email"] = ReceiptEmailService("", "noreply@localhost")

    if test_config is None and not is_vercel_runtime():
        with app.app_context():
            try:
                _bootstrap_database(app)
            except Exception:
                app.logger.exception("Bootstrap escaped create_app")

    return app


def _register_error_handlers(app: Flask) -> None:
    """Convert unexpected DB failures into a recoverable login redirect."""

    @app.errorhandler(SQLAlchemyError)
    def handle_sqlalchemy_error(exc: SQLAlchemyError):
        app.logger.exception("Unhandled SQLAlchemyError: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass
        # Only attempt repair when we already have a working engine (not a
        # dead remote). Repair itself is best-effort and never re-raises.
        if not isinstance(exc, OperationalError):
            try:
                repair_database()
            except Exception:
                app.logger.exception("Error-handler repair_database failed")
        flash(
            "A database operation failed and was rolled back. Please try again.",
            "warning",
        )
        return redirect(url_for("core.index"))

    @app.errorhandler(Exception)
    def handle_any_exception(exc):
        # Let HTTPException (404/400/redirects) pass through Werkzeug/Flask defaults.
        from werkzeug.exceptions import HTTPException

        if isinstance(exc, HTTPException):
            return exc
        app.logger.exception("Unhandled Exception: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass
        flash(
            "Something went wrong while loading that page. Please try again.",
            "danger",
        )
        return redirect(url_for("core.index"))


def _bootstrap_database(app: Flask) -> None:
    """Crash-proof startup: never raise out of bootstrap on Vercel cold starts."""

    def _rollback() -> None:
        try:
            db.session.rollback()
        except Exception:
            pass

    try:
        if is_vercel_runtime():
            # Strict readiness check only. DDL/seed work is performed before
            # deployment against the same persistent Supabase database.
            db.session.execute(text("SELECT 1"))
            db.session.rollback()
            app.logger.info("Supabase production connection verified.")
            return

        try:
            db.create_all()
        except Exception:
            app.logger.exception("db.create_all failed during bootstrap")
            _rollback()

        try:
            ensure_name_columns()
        except Exception:
            app.logger.exception("ensure_name_columns failed during bootstrap")
            _rollback()

        # Idempotent catalog: plans + trainers + upcoming classes.
        # Critical on Vercel SQLite where each cold start may get a fresh /tmp DB.
        presentation = {}
        try:
            presentation = ensure_presentation_seed()
        except Exception:
            app.logger.exception("ensure_presentation_seed failed during bootstrap")
            _rollback()
            try:
                ensure_default_plans()
                ensure_demo_accounts()
            except Exception:
                app.logger.exception("Fallback plans/accounts ensure failed")
                _rollback()

        try:
            repair_report = repair_database()
            app.logger.info("Database repair report: %s", repair_report)
        except Exception:
            app.logger.exception("repair_database failed during bootstrap")
            _rollback()
            repair_report = {}

        try:
            if db.engine.dialect.name == "sqlite":
                db.session.execute(text("PRAGMA journal_mode=DELETE"))
                db.session.commit()
        except Exception:
            app.logger.exception("SQLite PRAGMA setup failed during bootstrap")
            _rollback()

        try:
            seeded = ensure_demo_data()
        except Exception:
            app.logger.exception("ensure_demo_data failed during bootstrap")
            seeded = False
            _rollback()

        demo_accounts = (presentation or {}).get("accounts") or {}
        try:
            if not demo_accounts:
                demo_accounts = (repair_report or {}).get("demo_accounts", {}) or {}
            if not demo_accounts:
                demo_accounts = ensure_demo_accounts()
        except Exception:
            app.logger.exception("Final demo-account ensure failed during bootstrap")
            _rollback()

        try:
            dialect_name = db.engine.dialect.name
        except Exception:
            dialect_name = "unknown"
        app.logger.info(
            "Database bootstrap complete (%s / %s). Full seed %s. Presentation: %s.",
            dialect_name,
            app.config.get("DATABASE_SOURCE"),
            "applied" if seeded else "skipped/partial",
            presentation or demo_accounts,
        )
    except Exception:
        _rollback()
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
    repair_database()
    ensure_default_plans()
    if db.engine.dialect.name == "sqlite":
        db.session.execute(text("PRAGMA journal_mode=WAL"))
        db.session.commit()
    click.echo(f"Initialized database ({db.engine.dialect.name}).")


@click.command("upgrade-db")
def upgrade_db_command() -> None:
    """Ensure trainer user accounts exist for trainer profiles."""

    report = repair_database()
    created = upgrade_trainer_accounts()
    click.echo(f"Database repaired: {report}")
    click.echo(f"Trainer logins created: {created}.")
