from sqlmodel import Session

import cart
from core.order_state import State, Event, Role, next_state
from core.payment import cash_change
from models import Order, now_utc


def order_total(session: Session, order: Order) -> int:
    return cart.ticket(session, order)["total"]


def _ensure_can_pay(session: Session, order: Order) -> None:
    if order.is_paid:
        raise ValueError("This order is already paid")
    if not cart.get_lines(session, order):
        raise ValueError("Add something to the order first")


def pay_cash(session: Session, order: Order, tendered: int) -> None:
    _ensure_can_pay(session, order)
    total = order_total(session, order)
    order.change_cents = cash_change(total, tendered)   # INV-4, raises if not enough
    order.tendered_cents = tendered
    order.payment_method = "CASH"
    order.is_paid = True
    session.add(order)
    session.commit()


def pay_card(session: Session, order: Order) -> None:
    # Simulated card: the card always pays the exact total. No real card data.
    _ensure_can_pay(session, order)
    order.tendered_cents = order_total(session, order)
    order.change_cents = 0
    order.payment_method = "CARD"
    order.is_paid = True
    session.add(order)
    session.commit()


def send_to_kitchen(session: Session, order: Order) -> None:
    item_count = len(cart.get_lines(session, order))
    new_state = next_state(State(order.state), Event.SEND_TO_KITCHEN, Role.CASHIER,
                           item_count=item_count, is_paid=order.is_paid)
    order.state = new_state.value
    order.submitted_at = now_utc()
    session.add(order)
    session.commit()