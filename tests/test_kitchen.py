from datetime import datetime, timedelta, timezone

import pytest

import cart
import checkout
import kitchen
from core.order_state import Event, Role, TransitionError


def sent_order(session, paid=False):
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)          # Coke, total 264
    if paid:
        checkout.pay_card(session, order)
    checkout.send_to_kitchen(session, order)
    return order


def column(board, state):
    return next(c for c in board["columns"] if c["state"] == state)


def test_sent_order_shows_in_new_column(session):
    order = sent_order(session)
    b = kitchen.board(session)
    assert [c["order"].id for c in column(b, "SUBMITTED")["cards"]] == [order.id]
    assert column(b, "IN_OVEN")["cards"] == []


def test_kitchen_moves_order_to_oven_then_ready(session):
    order = sent_order(session)
    kitchen.advance(session, order.id, Event.START_COOKING, Role.KITCHEN)
    assert order.state == "IN_OVEN"
    kitchen.advance(session, order.id, Event.MARK_READY, Role.KITCHEN)
    assert order.state == "READY"
    assert [p["order"].id for p in kitchen.ready_for_pickup(session)] == [order.id]


def test_kitchen_cannot_hand_over(session):
    order = sent_order(session, paid=True)
    kitchen.advance(session, order.id, Event.START_COOKING, Role.KITCHEN)
    kitchen.advance(session, order.id, Event.MARK_READY, Role.KITCHEN)
    with pytest.raises(TransitionError):
        kitchen.advance(session, order.id, Event.HAND_OVER, Role.KITCHEN)


def test_unpaid_order_cannot_be_handed_over_until_paid(session):
    # INV-5 on the real flow
    order = sent_order(session, paid=False)
    kitchen.advance(session, order.id, Event.START_COOKING, Role.KITCHEN)
    kitchen.advance(session, order.id, Event.MARK_READY, Role.KITCHEN)
    with pytest.raises(TransitionError):
        kitchen.advance(session, order.id, Event.HAND_OVER, Role.CASHIER)
    checkout.pay_cash(session, order, 264)
    kitchen.advance(session, order.id, Event.HAND_OVER, Role.CASHIER)
    assert order.state == "COMPLETED"
    assert kitchen.ready_for_pickup(session) == []


def test_unknown_order_is_rejected(session):
    with pytest.raises(ValueError):
        kitchen.advance(session, 999, Event.START_COOKING, Role.KITCHEN)


@pytest.mark.parametrize("minutes, level", [(0, "ok"), (9, "ok"), (10, "warn"),
                                            (14, "warn"), (15, "late"), (60, "late")])
def test_wait_level(minutes, level):
    assert kitchen.wait_level(minutes) == level


def test_minutes_waiting():
    now = datetime(2026, 11, 20, 18, 30, tzinfo=timezone.utc)
    assert kitchen.minutes_waiting(now - timedelta(minutes=12, seconds=40), now) == 12
    assert kitchen.minutes_waiting(None, now) == 0
    naive = datetime(2026, 11, 20, 18, 25)                 # old row without timezone
    assert kitchen.minutes_waiting(naive, now) == 5