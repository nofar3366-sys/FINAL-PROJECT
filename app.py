"""Vercel / local WSGI entrypoint.

Vercel requires a top-level ``app = Flask(...)``.
On Vercel we keep that shell app for detection/import, and lazy-load the full
MVC application on the first request. That prevents import-time crashes from
showing up as FUNCTION_INVOCATION_FAILED with no handler.
"""

from __future__ import annotations

import logging
import os
import traceback

from flask import Flask, jsonify

logger = logging.getLogger("app_entry")

_ON_VERCEL = os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))
if _ON_VERCEL:
    os.environ["FORCE_SQLITE"] = "1"
    os.environ["USE_SQLITE"] = "1"
    os.environ["USE_POSTGRES"] = "0"
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SUPABASE_DB_PASSWORD", None)
    os.environ.pop("SUPABASE_PROJECT_REF", None)

# Literal Flask instance — required by Vercel detector.
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-only-change-me")

_REAL_APP: Flask | None = None
_LOAD_ERROR = ""
_LOAD_ATTEMPTED = False


@app.get("/health")
def shell_health():
    return jsonify(
        {
            "status": "ok" if not _LOAD_ERROR else "degraded",
            "mode": "full" if _REAL_APP is not None else "shell",
            "vercel": _ON_VERCEL,
            "git_sha": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:7] or None,
            "load_error": _LOAD_ERROR[:400] if _LOAD_ERROR else None,
        }
    ), (200 if not _LOAD_ERROR else 503)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def shell_home(path: str = ""):
    return (
        "<h1>Fitness Studio</h1>"
        "<p>Entry shell is online.</p>"
        f"<p>Full app loaded: {_REAL_APP is not None}</p>"
        f"<pre>{_LOAD_ERROR}</pre>"
        "<p><a href='/health'>/health</a></p>",
        200,
    )


def _load_real_app() -> Flask | None:
    global _REAL_APP, _LOAD_ERROR, _LOAD_ATTEMPTED
    if _REAL_APP is not None:
        return _REAL_APP
    if _LOAD_ATTEMPTED and _LOAD_ERROR:
        return None
    _LOAD_ATTEMPTED = True
    try:
        from fitness_studio import create_app

        _REAL_APP = create_app()
        _LOAD_ERROR = ""
        logger.info("Full Fitness Studio app loaded successfully")
        return _REAL_APP
    except Exception as exc:  # noqa: BLE001
        _LOAD_ERROR = "".join(
            traceback.format_exception_only(type(exc), exc)
        ).strip()
        logger.exception("Failed to load full app")
        return None


_SHELL_WSGI = app.wsgi_app


def _dispatch(environ, start_response):
    """Prefer the full MVC app; fall back to the shell Flask app."""

    real = _load_real_app()
    if real is not None:
        return real(environ, start_response)
    return _SHELL_WSGI(environ, start_response)


if _ON_VERCEL:
    # Lazy: import/create_app runs on first request, not during module import.
    app.wsgi_app = _dispatch
else:
    # Local/dev: load the full app immediately (CLI + flask run expect it).
    loaded = _load_real_app()
    if loaded is not None:
        app = loaded


if __name__ == "__main__":
    app.run(debug=True)
