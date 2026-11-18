import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from models import MenuItem, Topping


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