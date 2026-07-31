import os

from flask import Blueprint, current_app, flash, g, jsonify, redirect, request, url_for
from sqlalchemy import text

from fitness_studio.config import is_vercel_runtime
from models import db
from services.booking_service import BookingError, book_session


core_bp = Blueprint("core", __name__)


@core_bp.get("/")
def index():
    if g.user is None:
        return redirect(url_for("auth.login"))
    if g.user.normalized_role == "manager":
        return redirect(url_for("manager.dashboard"))
    if g.user.normalized_role == "trainer":
        return redirect(url_for("trainer.dashboard"))
    return redirect(url_for("member.dashboard"))


@core_bp.get("/schedule")
def schedule_alias():
    """Stable presentation URL that routes each role to its schedule."""

    if g.user is None:
        return redirect(url_for("auth.login"))
    if g.user.normalized_role == "manager":
        return redirect(url_for("manager.sessions"))
    if g.user.normalized_role == "trainer":
        return redirect(url_for("trainer.dashboard"))
    return redirect(url_for("member.schedule"))


@core_bp.post("/booking/create")
def booking_create_alias():
    """Compatibility endpoint for clients using the documented booking URL."""

    from controllers.auth import validate_csrf

    if g.user is None or g.user.normalized_role != "member" or g.user.member is None:
        return redirect(url_for("auth.login"))
    validate_csrf()
    try:
        session_id = int(request.form.get("session_id", "0"))
        book_session(g.user.member.id, session_id)
    except (TypeError, ValueError, BookingError) as exc:
        flash(str(exc), "danger")
    else:
        flash("Booking confirmed. One credit was used.", "success")
    return redirect(url_for("member.schedule"))


@core_bp.get("/health")
def health():
    database_ok = True
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        current_app.logger.exception("Database health check failed")
        database_ok = False

    payload = {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "unavailable",
        "database_engine": db.engine.dialect.name if database_ok else "unavailable",
        "database_source": current_app.config.get("DATABASE_SOURCE", "unknown"),
        "vercel_runtime": is_vercel_runtime(),
        "force_sqlite": os.environ.get("FORCE_SQLITE", ""),
        "database_url_present": bool(os.environ.get("DATABASE_URL")),
        "git_sha": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:7] or None,
        "bootstrapped": bool(current_app.config.get("_db_bootstrapped")),
        "groq": "configured" if current_app.config["GROQ_API_KEY"] else "mock-fallback",
        "email": (
            "resend-configured"
            if current_app.config["RESEND_API_KEY"]
            else "mock-fallback"
        ),
    }
    return jsonify(payload), 200 if database_ok else 503
