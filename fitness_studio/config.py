import os
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from dotenv import load_dotenv


load_dotenv()


def is_vercel_runtime() -> bool:
    """True when running inside a Vercel Serverless / Fluid Function."""

    return os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))


def _is_supabase_pooler_url(url: str) -> bool:
    """Detect Supabase transaction/session pooler endpoints (PgBouncer)."""

    lowered = url.lower()
    return (
        ":6543" in lowered
        or "pooler.supabase.com" in lowered
        or "pgbouncer=true" in lowered
    )


def build_supabase_pooler_url(
    project_ref: str,
    password: str,
    *,
    region: str = "ap-northeast-1",
    pooler_host: str | None = None,
) -> str:
    """Build a Supabase Transaction pooler URI (port 6543) for SQLAlchemy.

    Username format is ``postgres.<project_ref>`` (required by Supabase pooler).
    Special characters in the password (including ``%``) are URL-encoded.
    """

    ref = project_ref.strip()
    raw_password = password.strip()
    if not ref or not raw_password:
        return ""

    host = (pooler_host or "").strip() or f"aws-0-{region.strip()}.pooler.supabase.com"
    encoded_password = quote(raw_password, safe="")
    user = f"postgres.{ref}"
    return (
        f"postgresql://{user}:{encoded_password}@{host}:6543/postgres"
        f"?sslmode=require"
    )


def normalize_database_url(url: str) -> str:
    """Normalize Supabase/Heroku-style URLs for SQLAlchemy + psycopg (v3).

    - Rewrites legacy postgres:// to postgresql+psycopg://
    - Ensures sslmode=require for cloud Postgres / pooler URLs
    - Accepts direct (5432) and transaction pooler (6543) hosts
    """

    value = url.strip()
    if not value:
        return ""

    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]

    # Prefer psycopg3 so we can disable prepared statements for PgBouncer.
    if value.startswith("postgresql+psycopg2://"):
        value = "postgresql+psycopg://" + value[len("postgresql+psycopg2://") :]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://") :]

    if not value.startswith("postgresql"):
        return value

    parsed = urlparse(value)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    # psycopg rejects unknown libpq options such as Prisma's pgbouncer=true.
    query.pop("pgbouncer", None)

    return urlunparse(parsed._replace(query=urlencode(query)))


def resolve_database_uri() -> str:
    """Resolve Postgres URI from DATABASE_URL or Supabase pooler parts.

    Priority:
    1. ``DATABASE_URL``
    2. Built from ``SUPABASE_PROJECT_REF`` + ``SUPABASE_DB_PASSWORD``
       (+ optional ``SUPABASE_REGION`` / ``SUPABASE_POOLER_HOST``)
    3. Local SQLite fallback
    """

    explicit = normalize_database_url(os.environ.get("DATABASE_URL", ""))
    if explicit:
        return explicit

    project_ref = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
    password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    if project_ref and password:
        built = build_supabase_pooler_url(
            project_ref,
            password,
            region=os.environ.get("SUPABASE_REGION", "ap-northeast-1"),
            pooler_host=os.environ.get("SUPABASE_POOLER_HOST") or None,
        )
        return normalize_database_url(built)

    return "sqlite:///fitness_studio.db"


def sqlalchemy_engine_options(database_uri: str) -> dict:
    """Build SQLAlchemy engine options for local SQLite or serverless Postgres."""

    options: dict = {"pool_pre_ping": True}
    if database_uri.startswith("sqlite"):
        options["connect_args"] = {"timeout": 10}
        return options

    # NullPool avoids sticky connections across Vercel serverless invocations.
    from sqlalchemy.pool import NullPool

    options["poolclass"] = NullPool
    options["connect_args"] = {
        "connect_timeout": 15,
        # Critical for Supabase transaction pooler (PgBouncer on :6543).
        "prepare_threshold": None,
    }
    return options


class Config:
    """Base application configuration.

    Prefer Supabase Transaction pooler (port 6543) via DATABASE_URL.
    Local development falls back to instance SQLite when no cloud URI is set.
    """

    SECRET_KEY = os.environ.get("SECRET_KEY", "development-only-change-me")
    SQLALCHEMY_DATABASE_URI = resolve_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = sqlalchemy_engine_options(SQLALCHEMY_DATABASE_URI)
    CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7
    # Secure cookies on Vercel HTTPS so browsers retain the Flask session.
    SESSION_COOKIE_SECURE = is_vercel_runtime()

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "30"))

    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RECEIPT_FROM_EMAIL = os.environ.get(
        "RECEIPT_FROM_EMAIL", "Fitness Studio <onboarding@resend.dev>"
    )
