import pytest

import cart
import manager
from models import MenuItem, Topping


def test_update_price_from_text(session):
    item = manager.update_price(session, 1, "2.75")
    assert item.price_cents == 275


@pytest.mark.parametrize("text", ["0", "-1", "abc", "", "250.00", "2.999"])
def test_bad_prices_are_rejected(session, text):
    with pytest.raises(ValueError):
        manager.update_price(session, 1, text)
    assert session.get(MenuItem, 1).price_cents == 249       # nothing changed


def test_price_change_does_not_touch_old_orders(session):
    # INV-8 through the manager's own function
    order = cart.get_or_create_draft(session)
    cart.add_menu_item(session, order, 1)
    manager.update_price(session, 1, "3.99")
    assert cart.get_lines(session, order)[0].unit_price_cents == 249
    new_order_line_price = session.get(MenuItem, 1).price_cents
    assert new_order_line_price == 399


def test_hidden_item_cannot_be_ordered(session):
    manager.toggle_item(session, 1)
    order = cart.get_or_create_draft(session)
    with pytest.raises(ValueError):
        cart.add_menu_item(session, order, 1)
    manager.toggle_item(session, 1)                          # show it again
    cart.add_menu_item(session, order, 1)


def test_toggle_topping(session):
    topping = manager.toggle_topping(session, 1)
    assert topping.is_active is False
    assert manager.toggle_topping(session, 1).is_active is True


def login(client, user_id, pin):
    client.post("/login", data={"user_id": user_id, "pin": pin})


def test_only_manager_can_change_prices(client):
    login(client, 1, "1111")                                 # cashier
    assert client.post("/manager/menu/1/price", data={"price": "0.01"}).status_code == 403
    client.post("/logout")
    login(client, 3, "9999")                                 # manager
    r = client.post("/manager/menu/1/price", data={"price": "2.99"})
    assert "Coke now costs $2.99" in r.text


def test_hidden_topping_leaves_the_cashier_screen(client):
    login(client, 3, "9999")
    client.post("/manager/topping/1/toggle")
    page = client.get("/").text
    assert 'name="t_1"' not in page and 'name="t_2"' in page


def test_void_tells_the_report_to_refresh(client):
    login(client, 3, "9999")
    client.post("/cart/add/1")
    client.post("/order/send")
    r = client.post("/manager/void/1", data={"reason": "test order"})
    assert r.headers["HX-Trigger"] == "report-changed"