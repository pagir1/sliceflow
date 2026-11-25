from sqlmodel import Session, select

import auth
import config
from db import engine
from models import MenuItem, Topping, User

TOPPINGS = ["Pepperoni", "Mushroom", "Onion", "Green Pepper", "Black Olive", "Sausage",
            "Bacon", "Extra Cheese", "Jalapeno", "Pineapple", "Spinach", "Tomato"]

MENU_ITEMS = [
    ("Garlic Knots", "side", 499),
    ("Chicken Wings (8 pc)", "side", 999),
    ("Caesar Salad", "side", 699),
    ("Mozzarella Sticks", "side", 649),
    ("Coke", "drink", 249),
    ("Diet Coke", "drink", 249),
    ("Sprite", "drink", 249),
    ("Bottled Water", "drink", 199),
]

# Demo staff. These PINs are public (they are in the code), so they work only in dev mode.
STAFF = [
    ("Sita", "CASHIER", "1111"),
    ("Ram", "KITCHEN", "2222"),
    ("Pawan", "MANAGER", "9999"),
]


def staff_pin(role: str, demo_pin: str) -> str:
    """The first PIN for this role, from BHANSA_PIN_<role>. Demo PINs only in dev mode."""
    name = f"BHANSA_PIN_{role}"
    pin = config.setting(f"PIN_{role}")
    if not pin and config.is_dev_mode():
        return demo_pin
    if not auth.is_valid_pin_format(pin):
        raise RuntimeError(f"{name} must be set to a 4-digit PIN")
    if not config.is_dev_mode() and pin in {demo for _, _, demo in STAFF}:
        raise RuntimeError(f"{name} must not be one of the public demo PINs")
    return pin


def seed():
    with Session(engine) as session:
        if session.exec(select(Topping)).first() is None:
            for name in TOPPINGS:
                session.add(Topping(name=name))
            for name, category, price in MENU_ITEMS:
                session.add(MenuItem(name=name, category=category, price_cents=price))

        if session.exec(select(User)).first() is None:
            for name, role, demo_pin in STAFF:
                pin = staff_pin(role, demo_pin)
                session.add(User(name=name, role=role, pin_hash=auth.hash_pin(pin)))

        session.commit()