"""Vercel / local WSGI entrypoint.

Vercel Serverless Functions import this module and look for a global `app`.
On Vercel we force SQLite before any app factory work so a bad DATABASE_URL
cannot hang cold starts (FUNCTION_INVOCATION_FAILED).
"""

import logging
import os

# Hard override for serverless: never probe/bootstrap remote Postgres at import.
if os.environ.get("VERCEL") == "1" or os.environ.get("VERCEL_ENV"):
    os.environ["FORCE_SQLITE"] = "1"
    os.environ["USE_POSTGRES"] = "0"

logger = logging.getLogger(__name__)


def _recovery_app():
    from flask import Flask

    recovery = Flask(__name__)
    recovery.secret_key = "recovery-mode-only"

    @recovery.get("/health")
    def health():
        return {
            "status": "degraded",
            "database": "unavailable",
            "hint": "App recovered from startup failure",
        }, 503

    @recovery.route("/", defaults={"path": ""})
    @recovery.route("/<path:path>")
    def any_path(path: str):
        return (
            "<h1>Fitness Studio</h1>"
            "<p>Temporary startup recovery mode. Please refresh shortly.</p>"
            "<p><a href='/health'>/health</a></p>",
            503,
        )

    return recovery


try:
    from fitness_studio import create_app

    app = create_app()
except Exception:
    logger.exception("create_app() failed at import time; serving recovery app")
    app = _recovery_app()


if __name__ == "__main__":
    app.run(debug=True)
