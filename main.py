from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func

from db import create_db, get_session
from models import Topping, MenuItem, Order
from seed import seed

create_db()
seed()

app = FastAPI()
templates = Jinja2Templates(directory="templates")
templates.env.filters["money"] = lambda cents: f"${cents // 100}.{cents % 100:02d}"


def count_orders(session: Session) -> int:
    return session.exec(select(func.count(Order.id))).one()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, session: Session = Depends(get_session)):
    toppings = session.exec(select(Topping).where(Topping.is_active)).all()
    sides = session.exec(select(MenuItem).where(MenuItem.category == "side")).all()
    drinks = session.exec(select(MenuItem).where(MenuItem.category == "drink")).all()
    return templates.TemplateResponse(request, "index.html", {
        "count": count_orders(session),
        "toppings": toppings,
        "sides": sides,
        "drinks": drinks,
    })


@app.post("/order", response_class=HTMLResponse)
def order_pizza(session: Session = Depends(get_session)):
    session.add(Order())
    session.commit()
    return f"Orders in database: {count_orders(session)}"