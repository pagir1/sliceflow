from datetime import date

from fastapi import APIRouter, FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from starlette.middleware.sessions import SessionMiddleware

import auth
import cart
import checkout
import config
import display
import kitchen
import manager
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
                   secret_key=config.SECRET,
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


CASHIER_ROLES = ("CASHIER", "MANAGER")
cashier_routes = APIRouter(dependencies=[Depends(require(*CASHIER_ROLES))])
kitchen_routes = APIRouter(dependencies=[Depends(require("KITCHEN", "MANAGER"))])
manager_routes = APIRouter(dependencies=[Depends(require("MANAGER"))])


@app.get("/login", response_class=HTMLResponse)
def login_screen(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "login.html",
                                      {"staff": auth.active_staff(session), "error": "", "chosen": None})


def has_paid_unsent_order(request: Request, session: Session) -> bool:
    """Leaving now would lose an order the customer already paid for."""
    user = session.get(User, request.session.get("user_id") or 0)
    if user is None or not user.is_active or user.role not in CASHIER_ROLES:
        return False                                   # this user could not send it anyway
    order = session.get(Order, request.session.get("draft_order_id") or 0)
    return order is not None and order.state == "DRAFT" and order.is_paid


def back_to_paid_order(request: Request):
    request.session["notice"] = "This order is paid. Send it to the kitchen before logging out."
    return RedirectResponse("/", status_code=303)


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, session: Session = Depends(get_session)):
    if has_paid_unsent_order(request, session):        # a new login would replace this session
        return back_to_paid_order(request)
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
def logout(request: Request, session: Session = Depends(get_session)):
    if has_paid_unsent_order(request, session):
        return back_to_paid_order(request)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def active_toppings(session: Session) -> list[Topping]:
    return session.exec(select(Topping).where(Topping.is_active).order_by(Topping.id)).all()


def current_draft(request: Request, session: Session) -> Order:
    """The draft order of this logged-in register; its id lives in the login session."""
    order = cart.get_or_create_draft(session, request.session.get("draft_order_id"))
    request.session["draft_order_id"] = order.id
    return order


def ticket_context(request: Request, session: Session, message: str = "", error: str = "",
                   sent_qr: str = "", sent_url: str = "") -> dict:
    order = current_draft(request, session)
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
                                      ticket_context(request, session, message, error, sent_qr, sent_url))


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
        **ticket_context(request, session, error=request.session.pop("notice", "")),
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
    order = current_draft(request, session)
    try:
        selections = pizza.read_selections(form, active_toppings(session))
        cart.add_pizza(session, order, form.get("size", "L"), selections)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/cart/add/{item_id}", response_class=HTMLResponse)
def add_to_cart(item_id: int, request: Request, session: Session = Depends(get_session)):
    order = current_draft(request, session)
    try:
        cart.add_menu_item(session, order, item_id)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/cart/remove/{line_id}", response_class=HTMLResponse)
def remove_from_cart(line_id: int, request: Request, session: Session = Depends(get_session)):
    order = current_draft(request, session)
    try:
        cart.remove_one(session, order, line_id)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/cart/clear", response_class=HTMLResponse)
def clear_cart(request: Request, session: Session = Depends(get_session)):
    order = current_draft(request, session)
    try:
        cart.clear(session, order)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/checkout/cash", response_class=HTMLResponse)
async def pay_with_cash(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    order = current_draft(request, session)
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
    order = current_draft(request, session)
    try:
        checkout.pay_card(session, order)
    except ValueError as e:
        return render_ticket(request, session, error=str(e))
    return render_ticket(request, session)


@cashier_routes.post("/order/send", response_class=HTMLResponse)
def send_order_to_kitchen(request: Request, session: Session = Depends(get_session)):
    order = current_draft(request, session)
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


# ---------------- Manager ----------------

def parse_day(text: str | None) -> date:
    try:
        return date.fromisoformat(text) if text else manager.today_local()
    except ValueError:
        return manager.today_local()


def render_void_list(request: Request, session: Session, message: str = "", error: str = ""):
    context = {"voidable": manager.voidable_orders(session), "message": message, "error": error}
    return templates.TemplateResponse(request, "partials/void_list.html", context)


def render_paid_list(request: Request, session: Session, message: str = "", error: str = ""):
    context = {"paid_unsent": manager.paid_unsent_orders(session),
               "paid_message": message, "paid_error": error}
    return templates.TemplateResponse(request, "partials/paid_list.html", context)


def render_menu_editor(request: Request, session: Session, message: str = "", error: str = ""):
    context = {**manager.menu_for_editing(session), "menu_message": message, "menu_error": error}
    return templates.TemplateResponse(request, "partials/menu_editor.html", context)


@manager_routes.get("/manager", response_class=HTMLResponse)
def manager_screen(request: Request, day: str | None = None,
                   session: Session = Depends(get_session)):
    context = {"report": manager.daily_report(session, parse_day(day)),
               "voidable": manager.voidable_orders(session), "message": "", "error": "",
               "paid_unsent": manager.paid_unsent_orders(session),
               "paid_message": "", "paid_error": "",
               **manager.menu_for_editing(session), "menu_message": "", "menu_error": ""}
    return templates.TemplateResponse(request, "manager.html", context)


@manager_routes.get("/manager/report", response_class=HTMLResponse)
def manager_report(request: Request, day: str | None = None,
                   session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "partials/report.html",
                                      {"report": manager.daily_report(session, parse_day(day))})


@manager_routes.get("/manager/voidable", response_class=HTMLResponse)
def manager_voidable(request: Request, session: Session = Depends(get_session)):
    return render_void_list(request, session)


@manager_routes.post("/manager/paid/{order_id}/send", response_class=HTMLResponse)
def manager_send_paid(order_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        manager.send_paid_order(session, order_id)
    except (ValueError, TransitionError) as e:
        return render_paid_list(request, session, error=str(e))
    response = render_paid_list(request, session, message=f"Order #{order_id} sent to the kitchen")
    response.headers["HX-Trigger"] = "report-changed, orders-changed"   # it is an open order now
    return response


@manager_routes.post("/manager/paid/{order_id}/void", response_class=HTMLResponse)
async def manager_void_paid(order_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    order = session.get(Order, order_id)
    try:
        if order is None or order.state != "DRAFT":        # sent since this page was loaded
            raise ValueError(f"Order #{order_id} is not waiting to be sent")
        manager.void_order(session, order_id, form.get("reason", ""), request.state.user)
    except (ValueError, TransitionError) as e:
        return render_paid_list(request, session, error=str(e))
    response = render_paid_list(request, session,
                                message=f"Order #{order_id} voided. Give the money back.")
    response.headers["HX-Trigger"] = "report-changed"
    return response


@manager_routes.post("/manager/void/{order_id}", response_class=HTMLResponse)
async def manager_void(order_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    try:
        manager.void_order(session, order_id, form.get("reason", ""), request.state.user)
    except (ValueError, TransitionError) as e:
        return render_void_list(request, session, error=str(e))
    response = render_void_list(request, session, message=f"Order #{order_id} voided")
    response.headers["HX-Trigger"] = "report-changed"     # tell the report to reload itself
    return response


@manager_routes.post("/manager/menu/{item_id}/price", response_class=HTMLResponse)
async def manager_set_price(item_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    try:
        item = manager.update_price(session, item_id, form.get("price", ""))
    except ValueError as e:
        return render_menu_editor(request, session, error=str(e))
    return render_menu_editor(request, session, message=f"{item.name} now costs ${item.price_cents // 100}.{item.price_cents % 100:02d}")


@manager_routes.post("/manager/menu/{item_id}/toggle", response_class=HTMLResponse)
def manager_toggle_item(item_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        item = manager.toggle_item(session, item_id)
    except ValueError as e:
        return render_menu_editor(request, session, error=str(e))
    state = "shown on" if item.is_active else "hidden from"
    return render_menu_editor(request, session, message=f"{item.name} is {state} the menu")


@manager_routes.post("/manager/topping/{topping_id}/toggle", response_class=HTMLResponse)
def manager_toggle_topping(topping_id: int, request: Request, session: Session = Depends(get_session)):
    try:
        topping = manager.toggle_topping(session, topping_id)
    except ValueError as e:
        return render_menu_editor(request, session, error=str(e))
    state = "shown on" if topping.is_active else "hidden from"
    return render_menu_editor(request, session, message=f"{topping.name} is {state} the menu")


# Routers are added last, after all their routes are defined.
app.include_router(cashier_routes)
app.include_router(kitchen_routes)
app.include_router(manager_routes)