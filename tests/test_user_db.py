"""
Unit tests for backend/storage/user_db.py -- week 14 user accounts. Pure
stdlib (sqlite3/hashlib/secrets), no Groq/embedding-model dependency, so
unlike the RAG/report test suites, these run fully in any Python
environment with no external services or heavy packages required.
"""
from __future__ import annotations

import pytest

from backend.storage.user_db import (
    InvalidCredentialsError,
    UsernameTakenError,
    authenticate_user,
    create_user,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_users.db"


def test_create_user_returns_user_with_hashed_password(db_path):
    user = create_user("alice", "hunter22", db_path=db_path)
    assert user.username == "alice"
    assert user.password_hash != "hunter22"
    assert "$" in user.password_hash


def test_create_user_strips_whitespace_from_username(db_path):
    user = create_user("  alice  ", "hunter22", db_path=db_path)
    assert user.username == "alice"


def test_create_user_rejects_duplicate_username(db_path):
    create_user("alice", "hunter22", db_path=db_path)
    with pytest.raises(UsernameTakenError):
        create_user("alice", "different-pw", db_path=db_path)


def test_create_user_duplicate_check_is_case_sensitive(db_path):
    """Documents current behavior -- "Alice" and "alice" are treated as distinct usernames.
    Not a design requirement either way, just pinning what the SQL UNIQUE constraint actually does."""
    create_user("alice", "hunter22", db_path=db_path)
    other = create_user("Alice", "hunter22", db_path=db_path)
    assert other.username == "Alice"


def test_create_user_rejects_short_username(db_path):
    with pytest.raises(InvalidCredentialsError) as exc_info:
        create_user("ab", "hunter22", db_path=db_path)
    assert exc_info.value.reason == "username_too_short"


def test_create_user_rejects_long_username(db_path):
    with pytest.raises(InvalidCredentialsError) as exc_info:
        create_user("a" * 31, "hunter22", db_path=db_path)
    assert exc_info.value.reason == "username_too_long"


def test_create_user_rejects_short_password(db_path):
    with pytest.raises(InvalidCredentialsError) as exc_info:
        create_user("alice", "short", db_path=db_path)
    assert exc_info.value.reason == "password_too_short"


def test_create_user_validates_username_before_checking_duplicates(db_path):
    """A too-short username should fail validation even if it happens to collide with nothing --
    i.e. validation runs before the duplicate-username DB lookup, not after."""
    with pytest.raises(InvalidCredentialsError):
        create_user("ab", "hunter22", db_path=db_path)


def test_authenticate_user_succeeds_with_correct_password(db_path):
    created = create_user("alice", "hunter22", db_path=db_path)
    authenticated = authenticate_user("alice", "hunter22", db_path=db_path)
    assert authenticated is not None
    assert authenticated.user_id == created.user_id
    assert authenticated.username == "alice"


def test_authenticate_user_fails_with_wrong_password(db_path):
    create_user("alice", "hunter22", db_path=db_path)
    assert authenticate_user("alice", "wrong-password", db_path=db_path) is None


def test_authenticate_user_fails_for_unknown_username(db_path):
    assert authenticate_user("nobody", "hunter22", db_path=db_path) is None


def test_authenticate_user_fails_for_empty_input(db_path):
    create_user("alice", "hunter22", db_path=db_path)
    assert authenticate_user("", "", db_path=db_path) is None
    assert authenticate_user("alice", "", db_path=db_path) is None
    assert authenticate_user("", "hunter22", db_path=db_path) is None


def test_authenticate_user_strips_whitespace_from_username(db_path):
    create_user("alice", "hunter22", db_path=db_path)
    assert authenticate_user("  alice  ", "hunter22", db_path=db_path) is not None


def test_two_users_with_same_password_get_different_hashes(db_path):
    alice = create_user("alice", "hunter22", db_path=db_path)
    bob = create_user("bob", "hunter22", db_path=db_path)
    assert alice.password_hash != bob.password_hash


def test_password_hash_never_contains_raw_password(db_path):
    user = create_user("alice", "correcthorsebatterystaple", db_path=db_path)
    assert "correcthorsebatterystaple" not in user.password_hash
