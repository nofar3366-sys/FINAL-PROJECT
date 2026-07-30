"""Local Flask CLI / debug entry.

Vercel must use only ``app.py`` as the WSGI entrypoint. Keeping a second
module-level ``app`` in ``main.py`` can make modern Vercel builds fail when
both ``app.py`` and ``main.py`` are detected as Python entry files.

Use:
  flask --app app run --debug
  flask --app app init-db
"""

from fitness_studio import create_app


def create_flask_app():
    """Factory for tooling that prefers an explicit callable."""

    return create_app()


if __name__ == "__main__":
    create_flask_app().run(debug=True)
