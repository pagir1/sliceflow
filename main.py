from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

import cart
import checkout
import kitchen
import pizza
from core.order_state import Event, Role, TransitionError
from core.payment import parse_dollars, quick_cash_options
from core.pricing import SIZE_PRICE
from db import create_db, get_session
from models import MenuItem, Order, Topping
from seed import seed

create_db()
seed()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
templates.env.filters["money"] = lambda cents: f"${cents // 100}.{cents % 100:02d}"


def active_toppings(session: Session) -> list[Topping]:
    return session.exec(select(Topping).where(Topping.is_active).order_by(Topping.id)).all()


def ticket_context(session: Session, message: str = "", error: str = "") -> dict:
    order = cart.get_or_create_draft(session)
    context = cart.ticket(session, order)
    context["cash_options"] = quick_cash_options(context["total"]) if context["lines"] else []
    context["message"] = message
    context["error"] = error
    return context


def render_ticket(request: Request, session: Session, message: str = "", error: str = ""):
    return templates.TemplateResponse(request, "partials/ticket.html",
                                      ticket_context(session, message, error))


@app.get("/", response_class=HTMLResponse)
def cashier_screen(request: Request, session: Session = Depends(get_session)):
    sides = session.exec(select(MenuItem).where(MenuItem.category == "side", MenuItem.is_active)).all()
    drinks = session.exec(select(MenuItem).where(MenuItem.category == "drink", MenuItem.is_active)).all()
    sizes = [(code, pizza.SIZE_NAMES[code], price) for code, price in SIZE_PRICE.items()]
    context = {
        "sides": sides,
        "drinks": drinks,
        "sizes": sizes,
        "toppings": active_toppings(session),
        "pizza": pizza.build_view("L", []),
        "pickup": kitchen.ready_for_pickup(session),
        **ticket_context(session),
    }
    return templates.TemplateResponse(request, "index.html", context)


@app.post("/pizza/preview", response_class=HTMLResponse)
async def pizza_preview(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    try:
        selections = pizza.read_selections(form, active_toppings(session))
        view = pizza.build_view(form.get("size", "L"), selections)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pizza")
    return templates.TemplateResponse(request, "partials/pizza_preview.html", {"pizza": view})


@app.post("/cart/add-pizza", response_class=HTMLResponse)
async def add_pizza_to_cart(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    order = cart.get_or_create_draft(session)
    try:
        selections = pizza.read_selections(form, active_toppings(session))
        cart.add_pizza(session, order, form.get("size", "L"), selections)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@app.post("/cart/add/{item_id}", response_class=HTMLResponse)
def add_to_cart(item_id: int, request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        cart.add_menu_item(session, order, item_id)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@app.post("/cart/remove/{line_id}", response_class=HTMLResponse)
def remove_from_cart(line_id: int, request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        cart.remove_one(session, order, line_id)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@app.post("/cart/clear", response_class=HTMLResponse)
def clear_cart(request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        cart.clear(session, order)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@app.post("/checkout/cash", response_class=HTMLResponse)
async def pay_with_cash(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    order = cart.get_or_create_draft(session)
    try:
        if form.get("tendered_cents"):
            tendered = int(form["tendered_cents"])
        else:
            tendered = parse_dollars(form.get("tendered", ""))
        checkout.pay_cash(session, order, tendered)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@app.post("/checkout/card", response_class=HTMLResponse)
def pay_with_card(request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        checkout.pay_card(session, order)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@app.post("/order/send", response_class=HTMLResponse)
def send_order_to_kitchen(request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        checkout.send_to_kitchen(session, order)
    except TransitionError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session, message=f"Order #{order.id} sent to the kitchen")


# ---------------- Kitchen display ----------------

KITCHEN_ACTIONS = {"start": Event.START_COOKING, "ready": Event.MARK_READY}


def render_board(request: Request, session: Session, error: str = ""):
    context = {**kitchen.board(session), "error": error}
    return templates.TemplateResponse(request, "partials/kitchen_board.html", context)


@app.get("/kitchen", response_class=HTMLResponse)
def kitchen_screen(request: Request, session: Session = Depends(get_session)):
    context = {**kitchen.board(session), "error": ""}
    return templates.TemplateResponse(request, "kitchen.html", context)


@app.get("/kitchen/board", response_class=HTMLResponse)
def kitchen_board(request: Request, session: Session = Depends(get_session)):
    return render_board(request, session)


@app.post("/kitchen/{order_id}/{action}", response_class=HTMLResponse)
def kitchen_action(order_id: int, action: str, request: Request,
                   session: Session = Depends(get_session)):
    if action not in KITCHEN_ACTIONS:
        raise HTTPException(status_code=404, detail="Unknown action")
    try:
        kitchen.advance(session, order_id, KITCHEN_ACTIONS[action], Role.KITCHEN)
    except (ValueError, TransitionError) as e:
        return render_board(request, session, error=str(e))
    return render_board(request, session)


# ---------------- Pickup (cashier side) ----------------

def render_pickup(request: Request, session: Session, message: str = "", error: str = ""):
    context = {"pickup": kitchen.ready_for_pickup(session), "message": message, "error": error}
    return templates.TemplateResponse(request, "partials/pickup.html", context)


@app.get("/pickup", response_class=HTMLResponse)
def pickup_panel(request: Request, session: Session = Depends(get_session)):
    return render_pickup(request, session)


@app.post("/pickup/{order_id}/pay/{method}", response_class=HTMLResponse)
def pickup_pay(order_id: int, method: str, request: Request,
               session: Session = Depends(get_session)):
    order = session.get(Order, order_id)
    try:
        if order is None or order.state != "READY":
            raise ValueError("This order is not waiting for pickup")
        if method == "card":
            checkout.pay_card(session, order)
        elif method == "cash":
            checkout.pay_cash(session, order, checkout.order_total(session, order))
        else:
            raise ValueError("Unknown payment method")
    except ValueError as e:
        return render_pickup(request, session, error=str(e))
    return render_pickup(request, session)


@app.post("/pickup/{order_id}/hand-over", response_class=HTMLResponse)
def pickup_hand_over(order_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        kitchen.advance(session, order_id, Event.HAND_OVER, Role.CASHIER)
    except (ValueError, TransitionError) as e:
        return render_pickup(request, session, error=str(e))
    return render_pickup(request, session, message=f"Order #{order_id} handed over. Enjoy!")