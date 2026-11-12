from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")

pizza_count = 0


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"count": pizza_count})


@app.post("/order", response_class=HTMLResponse)
def order_pizza():
    global pizza_count
    pizza_count += 1
    return f"Pizzas ordered: {pizza_count}"