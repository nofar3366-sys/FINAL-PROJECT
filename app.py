"""Vercel / local WSGI entrypoint.

On Vercel we expose a tiny shell Flask app first. /health never imports the
full MVC stack — that isolates FUNCTION_INVOCATION_FAILED (import/bootstrap
crashes) from runtime detection. Other paths lazy-load create_app().
"""

from __future__ import annotations

import logging
import os
import traceback

from flask import Flask, jsonify

logger = logging.getLogger("app_entry")

_ON_VERCEL = os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))
if _ON_VERCEL:
    # Never touch remote Postgres during serverless cold starts.
    os.environ["FORCE_SQLITE"] = "1"
    os.environ["USE_SQLITE"] = "1"
    os.environ["USE_POSTGRES"] = "0"
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("SUPABASE_DB_PASSWORD", None)
    os.environ.pop("SUPABASE_PROJECT_REF", None)

# Literal Flask instance — required by Vercel detector.
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-only-change-me")

_REAL_APP = None  # type: ignore[var-annotated]
_LOAD_ERROR = ""
_LOAD_ATTEMPTED = False


def _shell_payload(extra=None):
    body = {
        "status": "ok" if not _LOAD_ERROR else "degraded",
        "mode": "full" if _REAL_APP is not None else "shell",
        "vercel": _ON_VERCEL,
        "git_sha": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:7] or None,
        "load_error": (_LOAD_ERROR[:500] if _LOAD_ERROR else None),
        "load_attempted": _LOAD_ATTEMPTED,
    }
    if extra:
        body.update(extra)
    return body


@app.get("/health")
def shell_health():
    """Always answered by the shell — never imports fitness_studio."""
    return jsonify(_shell_payload()), (200 if not _LOAD_ERROR else 503)


@app.get("/__boot")
def shell_boot():
    """Explicitly try loading the full app and report the result."""
    real = _load_real_app()
    code = 200 if real is not None else 503
    return jsonify(_shell_payload({"booted": real is not None})), code


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def shell_catch_all(path: str = ""):
    return (
        "<!doctype html><html><body style='font-family:sans-serif;padding:2rem'>"
        "<h1>Fitness Studio</h1>"
        "<p>Entry shell is online (full app not loaded for this response).</p>"
        f"<p>Full app loaded: {_REAL_APP is not None}</p>"
        f"<pre>{_LOAD_ERROR}</pre>"
        "<p><a href='/health'>/health</a> · <a href='/__boot'>/__boot</a> · "
        "<a href='/auth/login'>/auth/login</a></p>"
        "</body></html>",
        200,
    )


def _load_real_app():
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
    """Shell answers /health; everything else prefers the full MVC app."""
    path = environ.get("PATH_INFO") or "/"
    if path == "/health" or path == "/__shell":
        return _SHELL_WSGI(environ, start_response)

    real = _load_real_app()
    if real is not None:
        return real(environ, start_response)
    return _SHELL_WSGI(environ, start_response)


if _ON_VERCEL:
    app.wsgi_app = _dispatch
else:
    loaded = _load_real_app()
    if loaded is not None:
        app = loaded


if __name__ == "__main__":
    app.run(debug=True)
