"""Vercel / local WSGI entrypoint (must stay named app.py or main.py only once).

Do not add a second candidate entry file (main.py/index.py/server.py) that
imports the MVC stack — Vercel may import every candidate and crash before
this shell can answer /health.
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

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "development-only-change-me")

_REAL_APP = None
_LOAD_ERROR = ""
_SHELL_WSGI = None


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "mode": "shell" if _REAL_APP is None else "full",
            "on_vercel": _ON_VERCEL,
            "git_sha": (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "")[:7] or None,
            "load_error": _LOAD_ERROR[:500] if _LOAD_ERROR else None,
        }
    )


def _load_real_app():
    global _REAL_APP, _LOAD_ERROR
    if _REAL_APP is not None:
        return _REAL_APP
    if _LOAD_ERROR:
        return None
    try:
        from fitness_studio import create_app

        _REAL_APP = create_app()
        _LOAD_ERROR = ""
        return _REAL_APP
    except Exception as exc:  # noqa: BLE001
        _LOAD_ERROR = "".join(
            traceback.format_exception_only(type(exc), exc)
        ).strip()
        return None


def _dispatch(environ, start_response):
    path = environ.get("PATH_INFO") or "/"
    if path == "/health":
        return _SHELL_WSGI(environ, start_response)

    real = _load_real_app()
    if real is not None:
        return real(environ, start_response)
    return _SHELL_WSGI(environ, start_response)


_SHELL_WSGI = app.wsgi_app

if _ON_VERCEL:
    app.wsgi_app = _dispatch
else:
    loaded = _load_real_app()
    if loaded is not None:
        app = loaded


if __name__ == "__main__":
    app.run(debug=True)
