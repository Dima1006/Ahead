"""Waitlist: sign-up, duplicates, spam protection, admin numbers and export. Run: python3 tests/test_waitlist.py (from web/)"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pgtest
os.environ.update(DATABASE_URL=pgtest.fresh_database(), SECRET_KEY="t" * 40, ADMIN_PASSWORD="adminpass-123",
                  BASE_URL="https://testserver")
from starlette.testclient import TestClient
from app import config as cfg, db, maintenance
from app.security import limiter
from app.main import app
B = "https://testserver"


def csrf(c, path="/waitlist"):
    return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text).group(1)


def run(sql, *a):
    conn = db.connect()
    try:
        return conn.execute(sql, a).fetchall()
    finally:
        conn.close()


def total():
    return run("SELECT COUNT(*) FROM waitlist")[0][0]


with TestClient(app, base_url=B, headers={"accept-language": "en"}) as c:
    assert "/waitlist" in c.get("/").text
    page = c.get("/waitlist").text
    assert "Join the waitlist" in page and "people have already joined" not in page

    def join(**extra):
        data = {"csrf": csrf(c), "email": "Ola@Example.pl", "city": "Warsaw", "shop": "Kawa, Prosta 1", "consent": "1"}
        data.update(extra)
        return c.post("/waitlist", data=data, follow_redirects=False)

    assert c.post("/waitlist", data={"email": "a@b.pl", "city": "x", "consent": "1"}).status_code == 403   # no CSRF
    assert join(consent="").status_code == 400 and join(email="nope").status_code == 400 and join(city="  ").status_code == 400
    assert total() == 0
    assert join(website="spam").status_code == 303 and total() == 0          # honeypot
    first = join()
    assert first.status_code == 303 and first.headers["location"] == "/waitlist?joined=1" and total() == 1
    again = join(email="ola@example.pl", city="Krakow", shop="Other")        # same person, other capitals
    assert again.status_code == 303 and again.headers["location"] == first.headers["location"] and total() == 1
    assert run("SELECT city FROM waitlist")[0][0] == "Warsaw"                 # nobody can overwrite an entry

    limiter.reset()
    for i in range(cfg.WAITLIST_PER_HOUR):
        assert join(email=f"p{i}@example.pl", city="warsaw", shop="", name="=HYPERLINK(1)" if i == 0 else "").status_code == 303
    assert join(email="late@example.pl").status_code == 429
    n = total()
    assert n == 1 + cfg.WAITLIST_PER_HOUR
    assert f"<strong>{n}</strong>" in c.get("/waitlist").text                 # the real number, once it is big enough

    assert c.get("/admin/waitlist.csv", follow_redirects=False).headers["location"] == "/admin/login"
    entry = run("SELECT id FROM waitlist ORDER BY id LIMIT 1")[0][0]
    assert c.post(f"/admin/waitlist/{entry}/delete", data={"csrf": csrf(c)}, follow_redirects=False).headers["location"] == "/admin/login"
    assert total() == n

with TestClient(app, base_url=B, headers={"accept-language": "en"}) as a:
    a.post("/admin/login", data={"csrf": csrf(a, "/admin/login"), "password": "adminpass-123"})
    html = a.get("/admin").text
    assert f"<strong>{n}</strong>" in html and "Kawa, Prosta 1" in html
    assert re.search(r'Warsaw</span><span class="badge">%d<|warsaw</span><span class="badge">%d<' % (n, n), html), "cities are grouped"
    out = a.get("/admin/waitlist.csv")
    assert out.headers["content-type"].startswith("text/csv") and "ola@example.pl" in out.text
    assert "'=HYPERLINK(1)" in out.text
    a.post(f"/admin/waitlist/{entry}/delete", data={"csrf": csrf(a, "/admin")})
    assert total() == n - 1

run("UPDATE waitlist SET created_at = '2000-01-01 00:00:00' WHERE email = 'p0@example.pl'")
import asyncio
asyncio.run(maintenance.expire())
assert total() == n - 2, "old entries are deleted"

# An older database (schema version 1) gets the new table on start.
run("DROP TABLE waitlist"); run("UPDATE schema_meta SET version = 1")
db.init_db()
assert total() == 0
print("WAITLIST OK")
