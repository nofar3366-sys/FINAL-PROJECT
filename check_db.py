"""Verify DATABASE_URL / Supabase pooler settings without starting the web server.

Usage:
  .\\venv\\Scripts\\python.exe check_db.py
"""

import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv(override=True)

from fitness_studio.config import (  # noqa: E402
    build_supabase_pooler_url,
    normalize_database_url,
    resolve_database_uri,
    sqlalchemy_engine_options,
)


def _redact(uri: str) -> str:
    parts = urlsplit(uri)
    if "@" not in parts.netloc:
        return uri
    auth, host = parts.netloc.rsplit("@", 1)
    user = auth.split(":", 1)[0]
    return parts._replace(netloc=f"{user}:***@{host}").geturl()


def main() -> None:
    built = build_supabase_pooler_url(
        os.environ.get("SUPABASE_PROJECT_REF", ""),
        os.environ.get("SUPABASE_DB_PASSWORD", ""),
        region=os.environ.get("SUPABASE_REGION", "eu-central-1"),
        pooler_host=os.environ.get("SUPABASE_POOLER_HOST") or None,
    )
    uri = resolve_database_uri()
    opts = sqlalchemy_engine_options(uri)

    print("Resolved URI:", _redact(uri))
    print("Driver:", uri.split("://", 1)[0])
    print("Port 6543:", ":6543" in uri)
    print("Pooler host:", "pooler.supabase.com" in uri)
    print("prepare_threshold:", opts.get("connect_args", {}).get("prepare_threshold"))
    print("poolclass:", getattr(opts.get("poolclass"), "__name__", None))
    if built:
        print("Built from parts:", _redact(normalize_database_url(built)))

    if uri.startswith("sqlite"):
        raise SystemExit("No Supabase DATABASE_URL configured.")

    from sqlalchemy import text

    from fitness_studio import create_app
    from models import db

    # Keep variable name away from Vercel entrypoint detection ("app").
    flask_app = create_app()
    with flask_app.app_context():
        try:
            db.session.execute(text("SELECT 1"))
            db.create_all()
            print("SUCCESS: Connected and ensured tables exist.")
            print("Dialect:", db.engine.dialect.name)
        except Exception as exc:
            print(f"ERROR: {exc}")
            print(
                "If you see tenant/user ENOTFOUND, copy the exact Transaction "
                "pooler URI (including aws-0/aws-1 REGION) from the Supabase dashboard."
            )
            raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
