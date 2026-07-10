from tests.conftest import signup


# ---------- Signup ----------


def test_signup_success(client, valid_password):
    resp = signup(client, email="newuser@example.com", password=valid_password)
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_signup_missing_fields(client):
    resp = client.post("/api/signup", json={"email": "x@example.com"})
    assert resp.status_code == 400


def test_signup_invalid_email_format(client, valid_password):
    resp = signup(client, email="not-an-email", password=valid_password)
    assert resp.status_code == 400
    assert "valid email" in resp.get_json()["error"]


def test_signup_password_too_short(client):
    resp = signup(client, password="short1")
    assert resp.status_code == 400
    assert "at least" in resp.get_json()["error"]


def test_signup_password_no_digit(client):
    resp = signup(client, password="onlylettersnodigits")
    assert resp.status_code == 400
    assert "letter and one number" in resp.get_json()["error"]


def test_signup_password_too_common(client):
    resp = signup(client, password="password123")
    assert resp.status_code == 400
    assert "too common" in resp.get_json()["error"]


def test_signup_password_contains_email(client):
    resp = signup(client, email="janesmith@example.com", password="janesmith123")
    assert resp.status_code == 400
    assert "email address" in resp.get_json()["error"]


def test_signup_duplicate_email_rejected(client, valid_password):
    first = signup(client, email="dupe@example.com", password=valid_password)
    assert first.status_code == 200
    client.post("/api/logout")
    second = signup(client, email="dupe@example.com", password=valid_password)
    assert second.status_code == 409


def test_signup_logs_you_in(client, valid_password):
    signup(client, email="autologin@example.com", password=valid_password)
    resp = client.get("/api/me")
    assert resp.status_code == 200
    assert resp.get_json()["email"] == "autologin@example.com"


# ---------- Login / logout ----------


def test_login_wrong_password(client, valid_password):
    signup(client, email="login1@example.com", password=valid_password)
    client.post("/api/logout")
    resp = client.post("/api/login", json={"email": "login1@example.com", "password": "wrongpassword"})
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post("/api/login", json={"email": "nobody@example.com", "password": "whatever123"})
    assert resp.status_code == 401


def test_login_correct_password(client, valid_password):
    signup(client, email="login2@example.com", password=valid_password)
    client.post("/api/logout")
    resp = client.post("/api/login", json={"email": "login2@example.com", "password": valid_password})
    assert resp.status_code == 200


def test_me_requires_auth(client):
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_logout_clears_session(client, valid_password):
    signup(client, email="logout1@example.com", password=valid_password)
    client.post("/api/logout")
    resp = client.get("/api/me")
    assert resp.status_code == 401


# ---------- Manuscript submission ----------


def test_submit_article_requires_login(client, submission_form_data):
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 401


def test_submit_article_success(client, valid_password, submission_form_data):
    signup(client, email="submitter@example.com", password=valid_password)
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 302
    assert "submitted=1" in resp.headers["Location"]


def test_submit_article_creates_submission_record(client, valid_password, submission_form_data):
    from models import Submission

    signup(client, email="submitter2@example.com", password=valid_password)
    submission_form_data["ca-email"] = "submitter2@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    submission = Submission.query.filter_by(title="A Test Manuscript").first()
    assert submission is not None
    assert submission.status == "submitted"


def test_submit_article_missing_required_field(client, valid_password, submission_form_data):
    signup(client, email="submitter3@example.com", password=valid_password)
    del submission_form_data["articleTitle"]
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 302
    assert "error=" in resp.headers["Location"]


def test_submit_article_bad_file_extension(client, valid_password, submission_form_data):
    from io import BytesIO

    signup(client, email="submitter4@example.com", password=valid_password)
    submission_form_data["manuscript"] = (BytesIO(b"not a real document"), "manuscript.exe")
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 302
    assert "error=" in resp.headers["Location"]


def test_submit_article_content_does_not_match_extension(client, valid_password, submission_form_data):
    """A file renamed to .docx but not actually a ZIP/OOXML file should be rejected,
    even though the extension whitelist alone would have allowed it through."""
    from io import BytesIO
    from urllib.parse import unquote

    signup(client, email="submitter7@example.com", password=valid_password)
    submission_form_data["manuscript"] = (BytesIO(b"this is plain text, not a real docx"), "manuscript.docx")
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 302
    location = unquote(resp.headers["Location"])
    assert "error=" in location
    assert "content doesn't match its extension" in location


def test_submit_article_missing_ethics_ack(client, valid_password, submission_form_data):
    signup(client, email="submitter5@example.com", password=valid_password)
    del submission_form_data["eth-2"]
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 302
    assert "error=" in resp.headers["Location"]


def test_my_submissions_requires_login(client):
    resp = client.get("/api/my-submissions")
    assert resp.status_code == 401


def test_my_submissions_lists_own_submissions(client, valid_password, submission_form_data):
    signup(client, email="submitter6@example.com", password=valid_password)
    submission_form_data["ca-email"] = "submitter6@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    resp = client.get("/api/my-submissions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["title"] == "A Test Manuscript"
    assert data[0]["status"] == "submitted"


# ---------- Rate limiting ----------


def test_submit_article_rate_limited(client, valid_password, app):
    # Rate-limiting is off by default in tests (see conftest.py) so the other
    # tests above aren't affected by shared state between them; turn it on
    # just for this one to prove the limit itself actually works. Flask-
    # Limiter reads RATELIMIT_ENABLED once, in init_app, so flipping the
    # config alone after the app is already built has no effect — it has to
    # be re-applied to pick up the new value.
    from extensions import limiter

    app.config["RATELIMIT_ENABLED"] = True
    limiter.init_app(app)
    signup(client, email="ratelimit@example.com", password=valid_password)

    # The limiter check runs before the view body, so an otherwise-invalid
    # empty submission is enough to exercise it without needing 16 full
    # multipart uploads.
    statuses = [client.post("/submit-article", data={}).status_code for _ in range(16)]
    assert 429 in statuses


# ---------- Password reset ----------


def test_forgot_password_unknown_email_still_returns_ok(client):
    # Must not leak whether an email is registered.
    resp = client.post("/api/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_forgot_password_known_email_returns_ok(client, valid_password):
    signup(client, email="resetme@example.com", password=valid_password)
    resp = client.post("/api/forgot-password", json={"email": "resetme@example.com"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def _make_reset_token(app, email, password):
    from app import PASSWORD_RESET_SALT
    from itsdangerous import URLSafeTimedSerializer
    from models import User

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt=PASSWORD_RESET_SALT)
        return serializer.dumps({"user_id": user.id, "pw": user.password_hash[-16:]})


def test_reset_password_with_valid_token(client, app, valid_password):
    signup(client, email="resetvalid@example.com", password=valid_password)
    token = _make_reset_token(app, "resetvalid@example.com", valid_password)

    resp = client.post("/api/reset-password", json={"token": token, "password": "BrandNewPass99"})
    assert resp.status_code == 200

    client.post("/api/logout")
    login_resp = client.post(
        "/api/login", json={"email": "resetvalid@example.com", "password": "BrandNewPass99"}
    )
    assert login_resp.status_code == 200


def test_reset_password_with_garbage_token_rejected(client):
    resp = client.post("/api/reset-password", json={"token": "not-a-real-token", "password": "BrandNewPass99"})
    assert resp.status_code == 400


def test_reset_password_token_single_use(client, app, valid_password):
    signup(client, email="resetreuse@example.com", password=valid_password)
    token = _make_reset_token(app, "resetreuse@example.com", valid_password)

    first = client.post("/api/reset-password", json={"token": token, "password": "BrandNewPass99"})
    assert first.status_code == 200

    # Reusing the same token after the password already changed must fail —
    # the token embeds a fragment of the old password hash, so it goes stale
    # the moment the password it was issued for changes.
    second = client.post("/api/reset-password", json={"token": token, "password": "AnotherPass88"})
    assert second.status_code == 400


def test_reset_password_weak_password_rejected(client, app, valid_password):
    signup(client, email="resetweak@example.com", password=valid_password)
    token = _make_reset_token(app, "resetweak@example.com", valid_password)

    resp = client.post("/api/reset-password", json={"token": token, "password": "short1"})
    assert resp.status_code == 400


# ---------- Editor dashboard ----------


def _promote_to_editor(email):
    from models import User, db

    user = User.query.filter_by(email=email).first()
    user.is_editor = True
    db.session.commit()


def test_editor_submissions_requires_login(client):
    resp = client.get("/api/editor/submissions")
    assert resp.status_code == 401


def test_editor_submissions_requires_editor_role(client, valid_password):
    signup(client, email="notaneditor@example.com", password=valid_password)
    resp = client.get("/api/editor/submissions")
    assert resp.status_code == 403


def test_editor_can_list_all_submissions(client, valid_password, submission_form_data, app):
    # NOTE: promotion happens via the same ambient app-context session the
    # `app`/`client` fixtures already hold open for the whole test, not a
    # fresh `with app.app_context()`. A fresh context gets its own
    # SQLAlchemy session/identity map — Flask-Login's already-cached User
    # object in the fixture's session would never see a commit made through
    # a different session, and the update would silently appear to work
    # while the request-side `current_user.is_editor` stayed stale.
    signup(client, email="author9@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author9@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    client.post("/api/logout")

    signup(client, email="editor1@example.com", password=valid_password)
    _promote_to_editor("editor1@example.com")

    resp = client.get("/api/editor/submissions")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["author_email"] == "author9@example.com"


def test_editor_can_update_submission_status(client, valid_password, submission_form_data, app):
    from models import Submission, db

    signup(client, email="author10@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author10@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    client.post("/api/logout")

    signup(client, email="editor2@example.com", password=valid_password)
    _promote_to_editor("editor2@example.com")
    submission_id = Submission.query.first().id

    resp = client.post(f"/api/editor/submissions/{submission_id}/status", json={"status": "under-review"})
    assert resp.status_code == 200
    assert db.session.get(Submission, submission_id).status == "under-review"


def test_editor_rejects_invalid_status(client, valid_password, app):
    signup(client, email="editor3@example.com", password=valid_password)
    _promote_to_editor("editor3@example.com")

    resp = client.post("/api/editor/submissions/1/status", json={"status": "not-a-real-status"})
    assert resp.status_code == 400


# ---------- Security logging ----------


def test_login_failure_is_logged(client, caplog):
    import logging

    from security_log import security_logger

    security_logger.propagate = True
    try:
        with caplog.at_level(logging.WARNING, logger="jtead.security"):
            client.post("/api/login", json={"email": "nobody@example.com", "password": "wrong"})
        assert any("login failed" in r.message for r in caplog.records)
    finally:
        security_logger.propagate = False


def test_signup_success_is_logged(client, valid_password, caplog):
    import logging

    from security_log import security_logger

    security_logger.propagate = True
    try:
        with caplog.at_level(logging.INFO, logger="jtead.security"):
            signup(client, email="logtest@example.com", password=valid_password)
        assert any("signup success" in r.message for r in caplog.records)
    finally:
        security_logger.propagate = False
