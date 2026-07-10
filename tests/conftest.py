import os
import sys
import tempfile
from io import BytesIO

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# config.py requires SECRET_KEY to be set at import time (it raises if it's
# missing). Set a throwaway value before importing so tests don't need a
# real .env file.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

# security_log.py's logger is a process-wide singleton configured at import
# time, so it can't pick up per-test tmp_path overrides the way the app
# factory can. Point it at a scratch directory for the whole test session
# instead, so the real jtead-instance/security.log is never touched.
os.environ.setdefault("SECURITY_LOG_DIR", tempfile.mkdtemp(prefix="jtead-test-logs-"))

from app import create_app  # noqa: E402
from config import TestConfig  # noqa: E402
from models import db as _db  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    class IsolatedTestConfig(TestConfig):
        # Every real file this app touches (db, uploads) is redirected under
        # pytest's tmp_path, so a test run can never contend with — or
        # pollute — the real jtead-instance/ directory the dev server uses.
        INSTANCE_DIR = tmp_path
        UPLOAD_DIR = tmp_path / "uploads"

    application = create_app(IsolatedTestConfig)
    with application.app_context():
        yield application
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
    resp = client.post(
        "/api/signup", json={"full_name": full_name, "email": email, "password": password}
    )
    # Most tests aren't exercising the verify-email flow itself, and manuscript
    # submission is gated on a verified email — auto-verify here so existing
    # submission-focused tests don't all need to route through it. The
    # dedicated verification tests bypass this helper (or reset the flag)
    # to exercise the gate directly.
    if resp.status_code == 200:
        from models import User, db

        user = User.query.filter_by(email=email.strip().lower()).first()
        if user:
            user.email_verified = True
            db.session.commit()
    return resp
