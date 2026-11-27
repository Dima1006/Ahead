"""Odd input must never cause a server error. Run: python3 tests/test_errors.py (from web/)"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pgtest
os.environ.update(DATABASE_URL=pgtest.fresh_database(), SECRET_KEY="t" * 40, DEMO_SEED="1",
                  DEMO_PASSWORD="demo-pass-12345", BASE_URL="https://testserver")
from starlette.testclient import TestClient
from app.main import app

with TestClient(app, base_url="https://testserver", raise_server_exceptions=False, headers={"accept-language": "en"}) as c:
    def csrf(path):
        return re.search(r'name="csrf" value="([^"]+)"', c.get(path).text).group(1)

    def never_500():
        for path in ("/v/nope", "/v/%00", "/media/%00", "/verify/%00", "/reset/%00", "/lang/%00", "/?q=%00",
                     "/order/999", "/v/wood-coffee?reorder=%C2%B2", "/v/wood-coffee?reorder=99999999999999999999",
                     "/login/code/verify?email=%00", "/nope"):
            assert c.get(path).status_code < 500, path

    never_500()
    r = c.post("/signup", data={"csrf": csrf("/signup"), "name": "Ola", "email": "o@example.pl",
                                "password": "correct-horse-1", "agree": "1"})
    assert r.status_code == 200
    never_500()   # error pages for a signed-in visitor
    page = c.get("/v/nope")
    assert page.status_code == 404 and "Ola" in page.text
    for cart in ('[{"variant_id": Infinity, "qty": 1}]', '[{"variant_id": 1, "qty": NaN}]', "[" * 20000, "{}", "null",
                 '[{"variant_id": 99999999999999999999, "qty": 1}]'):
        r = c.post("/v/wood-coffee/order", data={"csrf": csrf("/v/wood-coffee"), "arrival_minutes": "15", "cart": cart})
        assert r.status_code < 500, (cart[:60], r.status_code)
    # Without e-mail the reset page says so instead of promising a message.
    for path in ("/forgot", "/venue/forgot"):
        assert "not available yet" in c.get(path).text
print("ERRORS OK")
