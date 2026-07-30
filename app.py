"""Vercel / local WSGI entrypoint.

On Vercel this module is intentionally a tiny Flask shell so /health can prove
the Python runtime works. Full MVC loads only from /__boot (or locally).
"""

from __future__ import annotations

import os
import traceback

from flask import Flask, jsonify

_ON_VERCEL = os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))

if _ON_VERCEL:
    for _key in (
        "DATABASE_URL",
        "SUPABASE_DB_PASSWORD",
        "SUPABASE_PROJECT_REF",
    ):
        os.environ.pop(_key, None)
    os.environ["FORCE_SQLITE"] = "1"
    os.environ["USE_SQLITE"] = "1"
    os.environ["USE_POSTGRES"] = "0"

# Top-level Flask instance required by Vercel.
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-only-change-me")

_REAL_APP = None
_LOAD_ERROR = ""


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "mode": "minimal-shell",
            "on_vercel": _ON_VERCEL,
            "vercel": os.environ.get("VERCEL"),
            "vercel_env": os.environ.get("VERCEL_ENV"),
            "git_sha": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:7] or None,
            "full_loaded": _REAL_APP is not None,
            "load_error": _LOAD_ERROR[:500] if _LOAD_ERROR else None,
        }
    )


@app.get("/__boot")
def boot():
    global _REAL_APP, _LOAD_ERROR
    if _REAL_APP is not None:
        return jsonify({"booted": True, "mode": "full"}), 200
    try:
        from fitness_studio import create_app

        _REAL_APP = create_app()
        _LOAD_ERROR = ""
        return jsonify({"booted": True, "mode": "full"}), 200
    except Exception as exc:  # noqa: BLE001
        _LOAD_ERROR = "".join(
            traceback.format_exception_only(type(exc), exc)
        ).strip()
        return jsonify({"booted": False, "error": _LOAD_ERROR}), 503


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def shell_home(path: str = ""):
    return (
        "<!doctype html><html><body style='font-family:sans-serif;padding:2rem'>"
        "<h1>Fitness Studio</h1>"
        "<p>Minimal Vercel shell is online.</p>"
        "<p><a href='/health'>/health</a> · <a href='/__boot'>/__boot</a></p>"
        f"<pre>{_LOAD_ERROR}</pre>"
        "</body></html>",
        200,
    )


def _mount_real_app():
    """Replace this module's WSGI app with the full MVC application."""
    global app, _REAL_APP, _LOAD_ERROR
    from fitness_studio import create_app

    _REAL_APP = create_app()
    app = _REAL_APP
    _LOAD_ERROR = ""
    return app


if not _ON_VERCEL:
    # Local flask CLI / pytest expect the real application.
    try:
        _mount_real_app()
    except Exception as exc:  # noqa: BLE001
        _LOAD_ERROR = str(exc)


if __name__ == "__main__":
    app.run(debug=True)
