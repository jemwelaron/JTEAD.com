"""Real end-to-end tests: a real Flask server + a real Chrome browser via
Playwright, driving the actual HTML/JS pages exactly as a user would
(clicks, file pickers, form submits) rather than calling the API directly.
Complements tests/test_app.py, which exercises the backend in isolation."""

import re


def _verify_email(e2e_app, email):
    with e2e_app.app_context():
        from models import User, db

        user = User.query.filter_by(email=email).first()
        user.email_verified = True
        db.session.commit()


def _promote_to_editor(e2e_app, email):
    with e2e_app.app_context():
        from models import User, db

        user = User.query.filter_by(email=email).first()
        user.is_editor = True
        db.session.commit()


def _make_upload_files(tmp_path):
    manuscript = tmp_path / "manuscript.docx"
    manuscript.write_bytes(b"PK\x03\x04" + b"manuscript body" + b"\x00" * 10)
    graphical = tmp_path / "graphical.png"
    graphical.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    cover = tmp_path / "cover.docx"
    cover.write_bytes(b"PK\x03\x04" + b"cover letter body" + b"\x00" * 10)
    return manuscript, graphical, cover


def test_signup_login_logout(page, base_url):
    page.goto(f"{base_url}/authentication.html")
    page.click("#show-signup-btn")
    page.fill("#signup-name", "E2E Signup Author")
    page.fill("#signup-email", "e2e-signup@example.com")
    page.fill("#signup-password", "Harbor Whistle33")
    page.click("#signup-form button[type=submit]")

    page.wait_for_url(re.compile(r"my-submissions\.html"))
    page.wait_for_selector("#accountName:has-text('E2E Signup Author')")

    page.click("#accountLink")  # "Log Out" once signed in
    page.wait_for_url(re.compile(r"index\.html"))

    # Logged out again: My Submissions should bounce back to sign-in.
    page.goto(f"{base_url}/my-submissions.html")
    page.wait_for_url(re.compile(r"authentication\.html"))


def test_full_submission_and_withdrawal_flow(page, base_url, e2e_app, tmp_path):
    email = "e2e-submitter@example.com"

    page.goto(f"{base_url}/authentication.html")
    page.click("#show-signup-btn")
    page.fill("#signup-name", "E2E Submitter")
    page.fill("#signup-email", email)
    page.fill("#signup-password", "Harbor Whistle33")
    page.click("#signup-form button[type=submit]")
    page.wait_for_url(re.compile(r"my-submissions\.html"))

    _verify_email(e2e_app, email)

    page.goto(f"{base_url}/Submit%20portal.html")

    page.select_option("#track", "computer-engineering")
    page.fill("#keywords", "e2e, playwright")
    page.fill("#title", "Playwright E2E Manuscript")
    page.fill("#abstract", "An abstract written by an actual browser, not a raw HTTP request.")
    page.fill("#ca-name", "E2E Submitter")
    page.fill("#ca-phone", "09171234567")
    page.fill("#ca-email", email)
    page.fill("#ca-org", "University of San Agustin")
    page.fill("#ca-city", "Iloilo City")
    page.select_option("#ca-country", "PH")
    page.select_option("#ca-identity", "author")
    page.select_option("#ca-category", "student")
    page.select_option("#coi-status", "no")

    manuscript, graphical, cover = _make_upload_files(tmp_path)
    page.set_input_files("#file-anon", str(manuscript))
    page.set_input_files("#file-graphical", str(graphical))
    page.set_input_files("#file-cover", str(cover))

    # Confirms the file-picker-wrapper -> hidden-input click delegation
    # (converted from onclick= to addEventListener) actually updated the
    # visible label, not just the underlying input's file list.
    assert page.inner_text("#label-file-anon") == "manuscript.docx"

    page.check("#eth-1")
    page.check("#eth-2")
    page.check("#eth-3")

    page.click("button:has-text('SUBMIT MANUSCRIPT')")

    page.wait_for_url(re.compile(r"submitted=1"))
    assert page.is_visible("#successBanner")

    page.goto(f"{base_url}/my-submissions.html")
    page.wait_for_selector("text=Playwright E2E Manuscript")
    page.click("text=Playwright E2E Manuscript")

    page.wait_for_url(re.compile(r"submission-detail\.html"))
    page.wait_for_selector("#fStatus:has-text('Submitted')")
    assert page.inner_text("#fAbstract") == "An abstract written by an actual browser, not a raw HTTP request."
    assert page.locator("#fHistory li").count() == 1

    page.once("dialog", lambda dialog: dialog.accept())
    page.click("#withdrawBtn")
    page.wait_for_selector("#fStatus:has-text('Withdrawn')")
    assert page.locator("#fHistory li").count() == 2


def test_editor_dashboard_status_change_and_history(page, base_url, e2e_app, tmp_path):
    author_email = "e2e-author2@example.com"
    editor_email = "e2e-editor@example.com"

    # Author signs up and submits, in one browser context.
    page.goto(f"{base_url}/authentication.html")
    page.click("#show-signup-btn")
    page.fill("#signup-name", "E2E Author Two")
    page.fill("#signup-email", author_email)
    page.fill("#signup-password", "Harbor Whistle33")
    page.click("#signup-form button[type=submit]")
    page.wait_for_url(re.compile(r"my-submissions\.html"))

    _verify_email(e2e_app, author_email)

    page.goto(f"{base_url}/Submit%20portal.html")
    page.select_option("#track", "architecture")
    page.fill("#keywords", "editor, e2e")
    page.fill("#title", "Editor Review E2E Manuscript")
    page.fill("#abstract", "Manuscript used to test the editor dashboard end to end.")
    page.fill("#ca-name", "E2E Author Two")
    page.fill("#ca-phone", "09171234567")
    page.fill("#ca-email", author_email)
    page.fill("#ca-org", "University of San Agustin")
    page.fill("#ca-city", "Iloilo City")
    page.select_option("#ca-country", "PH")
    page.select_option("#ca-identity", "author")
    page.select_option("#ca-category", "student")
    page.select_option("#coi-status", "no")
    manuscript, graphical, cover = _make_upload_files(tmp_path)
    page.set_input_files("#file-anon", str(manuscript))
    page.set_input_files("#file-graphical", str(graphical))
    page.set_input_files("#file-cover", str(cover))
    page.check("#eth-1")
    page.check("#eth-2")
    page.check("#eth-3")
    page.click("button:has-text('SUBMIT MANUSCRIPT')")
    page.wait_for_url(re.compile(r"submitted=1"))

    # "Submit portal.html" is a standalone page with no shared topbar/
    # #accountLink (unlike my-submissions.html etc.) — go somewhere that
    # has it before logging out.
    page.goto(f"{base_url}/my-submissions.html")
    page.click("#accountLink")
    page.wait_for_url(re.compile(r"index\.html"))

    # Editor account, promoted directly via the DB (mirrors `flask
    # make-editor`, which this test can't invoke against a scratch server).
    page.goto(f"{base_url}/authentication.html")
    page.click("#show-signup-btn")
    page.fill("#signup-name", "E2E Editor")
    page.fill("#signup-email", editor_email)
    page.fill("#signup-password", "Harbor Whistle33")
    page.click("#signup-form button[type=submit]")
    page.wait_for_url(re.compile(r"my-submissions\.html"))
    _promote_to_editor(e2e_app, editor_email)

    page.goto(f"{base_url}/editor-dashboard.html")
    page.wait_for_selector("text=Editor Review E2E Manuscript")

    row = page.locator("tr", has_text="Editor Review E2E Manuscript")
    row.locator("select[data-submission-id]").select_option("under-review")
    page.wait_for_selector("text=Saved")

    row.locator("a.history-toggle").click()
    history_row = page.locator("tr.history-row:not(.hidden)")
    history_row.wait_for()
    assert "Under Review" in history_row.inner_text()
    assert "by E2E Editor" in history_row.inner_text()
