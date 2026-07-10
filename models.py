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
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    submissions = db.relationship("Submission", backref="author", lazy=True)


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


class CoAuthor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submission.id"), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    org = db.Column(db.String(300), nullable=False)
