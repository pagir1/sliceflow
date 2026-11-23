from datetime import datetime, timedelta, timezone

import bcrypt
from sqlmodel import Session, select

from models import User

MAX_ATTEMPTS = 5        # FR-01: 5 wrong PINs in a row ...
LOCK_SECONDS = 60       # ... locks the account for 1 minute

HOME_PAGE = {"CASHIER": "/", "KITCHEN": "/kitchen", "MANAGER": "/"}


class LoginError(Exception):
    pass


def hash_pin(pin: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=rounds)).decode()


def check_pin(pin: str, pin_hash: str) -> bool:
    return bcrypt.checkpw(pin.encode(), pin_hash.encode())


def is_valid_pin_format(pin: str) -> bool:
    return len(pin) == 4 and pin.isdigit()


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def active_staff(session: Session) -> list[User]:
    return session.exec(select(User).where(User.is_active).order_by(User.id)).all()


def attempt_login(session: Session, user_id: int, pin: str, now: datetime | None = None) -> User:
    now = now or datetime.now(timezone.utc)
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise LoginError("Choose your name first")

    if user.locked_until and _as_utc(user.locked_until) > now:
        seconds = int((_as_utc(user.locked_until) - now).total_seconds()) + 1
        raise LoginError(f"Too many wrong PINs. Try again in {seconds} seconds.")

    if not is_valid_pin_format(pin) or not check_pin(pin, user.pin_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= MAX_ATTEMPTS:
            user.failed_attempts = 0
            user.locked_until = now + timedelta(seconds=LOCK_SECONDS)
            session.add(user)
            session.commit()
            raise LoginError("Too many wrong PINs. Locked for 1 minute.")
        session.add(user)
        session.commit()
        left = MAX_ATTEMPTS - user.failed_attempts
        raise LoginError(f"Wrong PIN. {left} tries left.")

    user.failed_attempts = 0
    user.locked_until = None
    session.add(user)
    session.commit()
    return user