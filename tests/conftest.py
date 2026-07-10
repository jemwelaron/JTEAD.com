import os
import sys
from io import BytesIO

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# app.py requires SECRET_KEY to be set at import time (config.py raises if
# it's missing). Set a throwaway value before importing so tests don't need
# a real .env file.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

from app import app as flask_app  # noqa: E402
from models import db as _db  # noqa: E402


@pytest.fixture()
def app():
    flask_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        RATELIMIT_ENABLED=False,
    )
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def valid_password():
    return "GoodPassword123"


@pytest.fixture()
def sample_files():
    """Fresh in-memory files for the 3 required uploads on the submission form.
    Content starts with real magic bytes so it passes file-signature validation,
    not just the filename extension check."""
    docx_bytes = b"PK\x03\x04" + b"\x00" * 20  # .docx is a ZIP container
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    return {
        "manuscript": (BytesIO(docx_bytes), "manuscript.docx"),
        "graphical_abstract": (BytesIO(png_bytes), "graphical.png"),
        "cover_letter": (BytesIO(docx_bytes), "cover.docx"),
    }


@pytest.fixture()
def submission_form_data(sample_files):
    return {
        "track": "computer-engineering",
        "keywords": "testing, pytest",
        "articleTitle": "A Test Manuscript",
        "abstract": "This is a test abstract.",
        "studentName": "Test Author",
        "ca-phone": "09171234567",
        "ca-email": "submitter@example.com",
        "ca-org": "Test University",
        "ca-city": "Iloilo City",
        "ca-country": "PH",
        "ca-identity": "author",
        "ca-category": "student",
        "coi-status": "no",
        "eth-1": "on",
        "eth-2": "on",
        "eth-3": "on",
        **sample_files,
    }


def signup(client, email="submitter@example.com", password="GoodPassword123", full_name="Test Author"):
    return client.post(
        "/api/signup", json={"full_name": full_name, "email": email, "password": password}
    )
