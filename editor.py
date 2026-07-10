from functools import wraps

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_login import current_user, login_required

from mailer import send_email
from models import StatusChange, Submission, User, db
from security_log import security_logger
from statuses import EDITOR_SETTABLE_STATUSES, STATUS_LABELS
from submission_files import FILE_FIELD_COLUMNS

editor_bp = Blueprint("editor", __name__, url_prefix="/api/editor")


def editor_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_editor:
            return jsonify({"error": "Editor access required."}), 403
        return view(*args, **kwargs)

    return wrapped


@editor_bp.route("/submissions")
@editor_required
def list_submissions():
    submissions = Submission.query.order_by(Submission.created_at.desc()).all()
    return jsonify(
        [
            {
                "id": s.id,
                "title": s.title,
                "track": s.track,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
                "corresponding_name": s.corresponding_name,
                "corresponding_email": s.corresponding_email,
                "author_email": s.author.email,
                "has_supplementary": bool(s.supplementary_path),
            }
            for s in submissions
        ]
    )


@editor_bp.route("/submissions/<int:submission_id>/files/<field>")
@editor_required
def download_file(submission_id, field):
    if field not in FILE_FIELD_COLUMNS:
        return jsonify({"error": "Unknown file field."}), 400

    submission = db.session.get(Submission, submission_id)
    if not submission:
        return jsonify({"error": "Submission not found."}), 404

    relative_path = getattr(submission, FILE_FIELD_COLUMNS[field])
    if not relative_path:
        return jsonify({"error": "No file uploaded for this field."}), 404

    security_logger.info(
        f"submission file downloaded id={submission_id} field={field} by_user_id={current_user.id}"
    )
    # relative_path is server-generated (uuid dir + secure_filename, set at
    # upload time) and read back from the database, never taken from this
    # request — send_from_directory's own traversal guard is defense in
    # depth here, not the primary protection.
    return send_from_directory(current_app.config["UPLOAD_DIR"], relative_path, as_attachment=True)


@editor_bp.route("/submissions/<int:submission_id>/status", methods=["POST"])
@editor_required
def update_status(submission_id):
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in EDITOR_SETTABLE_STATUSES:
        return jsonify({"error": "Invalid status."}), 400

    submission = db.session.get(Submission, submission_id)
    if not submission:
        return jsonify({"error": "Submission not found."}), 404

    old_status = submission.status
    submission.status = new_status
    db.session.add(
        StatusChange(
            submission_id=submission.id,
            old_status=old_status,
            new_status=new_status,
            changed_by_user_id=current_user.id,
        )
    )
    db.session.commit()
    security_logger.info(
        f"submission status changed id={submission_id} status={new_status} by_user_id={current_user.id}"
    )

    try:
        send_email(
            to=submission.corresponding_email,
            subject=f"Update on your JTEAD submission: {STATUS_LABELS.get(new_status, new_status)}",
            body=(
                f'The status of your manuscript "{submission.title}" has been updated to: '
                f"{STATUS_LABELS.get(new_status, new_status)}.\n\n"
                "You can view details anytime from My Submissions on the JTEAD site."
            ),
        )
    except Exception:
        current_app.logger.exception(f"Failed to send status-change email for submission id={submission_id}")

    return jsonify({"ok": True})


@editor_bp.route("/submissions/<int:submission_id>/history")
@editor_required
def submission_history(submission_id):
    submission = db.session.get(Submission, submission_id)
    if not submission:
        return jsonify({"error": "Submission not found."}), 404

    return jsonify(
        [
            {
                "old_status": h.old_status,
                "new_status": h.new_status,
                "changed_at": h.changed_at.isoformat(),
                "changed_by": h.changed_by.full_name if h.changed_by else None,
            }
            for h in submission.status_changes
        ]
    )


# ---------- Editor management ----------
#
# There's no separate "admin" role — any existing editor can promote or
# demote any other account. That's a deliberate simplification for a small
# team where editors are already trusted; if that stops being true, this is
# the place to add a distinct admin flag.


@editor_bp.route("/users")
@editor_required
def list_users():
    search = (request.args.get("search") or "").strip()
    query = User.query
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(User.email.ilike(like), User.full_name.ilike(like)))

    users = query.order_by(User.full_name).limit(25).all()
    return jsonify(
        [
            {"id": u.id, "full_name": u.full_name, "email": u.email, "is_editor": u.is_editor}
            for u in users
        ]
    )


@editor_bp.route("/users/<int:user_id>/promote", methods=["POST"])
@editor_required
def promote_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    user.is_editor = True
    db.session.commit()
    security_logger.info(f"user promoted to editor id={user_id} by_user_id={current_user.id}")
    return jsonify({"ok": True})


@editor_bp.route("/users/<int:user_id>/demote", methods=["POST"])
@editor_required
def demote_user(user_id):
    if user_id == current_user.id:
        # Otherwise the last editor could lock themselves out with no one
        # left who can promote them back.
        return jsonify({"error": "You can't remove your own editor access."}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    user.is_editor = False
    db.session.commit()
    security_logger.info(f"user demoted from editor id={user_id} by_user_id={current_user.id}")
    return jsonify({"ok": True})
