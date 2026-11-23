import os
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

import cart
from core.order_state import Event, Role, State, next_state
from models import Order, User

# The restaurant's own clock. Times are saved in UTC; reports use local days.
LOCAL_TZ = ZoneInfo(os.environ.get("SLICEFLOW_TZ", "America/New_York"))

VOIDABLE = ["SUBMITTED", "IN_OVEN", "READY"]


def today_local() -> date:
    return datetime.now(LOCAL_TZ).date()


def day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Midnight to midnight in local time, turned into UTC."""
    start = datetime.combine(day, time.min, tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def daily_report(session: Session, day: date) -> dict:
    start, end = day_bounds_utc(day)
    orders = session.exec(
        select(Order).where(Order.submitted_at >= start, Order.submitted_at < end)
    ).all()

    report = {"day": day, "completed": 0, "cancelled": 0, "open": 0,
              "subtotal": 0, "tax": 0, "total": 0, "cash": 0, "card": 0,
              "voided_after_payment": 0, "top_items": []}
    items = defaultdict(lambda: {"quantity": 0, "revenue": 0})

    for order in orders:
        totals = cart.ticket(session, order)
        if order.state == "CANCELLED":
            report["cancelled"] += 1
            if order.is_paid:
                report["voided_after_payment"] += totals["total"]   # money to give back
        elif order.state == "COMPLETED":
            report["completed"] += 1
            report["subtotal"] += totals["subtotal"]
            report["tax"] += totals["tax"]
            report["total"] += totals["total"]
            report[order.payment_method.lower()] += totals["total"]
            for line in totals["lines"]:
                items[line.name]["quantity"] += line.quantity
                items[line.name]["revenue"] += line.unit_price_cents * line.quantity
        else:
            report["open"] += 1

    ranked = sorted(items.items(), key=lambda kv: (-kv[1]["quantity"], -kv[1]["revenue"], kv[0]))
    report["top_items"] = [{"name": name, **numbers} for name, numbers in ranked[:5]]
    return report


def voidable_orders(session: Session) -> list[dict]:
    orders = session.exec(
        select(Order).where(Order.state.in_(VOIDABLE)).order_by(Order.submitted_at, Order.id)
    ).all()
    return [{"order": o, "total": cart.ticket(session, o)["total"]} for o in orders]


def void_order(session: Session, order_id: int, reason: str, manager: User) -> Order:
    reason = reason.strip()
    if len(reason) < 3:
        raise ValueError("Write a short reason before voiding")
    order = session.get(Order, order_id)
    if order is None:
        raise ValueError(f"Order #{order_id} not found")
    new_state = next_state(State(order.state), Event.VOID, Role(manager.role),
                           item_count=len(cart.get_lines(session, order)),
                           is_paid=order.is_paid)
    order.state = new_state.value
    order.void_reason = reason
    order.voided_by = manager.name
    session.add(order)
    session.commit()
    return order