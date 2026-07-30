"""Vercel / local WSGI entrypoint.

Vercel Serverless Functions import this module and look for a global `app`.
Keep this file free of side effects beyond creating the Flask application.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from fitness_studio import create_app

    app = create_app()
except Exception:
    # Absolute last resort: never leave Vercel without a WSGI callable.
    logger.exception("create_app() failed at import time; serving recovery app")
    from flask import Flask

    app = Flask(__name__)
    app.secret_key = "recovery-mode-only"

    @app.get("/health")
    def _recovery_health():
        return {"status": "degraded", "database": "unavailable"}, 503

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def _recovery_any(path: str):
        return (
            "<h1>Fitness Studio</h1>"
            "<p>The application is recovering from a startup error. "
            "Please refresh in a moment.</p>",
            503,
        )


if __name__ == "__main__":
    app.run(debug=True)
