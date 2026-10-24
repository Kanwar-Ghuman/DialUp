"""Harbor Community Clinic: a small, predictable appointment site for the live demo.

Flow: enter patient details -> pick a slot -> review -> "Book appointment" (guarded: needs the caller's yes).
"""
import uuid
from datetime import date, timedelta
from html import escape
from urllib.parse import urlencode

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(prefix="/clinic", default_response_class=HTMLResponse)

REASONS = ["General check-up", "Cough, cold or fever", "Flu or COVID vaccine", "Prescription refill"]

# (days from today, time, doctor, open?) — a mix of mornings, afternoons and full slots
SLOTS = [
    (1, "8:30 AM", "Dr. Maria Lopez", False),
    (1, "2:15 PM", "Dr. Maria Lopez", True),
    (2, "9:00 AM", "Dr. David Chen", True),
    (2, "11:30 AM", "Dr. David Chen", False),
    (3, "10:00 AM", "Dr. Maria Lopez", True),
    (4, "3:45 PM", "Dr. Aisha Patel", True),
]

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Harbor Community Clinic</title>
<style>body{{font-family:system-ui;max-width:600px;margin:40px auto;padding:0 16px}}
label{{display:block;margin:10px 0}}li{{margin:10px 0}}.full{{color:#888}}</style></head>
<body><p><b>Harbor Community Clinic</b> · Free and low-cost care · (demo site)</p>{body}</body></html>"""


def _page(body: str) -> str:
    return PAGE.format(body=body)


def _day(offset: int) -> str:
    """The `offset`-th weekday after today (the clinic is closed on weekends)."""
    d = date.today()
    while offset:
        d += timedelta(days=1)
        if d.weekday() < 5:
            offset -= 1
    return f"{d:%A, %B} {d.day}"


@router.get("")
async def start():
    examples = ", ".join(REASONS).lower()
    return _page(f"""<h1>Book an appointment</h1>
    <form action="/clinic/slots">
      <label>Patient full name <input name="name"></label>
      <label>Date of birth <input name="dob" placeholder="MM/DD/YYYY"></label>
      <label>Reason for visit <input name="reason" placeholder="For example: {escape(examples)}"></label>
      <button>Find appointments</button>
    </form>""")


@router.get("/slots")
async def slots(name: str = "", dob: str = "", reason: str = ""):
    if not name.strip() or not dob.strip():
        return _page('<h1>Missing details</h1><p>Patient name and date of birth are required.</p>'
                     '<p><a href="/clinic">Go back</a></p>')
    rows = []
    for i, (offset, time, doctor, open_) in enumerate(SLOTS):
        when = f"{_day(offset)}, {time}, {doctor}"
        if open_:
            q = urlencode({"slot": i, "name": name, "dob": dob, "reason": reason})
            rows.append(f'<li>{escape(when)} <a href="/clinic/review?{q}">Select {escape(_day(offset).split(",")[0])} {time}</a></li>')
        else:
            rows.append(f'<li class="full">{escape(when)} (full)</li>')
    return _page(f"<h1>Available appointments</h1><p>{escape(reason)} for {escape(name)}</p>"
                 f"<ul>{''.join(rows)}</ul>")


@router.get("/review")
async def review(slot: int, name: str, dob: str, reason: str = ""):
    if not 0 <= slot < len(SLOTS) or not SLOTS[slot][3]:
        return _page("<h1>That time is no longer available</h1><p><a href=\"/clinic\">Start over</a></p>")
    offset, time, doctor, _ = SLOTS[slot]
    q = urlencode({"slot": slot, "name": name, "dob": dob, "reason": reason})
    return _page(f"""<h1>Review appointment</h1>
    <p>{escape(name)} (born {escape(dob)})<br>{escape(reason)}<br>
    {escape(_day(offset))} at {time} with {doctor}</p>
    <p><a href="/clinic/book?{q}">Book appointment</a></p>""")


@router.get("/book")
async def book(slot: int, name: str, dob: str, reason: str = ""):
    if not 0 <= slot < len(SLOTS) or not SLOTS[slot][3]:
        return _page("<h1>That time is no longer available</h1>")
    offset, time, doctor, _ = SLOTS[slot]
    code = uuid.uuid4().hex[:5].upper()
    return _page(
        f"<h1>Appointment booked</h1><p>{escape(name)}, {escape(_day(offset))} at {time} with {doctor}. "
        f"Confirmation {code}. Arrive 10 minutes early and bring any ID. No cost for this visit.</p>"
    )
