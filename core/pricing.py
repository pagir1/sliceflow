# All money is in CENTS (whole numbers). 1699 means $16.99.

SIZE_PRICE = {"S": 1099, "M": 1399, "L": 1699}
TOPPING_PRICE = {"S": 100, "M": 150, "L": 175}
SIDES = ("LEFT", "RIGHT", "WHOLE")


def topping_cost(size: str, side: str) -> int:
    if size not in SIZE_PRICE:
        raise ValueError(f"Unknown size: {size}")
    if side not in SIDES:
        raise ValueError(f"Unknown side: {side}")
    full = TOPPING_PRICE[size]
    if side == "WHOLE":
        return full
    return (full + 1) // 2  # half price, rounded UP to the next cent


def pizza_price(size: str, toppings: list[tuple[str, str]]) -> int:
    price = SIZE_PRICE[size]
    for name, side in toppings:
        price += topping_cost(size, side)
    return price


def tax_cents(subtotal: int, rate_basis_points: int = 600) -> int:
    # 600 basis points = 6.00 %. Rounds half a cent UP.
    return (subtotal * rate_basis_points + 5000) // 10000


def order_totals(lines: list[tuple[int, int]]) -> dict:
    # lines = list of (unit_price_cents, quantity)
    subtotal = 0
    for unit_price, quantity in lines:
        if quantity < 1:
            raise ValueError(f"Quantity must be at least 1, got {quantity}")
        subtotal += unit_price * quantity

    tax = tax_cents(subtotal)
    total = subtotal + tax

    return {"subtotal": subtotal, "tax": tax, "total": total}