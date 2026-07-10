import os
import re
import uuid
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, jsonify, redirect, request
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from sqlalchemy.exc import IntegrityError

from config import Config
from file_signatures import file_content_matches_extension
from models import CoAuthor, Submission, User, db
from password_rules import validate_password_strength
from security_log import security_logger

app = Flask(__name__, static_folder=".", static_url_path="")
app.config.from_object(Config)

Config.INSTANCE_DIR.mkdir(exist_ok=True)
Config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

db.init_app(app)
csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address, app=app, default_limits=[], storage_uri=app.config["RATELIMIT_STORAGE_URI"]
)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

login_manager = LoginManager(app)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"error": "Sign in required."}), 401


with app.app_context():
    db.create_all()


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
@app.after_request
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


# ---------- Static pages ----------


@app.route("/")
def index():
    return app.send_static_file("index.html")


# ---------- Auth API ----------


@app.route("/api/csrf-token")
def csrf_token():
    return jsonify({"csrf_token": generate_csrf()})


@app.route("/api/signup", methods=["POST"])
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
    return jsonify({"ok": True, "user": {"full_name": user.full_name, "email": user.email}})


@app.route("/api/login", methods=["POST"])
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


@app.route("/api/logout", methods=["POST"])
def logout():
    logout_user()
    return jsonify({"ok": True})


@app.route("/api/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"error": "Not signed in."}), 401
    return jsonify({"full_name": current_user.full_name, "email": current_user.email})


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


def submission_rate_limit_key():
    # Rate-limit by account, not IP — this route already requires login, and
    # limiting by IP would unfairly throttle everyone behind the same NAT/
    # campus network as one heavy user (or one abusive account).
    if current_user.is_authenticated:
        return f"user:{current_user.id}"
    return get_remote_address()


@app.route("/submit-article", methods=["POST"])
@login_required
@limiter.limit("15/hour", key_func=submission_rate_limit_key)
def submit_article():
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
    submission_dir = Config.UPLOAD_DIR / submission_dir_name

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

    return redirect("/Submit%20portal.html?submitted=1")


@app.route("/api/my-submissions")
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


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 3000)), debug=app.config["DEBUG"])
