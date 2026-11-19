import cart
import checkout
import display
import kitchen
from core.order_state import Event, Role


def sent_order(session):
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)
    checkout.pay_card(session, order)
    checkout.send_to_kitchen(session, order)
    return order


def test_empty_board(session):
    assert display.customer_board(session) == {"preparing": [], "ready": []}


def test_new_and_in_oven_orders_are_preparing(session):
    a = sent_order(session)
    b = sent_order(session)
    kitchen.advance(session, b.id, Event.START_COOKING, Role.KITCHEN)
    board = display.customer_board(session)
    assert board["preparing"] == [a.id, b.id]
    assert board["ready"] == []


def test_ready_order_moves_to_ready(session):
    a = sent_order(session)
    kitchen.advance(session, a.id, Event.START_COOKING, Role.KITCHEN)
    kitchen.advance(session, a.id, Event.MARK_READY, Role.KITCHEN)
    assert display.customer_board(session) == {"preparing": [], "ready": [a.id]}


def test_completed_and_draft_orders_are_not_shown(session):
    a = sent_order(session)
    kitchen.advance(session, a.id, Event.START_COOKING, Role.KITCHEN)
    kitchen.advance(session, a.id, Event.MARK_READY, Role.KITCHEN)
    kitchen.advance(session, a.id, Event.HAND_OVER, Role.CASHIER)
    draft = cart.get_or_create_draft(session)
    cart.add_menu_item(session, draft, 1)
    assert display.customer_board(session) == {"preparing": [], "ready": []}