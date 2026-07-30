"""Vercel / local WSGI entrypoint.

Critical for Vercel: never touch remote Postgres during module import.
A hanging Supabase probe/bootstrap causes FUNCTION_INVOCATION_FAILED.
"""

from __future__ import annotations

import logging
import os
import traceback

logger = logging.getLogger("app_entry")

# --- Must run BEFORE importing fitness_studio ---
_ON_VERCEL = os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))
if _ON_VERCEL:
    os.environ["FORCE_SQLITE"] = "1"
    os.environ["USE_POSTGRES"] = "0"
    os.environ["USE_SQLITE"] = "1"
    # Prevent any import-time code from seeing a remote DATABASE_URL.
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SUPABASE_DB_PASSWORD", None)


def _build_recovery_app(error: BaseException | None = None):
    from flask import Flask, jsonify

    recovery = Flask(__name__)
    recovery.secret_key = os.environ.get("SECRET_KEY", "recovery-mode-only")
    detail = "".join(traceback.format_exception_only(type(error), error)).strip() if error else ""

    @recovery.get("/health")
    def health():
        return jsonify(
            {
                "status": "degraded",
                "database": "unavailable",
                "mode": "recovery",
                "error": detail[:300],
            }
        ), 503

    @recovery.route("/", defaults={"path": ""})
    @recovery.route("/<path:path>")
    def any_path(path: str):
        return (
            "<h1>Fitness Studio</h1>"
            "<p>Recovery mode (startup error).</p>"
            f"<pre>{detail}</pre>"
            "<p><a href='/health'>/health</a></p>",
            503,
        )

    return recovery


try:
    from fitness_studio import create_app

    app = create_app()
except Exception as exc:  # noqa: BLE001 — must never fail to expose WSGI app
    logger.exception("create_app failed; using recovery app")
    app = _build_recovery_app(exc)


if __name__ == "__main__":
    app.run(debug=True)
