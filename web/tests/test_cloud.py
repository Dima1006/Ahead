"""What matters with several server instances (Vercel). Run: python3 tests/test_cloud.py   (from web/)"""
import json, os, subprocess, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pgtest
os.environ.update(DATABASE_URL=pgtest.fresh_database(), SECRET_KEY="t" * 40, DEMO_PASSWORD="demo-pass-12345",
                  DEMO_SEED="1", CRON_SECRET="cron-secret-123", TELEGRAM_WEBHOOK_SECRET="hook-secret-123",
                  TELEGRAM_BOT_TOKEN="1:test")
from starlette.testclient import TestClient
from app import config as cfg, db, loyalty, orders, realtime, seed, telegram
from app.security import limiter

db.init_db(); seed.seed_demo()


def run(sql, *a):
    conn = db.connect()
    try:
        return conn.execute(sql, a).fetchall()
    finally:
        conn.close()


run("UPDATE venues SET open_time='00:00', close_time='00:00', prep_minutes=5, welcome_free=1, max_active=3 WHERE id=1")
users = []
for i in range(8):
    users.append(run("INSERT INTO users (email, name, email_verified) VALUES (?, 'T', 1) RETURNING id", f"u{i}@example.pl")[0][0])
variant = run("SELECT v.id FROM variants v JOIN items i ON i.id=v.item_id WHERE i.venue_id=1 AND i.loyalty=1 ORDER BY v.id LIMIT 1")[0][0]
cart = json.dumps([{"variant_id": variant, "qty": 1}])


def parallel(jobs):
    """Each job gets its own connection, like requests landing on different instances."""
    out, gate = [None] * len(jobs), threading.Barrier(len(jobs))

    def work(i):
        conn = db.connect()
        try:
            gate.wait()
            out[i] = jobs[i](conn)
        except Exception as exc:
            out[i] = exc
        finally:
            conn.close()
    threads = [threading.Thread(target=work, args=(i,)) for i in range(len(jobs))]
    [t.start() for t in threads]; [t.join(30) for t in threads]
    for r in out:
        assert not isinstance(r, Exception), r
    return out


def place(uid, key=""):
    def job(conn):
        venue = conn.execute("SELECT * FROM venues WHERE id=1").fetchone()
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return orders.create_order(conn, venue, user, 15, "", cart, key)
    return job


def clear():
    run("DELETE FROM orders"); run("DELETE FROM loyalty_cards")


# --- 8 customers at once, the venue takes 3 active orders
for _ in range(5):
    clear()
    made = [r for r in parallel([place(u) for u in users]) if r[0]]
    assert len(made) == 3, len(made)

# --- one customer, many parallel orders: per-venue limit holds, the welcome gift is used once
for _ in range(5):
    clear()
    made = [r for r in parallel([place(users[0]) for _ in range(6)]) if r[0]]
    assert len(made) == cfg.MAX_ACTIVE_PER_USER_VENUE, len(made)
    assert run("SELECT COUNT(*) FROM orders WHERE reward='welcome'")[0][0] == 1

# --- the same form sent in parallel creates one order
clear()
ids = {r[0] for r in parallel([place(users[0], "same-form-key-1") for _ in range(6)])}
assert len(ids) == 1 and run("SELECT COUNT(*) FROM orders")[0][0] == 1

# --- parallel expiry gives the reward back once
run("UPDATE orders SET arrive_at = utc_text('-5 hours')")
closed = parallel([orders.expire_stale for _ in range(4)])
assert sum(len(c) for c in closed) == 1

# --- shared rate limit holds across connections
limiter.reset()
assert sum(parallel([lambda conn: limiter.allow_shared("login:x", 5, 60) for _ in range(12)])) == 5

# --- search: SQL norm() ignores Polish letters like utils.normalize
assert run("SELECT norm('Łódź CAFÉ Żółć')")[0][0] == "lodz cafe zolc"
clear()
conn = db.connect()
oid = place(users[1])(conn)[0]
conn.execute("UPDATE orders SET customer_name='Paweł Śliwa' WHERE id=?", (oid,))
assert orders.list_orders(conn, 1, q="pawel sliwa")[1] == 1 and orders.list_orders(conn, 1, q="100%_")[1] == 0
conn.close()

# --- live updates: the change comes from another connection
assert realtime.changes({1: "new"}, {1: "ready", 2: "new"}) == [
    {"type": "order", "order_id": 1, "status": "ready", "new": False},
    {"type": "order", "order_id": 2, "status": "new", "new": True}]
cfg.WS_POLL_SECONDS = 0.2
from app.main import app
telegram_calls = []
async def fake_call(method, _timeout=15, **payload):
    telegram_calls.append((method, payload))
    return {"username": "ahead_test_bot", "message_id": 7}
telegram.call = fake_call

with TestClient(app, base_url="https://testserver") as c:
    import re
    token = re.search(r'name="csrf" value="([^"]+)"', c.get("/venue/login").text).group(1)
    assert c.post("/venue/login", data={"csrf": token, "email": "demo@woodcoffee.pl", "password": "demo-pass-12345"},
                  follow_redirects=False).status_code == 303
    with c.websocket_connect("/ws/panel", headers={"origin": "https://testserver"}) as ws:
        other = db.connect()
        assert orders.transition(other, 1, oid, "preparing")[1] is None
        other.close()
        assert ws.receive_json() == {"type": "order", "order_id": oid, "status": "preparing", "new": False}

    # --- cron needs the secret
    assert c.get("/cron/expire").status_code == 404
    assert c.get("/cron/expire", headers={"authorization": "Bearer wrong"}).status_code == 404
    assert c.get("/cron/expire", headers={"authorization": "Bearer cron-secret-123"}).text.startswith("expired:")

    # --- Telegram webhook needs the secret; "Decline" + reason works across two separate calls
    hook = {"x-telegram-bot-api-secret-token": "hook-secret-123"}
    assert c.post("/telegram/webhook", json={}).status_code == 404
    run("INSERT INTO tg_chats (venue_id, chat_id, title) VALUES (1, -1001234567890, 'staff')")
    press = {"callback_query": {"id": "1", "data": f"o:{oid}:decline", "message": {"chat": {"id": -1001234567890}}}}
    assert c.post("/telegram/webhook", json=press, headers=hook).status_code == 200
    reason = {"message": {"chat": {"id": -1001234567890}, "text": "Out of milk"}}
    assert c.post("/telegram/webhook", json=reason, headers=hook).status_code == 200
    row = run("SELECT status, decline_reason FROM orders WHERE id=?", oid)[0]
    assert (row["status"], row["decline_reason"]) == ("declined", "Out of milk")

# --- serverless mode starts, refuses to run without SECRET_KEY, and background work finishes before the answer
env = dict(os.environ, VERCEL="1", BASE_URL="https://testserver", TELEGRAM_BOT_TOKEN="")
bad = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0,'.'); import app.config"],
                     env=dict(env, SECRET_KEY=""), capture_output=True, text=True)
assert bad.returncode != 0 and "SECRET_KEY" in bad.stderr
code = '''
import sys, re, asyncio; sys.path.insert(0, ".")
from starlette.testclient import TestClient
from app import mail, config as cfg, db
from app.main import app
done = []
async def slow_mail(*a):
    await asyncio.sleep(0.3); done.append(a); return True
mail.send_mail = slow_mail
cfg.ADMIN_EMAIL = "owner@example.pl"
with TestClient(app, base_url="https://testserver") as c:
    t = re.search(r'name="csrf" value="([^"]+)"', c.get("/venue/register").text).group(1)
    r = c.post("/venue/register", data={"csrf": t, "venue_name": "New Place", "city": "Warszawa", "email": "new@example.pl",
               "password": "correct-horse-1", "agree": "1"}, headers={"x-real-ip": "203.0.113.9"}, follow_redirects=False)
    assert r.status_code == 303 and len(done) == 1, (r.status_code, done)
'''
ok = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
assert ok.returncode == 0, ok.stderr[-2000:]
print("cloud: all checks passed")
