"""Local-only runner. Not a Vercel entrypoint filename.

Vercel auto-detects main.py/app.py/index.py/server.py — keep create_app
imports out of those filenames except the real entry (app.py).
"""

from fitness_studio import create_app


def create_flask_app():
    return create_app()


if __name__ == "__main__":
    create_flask_app().run(debug=True)
