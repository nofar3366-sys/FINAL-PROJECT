import os

from dotenv import load_dotenv


load_dotenv()


def is_vercel_runtime() -> bool:
    """True when running inside a Vercel Serverless / Fluid Function."""

    return os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))


def normalize_database_url(url: str) -> str:
    """Normalize Supabase/Heroku-style URLs for SQLAlchemy + psycopg2."""

    value = url.strip()
    if not value:
        return ""

    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        value = "postgresql+psycopg2://" + value[len("postgresql://") :]

    if "sslmode=" not in value and value.startswith("postgresql"):
        separator = "&" if "?" in value else "?"
        value = f"{value}{separator}sslmode=require"
    return value


def resolve_database_uri() -> str:
    """Prefer DATABASE_URL (Supabase/Postgres); fall back to local SQLite."""

    configured = normalize_database_url(os.environ.get("DATABASE_URL", ""))
    if configured:
        return configured
    return "sqlite:///fitness_studio.db"


def sqlalchemy_engine_options(database_uri: str) -> dict:
    options = {"pool_pre_ping": True}
    if database_uri.startswith("sqlite"):
        options["connect_args"] = {"timeout": 10}
    else:
        # Small pool for Vercel serverless + Supabase.
        options.update({"pool_size": 1, "max_overflow": 0, "pool_recycle": 280})
        options["connect_args"] = {"connect_timeout": 10}
    return options


class Config:
    """Base application configuration.

    Production and Vercel should set DATABASE_URL to the Supabase PostgreSQL
    connection string. Local development falls back to instance SQLite when
    DATABASE_URL is unset.
    """

    SECRET_KEY = os.environ.get("SECRET_KEY", "development-only-change-me")
    SQLALCHEMY_DATABASE_URI = resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = sqlalchemy_engine_options(SQLALCHEMY_DATABASE_URI)
    CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "30"))

    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RECEIPT_FROM_EMAIL = os.environ.get(
        "RECEIPT_FROM_EMAIL", "Fitness Studio <onboarding@resend.dev>"
    )

    CLOUD_SERVICE_ENABLED = (
        os.environ.get("CLOUD_SERVICE_ENABLED", "false").lower() == "true"
    )
    CLOUD_SERVICE_PROVIDER = os.environ.get("CLOUD_SERVICE_PROVIDER", "cloudinary")
    CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
