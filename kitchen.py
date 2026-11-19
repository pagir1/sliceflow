from datetime import datetime, timezone

from sqlmodel import Session, select

import cart
from core.order_state import State, Event, Role, next_state
from models import Order

WARN_AFTER_MIN = 10     # card turns amber
LATE_AFTER_MIN = 15     # card turns red

COLUMNS = [("SUBMITTED", "New"), ("IN_OVEN", "In oven"), ("READY", "Ready")]


def minutes_waiting(since: datetime | None, now: datetime) -> int:
    if since is None:
        return 0
    if since.tzinfo is None:                       # be safe with old rows
        since = since.replace(tzinfo=timezone.utc)
    return max(0, int((now - since).total_seconds() // 60))


def wait_level(minutes: int) -> str:
    if minutes >= LATE_AFTER_MIN:
        return "late"
    if minutes >= WARN_AFTER_MIN:
        return "warn"
    return "ok"


def orders_in_state(session: Session, state: str) -> list[Order]:
    return session.exec(
        select(Order).where(Order.state == state).order_by(Order.submitted_at, Order.id)
    ).all()


def board(session: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    columns = []
    for state, title in COLUMNS:
        cards = []
        for order in orders_in_state(session, state):
            minutes = minutes_waiting(order.submitted_at, now)
            cards.append({
                "order": order,
                "lines": cart.get_lines(session, order),
                "minutes": minutes,
                "level": wait_level(minutes),
            })
        columns.append({"state": state, "title": title, "cards": cards})
    return {"columns": columns}


def advance(session: Session, order_id: int, event: Event, role: Role) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise ValueError(f"Order #{order_id} not found")
    new_state = next_state(State(order.state), event, role,
                           item_count=len(cart.get_lines(session, order)),
                           is_paid=order.is_paid)
    order.state = new_state.value
    session.add(order)
    session.commit()
    return order


def ready_for_pickup(session: Session) -> list[dict]:
    return [{"order": o, "total": cart.ticket(session, o)["total"]}
            for o in orders_in_state(session, "READY")]