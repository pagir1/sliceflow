from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

import cart
from db import create_db, get_session
from models import MenuItem
from seed import seed

create_db()
seed()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
templates.env.filters["money"] = lambda cents: f"${cents // 100}.{cents % 100:02d}"


def render_ticket(request: Request, session: Session):
    order = cart.get_or_create_draft(session)
    return templates.TemplateResponse(request, "partials/ticket.html", cart.ticket(session, order))


@app.get("/", response_class=HTMLResponse)
def cashier_screen(request: Request, session: Session = Depends(get_session)):
    sides = session.exec(select(MenuItem).where(MenuItem.category == "side", MenuItem.is_active)).all()
    drinks = session.exec(select(MenuItem).where(MenuItem.category == "drink", MenuItem.is_active)).all()
    order = cart.get_or_create_draft(session)
    context = {"sides": sides, "drinks": drinks, **cart.ticket(session, order)}
    return templates.TemplateResponse(request, "index.html", context)


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