from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Topping(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    is_active: bool = True


class MenuItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    category: str          # "side" or "drink"
    price_cents: int       # money in cents, never float
    is_active: bool = True


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    state: str = "DRAFT"
    created_at: datetime = Field(default_factory=now_utc)


class OrderLine(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    menu_item_id: int | None = Field(default=None, foreign_key="menuitem.id")
    name: str               # copied when added (INV-8)
    unit_price_cents: int   # copied when added (INV-8)
    quantity: int = 1