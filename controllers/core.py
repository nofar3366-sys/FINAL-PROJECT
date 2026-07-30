from flask import Blueprint, current_app, g, jsonify, redirect, url_for
from sqlalchemy import text

from models import db


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
        "groq": "configured" if current_app.config["GROQ_API_KEY"] else "mock-fallback",
        "email": (
            "resend-configured"
            if current_app.config["RESEND_API_KEY"]
            else "mock-fallback"
        ),
    }
    return jsonify(payload), 200 if database_ok else 503
