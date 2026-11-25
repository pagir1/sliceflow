import os

DEV_SECRET = "dev-secret-change-me"      # public (it is in the code), so only for development


def setting(name: str, default: str = "") -> str:
    """Read BHANSA_<name>, or the old SLICEFLOW_<name> if the new one is missing or blank."""
    for prefix in ("BHANSA_", "SLICEFLOW_"):
        value = os.environ.get(prefix + name, "").strip()
        if value:
            return value
    return default


def is_dev_mode() -> bool:
    return setting("DEV").lower() in {"1", "true", "yes", "on"}


def load_secret() -> str:
    """The key that signs sessions and tracker links. Refuse to run without a private one."""
    secret = setting("SECRET")
    if is_dev_mode():
        return secret or DEV_SECRET
    if not secret or secret == DEV_SECRET:
        raise RuntimeError(
            "BHANSA_SECRET must be set to a private random value. "
            "For local development only, set BHANSA_DEV=1 instead.")
    return secret


SECRET = load_secret()
