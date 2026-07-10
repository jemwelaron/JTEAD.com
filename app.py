import os
import re
import uuid
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

from flask import Blueprint, Flask, current_app, jsonify, redirect, request, send_from_directory
from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_wtf.csrf import generate_csrf
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from config import Config
from editor import editor_bp
from extensions import csrf, limiter, login_manager, migrate
from file_signatures import file_content_matches_extension
from mailer import send_email
from models import CoAuthor, Submission, User, db
from password_rules import validate_password_strength
from security_log import security_logger
from statuses import WITHDRAWABLE_STATUSES
from submission_files import FILE_FIELD_COLUMNS

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PASSWORD_RESET_SALT = "password-reset"
PASSWORD_RESET_MAX_AGE = 3600  # seconds
EMAIL_VERIFY_SALT = "email-verify"
EMAIL_VERIFY_MAX_AGE = 24 * 3600  # seconds

main_bp = Blueprint("main", __name__)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "Sign in required."}), 401


def _reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=PASSWORD_RESET_SALT)


def _email_verify_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=EMAIL_VERIFY_SALT)


def _send_verification_email(user):
    token = _email_verify_serializer().dumps({"user_id": user.id})
    verify_link = f"{request.host_url.rstrip('/')}/verify-email.html?token={token}"
    try:
        send_email(
            to=user.email,
            subject="Verify your JTEAD email address",
            body=(
                f"Welcome to JTEAD, {user.full_name}.\n\n"
                f"Please verify your email address to enable manuscript submission: {verify_link}\n\n"
                "This link expires in 24 hours."
            ),
        )
    except Exception:
        current_app.logger.exception(f"Failed to send verification email to {user.email}")


def submission_rate_limit_key():
    # Rate-limit by account, not IP — this route already requires login, and
    # limiting by IP would unfairly throttle everyone behind the same NAT/
    # campus network as one heavy user (or one abusive account).
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return request.remote_addr or "unknown"


# ---------- Static pages ----------


@main_bp.route("/")
def index():
    return current_app.send_static_file("index.html")


# ---------- Auth API ----------


@main_bp.route("/api/csrf-token")
def csrf_token():
    return jsonify({"csrf_token": generate_csrf()})


@main_bp.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not full_name or not email or not password:
        return jsonify({"error": "Full name, email, and password are all required."}), 400

    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400

    password_error = validate_password_strength(password, email=email, full_name=full_name)
    if password_error:
        return jsonify({"error": password_error}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with that email already exists."}), 409

    user = User(full_name=full_name, email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Someone else's signup for the same email landed between our check
        # above and this commit. The database's unique constraint on email
        # is the real guard here — the query above is just a fast, friendly
        # first check that can't fully close that race on its own.
        db.session.rollback()
        return jsonify({"error": "An account with that email already exists."}), 409

    login_user(user)
    security_logger.info(f"signup success email={email} ip={request.remote_addr}")
    _send_verification_email(user)
    return jsonify({"ok": True, "user": {"full_name": user.full_name, "email": user.email}})


@main_bp.route("/api/login", methods=["POST"])
@limiter.limit("10/minute")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    remember = bool(data.get("remember"))

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        security_logger.warning(f"login failed email={email} ip={request.remote_addr}")
        return jsonify({"error": "Incorrect email or password."}), 401

    login_user(user, remember=remember)
    security_logger.info(f"login success email={email} ip={request.remote_addr}")
    return jsonify({"ok": True, "user": {"full_name": user.full_name, "email": user.email}})


@main_bp.route("/api/logout", methods=["POST"])
def logout():
    logout_user()
    return jsonify({"ok": True})


@main_bp.route("/api/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not signed in."}), 401
    return jsonify(
        {
            "full_name": current_user.full_name,
            "email": current_user.email,
            "is_editor": current_user.is_editor,
            "email_verified": current_user.email_verified,
        }
    )


# ---------- Email verification ----------
#
# Verification isn't required to sign in or browse — only to submit a
# manuscript (see the check in submit_article below). That keeps a slow or
# undelivered email from locking someone out of their own account entirely.


@main_bp.route("/api/verify-email", methods=["POST"])
@limiter.limit("20/hour")
def verify_email():
    data = request.get_json(silent=True) or {}
    token = data.get("token") or ""

    try:
        payload = _email_verify_serializer().loads(token, max_age=EMAIL_VERIFY_MAX_AGE)
    except SignatureExpired:
        return jsonify({"error": "This verification link has expired. Request a new one from My Submissions."}), 400
    except BadSignature:
        return jsonify({"error": "This verification link is invalid."}), 400

    user = db.session.get(User, payload.get("user_id"))
    if not user:
        return jsonify({"error": "This verification link is invalid."}), 400

    if not user.email_verified:
        user.email_verified = True
        db.session.commit()
        security_logger.info(f"email verified email={user.email} ip={request.remote_addr}")

    return jsonify({"ok": True})


@main_bp.route("/api/resend-verification", methods=["POST"])
@login_required
@limiter.limit("5/hour")
def resend_verification():
    if current_user.email_verified:
        return jsonify({"ok": True, "already_verified": True})
    _send_verification_email(current_user)
    return jsonify({"ok": True})


@main_bp.route("/api/change-password", methods=["POST"])
@login_required
@limiter.limit("10/hour")
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    if not check_password_hash(current_user.password_hash, current_password):
        security_logger.warning(f"change-password wrong current password user_id={current_user.id}")
        return jsonify({"error": "Current password is incorrect."}), 401

    password_error = validate_password_strength(
        new_password, email=current_user.email, full_name=current_user.full_name
    )
    if password_error:
        return jsonify({"error": password_error}), 400

    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    security_logger.info(f"password changed email={current_user.email} ip={request.remote_addr}")

    try:
        send_email(
            to=current_user.email,
            subject="Your JTEAD password was changed",
            body=(
                "This is a confirmation that your JTEAD account password was just changed.\n\n"
                "If you didn't make this change, reset your password immediately from the "
                "sign-in page and contact the editorial office."
            ),
        )
    except Exception:
        current_app.logger.exception(f"Failed to send password-change notice to {current_user.email}")

    return jsonify({"ok": True})


# ---------- Password reset ----------
#
# Actual delivery goes through mailer.send_email, which sends a real message
# if SMTP_HOST is configured (see config.py) and otherwise falls back to
# logging the link — so this works in dev without any mail provider set up,
# and starts sending for real the moment SMTP env vars are added.


@main_bp.route("/api/forgot-password", methods=["POST"])
@limiter.limit("5/hour")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    user = User.query.filter_by(email=email).first() if email else None
    if user:
        token = _reset_serializer().dumps({"user_id": user.id, "pw": user.password_hash[-16:]})
        reset_link = f"{request.host_url.rstrip('/')}/reset-password.html?token={token}"
        security_logger.info(f"password reset requested email={email} ip={request.remote_addr}")
        try:
            send_email(
                to=user.email,
                subject="Reset your JTEAD password",
                body=(
                    "We received a request to reset your JTEAD account password.\n\n"
                    f"Reset it here: {reset_link}\n\n"
                    "This link expires in 1 hour. If you didn't request this, you can "
                    "safely ignore this email."
                ),
            )
        except Exception:
            # Delivery failure shouldn't surface to the client — that would
            # both leak whether the account exists and expose SMTP errors.
            # Log it server-side instead so it's visible to an operator.
            current_app.logger.exception(f"Failed to send password reset email to {email}")

    # Always return ok, whether or not the account exists, so this endpoint
    # can't be used to enumerate registered email addresses.
    return jsonify({"ok": True})


@main_bp.route("/api/reset-password", methods=["POST"])
@limiter.limit("10/hour")
def reset_password():
    data = request.get_json(silent=True) or {}
    token = data.get("token") or ""
    new_password = data.get("password") or ""

    try:
        payload = _reset_serializer().loads(token, max_age=PASSWORD_RESET_MAX_AGE)
    except SignatureExpired:
        return jsonify({"error": "This reset link has expired. Please request a new one."}), 400
    except BadSignature:
        return jsonify({"error": "This reset link is invalid."}), 400

    user = db.session.get(User, payload.get("user_id"))
    if not user or user.password_hash[-16:] != payload.get("pw"):
        # Token is well-formed but stale — the password already changed
        # since this link was issued (or the account is gone).
        return jsonify({"error": "This reset link is invalid."}), 400

    password_error = validate_password_strength(new_password, email=user.email, full_name=user.full_name)
    if password_error:
        return jsonify({"error": password_error}), 400

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    security_logger.info(f"password reset completed email={user.email} ip={request.remote_addr}")
    return jsonify({"ok": True})


# ---------- Manuscript submission ----------

FILE_FIELDS = {
    "manuscript": {
        "label": "Anonymized Manuscript File",
        "extensions": {"doc", "docx", "rtf"},
        "max_bytes": 5 * 1024 * 1024,
        "required": True,
    },
    "graphical_abstract": {
        "label": "Graphical Abstract",
        "extensions": {"pdf", "png", "tiff", "tif", "jpeg", "jpg"},
        "max_bytes": 5 * 1024 * 1024,
        "required": True,
    },
    "cover_letter": {
        "label": "Cover Letter",
        "extensions": {"doc", "docx", "rtf"},
        "max_bytes": 5 * 1024 * 1024,
        "required": True,
    },
    "supplementary": {
        "label": "Supplementary Data File",
        "extensions": {"pdf", "doc", "docx", "csv", "txt", "json", "zip", "xlsx", "xls"},
        "max_bytes": 10 * 1024 * 1024,
        "required": False,
    },
}


def file_extension_ok(filename, allowed_extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def file_size_ok(file_storage, max_bytes):
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    return size <= max_bytes


def submission_error(message):
    return redirect(f"/Submit%20portal.html?error={quote(message)}")


@main_bp.route("/submit-article", methods=["POST"])
@login_required
@limiter.limit("15/hour", key_func=submission_rate_limit_key)
def submit_article():
    if not current_user.email_verified:
        return submission_error("Please verify your email address before submitting a manuscript.")

    form = request.form
    files = request.files

    required_text_fields = [
        "track",
        "keywords",
        "articleTitle",
        "abstract",
        "studentName",
        "ca-phone",
        "ca-email",
        "ca-org",
        "ca-city",
        "ca-country",
        "ca-identity",
        "ca-category",
        "coi-status",
    ]
    missing = [f for f in required_text_fields if not (form.get(f) or "").strip()]
    if missing:
        return submission_error(f"Missing required fields: {', '.join(missing)}")

    if form.get("coi-status") == "yes" and not (form.get("coi-details") or "").strip():
        return submission_error("Please provide conflict of interest details.")

    if not all(form.get(f) == "on" for f in ("eth-1", "eth-2", "eth-3")):
        return submission_error("All three declarations must be acknowledged.")

    # Validate every file up front before saving anything.
    saved_paths = {}
    submission_dir_name = uuid.uuid4().hex
    submission_dir = current_app.config["UPLOAD_DIR"] / submission_dir_name

    for field_name, rules in FILE_FIELDS.items():
        file_storage = files.get(field_name)
        has_file = file_storage and file_storage.filename

        if not has_file:
            if rules["required"]:
                return submission_error(f"{rules['label']} is required.")
            continue

        if not file_extension_ok(file_storage.filename, rules["extensions"]):
            return submission_error(f"{rules['label']}: file type not allowed.")

        if not file_size_ok(file_storage, rules["max_bytes"]):
            return submission_error(f"{rules['label']}: file is too large.")

        extension = file_storage.filename.rsplit(".", 1)[1]
        if not file_content_matches_extension(file_storage, extension):
            return submission_error(f"{rules['label']}: file content doesn't match its extension.")

        saved_paths[field_name] = file_storage

    submission_dir.mkdir(parents=True, exist_ok=True)
    relative_paths = {}
    for field_name, file_storage in saved_paths.items():
        filename = secure_filename(file_storage.filename)
        file_storage.save(submission_dir / filename)
        relative_paths[field_name] = f"{submission_dir_name}/{filename}"

    submission = Submission(
        user_id=current_user.id,
        track=form.get("track", "").strip(),
        keywords=form.get("keywords", "").strip(),
        title=form.get("articleTitle", "").strip(),
        abstract=form.get("abstract", "").strip(),
        manuscript_path=relative_paths["manuscript"],
        graphical_abstract_path=relative_paths["graphical_abstract"],
        cover_letter_path=relative_paths["cover_letter"],
        supplementary_path=relative_paths.get("supplementary"),
        supplementary_description=(form.get("supplementary-description") or "").strip() or None,
        corresponding_name=form.get("studentName", "").strip(),
        corresponding_phone=form.get("ca-phone", "").strip(),
        corresponding_email=form.get("ca-email", "").strip(),
        corresponding_whatsapp=(form.get("ca-whatsapp") or "").strip() or None,
        corresponding_org=form.get("ca-org", "").strip(),
        corresponding_dept=(form.get("ca-dept") or "").strip() or None,
        corresponding_city=form.get("ca-city", "").strip(),
        corresponding_state=(form.get("ca-state") or "").strip() or None,
        corresponding_country=form.get("ca-country", "").strip(),
        submission_role=form.get("ca-identity", "").strip(),
        author_category=form.get("ca-category", "").strip(),
        coi_status=form.get("coi-status", "").strip(),
        coi_details=(form.get("coi-details") or "").strip() or None,
        ethics_acknowledged=True,
    )
    db.session.add(submission)
    db.session.flush()

    co_names = form.getlist("coauth_name[]")
    co_emails = form.getlist("coauth_email[]")
    co_orgs = form.getlist("coauth_org[]")
    for name, email, org in zip(co_names, co_emails, co_orgs):
        if name.strip() and email.strip() and org.strip():
            db.session.add(
                CoAuthor(submission_id=submission.id, name=name.strip(), email=email.strip(), org=org.strip())
            )

    db.session.commit()

    security_logger.info(
        f"submission created id={submission.id} user_id={current_user.id} ip={request.remote_addr}"
    )

    try:
        send_email(
            to=submission.corresponding_email,
            subject="JTEAD manuscript received",
            body=(
                f'We\'ve received your manuscript submission, "{submission.title}".\n\n'
                "You can track its review status anytime from My Submissions on the JTEAD site.\n\n"
                "Thank you for submitting to JTEAD."
            ),
        )
    except Exception:
        current_app.logger.exception(f"Failed to send submission confirmation email for submission id={submission.id}")

    return redirect("/Submit%20portal.html?submitted=1")


@main_bp.route("/api/my-submissions")
@login_required
def my_submissions():
    submissions = (
        Submission.query.filter_by(user_id=current_user.id)
        .order_by(Submission.created_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": s.id,
                "title": s.title,
                "track": s.track,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
            }
            for s in submissions
        ]
    )


@main_bp.route("/api/my-submissions/<int:submission_id>")
@login_required
def my_submission_detail(submission_id):
    submission = Submission.query.filter_by(id=submission_id, user_id=current_user.id).first()
    if not submission:
        return jsonify({"error": "Submission not found."}), 404

    return jsonify(
        {
            "id": submission.id,
            "title": submission.title,
            "track": submission.track,
            "keywords": submission.keywords,
            "abstract": submission.abstract,
            "status": submission.status,
            "created_at": submission.created_at.isoformat(),
            "corresponding_name": submission.corresponding_name,
            "corresponding_email": submission.corresponding_email,
            "corresponding_phone": submission.corresponding_phone,
            "corresponding_org": submission.corresponding_org,
            "corresponding_city": submission.corresponding_city,
            "corresponding_country": submission.corresponding_country,
            "coi_status": submission.coi_status,
            "coi_details": submission.coi_details,
            "has_supplementary": bool(submission.supplementary_path),
            "co_authors": [
                {"name": c.name, "email": c.email, "org": c.org} for c in submission.co_authors
            ],
            "can_withdraw": submission.status in WITHDRAWABLE_STATUSES,
        }
    )


@main_bp.route("/api/my-submissions/<int:submission_id>/files/<field>")
@login_required
def my_submission_file(submission_id, field):
    if field not in FILE_FIELD_COLUMNS:
        return jsonify({"error": "Unknown file field."}), 400

    submission = Submission.query.filter_by(id=submission_id, user_id=current_user.id).first()
    if not submission:
        return jsonify({"error": "Submission not found."}), 404

    relative_path = getattr(submission, FILE_FIELD_COLUMNS[field])
    if not relative_path:
        return jsonify({"error": "No file uploaded for this field."}), 404

    return send_from_directory(current_app.config["UPLOAD_DIR"], relative_path, as_attachment=True)


@main_bp.route("/api/my-submissions/<int:submission_id>/withdraw", methods=["POST"])
@login_required
def withdraw_submission(submission_id):
    submission = Submission.query.filter_by(id=submission_id, user_id=current_user.id).first()
    if not submission:
        return jsonify({"error": "Submission not found."}), 404

    if submission.status not in WITHDRAWABLE_STATUSES:
        return jsonify({"error": "This submission can no longer be withdrawn."}), 400

    submission.status = "withdrawn"
    db.session.commit()
    security_logger.info(f"submission withdrawn id={submission_id} user_id={current_user.id}")
    return jsonify({"ok": True})


# ---------- Security headers ----------

# NOTE on script-src/style-src: several pages (notably "Submit portal.html",
# which predates this backend work) rely on inline onclick handlers and
# inline <script>/<style> blocks, so this CSP allows 'unsafe-inline' for
# scripts and styles rather than breaking them. That specifically means this
# CSP does NOT block the class of attribute-injection XSS fixed in
# my-submissions.html — correct output escaping is what actually prevents
# that, not this header. What this CSP does still buy: no script/style/frame/
# object can load from a third-party domain, and the page can't be framed by
# another site. Tightening further to a nonce-based policy would mean
# reworking every inline handler site-wide — a separate, bigger project.
def set_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Only meaningful (and only safe to promise) once this is actually served
    # over HTTPS — sending it over plain HTTP would be a lie the browser
    # can't act on yet, and enabling it prematurely can lock a domain into
    # HTTPS before it's ready.
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def register_cli_commands(app):
    @app.cli.command("make-editor")
    def make_editor():
        """Promote a user to editor by email: flask make-editor"""
        import click

        email = click.prompt("Email address to promote to editor")
        user = User.query.filter_by(email=email.strip().lower()).first()
        if not user:
            click.echo(f"No account found for {email}.")
            return
        user.is_editor = True
        db.session.commit()
        click.echo(f"{user.email} is now an editor.")


def create_app(config_object=Config):
    app = Flask(__name__, static_folder=".", static_url_path="")
    app.config.from_object(config_object)

    app.config["INSTANCE_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"].mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(main_bp)
    app.register_blueprint(editor_bp)

    app.after_request(set_security_headers)

    register_cli_commands(app)

    if app.config.get("TESTING"):
        # Ephemeral in-memory databases don't need version tracking — just
        # build them fresh from the current models every test run. Real
        # databases (dev and prod) go through `flask db upgrade` instead,
        # so that schema changes are actual migrations, not a table that
        # silently stops matching what create_all() would produce.
        with app.app_context():
            db.create_all()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(port=int(os.environ.get("PORT", 3000)), debug=app.config["DEBUG"])
