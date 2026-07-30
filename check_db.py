"""Quick connectivity check against DATABASE_URL (pooler-friendly).

Usage:
  .\\venv\\Scripts\\python.exe check_db.py
"""

import os

from dotenv import load_dotenv

load_dotenv()

# Prefer the real env/.env value. Do not hard-code secrets here.
if not os.environ.get("DATABASE_URL"):
    raise SystemExit(
        "DATABASE_URL is not set. Put your Supabase Transaction pooler URI "
        "(port 6543) in .env or the environment."
    )

from fitness_studio.config import normalize_database_url, sqlalchemy_engine_options
from fitness_studio import create_app
from models import db
from sqlalchemy import text

uri = normalize_database_url(os.environ["DATABASE_URL"])
print("Using driver:", uri.split("://", 1)[0])
print("Pooler mode:", ":6543" in uri or "pooler.supabase.com" in uri)
print("Engine options keys:", sorted(sqlalchemy_engine_options(uri).keys()))

app = create_app()
with app.app_context():
    try:
        db.session.execute(text("SELECT 1"))
        db.create_all()
        print("SUCCESS: Connected via DATABASE_URL and ensured tables exist.")
        print("Dialect:", db.engine.dialect.name)
    except Exception as exc:
        print(f"ERROR: Failed to connect or create tables: {exc}")
        raise SystemExit(1) from exc
