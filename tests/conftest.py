import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

import auth
from models import MenuItem, Topping, User


@pytest.fixture
def session():
    # A fresh, empty database in memory for every test
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(MenuItem(name="Coke", category="drink", price_cents=249))
        s.add(MenuItem(name="Garlic Knots", category="side", price_cents=499))
        s.add(Topping(name="Pepperoni"))
        s.add(Topping(name="Mushroom"))
        s.commit()
        yield s


@pytest.fixture
def client(session):
    # A fake browser that talks to the app using the test database above
    from db import get_session
    from main import app

    for name, role, pin in [("Sita", "CASHIER", "1111"), ("Ram", "KITCHEN", "2222"),
                            ("Pawan", "MANAGER", "9999")]:
        session.add(User(name=name, role=role, pin_hash=auth.hash_pin(pin, rounds=4)))
    session.commit()

    def use_test_database():
        yield session

    app.dependency_overrides[get_session] = use_test_database
    yield TestClient(app)
    app.dependency_overrides.clear()