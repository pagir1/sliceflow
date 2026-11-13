import pytest
from core.pricing import topping_cost, pizza_price, tax_cents, order_totals


def test_whole_topping_is_full_price():
    assert topping_cost("L", "WHOLE") == 175


def test_half_topping_rounds_up():
    # half of 175 is 87.5 -> must become 88
    assert topping_cost("L", "LEFT") == 88
    assert topping_cost("L", "RIGHT") == 88


def test_plain_pizza_is_base_price():
    assert pizza_price("M", []) == 1399


def test_half_and_half_pizza():
    toppings = [("pepperoni", "LEFT"), ("mushroom", "RIGHT"), ("olive", "WHOLE")]
    assert pizza_price("L", toppings) == 1699 + 88 + 88 + 175


def test_tax_rounding():
    assert tax_cents(2299) == 138   # 2299 x 6% = 137.94 -> 138
    assert tax_cents(0) == 0


def test_unknown_side_is_rejected():
    with pytest.raises(ValueError):
        topping_cost("L", "MIDDLE")


def test_order_totals_receipt_example():
    result = order_totals([(2050, 1), (249, 1)])
    assert result == {"subtotal": 2299, "tax": 138, "total": 2437}


def test_order_totals_empty_order():
    result = order_totals([])
    assert result == {"subtotal": 0, "tax": 0, "total": 0}


def test_order_totals_rejects_zero_quantity():
    with pytest.raises(ValueError):
        order_totals([(2050, 0)])


def test_total_is_always_subtotal_plus_tax():
    # INV-3 from our requirements document
    examples = [[(2050, 1)], [(249, 3), (1699, 2)], [(1, 1)], []]
    for lines in examples:
        r = order_totals(lines)
        assert r["total"] == r["subtotal"] + r["tax"]