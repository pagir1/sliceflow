from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

import cart
import pizza
from core.pricing import SIZE_PRICE
from db import create_db, get_session
from models import MenuItem, Topping
from seed import seed

create_db()
seed()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
templates.env.filters["money"] = lambda cents: f"${cents // 100}.{cents % 100:02d}"


def active_toppings(session: Session) -> list[Topping]:
    return session.exec(select(Topping).where(Topping.is_active).order_by(Topping.id)).all()


def render_ticket(request: Request, session: Session):
    order = cart.get_or_create_draft(session)
    return templates.TemplateResponse(request, "partials/ticket.html", cart.ticket(session, order))


@app.get("/", response_class=HTMLResponse)
def cashier_screen(request: Request, session: Session = Depends(get_session)):
    sides = session.exec(select(MenuItem).where(MenuItem.category == "side", MenuItem.is_active)).all()
    drinks = session.exec(select(MenuItem).where(MenuItem.category == "drink", MenuItem.is_active)).all()
    sizes = [(code, pizza.SIZE_NAMES[code], price) for code, price in SIZE_PRICE.items()]
    order = cart.get_or_create_draft(session)
    context = {
        "sides": sides,
        "drinks": drinks,
        "sizes": sizes,
        "toppings": active_toppings(session),
        "pizza": pizza.build_view("L", []),
        **cart.ticket(session, order),
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
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid pizza")
    return render_ticket(request, session)


@app.post("/cart/add/{item_id}", response_class=HTMLResponse)
def add_to_cart(item_id: int, request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    try:
        cart.add_menu_item(session, order, item_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Menu item not found")
    return render_ticket(request, session)


@app.post("/cart/remove/{line_id}", response_class=HTMLResponse)
def remove_from_cart(line_id: int, request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    cart.remove_one(session, order, line_id)
    return render_ticket(request, session)


@app.post("/cart/clear", response_class=HTMLResponse)
def clear_cart(request: Request, session: Session = Depends(get_session)):
    order = cart.get_or_create_draft(session)
    cart.clear(session, order)
    return render_ticket(request, session)