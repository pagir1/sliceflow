from core.pricing import SIZE_PRICE, SIDES, pizza_price

SIZE_NAMES = {"S": "Small", "M": "Medium", "L": "Large"}
SIDE_NAMES = {"LEFT": "Left half", "RIGHT": "Right half", "WHOLE": "Whole"}

TOPPING_COLORS = {
    "Pepperoni": "#b91c1c", "Mushroom": "#a8a29e", "Onion": "#c4b5fd",
    "Green Pepper": "#16a34a", "Black Olive": "#1f2937", "Sausage": "#7c2d12",
    "Bacon": "#f87171", "Extra Cheese": "#fde047", "Jalapeno": "#65a30d",
    "Pineapple": "#facc15", "Spinach": "#14532d", "Tomato": "#ef4444",
}

# Places for topping dots on the LEFT half of a 240 x 240 pizza.
# The right half uses the mirror image (x becomes 240 - x).
LEFT_SPOTS = [
    (100, 56), (66, 78), (90, 74), (104, 96), (72, 102),
    (52, 124), (88, 120), (104, 140), (66, 146), (88, 160),
    (104, 182), (76, 180), (56, 100), (84, 96), (60, 166),
]


def read_selections(form, toppings) -> list[tuple[str, str]]:
    """Turn the builder form into a list like [("Pepperoni", "LEFT"), ...]."""
    selections = []
    for t in toppings:
        side = form.get(f"t_{t.id}", "NONE")
        if side == "NONE":
            continue
        if side not in SIDES:
            raise ValueError(f"Unknown side: {side}")
        selections.append((t.name, side))
    return selections


def describe(selections: list[tuple[str, str]]) -> str:
    if not selections:
        return "Cheese only"
    return ", ".join(f"{name} ({SIDE_NAMES[side]})" for name, side in selections)


def topping_dots(selections: list[tuple[str, str]]) -> list[dict]:
    dots = []
    n = len(LEFT_SPOTS)
    for k, (name, side) in enumerate(selections):
        color = TOPPING_COLORS.get(name, "#ea580c")
        for j in range(3):
            x, y = LEFT_SPOTS[(k + j * 5) % n]
            if side in ("LEFT", "WHOLE"):
                dots.append({"x": x, "y": y, "color": color})
            if side in ("RIGHT", "WHOLE"):
                dots.append({"x": 240 - x, "y": y, "color": color})
    return dots


def build_view(size: str, selections: list[tuple[str, str]]) -> dict:
    if size not in SIZE_PRICE:
        raise ValueError(f"Unknown size: {size}")
    return {
        "size": size,
        "size_name": SIZE_NAMES[size],
        "price": pizza_price(size, selections),
        "dots": topping_dots(selections),
        "chosen": [(name, SIDE_NAMES[side], TOPPING_COLORS.get(name, "#ea580c"))
                   for name, side in selections],
        "summary": describe(selections),
    }