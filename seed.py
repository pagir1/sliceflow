from sqlmodel import Session, select

import auth
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

# Demo staff. Change these PINs before any real use.
STAFF = [
    ("Sita", "CASHIER", "1111"),
    ("Ram", "KITCHEN", "2222"),
    ("Pawan", "MANAGER", "9999"),
]


def seed():
    with Session(engine) as session:
        if session.exec(select(Topping)).first() is None:
            for name in TOPPINGS:
                session.add(Topping(name=name))
            for name, category, price in MENU_ITEMS:
                session.add(MenuItem(name=name, category=category, price_cents=price))

        if session.exec(select(User)).first() is None:
            for name, role, pin in STAFF:
                session.add(User(name=name, role=role, pin_hash=auth.hash_pin(pin)))

        session.commit()