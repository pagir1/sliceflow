import math
import pytest

import cart
import pizza
from models import Topping


def test_read_selections_skips_none():
    toppings = [Topping(id=1, name="Pepperoni"), Topping(id=2, name="Mushroom")]
    form = {"size": "L", "t_1": "LEFT", "t_2": "NONE"}
    assert pizza.read_selections(form, toppings) == [("Pepperoni", "LEFT")]


def test_read_selections_rejects_unknown_side():
    toppings = [Topping(id=1, name="Pepperoni")]
    with pytest.raises(ValueError):
        pizza.read_selections({"t_1": "MIDDLE"}, toppings)


def test_build_view_price_matches_pricing_engine():
    view = pizza.build_view("L", [("Pepperoni", "LEFT"), ("Mushroom", "WHOLE")])
    assert view["price"] == 1699 + 88 + 175
    assert view["size_name"] == "Large"


def test_build_view_rejects_unknown_size():
    with pytest.raises(ValueError):
        pizza.build_view("XL", [])


def test_left_topping_dots_stay_on_left_half():
    dots = pizza.topping_dots([("Pepperoni", "LEFT")])
    assert len(dots) == 3
    assert all(d["x"] < 120 for d in dots)


def test_whole_topping_dots_cover_both_halves():
    dots = pizza.topping_dots([("Pepperoni", "WHOLE")])
    assert any(d["x"] < 120 for d in dots)
    assert any(d["x"] > 120 for d in dots)


def test_all_dots_are_on_the_pizza():
    selections = [(f"T{i}", "WHOLE") for i in range(12)]
    for d in pizza.topping_dots(selections):
        assert math.hypot(d["x"] - 120, d["y"] - 120) <= 81   # inside the cheese


def test_add_pizza_to_order(session):
    order = cart.get_or_create_draft(session)
    cart.add_pizza(session, order, "L", [("Pepperoni", "LEFT"), ("Mushroom", "RIGHT")])
    line = cart.get_lines(session, order)[0]
    assert line.name == "Large Pizza"
    assert line.details == "Pepperoni (Left half), Mushroom (Right half)"
    assert line.unit_price_cents == 1699 + 88 + 88


def test_add_pizza_rejects_unknown_size(session):
    order = cart.get_or_create_draft(session)
    with pytest.raises(ValueError):
        cart.add_pizza(session, order, "XL", [])