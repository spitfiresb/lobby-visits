"""Signup, login and sessions.

Sessions are a random token stored in a Python dict (token -> email) and sent
to the browser as an HttpOnly cookie. They're lost when the server restarts,
which is fine for a prototype.
"""

import secrets

from werkzeug.security import check_password_hash, generate_password_hash

import db

MIN_PASSWORD_LENGTH = 8

# What a person not on the allowlist is told. Friendly on purpose: a colleague
# who mistyped their email learns what to fix, which matters more than hiding
# from a stranger that an allowlist exists.
NOT_ALLOWED_MESSAGE = (
    "This email isn't on the list of people who can use The Front Desk. "
    "Check it for typos, or ask Brightline's workplace team for access."
)

sessions = {}  # token -> email


class AuthError(Exception):
    """A signup or login problem to show the person, with the HTTP status."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def signup(email, password):
    """Create an account if the email is on the allowlist. Returns the user."""
    email = db.normalize_email(email)
    if not email or not password:
        raise AuthError(400, "Enter your work email and a password.")

    user = db.find_allowed_user(email)
    if user is None:
        raise AuthError(403, NOT_ALLOWED_MESSAGE)
    if db.get_account(email):
        raise AuthError(409, "You already have an account. Sign in instead.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(400, f"Choose a password of at least {MIN_PASSWORD_LENGTH} characters.")

    db.create_account(email, generate_password_hash(password))
    return user


def login(email, password):
    """Check the email and password and start a session. Returns the token."""
    account = db.get_account(email)
    # Same message whether the email or the password is wrong, so the login
    # form can't be used to find out who has an account.
    if account is None or not check_password_hash(account["password_hash"], password or ""):
        raise AuthError(401, "That email and password don't match. Check both and try again.")

    token = secrets.token_urlsafe(32)
    sessions[token] = account["email"]
    return token


def logout(token):
    sessions.pop(token, None)


def user_for_token(token):
    """The signed-in user (email, name, role) for a session token, or None.
    The role comes from the allowlist on every request, so removing someone
    from the list takes effect immediately."""
    email = sessions.get(token)
    if email is None:
        return None
    return db.find_allowed_user(email)
