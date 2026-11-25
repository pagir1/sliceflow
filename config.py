import os

DEV_SECRET = "dev-secret-change-me"      # public (it is in the code), so only for development


def is_dev_mode() -> bool:
    return os.environ.get("SLICEFLOW_DEV", "").strip().lower() in {"1", "true", "yes", "on"}


def load_secret() -> str:
    """The key that signs sessions and tracker links. Refuse to run without a private one."""
    secret = os.environ.get("SLICEFLOW_SECRET", "").strip()
    if is_dev_mode():
        return secret or DEV_SECRET
    if not secret or secret == DEV_SECRET:
        raise RuntimeError(
            "SLICEFLOW_SECRET must be set to a private random value. "
            "For local development only, set SLICEFLOW_DEV=1 instead.")
    return secret


SECRET = load_secret()
