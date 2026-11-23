import os

from fastapi import APIRouter, FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

import auth
import cart
import checkout
import display
import kitchen
import pizza
import tracking
from core.order_state import Event, Role, TransitionError
from core.payment import parse_dollars, quick_cash_options
from core.pricing import SIZE_PRICE
from db import create_db, get_session
from models import MenuItem, Order, Topping, User
from seed import seed

create_db()
seed()

app = FastAPI()
app.add_middleware(SessionMiddleware,
                   secret_key=os.environ.get("SLICEFLOW_SECRET", "dev-secret-change-me"),
                   max_age=12 * 60 * 60)          # stay logged in for one 12-hour shift
templates = Jinja2Templates(directory="templates")
templates.env.filters["money"] = lambda cents: f"${cents // 100}.{cents % 100:02d}"


# ---------------- Login and roles ----------------

class LoginRequired(Exception):
    pass


class WrongRole(Exception):
    def __init__(self, user: User):
        self.user = user


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    if request.headers.get("HX-Request"):              # HTMX: ask the browser to go to /login
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(WrongRole)
async def wrong_role_handler(request: Request, exc: WrongRole):
    home = auth.HOME_PAGE[exc.user.role]
    if request.headers.get("HX-Request"):
        return Response(status_code=403, headers={"HX-Redirect": home})
    return templates.TemplateResponse(request, "forbidden.html",
                                      {"user": exc.user, "home": home}, status_code=403)


def require(*roles: str):
    """Make a dependency that lets only these roles in (SR-05, NFR-07)."""
    def check(request: Request, session: Session = Depends(get_session)) -> User:
        user_id = request.session.get("user_id")
        user = session.get(User, user_id) if user_id else None
        if user is None or not user.is_active:
            raise LoginRequired()
        if user.role not in roles:
            raise WrongRole(user)
        request.state.user = user                      # templates can show who is logged in
        return user
    return check


cashier_routes = APIRouter(dependencies=[Depends(require("CASHIER", "MANAGER"))])
kitchen_routes = APIRouter(dependencies=[Depends(require("KITCHEN", "MANAGER"))])


@app.get("/login", response_class=HTMLResponse)
def login_screen(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "login.html",
                                      {"staff": auth.active_staff(session), "error": "", "chosen": None})


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    try:
        user = auth.attempt_login(session, int(form.get("user_id") or 0), form.get("pin", ""))
    except auth.LoginError as e:
        context = {"staff": auth.active_staff(session), "error": str(e),
                   "chosen": int(form.get("user_id") or 0)}
        return templates.TemplateResponse(request, "login.html", context, status_code=401)
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse(auth.HOME_PAGE[user.role], status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def active_toppings(session: Session) -> list[Topping]:
    return session.exec(select(Topping).where(Topping.is_active).order_by(Topping.id)).all()


def ticket_context(session: Session, message: str = "", error: str = "",
                   sent_qr: str = "", sent_url: str = "") -> dict:
    order = cart.get_or_create_draft(session)
    context = cart.ticket(session, order)
    context["cash_options"] = quick_cash_options(context["total"]) if context["lines"] else []
    context["message"] = message
    context["error"] = error
    context["sent_qr"] = sent_qr
    context["sent_url"] = sent_url
    return context


def render_ticket(request: Request, session: Session, message: str = "", error: str = "",
                  sent_qr: str = "", sent_url: str = ""):
    return templates.TemplateResponse(request, "partials/ticket.html",
                                      ticket_context(session, message, error, sent_qr, sent_url))


@cashier_routes.get("/", response_class=HTMLResponse)
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


@cashier_routes.post("/pizza/preview", response_class=HTMLResponse)
async def pizza_preview(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    try:
        selections = pizza.read_selections(form, active_toppings(session))
        view = pizza.build_view(form.get("size", "L"), selections)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pizza")
    return templates.TemplateResponse(request, "partials/pizza_preview.html", {"pizza": view})


@cashier_routes.post("/cart/add-pizza", response_class=HTMLResponse)
async def add_pizza_to_cart(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    order = cart.get_or_create_draft(session)
    try:
        selections = pizza.read_selections(form, active_toppings(session))
        cart.add_pizza(session, order, form.get("size", "L"), selections)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/cart/add/{item_id}", response_class=HTMLResponse)
def add_to_cart(item_id: int, request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        cart.add_menu_item(session, order, item_id)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/cart/remove/{line_id}", response_class=HTMLResponse)
def remove_from_cart(line_id: int, request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        cart.remove_one(session, order, line_id)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/cart/clear", response_class=HTMLResponse)
def clear_cart(request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        cart.clear(session, order)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/checkout/cash", response_class=HTMLResponse)
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


@cashier_routes.post("/checkout/card", response_class=HTMLResponse)
def pay_with_card(request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        checkout.pay_card(session, order)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/order/send", response_class=HTMLResponse)
def send_order_to_kitchen(request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        checkout.send_to_kitchen(session, order)
    except TransitionError as e:
        return render_ticket(request, session, error=str(e))
    url = str(request.base_url).rstrip("/") + tracking.track_path(order.id)
    return render_ticket(request, session, message=f"Order #{order.id} sent to the kitchen",
                         sent_qr=tracking.qr_svg(url), sent_url=url)


# ---------------- Kitchen display ----------------

KITCHEN_ACTIONS = {"start": Event.START_COOKING, "ready": Event.MARK_READY}


def render_board(request: Request, session: Session, error: str = ""):
    context = {**kitchen.board(session), "error": error}
    return templates.TemplateResponse(request, "partials/kitchen_board.html", context)


@kitchen_routes.get("/kitchen", response_class=HTMLResponse)
def kitchen_screen(request: Request, session: Session = Depends(get_session)):
    context = {**kitchen.board(session), "error": ""}
    return templates.TemplateResponse(request, "kitchen.html", context)


@kitchen_routes.get("/kitchen/board", response_class=HTMLResponse)
def kitchen_board(request: Request, session: Session = Depends(get_session)):
    return render_board(request, session)


@kitchen_routes.post("/kitchen/{order_id}/{action}", response_class=HTMLResponse)
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


@cashier_routes.get("/pickup", response_class=HTMLResponse)
def pickup_panel(request: Request, session: Session = Depends(get_session)):
    return render_pickup(request, session)


@cashier_routes.post("/pickup/{order_id}/pay/{method}", response_class=HTMLResponse)
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


@cashier_routes.post("/pickup/{order_id}/hand-over", response_class=HTMLResponse)
def pickup_hand_over(order_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        kitchen.advance(session, order_id, Event.HAND_OVER, Role.CASHIER)
    except (ValueError, TransitionError) as e:
        return render_pickup(request, session, error=str(e))
    return render_pickup(request, session, message=f"Order #{order_id} handed over. Enjoy!")


# ---------------- Customer board (TV) ----------------

@app.get("/board", response_class=HTMLResponse)
def customer_board_screen(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "board.html", display.customer_board(session))


@app.get("/board/live", response_class=HTMLResponse)
def customer_board_live(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "partials/board_live.html",
                                      display.customer_board(session))


# ---------------- Order tracker (customer phone) ----------------

def tracked_order(session: Session, order_id: int, token: str) -> Order:
    order = session.get(Order, order_id)
    if order is None or not tracking.is_valid(order_id, token):
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.get("/track/{order_id}/{token}", response_class=HTMLResponse)
def tracker_screen(order_id: int, token: str, request: Request,
                   session: Session = Depends(get_session)):
    order = tracked_order(session, order_id, token)
    return templates.TemplateResponse(request, "tracker.html", tracking.tracker_view(session, order))


@app.get("/track/{order_id}/{token}/live", response_class=HTMLResponse)
def tracker_live(order_id: int, token: str, request: Request,
                 session: Session = Depends(get_session)):
    order = tracked_order(session, order_id, token)
    return templates.TemplateResponse(request, "partials/tracker_live.html",
                                      tracking.tracker_view(session, order))


# Routers are added last, after all their routes are defined.
app.include_router(cashier_routes)
app.include_router(kitchen_routes)