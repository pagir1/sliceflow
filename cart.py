from sqlmodel import Session, select

from core.pricing import order_totals
from models import Order, OrderLine, MenuItem


def get_or_create_draft(session: Session) -> Order:
    order = session.exec(
        select(Order).where(Order.state == "DRAFT").order_by(Order.id.desc())
    ).first()
    if order is None:
        order = Order()
        session.add(order)
        session.commit()
        session.refresh(order)
    return order


def get_lines(session: Session, order: Order) -> list[OrderLine]:
    return session.exec(
        select(OrderLine).where(OrderLine.order_id == order.id).order_by(OrderLine.id)
    ).all()


def add_menu_item(session: Session, order: Order, item_id: int) -> None:
    item = session.get(MenuItem, item_id)
    if item is None or not item.is_active:
        raise ValueError(f"Menu item {item_id} not found")

    line = session.exec(
        select(OrderLine).where(OrderLine.order_id == order.id,
                                OrderLine.menu_item_id == item.id)
    ).first()
    if line:
        line.quantity += 1
    else:
        line = OrderLine(order_id=order.id, menu_item_id=item.id,
                         name=item.name, unit_price_cents=item.price_cents)
    session.add(line)
    session.commit()


def remove_one(session: Session, order: Order, line_id: int) -> None:
    line = session.get(OrderLine, line_id)
    if line is None or line.order_id != order.id:
        return
    if line.quantity > 1:
        line.quantity -= 1
        session.add(line)
    else:
        session.delete(line)
    session.commit()


def clear(session: Session, order: Order) -> None:
    for line in get_lines(session, order):
        session.delete(line)
    session.commit()


def ticket(session: Session, order: Order) -> dict:
    lines = get_lines(session, order)
    totals = order_totals([(l.unit_price_cents, l.quantity) for l in lines])
    return {"order": order, "lines": lines, **totals}