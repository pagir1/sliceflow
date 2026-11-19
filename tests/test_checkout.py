import pytest

import cart
import checkout
from core.order_state import TransitionError


def make_order_with_coke(session):
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)        # Coke 249 + tax 15 = 264
    return order


def test_cash_payment_gives_correct_change(session):
    order = make_order_with_coke(session)
    checkout.pay_cash(session, order, 500)
    assert order.is_paid
    assert order.payment_method == "CASH"
    assert order.change_cents == 236             # 500 - 264


def test_cash_short_by_one_cent_is_rejected(session):
    order = make_order_with_coke(session)
    with pytest.raises(ValueError):
        checkout.pay_cash(session, order, 263)
    assert not order.is_paid


def test_card_pays_exact_total(session):
    order = make_order_with_coke(session)
    checkout.pay_card(session, order)
    assert order.is_paid and order.tendered_cents == 264 and order.change_cents == 0


def test_cannot_pay_twice(session):
    order = make_order_with_coke(session)
    checkout.pay_card(session, order)
    with pytest.raises(ValueError):
        checkout.pay_card(session, order)


def test_cannot_pay_empty_order(session):
    order = cart.get_or_create_draft(session)
    with pytest.raises(ValueError):
        checkout.pay_card(session, order)


def test_paid_order_cannot_be_changed(session):
    # INV-7: items do not change after payment
    order = make_order_with_coke(session)
    checkout.pay_card(session, order)
    with pytest.raises(ValueError):
        cart.add_menu_item(session, order, 2)


def test_send_to_kitchen_moves_to_submitted_and_starts_new_draft(session):
    order = make_order_with_coke(session)
    checkout.send_to_kitchen(session, order)
    assert order.state == "SUBMITTED"
    assert order.submitted_at is not None
    new_order = cart.get_or_create_draft(session)
    assert new_order.id != order.id


def test_cannot_send_empty_order(session):
    order = cart.get_or_create_draft(session)
    with pytest.raises(TransitionError):
        checkout.send_to_kitchen(session, order)