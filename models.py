from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_editor = db.Column(db.Boolean, nullable=False, default=False)
    is_reviewer = db.Column(db.Boolean, nullable=False, default=False)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    # Public Editorial Board listing (editorial-board.html). Set when an
    # editor promotes this account via editor-users.html; cleared (category
    # only) on demotion so a removed editor drops off the public page
    # without losing the rest of the profile if they're re-promoted later.
    board_category = db.Column(db.String(20), nullable=True)  # "editor_in_chief" | "associate_editor"
    board_display_name = db.Column(db.String(200), nullable=True)
    board_roles = db.Column(db.String(500), nullable=True)
    board_affiliation = db.Column(db.String(300), nullable=True)
    board_photo = db.Column(db.String(300), nullable=True)
    # Bumped on every password change/reset. Embedded in the session cookie
    # (see get_id() below) so that changing your password invalidates any
    # other already-authenticated session/remember-me cookie — e.g. one an
    # attacker holds on a shared computer, or a leaked cookie — instead of
    # only affecting future logins.
    session_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    submissions = db.relationship("Submission", backref="author", lazy=True)

    def get_id(self):
        return f"{self.id}.{self.session_version}"


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)

    # Primary details
    track = db.Column(db.String(100), nullable=False)
    keywords = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    abstract = db.Column(db.Text, nullable=False)

    # Uploaded files (paths relative to the instance uploads directory)
    manuscript_path = db.Column(db.String(500), nullable=False)
    graphical_abstract_path = db.Column(db.String(500), nullable=False)
    cover_letter_path = db.Column(db.String(500), nullable=False)
    supplementary_path = db.Column(db.String(500), nullable=True)
    supplementary_description = db.Column(db.String(500), nullable=True)

    # Corresponding author details
    corresponding_name = db.Column(db.String(200), nullable=False)
    corresponding_phone = db.Column(db.String(50), nullable=False)
    corresponding_email = db.Column(db.String(255), nullable=False)
    corresponding_whatsapp = db.Column(db.String(50), nullable=True)
    corresponding_org = db.Column(db.String(300), nullable=False)
    corresponding_dept = db.Column(db.String(200), nullable=True)
    corresponding_city = db.Column(db.String(150), nullable=False)
    corresponding_state = db.Column(db.String(150), nullable=True)
    corresponding_country = db.Column(db.String(10), nullable=False)
    submission_role = db.Column(db.String(50), nullable=False)
    author_category = db.Column(db.String(50), nullable=False)

    # Disclosures
    coi_status = db.Column(db.String(10), nullable=False)
    coi_details = db.Column(db.Text, nullable=True)
    ethics_acknowledged = db.Column(db.Boolean, nullable=False, default=False)

    status = db.Column(db.String(50), nullable=False, default="submitted")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    co_authors = db.relationship(
        "CoAuthor", backref="submission", lazy=True, cascade="all, delete-orphan"
    )
    status_changes = db.relationship(
        "StatusChange",
        backref="submission",
        lazy=True,
        order_by="StatusChange.changed_at",
        cascade="all, delete-orphan",
    )
    review_assignments = db.relationship(
        "ReviewAssignment",
        backref="submission",
        lazy=True,
        order_by="ReviewAssignment.assigned_at",
        cascade="all, delete-orphan",
    )


class CoAuthor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    org = db.Column(db.String(300), nullable=False)


class StatusChange(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), nullable=False, index=True)
    old_status = db.Column(db.String(50), nullable=True)  # null for the initial "submitted" entry
    new_status = db.Column(db.String(50), nullable=False)
    # Nullable so history survives even if the account that made the change
    # is later deleted (not currently possible via the app, but the schema
    # shouldn't assume it never will be).
    changed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    changed_by = db.relationship("User")
    changed_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ReviewAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    # Null until the reviewer submits — a review, once submitted, is
    # immutable (see reviewer.py): if it needs to change, an editor removes
    # the assignment and creates a fresh one, the same way a withdrawn
    # submission isn't un-deleted, it's a new event.
    recommendation = db.Column(db.String(30), nullable=True)
    comments_to_author = db.Column(db.Text, nullable=True)
    comments_to_editor = db.Column(db.Text, nullable=True)  # never shown to the author
    submitted_at = db.Column(db.DateTime, nullable=True)

    # A reviewer who can't take the assignment declines instead of just
    # never responding — lets the editor see that explicitly and reassign,
    # rather than an assignment silently sitting at "pending" forever.
    declined_at = db.Column(db.DateTime, nullable=True)

    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_user_id])

    __table_args__ = (
        db.UniqueConstraint("submission_id", "reviewer_id", name="uq_review_assignment_submission_reviewer"),
    )
