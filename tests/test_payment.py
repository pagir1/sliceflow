import pytest
from core.payment import parse_dollars, cash_change, quick_cash_options


@pytest.mark.parametrize("text, cents", [
    ("20", 2000), ("22.66", 2266), ("$30.5", 3050), (" 7.05 ", 705),
    ("0.99", 99), (".5", 50), ("1,000", 100000),
])
def test_parse_dollars_valid(text, cents):
    assert parse_dollars(text) == cents


@pytest.mark.parametrize("text", ["", "abc", "1.2.3", "-5", "10.999", "12a"])
def test_parse_dollars_invalid(text):
    with pytest.raises(ValueError):
        parse_dollars(text)


def test_cash_change_normal():
    assert cash_change(2266, 3000) == 734


def test_cash_change_exact():
    assert cash_change(2266, 2266) == 0


def test_cash_short_by_one_cent_is_rejected():
    # INV-4: amount given must be >= total
    with pytest.raises(ValueError):
        cash_change(2266, 2265)


def test_quick_options_for_22_66():
    assert quick_cash_options(2266) == [2266, 2500, 3000, 5000, 10000]


def test_quick_options_never_below_total():
    for total in [1, 499, 500, 1999, 2000, 9999, 12345]:
        assert all(o >= total for o in quick_cash_options(total))