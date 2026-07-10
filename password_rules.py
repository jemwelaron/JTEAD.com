import re

MIN_LENGTH = 10

# A short blocklist of the most commonly breached/guessed passwords. Not
# exhaustive — this catches the obviously weak ones without needing an
# external breach-check API or dependency.
COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456", "12345678", "123456789",
    "1234567890", "12345", "qwerty", "qwerty123", "letmein", "welcome",
    "welcome1", "admin", "admin123", "iloveyou", "monkey", "dragon",
    "sunshine", "princess", "football", "baseball", "shadow", "master",
    "superman", "trustno1", "abc123", "abcd1234", "1q2w3e4r", "1qaz2wsx",
    "starwars", "whatever", "freedom", "letmein123", "passw0rd", "p@ssword",
    "p@ssw0rd", "changeme", "temppass", "temppassword", "student", "student123",
    "author123", "jtead123", "philippines", "iloilo123", "test1234", "testing123",
}


def validate_password_strength(password, email="", full_name=""):
    """Returns an error message string if the password is too weak, else None."""
    if len(password) < MIN_LENGTH:
        return f"Password must be at least {MIN_LENGTH} characters."

    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return "Password must contain at least one letter and one number."

    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return "That password is too common. Please choose a different one."

    email_local = email.split("@", 1)[0].lower() if email else ""
    if email_local and email_local in lowered:
        return "Password must not contain your email address."
    if full_name:
        name_parts = [p.lower() for p in full_name.split() if len(p) >= 4]
        if any(part in lowered for part in name_parts):
            return "Password must not contain your name."

    return None
