from functools import wraps

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_login import current_user, login_required

from mailer import send_email
from models import Submission, db
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

    submission.status = new_status
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
