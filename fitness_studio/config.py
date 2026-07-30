import os

from dotenv import load_dotenv


load_dotenv()


def is_vercel_runtime() -> bool:
    """True when running inside a Vercel Serverless / Fluid Function."""

    return os.environ.get("VERCEL") == "1" or bool(os.environ.get("VERCEL_ENV"))


class Config:
    """Base application configuration.

    A relative SQLite URI is resolved by Flask-SQLAlchemy against Flask's
    instance directory, so the primary database is always
    instance/fitness_studio.db locally. On Vercel, create_app overrides the
    URI to a writable /tmp path.
    """

    SECRET_KEY = os.environ.get("SECRET_KEY", "development-only-change-me")
    SQLALCHEMY_DATABASE_URI = "sqlite:///fitness_studio.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 10},
        "pool_pre_ping": True,
    }
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
