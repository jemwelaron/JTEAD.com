from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_login import current_user, login_required

from mailer import send_email
from models import ReviewAssignment, User, db
from security_log import security_logger
from statuses import VALID_REVIEW_RECOMMENDATIONS

reviewer_bp = Blueprint("reviewer", __name__, url_prefix="/api/reviewer")

# Blind review: reviewers only ever see the manuscript itself, the graphical
# abstract, and any supplementary data file — never the cover letter (which
# typically addresses the editor by name and often identifies the authors)
# and never any corresponding-author/co-author field. This mirrors the
# "Anonymized Manuscript File" naming the submission form already uses.
REVIEWER_VISIBLE_FILE_FIELDS = {
    "manuscript": "manuscript_path",
    "graphical_abstract": "graphical_abstract_path",
    "supplementary": "supplementary_path",
}


def reviewer_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_reviewer:
            return jsonify({"error": "Reviewer access required."}), 403
        return view(*args, **kwargs)

    return wrapped


def _get_own_assignment(assignment_id):
    """Ownership-scoped lookup — a reviewer only ever sees their own
    assignments, never another reviewer's (or an unassigned submission)."""
    return ReviewAssignment.query.filter_by(id=assignment_id, reviewer_id=current_user.id).first()


@reviewer_bp.route("/assignments")
@reviewer_required
def list_assignments():
    assignments = (
        ReviewAssignment.query.filter_by(reviewer_id=current_user.id)
        .order_by(ReviewAssignment.assigned_at.desc())
        .all()
    )
    return jsonify(
        [
            {
                "id": a.id,
                "submission_id": a.submission_id,
                "title": a.submission.title,
                "track": a.submission.track,
                "assigned_at": a.assigned_at.isoformat(),
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
                "declined_at": a.declined_at.isoformat() if a.declined_at else None,
                "recommendation": a.recommendation,
            }
            for a in assignments
        ]
    )


@reviewer_bp.route("/assignments/<int:assignment_id>")
@reviewer_required
def assignment_detail(assignment_id):
    assignment = _get_own_assignment(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found."}), 404

    submission = assignment.submission
    return jsonify(
        {
            "id": assignment.id,
            "submission_id": submission.id,
            "title": submission.title,
            "track": submission.track,
            "keywords": submission.keywords,
            "abstract": submission.abstract,
            "has_supplementary": bool(submission.supplementary_path),
            "recommendation": assignment.recommendation,
            "comments_to_author": assignment.comments_to_author,
            "comments_to_editor": assignment.comments_to_editor,
            "submitted_at": assignment.submitted_at.isoformat() if assignment.submitted_at else None,
            "declined_at": assignment.declined_at.isoformat() if assignment.declined_at else None,
        }
    )


@reviewer_bp.route("/assignments/<int:assignment_id>/files/<field>")
@reviewer_required
def download_file(assignment_id, field):
    assignment = _get_own_assignment(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found."}), 404

    if field not in REVIEWER_VISIBLE_FILE_FIELDS:
        return jsonify({"error": "Unknown file field."}), 400

    relative_path = getattr(assignment.submission, REVIEWER_VISIBLE_FILE_FIELDS[field])
    if not relative_path:
        return jsonify({"error": "No file uploaded for this field."}), 404

    security_logger.info(
        f"review file downloaded assignment_id={assignment_id} field={field} by_user_id={current_user.id}"
    )
    return send_from_directory(current_app.config["UPLOAD_DIR"], relative_path, as_attachment=True)


@reviewer_bp.route("/assignments/<int:assignment_id>/submit", methods=["POST"])
@reviewer_required
def submit_review(assignment_id):
    assignment = _get_own_assignment(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found."}), 404

    if assignment.submitted_at:
        return jsonify({"error": "This review has already been submitted."}), 400
    if assignment.declined_at:
        return jsonify({"error": "You've already declined this assignment."}), 400

    data = request.get_json(silent=True) or {}
    recommendation = data.get("recommendation")
    comments_to_author = (data.get("comments_to_author") or "").strip()
    comments_to_editor = (data.get("comments_to_editor") or "").strip()

    if recommendation not in VALID_REVIEW_RECOMMENDATIONS:
        return jsonify({"error": "Please select a valid recommendation."}), 400
    if not comments_to_author:
        return jsonify({"error": "Please provide comments for the author."}), 400

    assignment.recommendation = recommendation
    assignment.comments_to_author = comments_to_author
    assignment.comments_to_editor = comments_to_editor or None
    assignment.submitted_at = datetime.now(timezone.utc)
    db.session.commit()
    security_logger.info(
        f"review submitted assignment_id={assignment_id} submission_id={assignment.submission_id} "
        f"by_user_id={current_user.id}"
    )

    editors = User.query.filter_by(is_editor=True).all()
    for editor in editors:
        try:
            send_email(
                to=editor.email,
                subject=f"JTEAD: a review was submitted for \"{assignment.submission.title}\"",
                body=(
                    f"{current_user.full_name} submitted a review for \"{assignment.submission.title}\" "
                    f"with recommendation: {recommendation}.\n\n"
                    "View it from the Editor Dashboard."
                ),
            )
        except Exception:
            current_app.logger.exception(f"Failed to send review-submitted notice to {editor.email}")

    return jsonify({"ok": True})


@reviewer_bp.route("/assignments/<int:assignment_id>/decline", methods=["POST"])
@reviewer_required
def decline_review(assignment_id):
    assignment = _get_own_assignment(assignment_id)
    if not assignment:
        return jsonify({"error": "Assignment not found."}), 404

    if assignment.submitted_at:
        return jsonify({"error": "This review has already been submitted."}), 400
    if assignment.declined_at:
        return jsonify({"error": "You've already declined this assignment."}), 400

    assignment.declined_at = datetime.now(timezone.utc)
    db.session.commit()
    security_logger.info(
        f"review declined assignment_id={assignment_id} submission_id={assignment.submission_id} "
        f"by_user_id={current_user.id}"
    )

    editors = User.query.filter_by(is_editor=True).all()
    for editor in editors:
        try:
            send_email(
                to=editor.email,
                subject=f'JTEAD: {current_user.full_name} declined a review for "{assignment.submission.title}"',
                body=(
                    f'{current_user.full_name} is unable to review "{assignment.submission.title}" and has '
                    "declined the assignment. Assign a different reviewer from the Editor Dashboard."
                ),
            )
        except Exception:
            current_app.logger.exception(f"Failed to send review-declined notice to {editor.email}")

    return jsonify({"ok": True})
