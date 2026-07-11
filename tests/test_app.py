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


def test_login_email_rate_limit_key_is_per_account(app):
    from app import login_email_rate_limit_key

    with app.test_request_context(
        "/api/login", method="POST", json={"email": "Victim@Example.com", "password": "x"}
    ):
        assert login_email_rate_limit_key() == "login-email:victim@example.com"

    with app.test_request_context("/api/login", method="POST", json={"password": "x"}):
        # No email in the payload — falls back to per-IP instead of an
        # empty "login-email:" key that would bucket every emailless
        # request together under one shared limit.
        key = login_email_rate_limit_key()
        assert key and not key.startswith("login-email:")


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


def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_healthz_no_auth_required(client):
    # Explicitly not gated behind login_required — monitoring tools hitting
    # this shouldn't need credentials.
    resp = client.get("/healthz")
    assert resp.status_code != 401


def test_logout_clears_session(client, valid_password):
    signup(client, email="logout1@example.com", password=valid_password)
    client.post("/api/logout")
    resp = client.get("/api/me")
    assert resp.status_code == 401


# ---------- Manuscript submission ----------


def test_submit_article_requires_login(client, submission_form_data):
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 401


def test_submit_article_requires_verified_email(client, valid_password, submission_form_data):
    from urllib.parse import unquote

    from models import User, db

    signup(client, email="unverified@example.com", password=valid_password)
    # signup()'s auto-verify is a test convenience for every other test —
    # undo it here to exercise the actual gate in submit_article.
    user = User.query.filter_by(email="unverified@example.com").first()
    user.email_verified = False
    db.session.commit()

    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 302
    assert "verify your email" in unquote(resp.headers["Location"])


def test_submit_article_success(client, valid_password, submission_form_data):
    signup(client, email="submitter@example.com", password=valid_password)
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 302
    assert "submitted=1" in resp.headers["Location"]


def test_submit_article_sends_confirmation_email(client, valid_password, submission_form_data, monkeypatch):
    import app as app_module

    sent = {}

    def fake_send_email(to, subject, body):
        sent["to"] = to
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(app_module, "send_email", fake_send_email)

    signup(client, email="emailconfirm@example.com", password=valid_password)
    submission_form_data["ca-email"] = "emailconfirm@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    assert sent["to"] == "emailconfirm@example.com"
    assert "received" in sent["subject"].lower()
    assert "A Test Manuscript" in sent["body"]


def test_submit_article_creates_submission_record(client, valid_password, submission_form_data):
    from models import Submission

    signup(client, email="submitter2@example.com", password=valid_password)
    submission_form_data["ca-email"] = "submitter2@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    submission = Submission.query.filter_by(title="A Test Manuscript").first()
    assert submission is not None
    assert submission.status == "submitted"


def test_submit_article_same_filename_across_fields_does_not_collide(
    client, valid_password, submission_form_data
):
    from io import BytesIO

    from models import Submission

    signup(client, email="submitter8@example.com", password=valid_password)
    submission_form_data["ca-email"] = "submitter8@example.com"

    # Two different files that happen to share an original filename — before
    # the field-name prefix fix, the second one saved would silently
    # overwrite the first on disk and both DB columns would point at the
    # same (wrong) file.
    manuscript_bytes = b"PK\x03\x04" + b"manuscript-content" + b"\x00" * 10
    cover_letter_bytes = b"PK\x03\x04" + b"cover-letter-content" + b"\x00" * 10
    submission_form_data["manuscript"] = (BytesIO(manuscript_bytes), "paper.docx")
    submission_form_data["cover_letter"] = (BytesIO(cover_letter_bytes), "paper.docx")

    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    submission = Submission.query.filter_by(user_id=1).first()
    assert submission.manuscript_path != submission.cover_letter_path

    manuscript_resp = client.get(f"/api/my-submissions/{submission.id}/files/manuscript")
    cover_letter_resp = client.get(f"/api/my-submissions/{submission.id}/files/cover_letter")
    assert manuscript_resp.data == manuscript_bytes
    assert cover_letter_resp.data == cover_letter_bytes


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


def test_submit_article_invalid_corresponding_email_rejected(client, valid_password, submission_form_data):
    from urllib.parse import unquote

    signup(client, email="submitter9@example.com", password=valid_password)
    submission_form_data["ca-email"] = "not-an-email"
    resp = client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    assert resp.status_code == 302
    assert "valid corresponding author email" in unquote(resp.headers["Location"])


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


# ---------- Submission detail, file download, withdrawal ----------


def test_submission_detail_requires_ownership(client, valid_password, submission_form_data):
    from models import Submission

    signup(client, email="owner1@example.com", password=valid_password)
    submission_form_data["ca-email"] = "owner1@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    submission_id = Submission.query.first().id
    client.post("/api/logout")

    signup(client, email="notowner1@example.com", password=valid_password)
    resp = client.get(f"/api/my-submissions/{submission_id}")
    assert resp.status_code == 404


def test_submission_detail_returns_full_fields(client, valid_password, submission_form_data):
    signup(client, email="owner2@example.com", password=valid_password)
    submission_form_data["ca-email"] = "owner2@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    resp = client.get("/api/my-submissions/1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["title"] == "A Test Manuscript"
    assert data["abstract"] == "This is a test abstract."
    assert data["can_withdraw"] is True
    assert data["co_authors"] == []

    # A fresh submission already has one history entry recording its
    # initial status, and the author-facing view never names who touched
    # it (there's only ever been the author so far, but the shape should
    # hold regardless).
    assert len(data["history"]) == 1
    assert data["history"][0]["status"] == "submitted"
    assert "changed_by" not in data["history"][0]


def test_submission_file_download_owner_only(client, valid_password, submission_form_data):
    from models import Submission

    signup(client, email="owner3@example.com", password=valid_password)
    submission_form_data["ca-email"] = "owner3@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    submission_id = Submission.query.first().id
    client.post("/api/logout")

    signup(client, email="notowner3@example.com", password=valid_password)
    resp = client.get(f"/api/my-submissions/{submission_id}/files/manuscript")
    assert resp.status_code == 404


def test_submission_file_download_success(client, valid_password, submission_form_data):
    signup(client, email="owner4@example.com", password=valid_password)
    submission_form_data["ca-email"] = "owner4@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    resp = client.get("/api/my-submissions/1/files/manuscript")
    assert resp.status_code == 200
    assert resp.data.startswith(b"PK\x03\x04")


def test_withdraw_submission_success(client, valid_password, submission_form_data):
    signup(client, email="owner5@example.com", password=valid_password)
    submission_form_data["ca-email"] = "owner5@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    resp = client.post("/api/my-submissions/1/withdraw")
    assert resp.status_code == 200

    detail = client.get("/api/my-submissions/1").get_json()
    assert detail["status"] == "withdrawn"
    assert detail["can_withdraw"] is False


def test_withdraw_submission_not_owner(client, valid_password, submission_form_data):
    from models import Submission

    signup(client, email="owner6@example.com", password=valid_password)
    submission_form_data["ca-email"] = "owner6@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    submission_id = Submission.query.first().id
    client.post("/api/logout")

    signup(client, email="notowner6@example.com", password=valid_password)
    resp = client.post(f"/api/my-submissions/{submission_id}/withdraw")
    assert resp.status_code == 404


def test_withdraw_submission_already_withdrawn_rejected(client, valid_password, submission_form_data):
    signup(client, email="owner7@example.com", password=valid_password)
    submission_form_data["ca-email"] = "owner7@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    client.post("/api/my-submissions/1/withdraw")
    resp = client.post("/api/my-submissions/1/withdraw")
    assert resp.status_code == 400


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


def test_signup_rate_limited(client, app):
    from extensions import limiter

    app.config["RATELIMIT_ENABLED"] = True
    limiter.init_app(app)

    statuses = [
        client.post(
            "/api/signup",
            json={"full_name": "Flood", "email": f"flood{i}@example.com", "password": "GoodPassword123"},
        ).status_code
        for i in range(15)
    ]
    assert 429 in statuses


# ---------- Change password ----------


def test_change_password_requires_login(client):
    resp = client.post(
        "/api/change-password", json={"current_password": "x", "new_password": "NewPassword99"}
    )
    assert resp.status_code == 401


def test_change_password_wrong_current_password(client, valid_password):
    signup(client, email="changepw1@example.com", password=valid_password)
    resp = client.post(
        "/api/change-password",
        json={"current_password": "totallywrong", "new_password": "NewPassword99"},
    )
    assert resp.status_code == 401


def test_change_password_weak_new_password(client, valid_password):
    signup(client, email="changepw2@example.com", password=valid_password)
    resp = client.post(
        "/api/change-password", json={"current_password": valid_password, "new_password": "short1"}
    )
    assert resp.status_code == 400


def test_change_password_success_and_can_login_with_new_password(client, valid_password):
    signup(client, email="changepw3@example.com", password=valid_password)
    resp = client.post(
        "/api/change-password",
        json={"current_password": valid_password, "new_password": "BrandNewPass99"},
    )
    assert resp.status_code == 200

    client.post("/api/logout")
    login_resp = client.post(
        "/api/login", json={"email": "changepw3@example.com", "password": "BrandNewPass99"}
    )
    assert login_resp.status_code == 200

    old_login_resp = client.post(
        "/api/login", json={"email": "changepw3@example.com", "password": valid_password}
    )
    assert old_login_resp.status_code == 401


def test_change_password_sends_notification_email(client, valid_password, monkeypatch):
    import app as app_module

    sent = {}
    monkeypatch.setattr(
        app_module, "send_email", lambda to, subject, body: sent.update(to=to, subject=subject)
    )

    signup(client, email="changepw4@example.com", password=valid_password)
    client.post(
        "/api/change-password",
        json={"current_password": valid_password, "new_password": "BrandNewPass99"},
    )

    assert sent["to"] == "changepw4@example.com"
    assert "password was changed" in sent["subject"].lower()


def _request(client, method, *args, **kwargs):
    # Flask's `g` is scoped to the *app context*, not the request — and the
    # `app` fixture holds one ambient app context open for the whole test
    # (so plain ORM queries like `Submission.query...` work directly in test
    # bodies). Flask-Login's current_user is a lazy, cache-once-per-`g`
    # LocalProxy, so without this, a second test_client() sharing that same
    # ambient context would keep seeing whichever user was first resolved
    # into `g`, regardless of which client's cookies the next call actually
    # sends. Real production requests never share an app context this way —
    # every request gets its own from scratch — so this is purely a test
    # harness quirk, not something the app itself needs to handle. Clearing
    # it before each call forces Flask-Login to re-resolve current_user from
    # that specific call's actual session cookie.
    from flask import g

    if hasattr(g, "_login_user"):
        del g._login_user
    return getattr(client, method)(*args, **kwargs)


def test_change_password_invalidates_other_sessions(app, valid_password):
    # Two independent cookie jars against the same app/db — simulates the
    # account being logged in on two different browsers/devices at once.
    client_a = app.test_client()
    client_b = app.test_client()

    signup(client_a, email="twosession@example.com", password=valid_password)
    _request(
        client_b,
        "post",
        "/api/login",
        json={"email": "twosession@example.com", "password": valid_password},
    )

    # Both sessions work before the change.
    assert _request(client_a, "get", "/api/me").status_code == 200
    assert _request(client_b, "get", "/api/me").status_code == 200

    _request(
        client_a,
        "post",
        "/api/change-password",
        json={"current_password": valid_password, "new_password": "BrandNewPass99"},
    )

    # client_a made the change and gets a refreshed cookie, so it stays in.
    assert _request(client_a, "get", "/api/me").status_code == 200
    # client_b's cookie was issued before the change and embeds the old
    # session_version — it must now be treated as logged out.
    assert _request(client_b, "get", "/api/me").status_code == 401


def test_reset_password_invalidates_other_sessions(client, app, valid_password):
    signup(client, email="resetinvalidate@example.com", password=valid_password)
    assert _request(client, "get", "/api/me").status_code == 200

    token = _make_reset_token(app, "resetinvalidate@example.com", valid_password)
    # A separate client performs the reset (mirrors the real flow — reset
    # links are used from an unauthenticated browser context).
    reset_client = app.test_client()
    _request(
        reset_client,
        "post",
        "/api/reset-password",
        json={"token": token, "password": "BrandNewPass99"},
    )

    # The original session, still holding a cookie from before the reset,
    # must no longer be treated as logged in.
    assert _request(client, "get", "/api/me").status_code == 401


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


def test_forgot_password_still_ok_when_email_delivery_fails(client, valid_password, monkeypatch):
    # SMTP_HOST isn't set in tests, so mailer.send_email already takes the
    # logging fallback rather than hitting the network — this simulates the
    # case where SMTP *is* configured but delivery throws, to confirm the
    # client-facing response (and the anti-enumeration guarantee it makes)
    # doesn't depend on delivery succeeding.
    import app as app_module

    def boom(**kwargs):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(app_module, "send_email", boom)

    signup(client, email="resetfail@example.com", password=valid_password)
    resp = client.post("/api/forgot-password", json={"email": "resetfail@example.com"})
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


# ---------- Email verification ----------


def test_signup_sends_verification_email(client, valid_password, monkeypatch):
    import app as app_module

    sent = {}

    def fake_send_email(to, subject, body):
        sent["to"] = to
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(app_module, "send_email", fake_send_email)

    resp = client.post(
        "/api/signup",
        json={"full_name": "Verify Me", "email": "verifyflow@example.com", "password": valid_password},
    )
    assert resp.status_code == 200
    assert sent["to"] == "verifyflow@example.com"
    assert "verify" in sent["subject"].lower()


def test_new_signup_is_unverified_until_confirmed(client, valid_password):
    # Bypasses the signup() test helper's auto-verify convenience on purpose,
    # to check the real default a fresh account starts with.
    client.post(
        "/api/signup",
        json={"full_name": "Real Default", "email": "realdefault@example.com", "password": valid_password},
    )
    resp = client.get("/api/me")
    assert resp.get_json()["email_verified"] is False


def _make_verify_token(app, email):
    from app import EMAIL_VERIFY_SALT
    from itsdangerous import URLSafeTimedSerializer
    from models import User

    with app.app_context():
        user = User.query.filter_by(email=email).first()
        serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt=EMAIL_VERIFY_SALT)
        return serializer.dumps({"user_id": user.id})


def test_verify_email_with_valid_token(client, app, valid_password):
    client.post(
        "/api/signup",
        json={"full_name": "Verify Valid", "email": "verifyvalid@example.com", "password": valid_password},
    )
    token = _make_verify_token(app, "verifyvalid@example.com")

    resp = client.post("/api/verify-email", json={"token": token})
    assert resp.status_code == 200

    me = client.get("/api/me").get_json()
    assert me["email_verified"] is True


def test_verify_email_with_garbage_token_rejected(client):
    resp = client.post("/api/verify-email", json={"token": "not-a-real-token"})
    assert resp.status_code == 400


def test_resend_verification_requires_login(client):
    resp = client.post("/api/resend-verification")
    assert resp.status_code == 401


def test_resend_verification_sends_email_when_unverified(client, valid_password, monkeypatch):
    import app as app_module

    client.post(
        "/api/signup",
        json={"full_name": "Resend Me", "email": "resendme@example.com", "password": valid_password},
    )

    sent = {}
    monkeypatch.setattr(
        app_module, "send_email", lambda to, subject, body: sent.update(to=to, subject=subject)
    )

    resp = client.post("/api/resend-verification")
    assert resp.status_code == 200
    assert sent["to"] == "resendme@example.com"


def test_resend_verification_noop_when_already_verified(client, valid_password):
    # signup() helper auto-verifies, so this account is already verified.
    signup(client, email="alreadyverified@example.com", password=valid_password)

    resp = client.post("/api/resend-verification")
    assert resp.status_code == 200
    assert resp.get_json()["already_verified"] is True


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


def test_editor_status_change_recorded_in_history(client, valid_password, submission_form_data):
    from models import Submission

    signup(client, email="author15@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author15@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    client.post("/api/logout")

    signup(client, email="editor12@example.com", password=valid_password, full_name="History Editor")
    _promote_to_editor("editor12@example.com")
    submission_id = Submission.query.first().id

    client.post(f"/api/editor/submissions/{submission_id}/status", json={"status": "under-review"})
    client.post(f"/api/editor/submissions/{submission_id}/status", json={"status": "accepted"})

    resp = client.get(f"/api/editor/submissions/{submission_id}/history")
    assert resp.status_code == 200
    history = resp.get_json()
    assert [h["new_status"] for h in history] == ["submitted", "under-review", "accepted"]
    assert history[0]["old_status"] is None
    assert history[1]["old_status"] == "submitted"
    assert history[-1]["changed_by"] == "History Editor"


def test_editor_submission_history_requires_editor_role(client, valid_password, submission_form_data):
    signup(client, email="author16@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author16@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    resp = client.get("/api/editor/submissions/1/history")
    assert resp.status_code == 403


def test_withdraw_recorded_in_history(client, valid_password, submission_form_data):
    signup(client, email="author17@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author17@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    client.post("/api/my-submissions/1/withdraw")

    detail = client.get("/api/my-submissions/1").get_json()
    assert [h["status"] for h in detail["history"]] == ["submitted", "withdrawn"]


def test_editor_status_change_sends_email(client, valid_password, submission_form_data, monkeypatch):
    from models import Submission

    import editor as editor_module

    sent = {}

    def fake_send_email(to, subject, body):
        sent["to"] = to
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(editor_module, "send_email", fake_send_email)

    signup(client, email="author14@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author14@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    client.post("/api/logout")

    signup(client, email="editor7@example.com", password=valid_password)
    _promote_to_editor("editor7@example.com")
    submission_id = Submission.query.first().id

    client.post(f"/api/editor/submissions/{submission_id}/status", json={"status": "accepted"})

    assert sent["to"] == "author14@example.com"
    assert "Accepted" in sent["subject"]
    assert "A Test Manuscript" in sent["body"]


def test_editor_rejects_invalid_status(client, valid_password, app):
    signup(client, email="editor3@example.com", password=valid_password)
    _promote_to_editor("editor3@example.com")

    resp = client.post("/api/editor/submissions/1/status", json={"status": "not-a-real-status"})
    assert resp.status_code == 400


def test_editor_can_download_submission_file(client, valid_password, submission_form_data, app):
    from models import Submission

    signup(client, email="author11@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author11@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    client.post("/api/logout")

    signup(client, email="editor4@example.com", password=valid_password)
    _promote_to_editor("editor4@example.com")
    submission_id = Submission.query.first().id

    resp = client.get(f"/api/editor/submissions/{submission_id}/files/manuscript")
    assert resp.status_code == 200
    assert resp.data.startswith(b"PK\x03\x04")


def test_editor_file_download_requires_editor_role(client, valid_password, submission_form_data):
    signup(client, email="author12@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author12@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")

    resp = client.get("/api/editor/submissions/1/files/manuscript")
    assert resp.status_code == 403


def test_editor_file_download_unknown_field(client, valid_password, app):
    signup(client, email="editor5@example.com", password=valid_password)
    _promote_to_editor("editor5@example.com")

    resp = client.get("/api/editor/submissions/1/files/not-a-real-field")
    assert resp.status_code == 400


def test_editor_file_download_missing_optional_file(client, valid_password, submission_form_data, app):
    from models import Submission

    signup(client, email="author13@example.com", password=valid_password)
    submission_form_data["ca-email"] = "author13@example.com"
    client.post("/submit-article", data=submission_form_data, content_type="multipart/form-data")
    client.post("/api/logout")

    signup(client, email="editor6@example.com", password=valid_password)
    _promote_to_editor("editor6@example.com")
    submission_id = Submission.query.first().id

    # submission_form_data never included a "supplementary" file.
    resp = client.get(f"/api/editor/submissions/{submission_id}/files/supplementary")
    assert resp.status_code == 404


# ---------- Editor management ----------


def test_list_users_requires_editor_role(client, valid_password):
    signup(client, email="plainuser@example.com", password=valid_password)
    resp = client.get("/api/editor/users")
    assert resp.status_code == 403


def test_list_users_search_matches_name_or_email(client, valid_password):
    signup(client, email="findme@example.com", password=valid_password, full_name="Unique Findable Name")
    signup(client, email="editor8@example.com", password=valid_password)
    _promote_to_editor("editor8@example.com")

    by_email = client.get("/api/editor/users?search=findme@example.com").get_json()
    assert any(u["email"] == "findme@example.com" for u in by_email)

    by_name = client.get("/api/editor/users?search=Findable").get_json()
    assert any(u["email"] == "findme@example.com" for u in by_name)


def test_promote_user_grants_editor_access(client, valid_password):
    from models import User, db

    signup(client, email="tobepromoted@example.com", password=valid_password)
    client.post("/api/logout")

    signup(client, email="editor9@example.com", password=valid_password)
    _promote_to_editor("editor9@example.com")

    target = User.query.filter_by(email="tobepromoted@example.com").first()
    resp = client.post(f"/api/editor/users/{target.id}/promote")
    assert resp.status_code == 200
    assert db.session.get(User, target.id).is_editor is True


def test_demote_user_removes_editor_access(client, valid_password):
    from models import User, db

    signup(client, email="tobedemoted@example.com", password=valid_password)
    _promote_to_editor("tobedemoted@example.com")
    client.post("/api/logout")

    signup(client, email="editor10@example.com", password=valid_password)
    _promote_to_editor("editor10@example.com")

    target = User.query.filter_by(email="tobedemoted@example.com").first()
    resp = client.post(f"/api/editor/users/{target.id}/demote")
    assert resp.status_code == 200
    assert db.session.get(User, target.id).is_editor is False


def test_editor_cannot_demote_self(client, valid_password):
    signup(client, email="editor11@example.com", password=valid_password)
    _promote_to_editor("editor11@example.com")

    from models import User, db

    me = User.query.filter_by(email="editor11@example.com").first()
    resp = client.post(f"/api/editor/users/{me.id}/demote")
    assert resp.status_code == 400
    assert db.session.get(User, me.id).is_editor is True


def test_promote_user_requires_editor_role(client, valid_password):
    from models import User, db

    signup(client, email="notanadmin@example.com", password=valid_password)
    other = User.query.filter_by(email="notanadmin@example.com").first()

    resp = client.post(f"/api/editor/users/{other.id}/promote")
    assert resp.status_code == 403


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
