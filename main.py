"""Local-only helpers. Do NOT expose a module-level Flask ``app`` here.

Vercel must use ``app.py`` exclusively (see ``pyproject.toml`` tool.vercel.entrypoint).
"""

from fitness_studio import create_app


def create_flask_app():
    return create_app()


if __name__ == "__main__":
    create_flask_app().run(debug=True)
