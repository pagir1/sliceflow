from sqlmodel import Session, select
from db import engine
from models import Topping, MenuItem

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


def seed():
    with Session(engine) as session:
        already_seeded = session.exec(select(Topping)).first()
        if already_seeded:
            return
        for name in TOPPINGS:
            session.add(Topping(name=name))
        for name, category, price in MENU_ITEMS:
            session.add(MenuItem(name=name, category=category, price_cents=price))
        session.commit()