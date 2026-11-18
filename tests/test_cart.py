import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

import cart
from models import MenuItem


@pytest.fixture
def session():
    # A fresh, empty database in memory for every test
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(MenuItem(name="Coke", category="drink", price_cents=249))
        s.add(MenuItem(name="Garlic Knots", category="side", price_cents=499))
        s.commit()
        yield s


def test_new_draft_order_is_empty(session):
    order = cart.get_or_create_draft(session)
    t = cart.ticket(session, order)
    assert t["lines"] == []
    assert t["total"] == 0


def test_adding_same_item_twice_increases_quantity(session):
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)
    cart.add_menu_item(session, order, 1)
    lines = cart.get_lines(session, order)
    assert len(lines) == 1
    assert lines[0].quantity == 2


def test_ticket_totals(session):
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)   # Coke 249
    cart.add_menu_item(session, order, 2)   # Garlic Knots 499
    t = cart.ticket(session, order)
    assert t["subtotal"] == 748
    assert t["tax"] == 45                   # 748 x 6% = 44.88 -> 45
    assert t["total"] == 793


def test_remove_one_then_line_disappears(session):
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)
    line = cart.get_lines(session, order)[0]
    cart.remove_one(session, order, line.id)
    assert cart.get_lines(session, order) == []


def test_price_is_snapshot_when_added(session):
    # INV-8: a later menu price change must not change the order
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)
    coke = session.get(MenuItem, 1)
    coke.price_cents = 999
    session.add(coke)
    session.commit()
    assert cart.get_lines(session, order)[0].unit_price_cents == 249


def test_unknown_item_is_rejected(session):
    order = cart.get_or_create_draft(session)
    with pytest.raises(ValueError):
        cart.add_menu_item(session, order, 999)