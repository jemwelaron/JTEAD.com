# JTEAD — Journal of Technology, Engineering, Architecture and Design

Static site + Flask backend for author accounts and manuscript submission.

## Local setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
# then edit .env and set a real SECRET_KEY:
python -c "import secrets; print(secrets.token_hex(32))"

export FLASK_APP="app:create_app()"
flask db upgrade

python app.py
```

The site is then served at `http://localhost:3000` (or whatever `PORT` is
set to in `.env`).

The database and uploaded manuscripts live in `../jtead-instance/` (a
sibling of this directory, outside anything Flask serves publicly) —
`create_app()` creates the directory automatically, but the database
schema itself comes from `flask db upgrade` (Flask-Migrate/Alembic), not
from the app on its own.

## Changing the database schema

After editing a model in `models.py`:

```
export FLASK_APP="app:create_app()"
flask db migrate -m "Describe the change"
# review the generated file under migrations/versions/ before applying
flask db upgrade
```

Commit the generated migration file alongside the model change. Tests don't
need any of this — they build a fresh in-memory database from the current
models on every run (see `tests/conftest.py`), so migrations only matter for
the real dev/production database.

## Running tests

```
pip install -r requirements-dev.txt
pytest
```

Tests never touch `../jtead-instance/` — each test run gets its own
in-memory database and a throwaway temp directory for uploads/logs (see
`tests/conftest.py`).

This also runs `tests/e2e/` — real end-to-end tests that drive an actual
Chrome instance against a real (temporary) running server via Playwright,
covering things `tests/test_app.py`'s API-level tests can't: real file
pickers, real multi-page navigation, real DOM updates. First time only:
```
playwright install chromium
```
To run just the fast API-level suite (skip the browser tests):
```
pytest --ignore=tests/e2e
```

## Promoting editors and reviewers

The first editor has to be promoted via the CLI:

```
FLASK_APP=app:create_app() flask make-editor
```

After that, any editor can promote or demote other accounts as editors or
reviewers from `editor-users.html` (linked from the Editor Dashboard) — no
need to go back to the CLI. `flask make-reviewer` also exists for scripting/
bootstrapping, same pattern as `make-editor`.

## Peer review workflow

Editors assign one or more reviewers to a submission from the Editor
Dashboard's expandable row (search/assign, remove before a review is
submitted). Reviewers see an anonymized view — never the corresponding
author's name, email, or the cover letter, only the manuscript, graphical
abstract, and any supplementary file — from `reviewer-dashboard.html`, and
submit a recommendation plus comments (a public one to the author, an
optional confidential one visible only to editors) via `review-form.html`.
A review is immutable once submitted; if it needs to change, an editor
removes the assignment and creates a fresh one. A reviewer who can't take
an assignment can decline it instead of leaving it silently pending —
editors see the decline and assign someone else.

When an editor sets a submission's status to "Revision Requested", the
author gets a "Submit a Revision" form on their submission detail page to
upload new files against the *same* submission (old files stay on disk,
new ones just replace the DB pointers) — status becomes "Revision
Submitted" and editors are notified, all without losing the existing
review history or reviewer assignments.

## More

- `.env.example` — every environment variable the app reads, with comments.
- `DEPLOYMENT.md` — going from `python app.py` to a real production deploy
  (gunicorn, reverse proxy/HTTPS, email delivery, backups, migrations).
