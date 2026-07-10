# Deploying JTEAD to production

This app is dev-tested with Flask's built-in server (`python app.py`), which
is explicitly unsafe for production (`FLASK_DEBUG=1` and the Werkzeug dev
server both leak internals / aren't hardened for concurrent real traffic).
This is the checklist to go from "works on my machine" to a real deployment.

## 1. Environment

Set these in the production `.env` (or your host's secrets manager — don't
commit `.env`):

- `SECRET_KEY` — a fresh value, not the one used in dev. Generate with:
  `python -c "import secrets; print(secrets.token_hex(32))"`
- `FLASK_DEBUG=0` — must be unset or `0`. Never `1` in production.
- `SESSION_COOKIE_SECURE=1` — only send session/remember cookies over HTTPS.
  Requires the app to actually be served over HTTPS (see §3).
- `RATELIMIT_STORAGE_URI` — the default (`memory://`) only works correctly
  with a single worker process. Any real deployment should run multiple
  gunicorn workers, so point this at a shared backend, e.g.
  `redis://localhost:6379`. Without this, each worker enforces rate limits
  independently, so the real limit becomes (configured limit × worker count).

## 2. Application server

`wsgi.py` exposes `app = create_app()` as the entry point. Run it with
gunicorn (already in `requirements.txt`) instead of `python app.py`:

```
gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app
```

`-w 4` is a starting point (roughly `2 × CPU cores + 1`); tune based on
actual load. Bind to localhost and put a reverse proxy in front (§3) rather
than exposing gunicorn directly to the internet.

For long-running management, run it under a process supervisor (systemd,
supervisord, or your host's equivalent) so it restarts on crash/reboot.
Minimal systemd unit sketch:

```
[Unit]
Description=JTEAD
After=network.target

[Service]
User=jtead
WorkingDirectory=/path/to/jtead-website
EnvironmentFile=/path/to/jtead-website/.env
ExecStart=/path/to/jtead-website/.venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

## 3. Reverse proxy + HTTPS

Put nginx (or Caddy/similar) in front of gunicorn to terminate TLS and
serve as the public entry point. Minimal nginx sketch:

```
server {
    listen 443 ssl;
    server_name jtead.example.edu;

    ssl_certificate     /etc/letsencrypt/live/jtead.example.edu/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/jtead.example.edu/privkey.pem;

    client_max_body_size 32M;  # matches Config.MAX_CONTENT_LENGTH

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Get a certificate via certbot (Let's Encrypt) or your host's managed TLS.
Once this is live, set `SESSION_COOKIE_SECURE=1` — the HSTS header in
`app.py`'s `set_security_headers` already activates automatically once
`request.is_secure` is true (i.e. once requests are actually arriving over
HTTPS, which they will be once nginx terminates TLS and forwards
`X-Forwarded-Proto`; Flask needs `ProxyFix` from `werkzeug.middleware.proxy_fix`
wrapped around the app in `wsgi.py` to trust that header — add it once a
proxy is actually in place).

## 4. Filesystem & data

- `Config.INSTANCE_DIR` (`jtead-instance/`, a sibling of the project
  directory) holds the SQLite database and uploaded manuscripts. Make sure
  it's on persistent storage (not an ephemeral container filesystem) and is
  backed up — there is currently no automated backup.
- SQLite is fine at this scale (a college journal) but has no built-in
  replication. If usage grows enough that concurrent-write contention
  becomes a problem, that's the point to migrate to Postgres — the app
  already goes through SQLAlchemy, so the model code wouldn't need to
  change, just `SQLALCHEMY_DATABASE_URI`.
- **Schema changes go through Flask-Migrate.** `create_app()` no longer
  calls `db.create_all()` against a real database (only against tests'
  throwaway in-memory ones) — the actual schema comes from running
  `flask db upgrade`. Run it once before the very first deploy, and again
  after pulling any change that includes a new file under
  `migrations/versions/`. See the "Changing the database schema" section in
  `README.md` for the day-to-day workflow. This is what makes future model
  changes an `ALTER TABLE` against real data instead of the choice between
  "broken" and "wipe the database" that bit local dev before this was set up.

## 5. Email

Password reset sends real email via `mailer.py` (plain `smtplib`, works with
any standard SMTP relay — Gmail app passwords, an institutional SMTP server,
or the SMTP endpoints SendGrid/Mailgun/etc. all expose). Set these in
production `.env`:

- `SMTP_HOST`, `SMTP_PORT` (default `587`)
- `SMTP_USERNAME`, `SMTP_PASSWORD`
- `SMTP_USE_TLS` (default on)
- `MAIL_FROM` — the From address recipients see

Until `SMTP_HOST` is set, it falls back to logging the reset link instead of
emailing it (via the app logger), which is what dev currently relies on —
so this is safe to leave unset locally, just don't deploy without it.

## 6. First editor account

There's no admin UI for granting editor access. After deploying, promote an
account via the Flask CLI:

```
FLASK_APP=wsgi.py flask make-editor
```

## Pre-launch checklist

- [ ] Fresh `SECRET_KEY`, not reused from dev
- [ ] `flask db upgrade` run against the production database
- [ ] `FLASK_DEBUG=0`
- [ ] `SESSION_COOKIE_SECURE=1`, served over real HTTPS
- [ ] `RATELIMIT_STORAGE_URI` pointed at a shared backend if running >1 worker
- [ ] gunicorn behind a reverse proxy, not exposed directly
- [ ] `jtead-instance/` on persistent, backed-up storage
- [ ] `SMTP_HOST`/`SMTP_USERNAME`/`SMTP_PASSWORD`/`MAIL_FROM` set for real password-reset email delivery
- [ ] At least one editor account promoted
