import hashlib
import hmac
import os
import re

import qrcode
import qrcode.image.svg
from sqlmodel import Session

import cart
import pizza
from models import Order

# Keep this secret on a real server: set the SLICEFLOW_SECRET environment variable.
SECRET = os.environ.get("SLICEFLOW_SECRET", "dev-secret-change-me").encode()

STAGES = [
    ("SUBMITTED", "Order received"),
    ("IN_OVEN", "In the oven"),
    ("READY", "Ready for pickup"),
    ("COMPLETED", "Picked up"),
]


def token_for(order_id: int) -> str:
    """A code only our server can make, so nobody can guess another order's link."""
    return hmac.new(SECRET, str(order_id).encode(), hashlib.sha256).hexdigest()[:16]


def is_valid(order_id: int, token: str) -> bool:
    return hmac.compare_digest(token_for(order_id), token)


def track_path(order_id: int) -> str:
    return f"/track/{order_id}/{token_for(order_id)}"


def qr_svg(url: str, size_px: int = 180) -> str:
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage)
    svg = image.to_string(encoding="unicode")
    # The library uses millimetres; show it in pixels instead.
    return re.sub(r'width="[^"]+" height="[^"]+"',
                  f'width="{size_px}" height="{size_px}"', svg, count=1)


def tracker_view(session: Session, order: Order) -> dict:
    states = [state for state, _ in STAGES]
    stage_index = states.index(order.state) if order.state in states else -1

    pizzas, others = [], []
    for line in cart.get_lines(session, order):
        if line.name.endswith(" Pizza"):
            size = pizza.size_from_line_name(line.name)
            pizzas.append(pizza.build_view(size, pizza.parse_details(line.details)))
        else:
            others.append(line)

    return {
        "order": order,
        "stages": STAGES,
        "stage_index": stage_index,
        "pizzas": pizzas,
        "others": others,
        "token": token_for(order.id),
    }