"""BusBook: a small, predictable site for the live demo."""
import uuid
from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/bus", default_response_class=HTMLResponse)

BUSES = [
    {"id": "1", "name": "CityLink 6:30 AM", "price": 24},
    {"id": "2", "name": "Express 9:15 AM", "price": 31},
    {"id": "3", "name": "NightRider 11:00 PM", "price": 19},
]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>BusBook</title>
<style>body{{font-family:system-ui;max-width:560px;margin:40px auto;padding:0 16px}}
label{{display:block;margin:8px 0}}li{{margin:8px 0}}</style></head><body>{body}</body></html>"""


def _page(body: str) -> str:
    return PAGE.format(body=body)


@router.get("")
async def search():
    return _page("""<h1>BusBook</h1>
    <form action="/bus/results">
      <label>From <input name="src"></label>
      <label>To <input name="dst"></label>
      <button>Search</button>
    </form>""")


@router.get("/results")
async def results(src: str = "", dst: str = ""):
    rows = "".join(
        f'<li>{b["name"]}, ${b["price"]} <a href="/bus/hold?id={b["id"]}">Hold seat {b["id"]}</a></li>'
        for b in BUSES
    )
    return _page(f"<h1>{escape(src)} to {escape(dst)}</h1><p>Tomorrow</p><ul>{rows}</ul>")


@router.get("/hold")
async def hold(id: str, name: str = ""):
    bus = next((b for b in BUSES if b["id"] == id), None)
    if not bus:
        return _page("<h1>No such bus</h1>")
    if not name:
        return _page(f"""<h1>Hold seat on {bus["name"]}</h1>
        <form action="/bus/hold">
          <input type="hidden" name="id" value="{escape(id)}">
          <label>Passenger name <input name="name"></label>
          <button>Confirm hold</button>
        </form>""")
    code = uuid.uuid4().hex[:5].upper()
    return _page(
        f"<h1>Seat held</h1><p>{escape(name)}, {bus['name']}, ${bus['price']}. "
        f"Code {code}. Pay at the counter.</p>"
    )
