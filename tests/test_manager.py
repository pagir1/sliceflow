from datetime import date, datetime, timezone

import pytest

import cart
import checkout
import kitchen
import manager
from core.order_state import Event, Role, TransitionError
from models import Order, User


def make_order(session, item_ids, paid=True, method="card"):
    order = cart.get_or_create_draft(session)
    for item_id in item_ids:
        cart.add_menu_item(session, order, item_id)
    if paid:
        if method == "card":
            checkout.pay_card(session, order)
        else:
            checkout.pay_cash(session, order, 10000)
    checkout.send_to_kitchen(session, order)
    return order


def finish(session, order):
    kitchen.advance(session, order.id, Event.START_COOKING, Role.KITCHEN)
    kitchen.advance(session, order.id, Event.MARK_READY, Role.KITCHEN)
    kitchen.advance(session, order.id, Event.HAND_OVER, Role.CASHIER)


def boss(session):
    user = User(name="Pawan", role="MANAGER", pin_hash="x")
    session.add(user)
    session.commit()
    return user


def test_report_counts_only_completed_orders_as_sales(session):
    a = make_order(session, [1, 1])               # 2 Coke = 498, tax 30, total 528
    finish(session, a)
    b = make_order(session, [2], method="cash")   # Garlic Knots 499, tax 30, total 529
    finish(session, b)
    make_order(session, [2])                      # still in kitchen
    report = manager.daily_report(session, manager.today_local())
    assert report["completed"] == 2
    assert report["open"] == 1
    assert report["total"] == 528 + 529
    assert report["tax"] == 30 + 30
    assert report["card"] == 528 and report["cash"] == 529
    assert report["top_items"][0] == {"name": "Coke", "quantity": 2, "revenue": 498}


def test_cancelled_order_is_not_a_sale(session):
    a = make_order(session, [1])
    manager.void_order(session, a.id, "test order", boss(session))
    report = manager.daily_report(session, manager.today_local())
    assert report["cancelled"] == 1 and report["total"] == 0
    assert report["voided_after_payment"] == 264        # it was paid, so a refund is owed


def test_day_uses_local_time_not_utc():
    # 03:30 UTC on Nov 24 is still 22:30 on Nov 23 in New York
    start, end = manager.day_bounds_utc(date(2026, 11, 23))
    late_evening = datetime(2026, 11, 24, 3, 30, tzinfo=timezone.utc)
    assert start <= late_evening < end


def test_void_needs_a_reason(session):
    a = make_order(session, [1])
    with pytest.raises(ValueError):
        manager.void_order(session, a.id, "  ", boss(session))
    assert a.state == "SUBMITTED"


def test_manager_can_void_a_ready_order(session):
    # CR-02: an order the customer never picked up can be voided
    a = make_order(session, [1])
    kitchen.advance(session, a.id, Event.START_COOKING, Role.KITCHEN)
    kitchen.advance(session, a.id, Event.MARK_READY, Role.KITCHEN)
    manager.void_order(session, a.id, "customer never came", boss(session))
    assert a.state == "CANCELLED" and a.voided_by == "Pawan"
    assert manager.voidable_orders(session) == []


def test_completed_order_cannot_be_voided(session):
    a = make_order(session, [1])
    finish(session, a)
    with pytest.raises(TransitionError):
        manager.void_order(session, a.id, "too late", boss(session))


def test_cashier_cannot_void(session):
    a = make_order(session, [1])
    cashier = User(name="Sita", role="CASHIER", pin_hash="x")
    with pytest.raises(TransitionError):
        manager.void_order(session, a.id, "please", cashier)