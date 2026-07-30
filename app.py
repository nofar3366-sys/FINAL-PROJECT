"""Vercel / local WSGI entrypoint.

Vercel’s Flask detector requires a top-level ``app = Flask(...)`` assignment.
We create that first, then replace it with the real application factory result.
"""

from __future__ import annotations

import logging
import os
import traceback

from flask import Flask

logger = logging.getLogger("app_entry")

# --- Must run BEFORE importing fitness_studio ---
_ON_VERCEL = os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))
if _ON_VERCEL:
    os.environ["FORCE_SQLITE"] = "1"
    os.environ["USE_POSTGRES"] = "0"
    os.environ["USE_SQLITE"] = "1"
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SUPABASE_DB_PASSWORD", None)

# Required by Vercel Flask detection (literal top-level Flask instance).
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-only-change-me")


def _build_recovery_app(error: BaseException | None = None) -> Flask:
    from flask import jsonify

    recovery = Flask(__name__)
    recovery.secret_key = os.environ.get("SECRET_KEY", "recovery-mode-only")
    detail = (
        "".join(traceback.format_exception_only(type(error), error)).strip()
        if error
        else ""
    )

    @recovery.get("/health")
    def health():
        return (
            jsonify(
                {
                    "status": "degraded",
                    "database": "unavailable",
                    "mode": "recovery",
                    "error": detail[:300],
                }
            ),
            503,
        )

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
except Exception as exc:  # noqa: BLE001 — must always expose a WSGI app
    logger.exception("create_app failed; using recovery app")
    app = _build_recovery_app(exc)


if __name__ == "__main__":
    app.run(debug=True)
