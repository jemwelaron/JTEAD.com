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


def _promote_to_reviewer(e2e_app, email):
    with e2e_app.app_context():
        from models import User, db

        user = User.query.filter_by(email=email).first()
        user.is_reviewer = True
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


def test_peer_review_flow(page, base_url, e2e_app, tmp_path):
    author_email = "e2e-author3@example.com"
    editor_email = "e2e-editor2@example.com"
    reviewer_email = "e2e-reviewer@example.com"

    # Author submits a manuscript.
    page.goto(f"{base_url}/authentication.html")
    page.click("#show-signup-btn")
    page.fill("#signup-name", "E2E Author Three")
    page.fill("#signup-email", author_email)
    page.fill("#signup-password", "Harbor Whistle33")
    page.click("#signup-form button[type=submit]")
    page.wait_for_url(re.compile(r"my-submissions\.html"))
    _verify_email(e2e_app, author_email)

    page.goto(f"{base_url}/Submit%20portal.html")
    page.select_option("#track", "fine-arts")
    page.fill("#keywords", "peer, review, e2e")
    page.fill("#title", "Peer Review E2E Manuscript")
    page.fill("#abstract", "Manuscript used to test the full peer review flow end to end.")
    page.fill("#ca-name", "E2E Author Three")
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

    page.goto(f"{base_url}/my-submissions.html")
    page.click("#accountLink")
    page.wait_for_url(re.compile(r"index\.html"))

    # Reviewer account (promoted directly, mirrors `flask make-reviewer`).
    page.goto(f"{base_url}/authentication.html")
    page.click("#show-signup-btn")
    page.fill("#signup-name", "E2E Reviewer")
    page.fill("#signup-email", reviewer_email)
    page.fill("#signup-password", "Harbor Whistle33")
    page.click("#signup-form button[type=submit]")
    page.wait_for_url(re.compile(r"my-submissions\.html"))
    _promote_to_reviewer(e2e_app, reviewer_email)
    page.click("#accountLink")
    page.wait_for_url(re.compile(r"index\.html"))

    # Editor account, assigns the reviewer to the new submission.
    page.goto(f"{base_url}/authentication.html")
    page.click("#show-signup-btn")
    page.fill("#signup-name", "E2E Editor Two")
    page.fill("#signup-email", editor_email)
    page.fill("#signup-password", "Harbor Whistle33")
    page.click("#signup-form button[type=submit]")
    page.wait_for_url(re.compile(r"my-submissions\.html"))
    _promote_to_editor(e2e_app, editor_email)

    page.goto(f"{base_url}/editor-dashboard.html")
    page.wait_for_selector("text=Peer Review E2E Manuscript")
    row = page.locator("tr", has_text="Peer Review E2E Manuscript")
    row.locator("a.history-toggle").click()
    details_row = page.locator("tr.history-row:not(.hidden)")
    details_row.wait_for()

    reviewers_section = details_row.locator(".reviewers-section")
    reviewers_section.locator(".assign-reviewer-select").select_option(label="E2E Reviewer")
    reviewers_section.locator(".assign-reviewer-btn").click()
    reviewers_section.locator("text=Pending").wait_for()

    page.goto(f"{base_url}/my-submissions.html")
    page.click("#accountLink")
    page.wait_for_url(re.compile(r"index\.html"))

    # Reviewer sees the assignment and submits a review through the real form.
    # (redirectAfterAuth() already sends them straight to their dashboard.)
    page.goto(f"{base_url}/authentication.html")
    page.fill("#login-email", reviewer_email)
    page.fill("#login-password", "Harbor Whistle33")
    page.click("#login-form button[type=submit]")
    page.wait_for_url(re.compile(r"reviewer-dashboard\.html"))
    page.wait_for_selector("text=Peer Review E2E Manuscript")
    page.click("text=Peer Review E2E Manuscript")

    page.wait_for_url(re.compile(r"review-form\.html"))
    assert page.inner_text("#fAbstract") == "Manuscript used to test the full peer review flow end to end."
    # Blind review: the reviewer-facing page never receives the author's
    # identifying details at all (checked properly at the API level in
    # tests/test_app.py::test_reviewer_assignment_detail_hides_identifying_fields
    # — this just spot-checks the actual author's name/email never end up
    # rendered anywhere on the real page).
    page_text = page.content()
    assert "E2E Author Three" not in page_text
    assert author_email not in page_text

    page.select_option("#recommendation", "minor-revisions")
    page.fill("#comments-to-author", "Please expand the methodology section.")
    page.fill("#comments-to-editor", "Otherwise solid, leaning toward acceptance.")
    page.click("#submit-btn")

    # Not "text=Review submitted" — that badge text exists in the static
    # HTML from page load (just CSS-hidden via a class on its parent), so
    # it can transiently match as "visible" during a fresh page load before
    # the stylesheet has applied, well before the post-reload init() has
    # actually fetched and rendered the submitted review. Waiting on text
    # that only ever gets set by JS (never present in the raw markup) is
    # immune to that race.
    page.wait_for_selector("#submittedRecommendation:has-text('Minor Revisions')")
    assert page.inner_text("#submittedRecommendation") == "Minor Revisions"

    # Editor sees the submitted review, including the confidential comment.
    page.click("#accountLink")
    page.wait_for_url(re.compile(r"index\.html"))
    page.goto(f"{base_url}/authentication.html")
    page.fill("#login-email", editor_email)
    page.fill("#login-password", "Harbor Whistle33")
    page.click("#login-form button[type=submit]")
    page.wait_for_url(re.compile(r"editor-dashboard\.html"))

    page.wait_for_selector("text=Peer Review E2E Manuscript")
    row = page.locator("tr", has_text="Peer Review E2E Manuscript")
    row.locator("a.history-toggle").click()
    details_row = page.locator("tr.history-row:not(.hidden)")
    details_row.wait_for()
    reviewers_section = details_row.locator(".reviewers-section")
    assert "Submitted — Minor Revisions" in reviewers_section.inner_text()
