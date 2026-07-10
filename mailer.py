import smtplib
from email.message import EmailMessage

from flask import current_app


def send_email(to, subject, body):
    """Sends a real email if SMTP is configured; otherwise falls back to
    logging the message so nothing is silently lost in dev/before a mail
    provider is set up. Any SMTP standard relay works here (Gmail app
    passwords, an institutional SMTP server, SendGrid/Mailgun's SMTP
    endpoints, etc.) — set SMTP_HOST/PORT/USERNAME/PASSWORD/MAIL_FROM in the
    environment to turn it on."""
    host = current_app.config.get("SMTP_HOST")
    if not host:
        current_app.logger.info(f"[email not sent — SMTP not configured] to={to} subject={subject!r}\n{body}")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = current_app.config.get("MAIL_FROM") or current_app.config.get("SMTP_USERNAME")
    message["To"] = to
    message.set_content(body)

    port = current_app.config.get("SMTP_PORT", 587)
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")
    use_tls = current_app.config.get("SMTP_USE_TLS", True)

    with smtplib.SMTP(host, port, timeout=10) as server:
        if use_tls:
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(message)
    return True
