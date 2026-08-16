"""
Week 14 user accounts: SQLite persistence + password hashing for the
minimal username/password login decision #43 scoped this project to (see
models/user_schema.py's docstring for what's deliberately NOT here --
no profile fields, no OAuth, no "remember me" persistence).

Owns its own `users` table in the same sessions.db file backend/storage/
db.py already uses for the `sessions` table -- a second
`CREATE TABLE IF NOT EXISTS` against the same SQLite file is safe and
idempotent, and keeping each storage module responsible for creating its
own table (rather than a shared schema-setup function) mirrors db.py's own
existing pattern; there was no reason to introduce a second database file
or a cross-module dependency just for this.

Password hashing: PBKDF2-HMAC-SHA256 via the stdlib `hashlib`, not bcrypt/
passlib -- avoids adding a new dependency for a solo-practice-tool login
system with no untrusted external users (decision #43). Stored as
"<salt_hex>$<hash_hex>"; a fresh random salt (secrets.token_bytes) is drawn
per password, so two identical passwords never produce the same stored
value (see test_two_users_with_same_password_get_different_hashes).
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.user_schema import User

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sessions.db"

# Basic sanity bounds (decision #43) -- not aiming for production-grade
# password policy (no complexity rules, no breach-list checks), just
# guarding against empty/degenerate values. frontend/strings.py's
# auth_error_username_too_short/_too_long/_password_too_short copy hardcodes
# these same numbers (3/30/6) for its localized messages -- if these
# constants ever change, update that copy to match.
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 30
MIN_PASSWORD_LENGTH = 6

_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


class UsernameTakenError(Exception):
    """Raised by create_user() when the username is already registered. Carries no message text --
    callers map this to a localized string themselves (see frontend/app.py's auth error handling)."""


class InvalidCredentialsError(Exception):
    """
    Raised by create_user() when username/password fail the basic sanity
    bounds above. `reason` is a stable machine-readable code -- one of
    "username_too_short", "username_too_long", "password_too_short" -- not
    human-facing text, so callers map it to a localized message themselves
    (frontend/strings.py's t()) instead of this backend module hardcoding
    zh/en prose, same reasoning as every other backend module in this
    project staying free of UI copy.
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt if salt is not None else secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison (secrets.compare_digest) against a stored "<salt_hex>$<hash_hex>"
    value -- False (never an exception) on any malformed stored value, so a corrupt row can't crash
    a login attempt."""
    try:
        salt_hex, _ = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    candidate = _hash_password(password, salt=salt)
    return secrets.compare_digest(candidate, stored)


def _get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def _validate_username(username: str) -> str:
    normalized = username.strip()
    if len(normalized) < MIN_USERNAME_LENGTH:
        raise InvalidCredentialsError("username_too_short")
    if len(normalized) > MAX_USERNAME_LENGTH:
        raise InvalidCredentialsError("username_too_long")
    return normalized


def _validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidCredentialsError("password_too_short")


def create_user(username: str, password: str, db_path: Path | str = DEFAULT_DB_PATH) -> User:
    """
    Register a new account.

    Raises InvalidCredentialsError (see its docstring for `reason` codes) on
    a malformed username/password, or UsernameTakenError if the
    (case-sensitive) username is already registered -- checked and inserted
    inside the same connection to avoid a race between the check and the
    insert. Returns the new User on success; password_hash is set, the raw
    password is never stored or returned.
    """
    normalized_username = _validate_username(username)
    _validate_password(password)

    conn = _get_connection(db_path)
    try:
        existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (normalized_username,)).fetchone()
        if existing is not None:
            raise UsernameTakenError(normalized_username)

        user = User(username=normalized_username, password_hash=_hash_password(password))
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user.user_id, user.username, user.password_hash, user.created_at.isoformat()),
        )
        conn.commit()
        return user
    finally:
        conn.close()


def authenticate_user(username: str, password: str, db_path: Path | str = DEFAULT_DB_PATH) -> Optional[User]:
    """
    Verify a login attempt. Returns the User on success, or None on ANY
    failure (unknown username, wrong password, empty input) -- deliberately
    a return value rather than an exception, unlike create_user()'s
    validation errors: a caller building a login form needs to show the
    same generic "wrong username or password" message for every failure
    mode, and distinguishing "unknown username" from "wrong password" in the
    response would let a caller enumerate valid usernames.
    """
    normalized_username = username.strip()
    if not normalized_username or not password:
        return None

    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT user_id, username, password_hash, created_at FROM users WHERE username = ?",
            (normalized_username,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    user_id, stored_username, password_hash, created_at = row
    if not _verify_password(password, password_hash):
        return None

    return User(
        user_id=user_id,
        username=stored_username,
        password_hash=password_hash,
        created_at=datetime.fromisoformat(created_at),
    )
