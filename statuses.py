# Single source of truth for submission status values on the Python side.
# The client-side equivalent is status-labels.js — kept as a second copy
# (not templated from this file) since the site has no build step or
# server-side rendering for its static pages, but every *Python* consumer
# (editor.py, app.py) should reference this instead of re-declaring it.

STATUS_LABELS = {
    "submitted": "Submitted",
    "under-review": "Under Review",
    "revision-requested": "Revision Requested",
    "revision-submitted": "Revision Submitted",
    "accepted": "Accepted",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}

# Statuses an editor can set via POST /api/editor/submissions/<id>/status.
# "withdrawn" and "revision-submitted" are deliberately excluded — both are
# only ever set by the author themselves (POST /api/my-submissions/<id>/
# withdraw and .../revise respectively), never picked from the editor's
# dropdown.
EDITOR_SETTABLE_STATUSES = {"submitted", "under-review", "revision-requested", "accepted", "rejected"}

# Statuses an author can withdraw *from* — once a submission reaches a
# final decision (accepted/rejected) or is already withdrawn, withdrawing
# no longer makes sense.
WITHDRAWABLE_STATUSES = {"submitted", "under-review", "revision-requested", "revision-submitted"}

# The only status a revised-manuscript upload is accepted from — an editor
# has to actually request revisions before the author can act on it.
REVISABLE_STATUS = "revision-requested"

REVIEW_RECOMMENDATION_LABELS = {
    "accept": "Accept",
    "minor-revisions": "Minor Revisions",
    "major-revisions": "Major Revisions",
    "reject": "Reject",
}
VALID_REVIEW_RECOMMENDATIONS = set(REVIEW_RECOMMENDATION_LABELS)
