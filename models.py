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
    submitted_at: datetime | None = None
    is_paid: bool = False
    payment_method: str = ""        # "CASH" or "CARD"
    tendered_cents: int = 0         # money the customer gave
    change_cents: int = 0           # money we gave back
    void_reason: str = ""           # why a manager voided it
    voided_by: str = ""             # which manager voided it


class OrderLine(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    menu_item_id: int | None = Field(default=None, foreign_key="menuitem.id")
    name: str               # copied when added (INV-8)
    details: str = ""       # pizza toppings, for example "Pepperoni (Left half)"
    unit_price_cents: int   # copied when added (INV-8)
    quantity: int = 1


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    role: str                                   # "CASHIER", "KITCHEN" or "MANAGER"
    pin_hash: str                               # never the real PIN (SR-04)
    failed_attempts: int = 0
    locked_until: datetime | None = None
    is_active: bool = True