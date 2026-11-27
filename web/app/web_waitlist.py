"""Waitlist: people who want to use the service before coffee shops join it. The owner sees the real numbers in
/admin and shows coffee shops the totals only (never names or e-mail addresses)."""
import csv
import io

from starlette.exceptions import HTTPException
from starlette.responses import Response

from . import config as cfg
from .core import go, read_form, render, require_admin, route
from .legal import CAPTCHA_ERROR, captcha_ok
from .security import client_ip, limiter
from .utils import clean, valid_email

DONE = "You are on the waitlist. Thank you!"


def count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]


def _page(request, conn, status: int = 200, **ctx):
    total = count(conn)
    # The public number is always the real one; a very small number is simply not shown.
    return render(request, "waitlist.html", status, total=total if total >= cfg.WAITLIST_SHOW_FROM else 0, **ctx)


@route
async def waitlist(request, conn):
    if request.method == "GET":
        return _page(request, conn, form={}, joined=request.query_params.get("joined") == "1")
    form = await read_form(request)
    data = {"email": clean(str(form.get("email", "")), 254).lower(), "name": clean(str(form.get("name", "")), 60),
            "city": clean(str(form.get("city", "")), 60), "shop": clean(str(form.get("shop", "")), 80)}
    if form.get("website"):   # honeypot: only bots fill it. Pretend it worked.
        return go(request, "/waitlist?joined=1", msg=DONE)
    if not limiter.allow_shared(f"waitlist:{client_ip(request)}", cfg.WAITLIST_PER_HOUR, 3600):
        raise HTTPException(429, "Too many sign-ups from your network. Please try again later.")
    if not await captcha_ok(request, form):
        error = CAPTCHA_ERROR
    elif not valid_email(data["email"]):
        error = "Enter a valid email address."
    elif not data["city"]:
        error = "Enter your city."
    elif not form.get("consent"):
        error = "Please tick the box to join the waitlist."
    else:
        error = None
    if error:
        return _page(request, conn, 400, form=data, error=error)
    with conn:
        # An address already on the list gets the same answer, so nobody can find out who signed up,
        # and its entry is left as it was, so nobody can overwrite another person's answers.
        conn.execute("INSERT INTO waitlist (email, name, city, shop) VALUES (?, ?, ?, ?) ON CONFLICT (email) DO NOTHING",
                     (data["email"], data["name"], data["city"], data["shop"]))
    return go(request, "/waitlist?joined=1", msg=DONE)


def stats(conn) -> dict:
    def grouped(column: str):   # "column" is one of two constants below, never user input
        return conn.execute(
            f"SELECT MIN({column}) AS label, COUNT(*) AS n FROM waitlist WHERE {column} <> '' "
            f"GROUP BY norm({column}) ORDER BY n DESC, label LIMIT 15").fetchall()
    return {"total": count(conn),
            "week": conn.execute("SELECT COUNT(*) FROM waitlist WHERE created_at >= utc_text('-7 days')").fetchone()[0],
            "cities": grouped("city"), "shops": grouped("shop"),
            "latest": conn.execute("SELECT * FROM waitlist ORDER BY id DESC LIMIT 100").fetchall()}


def _cell(value) -> str:
    """Spreadsheets run cells that start like a formula: neutralise them."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@route
async def admin_export(request, conn):
    require_admin(request)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["email", "name", "city", "coffee_shop", "joined_utc"])
    for row in conn.execute("SELECT email, name, city, shop, created_at FROM waitlist ORDER BY id"):
        writer.writerow([_cell(v) for v in row])
    return Response("﻿" + out.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="waitlist.csv"', "Cache-Control": "no-store"})


@route
async def admin_delete(request, conn):
    await read_form(request)
    require_admin(request)
    with conn:
        conn.execute("DELETE FROM waitlist WHERE id = ?", (request.path_params["entry_id"],))
    return go(request, "/admin", msg="Removed from the waitlist.")
