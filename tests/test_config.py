import os
import subprocess
import sys
from pathlib import Path

import pytest

import config

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(monkeypatch):
    monkeypatch.delenv("BHANSA_SECRET", raising=False)
    monkeypatch.delenv("BHANSA_DEV", raising=False)
    return monkeypatch


@pytest.mark.parametrize("secret", [None, "", "   ", config.DEV_SECRET])
def test_missing_or_public_secret_is_refused(env, secret):
    if secret is not None:
        env.setenv("BHANSA_SECRET", secret)
    with pytest.raises(RuntimeError, match="BHANSA_SECRET"):
        config.load_secret()


def test_private_secret_is_used(env):
    env.setenv("BHANSA_SECRET", "a-private-value")
    assert config.load_secret() == "a-private-value"


def test_dev_mode_allows_the_default_secret(env):
    env.setenv("BHANSA_DEV", "1")
    assert config.load_secret() == config.DEV_SECRET


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_dev_mode_must_really_be_on(env, value):
    env.setenv("BHANSA_DEV", value)
    with pytest.raises(RuntimeError):
        config.load_secret()


def start_app(tmp_path, code="import main", **settings):
    # Import the real app in a new process; tmp_path keeps its database away from ours
    env = {k: v for k, v in os.environ.items() if not k.startswith(("BHANSA_", "SLICEFLOW_"))
           and k != "DATABASE_URL"}
    env.update(settings, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=60)


def test_app_refuses_to_start_without_secret(tmp_path):
    result = start_app(tmp_path)
    assert result.returncode != 0
    assert "BHANSA_SECRET must be set" in result.stderr
    assert not (tmp_path / "sliceflow.db").exists()      # stopped before touching the database


@pytest.mark.parametrize("settings", [{"BHANSA_DEV": "1"}, {
    "BHANSA_SECRET": "private", "BHANSA_PIN_CASHIER": "4821",
    "BHANSA_PIN_KITCHEN": "5932", "BHANSA_PIN_MANAGER": "6043"}])
def test_app_starts_in_dev_mode_or_with_secret(tmp_path, settings):
    result = start_app(tmp_path, **settings)
    assert result.returncode == 0, result.stderr
