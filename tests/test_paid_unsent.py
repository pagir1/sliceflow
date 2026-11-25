import pytest
from fastapi.testclient import TestClient

import cart
import checkout
import manager
from core.order_state import TransitionError
from models import User


def draft(session, paid=True):
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)             # Coke, total 264
    if paid:
        checkout.pay_card(session, order)
    return order


def listed(session):
    return [p["order"].id for p in manager.paid_unsent_orders(session)]


@pytest.fixture
def boss(client):
    client.post("/login", data={"user_id": 3, "pin": "9999"})
    return client


@pytest.fixture
def register(client):
    # Another browser, where a cashier took the money but did not send the order
    other = TestClient(client.app, base_url="https://testserver")
    other.post("/login", data={"user_id": 1, "pin": "1111"})
    other.post("/cart/add/1")
    other.post("/checkout/card")
    return other


def test_list_shows_only_paid_drafts(session):
    paid = draft(session)
    draft(session, paid=False)
    sent = draft(session)
    checkout.send_to_kitchen(session, sent)
    assert listed(session) == [paid.id]


def test_manager_screen_shows_order_lost_by_a_register(register, boss, session):
    register.cookies.clear()                          # the register forgets its order
    [order_id] = listed(session)
    assert f"/manager/paid/{order_id}/send" in boss.get("/manager").text


def test_manager_sends_a_paid_order(boss, session):
    order = draft(session)
    r = boss.post(f"/manager/paid/{order.id}/send")
    assert "sent to the kitchen" in r.text and "orders-changed" in r.headers["HX-Trigger"]
    assert order.state == "SUBMITTED" and order.submitted_at is not None
    assert listed(session) == []
    assert f"/manager/void/{order.id}" in boss.get("/manager/voidable").text
    assert "not waiting" in boss.post(f"/manager/paid/{order.id}/send").text    # not twice


def test_manager_voids_a_paid_order_and_the_refund_is_reported(boss, session):
    order = draft(session)
    assert "short reason" in boss.post(f"/manager/paid/{order.id}/void", data={"reason": " "}).text
    assert order.state == "DRAFT"
    r = boss.post(f"/manager/paid/{order.id}/void", data={"reason": "customer left"})
    assert "voided" in r.text and r.headers["HX-Trigger"] == "report-changed"
    assert order.state == "CANCELLED" and order.voided_by == "Pawan"
    assert listed(session) == []
    report = manager.daily_report(session, manager.today_local())
    assert report["cancelled"] == 1 and report["voided_after_payment"] == 264


def test_unpaid_draft_cannot_be_sent_or_voided_here(boss, session):
    order = draft(session, paid=False)
    boss.post(f"/manager/paid/{order.id}/send")
    boss.post(f"/manager/paid/{order.id}/void", data={"reason": "not paid"})
    assert order.state == "DRAFT"
    with pytest.raises(TransitionError):
        manager.void_order(session, order.id, "not paid", session.get(User, 3))


def test_already_sent_order_is_not_voided_from_a_stale_list(boss, session):
    order = draft(session)
    checkout.send_to_kitchen(session, order)
    r = boss.post(f"/manager/paid/{order.id}/void", data={"reason": "old page"})
    assert "not waiting" in r.text and order.state == "SUBMITTED"


def test_unknown_order_is_an_error(boss):
    assert "not waiting" in boss.post("/manager/paid/999/send").text
    assert "not waiting" in boss.post("/manager/paid/999/void", data={"reason": "nothing"}).text


@pytest.mark.parametrize("action", ["send", "void"])
def test_cashier_cannot_use_the_paid_list(client, session, action):
    order = draft(session)
    client.post("/login", data={"user_id": 1, "pin": "1111"})
    r = client.post(f"/manager/paid/{order.id}/{action}", data={"reason": "please"})
    assert r.status_code == 403 and order.state == "DRAFT"


def test_register_continues_normally_after_manager_sends_its_order(register, boss, session):
    [order_id] = listed(session)
    boss.post(f"/manager/paid/{order_id}/send")
    assert "empty order" in register.post("/order/send").text      # not sent twice
    register.post("/logout")
    assert register.get("/", follow_redirects=False).status_code == 303
