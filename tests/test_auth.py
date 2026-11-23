from datetime import datetime, timedelta, timezone

import pytest

import auth
from models import User


def add_user(session, name="Sita", role="CASHIER", pin="1111"):
    user = User(name=name, role=role, pin_hash=auth.hash_pin(pin, rounds=4))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_pin_is_stored_as_a_hash_not_plain_text():
    pin_hash = auth.hash_pin("1111", rounds=4)
    assert "1111" not in pin_hash
    assert auth.check_pin("1111", pin_hash)
    assert not auth.check_pin("1112", pin_hash)


@pytest.mark.parametrize("pin, ok", [("1234", True), ("0000", True), ("123", False),
                                     ("12345", False), ("12a4", False), ("", False)])
def test_pin_format(pin, ok):
    assert auth.is_valid_pin_format(pin) == ok


def test_correct_pin_logs_in(session):
    user = add_user(session)
    assert auth.attempt_login(session, user.id, "1111").id == user.id


def test_wrong_pin_counts_tries(session):
    user = add_user(session)
    with pytest.raises(auth.LoginError, match="4 tries left"):
        auth.attempt_login(session, user.id, "0000")
    assert user.failed_attempts == 1


def test_five_wrong_pins_lock_the_account_for_one_minute(session):
    # FR-01
    user = add_user(session)
    now = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)
    for _ in range(5):
        with pytest.raises(auth.LoginError):
            auth.attempt_login(session, user.id, "0000", now=now)
    with pytest.raises(auth.LoginError, match="Try again"):
        auth.attempt_login(session, user.id, "1111", now=now + timedelta(seconds=30))
    later = now + timedelta(seconds=61)
    assert auth.attempt_login(session, user.id, "1111", now=later).id == user.id


def test_success_resets_the_counter(session):
    user = add_user(session)
    with pytest.raises(auth.LoginError):
        auth.attempt_login(session, user.id, "0000")
    auth.attempt_login(session, user.id, "1111")
    assert user.failed_attempts == 0


def test_unknown_or_inactive_user_is_rejected(session):
    user = add_user(session)
    user.is_active = False
    session.add(user)
    session.commit()
    with pytest.raises(auth.LoginError):
        auth.attempt_login(session, user.id, "1111")
    with pytest.raises(auth.LoginError):
        auth.attempt_login(session, 999, "1111")