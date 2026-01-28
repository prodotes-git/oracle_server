from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import os

router = APIRouter()

def render_template(filename: str):
    path = os.path.join("templates", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"Template {filename} not found"

@router.get("/local-currency", response_class=HTMLResponse)
def local_currency_page():
    return HTMLResponse(content=render_template("local_currency_map.html"))
