# Single source of truth for submission status values on the Python side.
# The client-side equivalent is status-labels.js — kept as a second copy
# (not templated from this file) since the site has no build step or
# server-side rendering for its static pages, but every *Python* consumer
# (editor.py, app.py) should reference this instead of re-declaring it.

STATUS_LABELS = {
    "submitted": "Submitted",
    "under-review": "Under Review",
    "revision-requested": "Revision Requested",
    "accepted": "Accepted",
    "rejected": "Rejected",
    "withdrawn": "Withdrawn",
}

# Statuses an editor can set via POST /api/editor/submissions/<id>/status.
# "withdrawn" is deliberately excluded — it's only ever set by the author
# themselves, via POST /api/my-submissions/<id>/withdraw.
EDITOR_SETTABLE_STATUSES = {"submitted", "under-review", "revision-requested", "accepted", "rejected"}

# Statuses an author can withdraw *from* — once a submission reaches a
# final decision (accepted/rejected) or is already withdrawn, withdrawing
# no longer makes sense.
WITHDRAWABLE_STATUSES = {"submitted", "under-review", "revision-requested"}
