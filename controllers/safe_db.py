"""Helpers that keep database failures from becoming hard 500 responses."""

from __future__ import annotations

from functools import wraps

from flask import current_app, flash, redirect, session, url_for
from sqlalchemy.exc import SQLAlchemyError

from models import db


def recover_from_db_error(message: str | None = None) -> None:
    """Rollback, optionally repair schema, and clear the auth session."""

    try:
        db.session.rollback()
    except Exception:
        pass
    # Avoid hammering a dead remote database during request recovery.
    try:
        dialect = db.engine.dialect.name
    except Exception:
        dialect = ""
    if dialect == "sqlite":
        try:
            from services.schema_service import repair_database

            repair_database()
        except Exception:
            current_app.logger.exception("Post-error database repair failed")
    session.clear()
    flash(
        message
        or (
            "The studio database needed a quick repair. Please sign in again. "
            "If this keeps happening, contact your manager."
        ),
        "warning",
    )


def db_safe(view):
    """Decorator: convert unhandled SQLAlchemy errors into a login redirect."""

    @wraps(view)
    def wrapped_view(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except SQLAlchemyError:
            current_app.logger.exception(
                "Database error in %s", getattr(view, "__name__", "view")
            )
            recover_from_db_error()
            return redirect(url_for("auth.login"))

    return wrapped_view
