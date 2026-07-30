import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from dotenv import load_dotenv


load_dotenv()


def is_vercel_runtime() -> bool:
    """True when running inside a Vercel Serverless / Fluid Function."""

    return os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))


def build_supabase_pooler_url(
    project_ref: str,
    password: str,
    *,
    region: str = "eu-west-2",
    pooler_host: str | None = None,
) -> str:
    """Build a Supabase Transaction pooler URI (port 6543) for SQLAlchemy."""

    ref = project_ref.strip()
    raw_password = password.strip()
    if not ref or not raw_password:
        return ""

    # Prefer explicit host; otherwise aws-0-<region>. Some new projects land on aws-1.
    host = (pooler_host or "").strip() or f"aws-0-{region.strip()}.pooler.supabase.com"
    encoded_password = quote(raw_password, safe="")
    user = f"postgres.{ref}"
    return (
        f"postgresql://{user}:{encoded_password}@{host}:6543/postgres"
        f"?sslmode=require"
    )


def normalize_database_url(url: str) -> str:
    """Normalize Supabase/Heroku-style URLs for SQLAlchemy + psycopg (v3)."""

    value = url.strip()
    if not value:
        return ""

    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]

    if value.startswith("postgresql+psycopg2://"):
        value = "postgresql+psycopg://" + value[len("postgresql+psycopg2://") :]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://") :]

    if not value.startswith("postgresql"):
        return value

    parsed = urlparse(value)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    query.pop("pgbouncer", None)

    return urlunparse(parsed._replace(query=urlencode(query)))


def sqlite_fallback_uri(instance_path: str | Path | None = None) -> str:
    """Return a writable SQLite URI (Vercel-safe under /tmp when needed)."""

    if instance_path:
        db_path = Path(instance_path) / "fitness_studio.db"
        return f"sqlite:///{db_path.resolve().as_posix()}"
    if is_vercel_runtime():
        db_path = Path(tempfile.gettempdir()) / "fitness_studio.db"
        return f"sqlite:///{db_path.resolve().as_posix()}"
    return "sqlite:///fitness_studio.db"


def resolve_database_uri(instance_path: str | Path | None = None) -> str:
    """Resolve Postgres URI from env, else local/Vercel SQLite."""

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

    return sqlite_fallback_uri(instance_path)


def sqlalchemy_engine_options(database_uri: str) -> dict:
    """Build SQLAlchemy engine options for local SQLite or serverless Postgres."""

    options: dict = {"pool_pre_ping": True}
    if database_uri.startswith("sqlite"):
        options["connect_args"] = {"timeout": 10}
        return options

    from sqlalchemy.pool import NullPool

    options["poolclass"] = NullPool
    options["connect_args"] = {
        # Fail fast so Vercel cold starts do not hang on a bad DATABASE_URL.
        "connect_timeout": 1 if is_vercel_runtime() else 2,
        "prepare_threshold": None,
    }
    return options


def probe_database_uri(database_uri: str, timeout_seconds: float = 3.0) -> bool:
    """Return True when a short SELECT 1 succeeds against the URI.

    Wall-clock bounded: DNS failures on dead Supabase hosts can ignore
    ``connect_timeout`` and hang for many seconds, which breaks Vercel cold starts.
    """

    if not database_uri:
        return False
    if database_uri.startswith("sqlite"):
        return True

    def _probe() -> bool:
        from sqlalchemy import create_engine, text

        engine = create_engine(
            database_uri,
            pool_pre_ping=False,
            connect_args={
                "connect_timeout": max(1, int(timeout_seconds)),
                "prepare_threshold": None,
            },
        )
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
        finally:
            engine.dispose()

    # Hard wall-clock cap — connect_timeout alone does not bound DNS ENOTFOUND.
    # Important: shutdown(wait=False) so a hung DNS thread cannot block return.
    wall = max(0.5, float(timeout_seconds))
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_probe)
        return bool(future.result(timeout=wall))
    except (FuturesTimeout, Exception):
        return False
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def resolve_runtime_database_uri(instance_path: str | Path | None = None) -> tuple[str, str]:
    """Choose a working DB URI.

    Returns ``(uri, source)`` where source is ``postgres``, ``sqlite-fallback``,
    ``sqlite-forced``, or ``sqlite``.

    Vercel serverless cold starts must stay under a few seconds. Probing or
    bootstrapping Supabase from ``create_app()`` regularly takes 20–40s and
    causes ``FUNCTION_INVOCATION_FAILED``. Therefore Vercel always uses a
    writable SQLite DB under ``/tmp``. Local/dev can still use Supabase via
    ``DATABASE_URL``.

    Set ``FORCE_SQLITE=1`` locally to skip Postgres. Set ``USE_POSTGRES=1`` on
    Vercel only if you accept slower cold starts against a live pooler.
    """

    force_sqlite = os.environ.get("FORCE_SQLITE", "").lower() in {
        "1",
        "true",
        "yes",
    } or os.environ.get("USE_SQLITE", "").lower() in {"1", "true", "yes"}

    # Vercel: ALWAYS SQLite. Remote Supabase during cold start causes
    # FUNCTION_INVOCATION_FAILED (~30s). Local/dev may still use DATABASE_URL.
    if force_sqlite or is_vercel_runtime():
        return sqlite_fallback_uri(instance_path), "sqlite-forced"

    configured = resolve_database_uri(instance_path)
    if configured.startswith("sqlite"):
        return configured, "sqlite"

    if probe_database_uri(configured, timeout_seconds=3.0):
        return configured, "postgres"

    return sqlite_fallback_uri(instance_path), "sqlite-fallback"


class Config:
    """Base application configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "development-only-change-me")
    # Placeholder only — create_app() always overwrites with a runtime URI.
    # Do not call resolve_database_uri() here: class-body evaluation runs on
    # import and can pull a bad DATABASE_URL before Vercel overrides apply.
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 7
    SESSION_COOKIE_SECURE = is_vercel_runtime()
    DATABASE_SOURCE = "unresolved"

    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "30"))

    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    RECEIPT_FROM_EMAIL = os.environ.get(
        "RECEIPT_FROM_EMAIL", "Fitness Studio <onboarding@resend.dev>"
    )
