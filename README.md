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

python app.py
```

The site is then served at `http://localhost:3000` (or whatever `PORT` is
set to in `.env`).

The database and uploaded manuscripts live in `../jtead-instance/` (a
sibling of this directory, outside anything Flask serves publicly) —
`create_app()` creates it automatically on first run.

## Running tests

```
pip install -r requirements-dev.txt
pytest
```

Tests never touch `../jtead-instance/` — each test run gets its own
in-memory database and a throwaway temp directory for uploads/logs (see
`tests/conftest.py`).

## Promoting an editor

There's no admin UI yet. After an account signs up:

```
FLASK_APP=app:create_app() flask make-editor
```

## More

- `.env.example` — every environment variable the app reads, with comments.
- `DEPLOYMENT.md` — going from `python app.py` to a real production deploy
  (gunicorn, reverse proxy/HTTPS, email delivery, backups, migrations).
