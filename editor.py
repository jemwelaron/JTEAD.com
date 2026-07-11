import csv
import io
from functools import wraps

from flask import Blueprint, Response, current_app, jsonify, request, send_from_directory
from flask_login import current_user, login_required

from mailer import send_email
from models import ReviewAssignment, StatusChange, Submission, User, db
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
                "reviewers_assigned": len(s.review_assignments),
                "reviews_submitted": sum(1 for r in s.review_assignments if r.submitted_at),
            }
            for s in submissions
        ]
    )


@editor_bp.route("/submissions/export")
@editor_required
def export_submissions():
    submissions = Submission.query.order_by(Submission.created_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "ID", "Title", "Track", "Status", "Submitted",
            "Corresponding Name", "Corresponding Email", "Author Account Email",
            "Reviewers Assigned", "Reviews Submitted",
        ]
    )
    for s in submissions:
        writer.writerow(
            [
                s.id,
                s.title,
                s.track,
                STATUS_LABELS.get(s.status, s.status),
                s.created_at.isoformat(),
                s.corresponding_name,
                s.corresponding_email,
                s.author.email,
                len(s.review_assignments),
                sum(1 for r in s.review_assignments if r.submitted_at),
            ]
        )

    security_logger.info(f"submissions exported by_user_id={current_user.id}")
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=jtead-submissions.csv"},
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
            {
                "id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "is_editor": u.is_editor,
                "is_reviewer": u.is_reviewer,
            }
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


@editor_bp.route("/users/<int:user_id>/promote-reviewer", methods=["POST"])
@editor_required
def promote_reviewer(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    user.is_reviewer = True
    db.session.commit()
    security_logger.info(f"user promoted to reviewer id={user_id} by_user_id={current_user.id}")
    return jsonify({"ok": True})


@editor_bp.route("/users/<int:user_id>/demote-reviewer", methods=["POST"])
@editor_required
def demote_reviewer(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    user.is_reviewer = False
    db.session.commit()
    security_logger.info(f"user demoted from reviewer id={user_id} by_user_id={current_user.id}")
    return jsonify({"ok": True})


# ---------- Review assignment ----------


@editor_bp.route("/reviewers")
@editor_required
def list_reviewers():
    reviewers = User.query.filter_by(is_reviewer=True).order_by(User.full_name).all()
    return jsonify([{"id": r.id, "full_name": r.full_name, "email": r.email} for r in reviewers])


@editor_bp.route("/submissions/<int:submission_id>/reviews")
@editor_required
def list_reviews(submission_id):
    submission = db.session.get(Submission, submission_id)
    if not submission:
        return jsonify({"error": "Submission not found."}), 404

    return jsonify(
        [
            {
                "id": r.id,
                "reviewer_name": r.reviewer.full_name,
                "reviewer_email": r.reviewer.email,
                "assigned_at": r.assigned_at.isoformat(),
                "recommendation": r.recommendation,
                "comments_to_author": r.comments_to_author,
                "comments_to_editor": r.comments_to_editor,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
                "declined_at": r.declined_at.isoformat() if r.declined_at else None,
            }
            for r in submission.review_assignments
        ]
    )


@editor_bp.route("/submissions/<int:submission_id>/reviewers", methods=["POST"])
@editor_required
def assign_reviewer(submission_id):
    submission = db.session.get(Submission, submission_id)
    if not submission:
        return jsonify({"error": "Submission not found."}), 404

    data = request.get_json(silent=True) or {}
    reviewer_id = data.get("reviewer_id")
    reviewer = db.session.get(User, reviewer_id) if reviewer_id else None
    if not reviewer or not reviewer.is_reviewer:
        return jsonify({"error": "Not a valid reviewer."}), 400

    if ReviewAssignment.query.filter_by(submission_id=submission_id, reviewer_id=reviewer_id).first():
        return jsonify({"error": "This reviewer is already assigned to this submission."}), 409

    assignment = ReviewAssignment(
        submission_id=submission_id, reviewer_id=reviewer_id, assigned_by_user_id=current_user.id
    )
    db.session.add(assignment)
    db.session.commit()
    security_logger.info(
        f"reviewer assigned submission_id={submission_id} reviewer_id={reviewer_id} by_user_id={current_user.id}"
    )

    try:
        send_email(
            to=reviewer.email,
            subject="JTEAD: you've been asked to review a manuscript",
            body=(
                f"You've been assigned to review a manuscript submitted to JTEAD "
                f'(track: {submission.track}).\n\n'
                "Sign in and visit your Reviewer Dashboard to view the anonymized "
                "manuscript and submit your recommendation."
            ),
        )
    except Exception:
        current_app.logger.exception(f"Failed to send review-assignment email to {reviewer.email}")

    return jsonify({"ok": True, "id": assignment.id})


@editor_bp.route("/submissions/<int:submission_id>/reviewers/<int:assignment_id>", methods=["DELETE"])
@editor_required
def unassign_reviewer(submission_id, assignment_id):
    assignment = ReviewAssignment.query.filter_by(id=assignment_id, submission_id=submission_id).first()
    if not assignment:
        return jsonify({"error": "Assignment not found."}), 404

    if assignment.submitted_at:
        return jsonify({"error": "This review has already been submitted and can't be removed."}), 400

    db.session.delete(assignment)
    db.session.commit()
    security_logger.info(
        f"reviewer unassigned submission_id={submission_id} assignment_id={assignment_id} by_user_id={current_user.id}"
    )
    return jsonify({"ok": True})
