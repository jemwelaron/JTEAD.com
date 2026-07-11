// Single source of truth for submission status display labels on the
// client side — my-submissions.html, editor-dashboard.html, and
// submission-detail.html all include this instead of each declaring their
// own copy. Keep in sync with statuses.py (the Python-side equivalent);
// there's no shared build step between the two, so this is a second
// hand-maintained copy by necessity, not an oversight.
const STATUS_LABELS = {
  submitted: "Submitted",
  "under-review": "Under Review",
  accepted: "Accepted",
  rejected: "Rejected",
  "revision-requested": "Revision Requested",
  withdrawn: "Withdrawn",
};

const REVIEW_RECOMMENDATION_LABELS = {
  accept: "Accept",
  "minor-revisions": "Minor Revisions",
  "major-revisions": "Major Revisions",
  reject: "Reject",
};
