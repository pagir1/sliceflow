import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import auth
import db
import seed
from models import Topping, User
from test_config import start_app

PINS = {"SLICEFLOW_PIN_CASHIER": "4821", "SLICEFLOW_PIN_KITCHEN": "5932",
        "SLICEFLOW_PIN_MANAGER": "6043"}
DEMO_PINS = {"CASHIER": "1111", "KITCHEN": "2222", "MANAGER": "9999"}


# ---------------- Database location ----------------

@pytest.mark.parametrize("value", [None, "", "  "])
def test_database_default(monkeypatch, value):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if value is not None:
        monkeypatch.setenv("DATABASE_URL", value)
    assert db.database_url() == "sqlite:///sliceflow.db"


def test_app_uses_database_url(tmp_path):
    disk = tmp_path / "disk"
    disk.mkdir()
    result = start_app(tmp_path, SLICEFLOW_SECRET="private", **PINS,
                       DATABASE_URL=f"sqlite:///{(disk / 'shop.db').as_posix()}")
    assert result.returncode == 0, result.stderr
    assert (disk / "shop.db").exists()
    assert not (tmp_path / "sliceflow.db").exists()


# ---------------- Staff PINs ----------------

@pytest.fixture
def empty_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(seed, "engine", engine)
    for name in [*PINS, "SLICEFLOW_DEV"]:
        monkeypatch.delenv(name, raising=False)
    return engine


def has_pins(engine, pins):
    with Session(engine) as session:
        users = session.exec(select(User)).all()
    return {u.role for u in users if auth.check_pin(pins[u.role], u.pin_hash)} == set(pins)


def test_pins_come_from_env(empty_db, monkeypatch):
    for name, pin in PINS.items():
        monkeypatch.setenv(name, pin)
    seed.seed()
    assert has_pins(empty_db, {n.removeprefix("SLICEFLOW_PIN_"): p for n, p in PINS.items()})


def test_dev_mode_keeps_demo_pins(empty_db, monkeypatch):
    monkeypatch.setenv("SLICEFLOW_DEV", "1")
    seed.seed()
    assert has_pins(empty_db, DEMO_PINS)


@pytest.mark.parametrize("name", PINS)
@pytest.mark.parametrize("bad", ["", "123", "12345", "abcd", "1111", "2222", "9999"])
def test_bad_or_demo_pin_is_refused_outside_dev(empty_db, monkeypatch, name, bad):
    for key, pin in PINS.items():
        monkeypatch.setenv(key, pin)
    monkeypatch.setenv(name, bad)
    with pytest.raises(RuntimeError, match=name):
        seed.seed()
    with Session(empty_db) as session:                # nothing half-created
        assert session.exec(select(User)).first() is None
        assert session.exec(select(Topping)).first() is None


def test_existing_staff_need_no_pin_settings(empty_db, monkeypatch):
    for name, pin in PINS.items():
        monkeypatch.setenv(name, pin)
    seed.seed()
    for name in PINS:
        monkeypatch.delenv(name)
    seed.seed()


# ---------------- HTTPS ----------------

def test_login_cookie_is_https_only(client):
    r = client.post("/login", data={"user_id": 1, "pin": "1111"}, follow_redirects=False)
    assert "secure" in r.headers["set-cookie"].lower()


@pytest.mark.parametrize("dev, expected", [("1", False), ("0", True)])
def test_https_only_follows_dev_mode(tmp_path, dev, expected):
    code = ("import main; m = [m for m in main.app.user_middleware if 'https_only' in m.kwargs][0];"
            f"assert m.kwargs['https_only'] is {expected}")
    result = start_app(tmp_path, code=code, SLICEFLOW_SECRET="private", SLICEFLOW_DEV=dev, **PINS)
    assert result.returncode == 0, result.stderr


def test_qr_link_is_https_behind_proxy(client):
    from main import app
    proxied = TestClient(ProxyHeadersMiddleware(app, trusted_hosts="*"),
                         base_url="http://shop.onrender.com",
                         headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": "203.0.113.5"})

    def post(path, data=None):
        # The browser talks https to Render, so it does send the secure cookie back
        r = proxied.post(path, data=data, follow_redirects=False)
        if "set-cookie" in r.headers:
            proxied.headers["Cookie"] = r.headers["set-cookie"].split(";")[0]
        return r

    post("/login", {"user_id": 1, "pin": "1111"})
    post("/cart/add/1")
    post("/checkout/card")
    text = post("/order/send").text
    assert "https://shop.onrender.com/track/" in text
    assert "http://shop.onrender.com" not in text
