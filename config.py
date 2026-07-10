import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not set. Create a .env file with a real SECRET_KEY "
            "(generate one with: python -c \"import secrets; print(secrets.token_hex(32))\")."
        )

    # IMPORTANT: this must live OUTSIDE the project directory. app.py serves the
    # entire project root as static files (static_folder='.'), so anything placed
    # inside the project root — including a conventionally-named "instance/"
    # folder — is directly downloadable by anyone who guesses/finds the URL.
    # Keeping the database and uploaded manuscripts as a sibling directory is
    # what actually keeps them off the public static route.
    INSTANCE_DIR = BASE_DIR.parent / "jtead-instance"
    UPLOAD_DIR = INSTANCE_DIR / "uploads"

    SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(INSTANCE_DIR / "jtead.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB hard cap across all files in one request

    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Only send the session cookie over HTTPS once this is actually deployed behind TLS.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"

    WTF_CSRF_TIME_LIMIT = None  # tokens don't expire mid-form-fill

    # Defaults to in-memory, which only works correctly with a single worker
    # process — fine for local dev, silently broken (each worker counts limits
    # separately) once deployed with more than one. Set RATELIMIT_STORAGE_URI
    # to a real backend (e.g. redis://localhost:6379) before running with
    # multiple workers.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"

    # Password-reset emails. Leave SMTP_HOST unset to keep the dev fallback
    # (link logged server-side instead of emailed) — see mailer.py.
    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"
    MAIL_FROM = os.environ.get("MAIL_FROM", "no-reply@jtead.local")


class TestConfig(Config):
    """Used only by the pytest suite. Everything lives in-memory / under a
    pytest-managed tmp_path so tests never touch the real jtead-instance/
    directory that the dev server and production use."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
