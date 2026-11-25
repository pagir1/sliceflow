import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

import auth
import cart
import checkout
from models import Order, OrderLine, User


def login(client, user_id=1, pin="1111"):
    r = client.post("/login", data={"user_id": user_id, "pin": pin}, follow_redirects=False)
    assert r.status_code == 303
    return client


def ticket(client, path, data=None):
    """Only the ticket part of the answer (the menu also contains the item names)."""
    r = client.post(path, data=data)
    assert r.status_code == 200
    return r.text


@pytest.fixture
def registers(client, session):
    # Two cashiers on two registers: each TestClient has its own cookies
    session.add(User(name="Gita", role="CASHIER", pin_hash=auth.hash_pin("3333", rounds=4)))
    session.commit()
    return login(client), login(TestClient(client.app, base_url="https://testserver"), 4, "3333")


def lines(session):
    found = session.exec(select(OrderLine).order_by(OrderLine.id)).all()
    return [(l.order_id, l.name, l.quantity) for l in found]


def test_two_cashiers_do_not_share_a_cart(registers, session):
    a, b = registers
    text_a = ticket(a, "/cart/add/1")
    text_b = ticket(b, "/cart/add/2")
    assert "Coke" in text_a and "Garlic Knots" not in text_a
    assert "Garlic Knots" in text_b and "Coke" not in text_b
    found = lines(session)
    assert len(found) == 2 and found[0][0] != found[1][0]


def test_a_register_keeps_its_cart_between_requests(registers, session):
    a, b = registers
    ticket(a, "/cart/add/1")
    ticket(b, "/cart/add/1")
    assert a.get("/").status_code == 200
    ticket(a, "/cart/add/1")
    assert [quantity for _, _, quantity in lines(session)] == [2, 1]


def test_same_cashier_on_two_registers_has_two_carts(client):
    other = login(TestClient(client.app, base_url="https://testserver"))
    ticket(login(client), "/cart/add/1")
    assert "Coke" not in ticket(other, "/cart/add/2")


def test_clear_and_remove_leave_the_other_cart_alone(registers, session):
    a, b = registers
    ticket(a, "/cart/add/1")
    ticket(b, "/cart/add/2")
    a_line = session.exec(select(OrderLine).where(OrderLine.name == "Coke")).one()
    ticket(b, f"/cart/remove/{a_line.id}")
    ticket(b, "/cart/clear")
    assert [name for _, name, _ in lines(session)] == ["Coke"]


@pytest.mark.parametrize("path, data", [("/checkout/card", None),
                                        ("/checkout/cash", {"tendered_cents": 500})])
def test_paying_and_sending_affect_only_own_order(registers, session, path, data):
    a, b = registers
    ticket(a, "/cart/add/1")
    ticket(b, "/cart/add/2")
    ticket(a, path, data)
    ticket(a, "/order/send")
    owner = {name: session.get(Order, order_id) for order_id, name, _ in lines(session)}
    assert owner["Coke"].state == "SUBMITTED" and owner["Coke"].is_paid
    assert owner["Garlic Knots"].state == "DRAFT" and not owner["Garlic Knots"].is_paid
    # A starts a fresh order, not B's
    assert "Garlic Knots" not in ticket(a, "/cart/add/1")
    assert len({order_id for order_id, _, _ in lines(session)}) == 3


def test_pizza_goes_to_own_cart(registers):
    a, b = registers
    assert "Large Pizza" in ticket(a, "/cart/add-pizza", {"size": "L"})
    assert "Large Pizza" not in ticket(b, "/cart/add/1")


def test_next_login_on_a_register_does_not_get_the_old_cart(client):
    ticket(login(client), "/cart/add/1")
    client.post("/logout")
    assert "Coke" not in ticket(login(client, 3, "9999"), "/cart/add/2")


def test_get_or_create_draft_uses_only_the_given_open_draft(session):
    first = cart.get_or_create_draft(session)
    assert cart.get_or_create_draft(session, first.id).id == first.id
    assert cart.get_or_create_draft(session).id != first.id
    assert cart.get_or_create_draft(session, 9999).id != first.id
    cart.add_menu_item(session, first, 1)
    checkout.send_to_kitchen(session, first)
    assert cart.get_or_create_draft(session, first.id).id != first.id


def is_logged_in(client):
    return client.get("/", follow_redirects=False).status_code == 200


@pytest.fixture
def paid(client):
    ticket(login(client), "/cart/add/1")
    ticket(client, "/checkout/card")
    return client


def test_logout_is_blocked_until_a_paid_order_is_sent(paid):
    r = paid.post("/logout")
    assert r.url.path == "/" and "Send it to the kitchen before logging out" in r.text
    assert "Coke" in r.text.split('id="ticket"')[1]               # still the paid order
    assert "before logging out" not in paid.get("/").text         # shown once
    ticket(paid, "/order/send")
    paid.post("/logout")
    assert not is_logged_in(paid)


def test_manager_logout_is_blocked_too(client):
    ticket(login(client, 3, "9999"), "/cart/add/1")
    ticket(client, "/checkout/cash", {"tendered_cents": 500})
    client.post("/logout")
    assert is_logged_in(client)


def test_login_cannot_replace_a_session_with_a_paid_unsent_order(paid, session):
    r = paid.post("/login", data={"user_id": 3, "pin": "9999"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert paid.get("/manager").status_code == 403                # still the cashier
    ticket(paid, "/order/send")
    assert session.exec(select(Order).where(Order.is_paid)).one().state == "SUBMITTED"


def test_unpaid_order_does_not_block_logout(client):
    ticket(login(client), "/cart/add/1")
    client.post("/logout")
    assert not is_logged_in(client)


def test_paid_order_does_not_block_another_register(paid):
    other = login(TestClient(paid.app, base_url="https://testserver"), 3, "9999")
    other.post("/logout")
    assert not is_logged_in(other)


def test_deactivated_cashier_does_not_lock_the_register(paid, session):
    user = session.get(User, 1)
    user.is_active = False
    session.add(user)
    session.commit()
    login(paid, 3, "9999")
    assert paid.get("/manager").status_code == 200
