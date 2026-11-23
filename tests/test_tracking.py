import itertools

import pytest

import cart
import checkout
import kitchen
import pizza
import tracking
from core.order_state import Event, Role


def test_token_is_valid_only_for_its_own_order():
    token = tracking.token_for(5)
    assert tracking.is_valid(5, token)
    assert not tracking.is_valid(6, token)          # cannot reuse it for another order
    assert not tracking.is_valid(5, "0" * 16)       # cannot guess it


def test_track_path_contains_id_and_token():
    assert tracking.track_path(7) == f"/track/7/{tracking.token_for(7)}"


def test_qr_svg_is_an_svg_with_pixel_size():
    svg = tracking.qr_svg("http://192.168.1.20:8000/track/1/abc", size_px=160)
    assert svg.startswith("<svg") and 'width="160" height="160"' in svg


def test_parse_details_round_trip():
    # describe() and parse_details() must be exact opposites
    names = ["Pepperoni", "Green Pepper", "Black Olive"]
    sides = ["LEFT", "RIGHT", "WHOLE"]
    for count in range(len(names) + 1):
        for chosen in itertools.permutations(names, count):
            for side_combo in itertools.product(sides, repeat=count):
                selections = list(zip(chosen, side_combo))
                assert pizza.parse_details(pizza.describe(selections)) == selections


def test_parse_details_rejects_garbage():
    with pytest.raises(ValueError):
        pizza.parse_details("Pepperoni (Middle)")


def test_size_from_line_name():
    assert pizza.size_from_line_name("Large Pizza") == "L"
    with pytest.raises(ValueError):
        pizza.size_from_line_name("Coke")


def test_tracker_follows_the_order(session):
    order = cart.get_or_create_draft(session)
    cart.add_pizza(session, order, "M", [("Pepperoni", "LEFT")])
    cart.add_menu_item(session, order, 1)            # Coke
    checkout.pay_card(session, order)
    checkout.send_to_kitchen(session, order)

    view = tracking.tracker_view(session, order)
    assert view["stage_index"] == 0                  # Order received
    assert view["pizzas"][0]["size_name"] == "Medium"
    assert view["pizzas"][0]["chosen"][0][:2] == ("Pepperoni", "Left half")
    assert [l.name for l in view["others"]] == ["Coke"]

    kitchen.advance(session, order.id, Event.START_COOKING, Role.KITCHEN)
    assert tracking.tracker_view(session, order)["stage_index"] == 1
    kitchen.advance(session, order.id, Event.MARK_READY, Role.KITCHEN)
    assert tracking.tracker_view(session, order)["stage_index"] == 2
    kitchen.advance(session, order.id, Event.HAND_OVER, Role.CASHIER)
    assert tracking.tracker_view(session, order)["stage_index"] == 3