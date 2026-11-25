import pytest

import config
import tracking
from models import Order
from test_config import start_app

OLD_SETTINGS = {"SLICEFLOW_SECRET": "private", "SLICEFLOW_PIN_CASHIER": "4821",
                "SLICEFLOW_PIN_KITCHEN": "5932", "SLICEFLOW_PIN_MANAGER": "6043"}


# ---------------- Old and new setting names ----------------

@pytest.mark.parametrize("new, old, expected", [
    ("new", None, "new"),
    (None, "old", "old"),
    ("new", "old", "new"),             # the new name wins
    ("  ", "old", "old"),              # blank counts as missing
    (None, None, "default"),
])
def test_setting_accepts_both_names(monkeypatch, new, old, expected):
    for name, value in [("BHANSA_X", new), ("SLICEFLOW_X", old)]:
        monkeypatch.delenv(name, raising=False)
        if value is not None:
            monkeypatch.setenv(name, value)
    assert config.setting("X", "default") == expected


def test_new_dev_setting_can_turn_the_old_one_off(monkeypatch):
    monkeypatch.setenv("SLICEFLOW_DEV", "1")
    monkeypatch.setenv("BHANSA_DEV", "0")
    assert not config.is_dev_mode()


@pytest.mark.parametrize("settings", [OLD_SETTINGS, {"SLICEFLOW_DEV": "1"}])
def test_app_starts_with_only_old_names(tmp_path, settings):
    code = ("import main, auth, seed; from models import User; from sqlmodel import Session, select\n"
            "pins = {u.role: u.pin_hash for u in Session(seed.engine).exec(select(User))}\n"
            f"pin = {settings.get('SLICEFLOW_PIN_MANAGER', '9999')!r}\n"
            "assert auth.check_pin(pin, pins['MANAGER'])\n"
            "import manager; assert manager.LOCAL_TZ.key == 'Asia/Kathmandu'")
    result = start_app(tmp_path, code=code, SLICEFLOW_TZ="Asia/Kathmandu", **settings)
    assert result.returncode == 0, result.stderr


# ---------------- The name people see ----------------

def test_pages_show_the_new_name(client, session):
    order = Order(state="SUBMITTED")
    session.add(order)
    session.commit()
    pages = [client.get("/login"), client.get("/board"), client.get(tracking.track_path(order.id)),
             client.get("/docs")]
    client.post("/login", data={"user_id": 2, "pin": "2222"})
    pages.append(client.get("/"))                      # forbidden page
    client.post("/logout")
    client.post("/login", data={"user_id": 3, "pin": "9999"})
    pages += [client.get(path) for path in ("/", "/kitchen", "/manager")]
    for page in pages:
        assert "Bhansa" in page.text, page.url
        assert "sliceflow" not in page.text.lower(), page.url
