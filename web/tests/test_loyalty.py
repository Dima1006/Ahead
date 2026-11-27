"""Loyalty rewards (welcome gift, stamp card). Run: python3 tests/test_loyalty.py   (from the web/ folder)
Works on the order rules directly, so it needs no HTTP client."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pgtest
os.environ.update(DATABASE_URL=pgtest.fresh_database(), SECRET_KEY="t" * 40, DEMO_PASSWORD="demo-pass-12345")
from app import db, loyalty, orders, seed

db.init_db()
seed.seed_demo()
conn = db.connect()
conn.execute("UPDATE venues SET open_time='00:00', close_time='00:00', prep_minutes=5, welcome_free=1, stamp_every=4 WHERE id=1")
for email in ("ola@example.pl", "jan@example.pl"):
    conn.execute("INSERT INTO users (email, name, email_verified) VALUES (?, 'Test', 1)", (email,))

def venue(): return conn.execute("SELECT * FROM venues WHERE id=1").fetchone()
def user(email): return conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
def variant(item, label):
    return conn.execute("SELECT v.id, v.price FROM variants v JOIN items i ON i.id=v.item_id WHERE i.name=? AND v.label=?",
                        (item, label)).fetchone()
def order(u, lines, key=""):
    cart = json.dumps([{"variant_id": variant(n, l)["id"], "qty": q} for n, l, q in lines])
    oid, err = orders.create_order(conn, venue(), u, 15, "", cart, key)
    assert err is None, err
    return conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
def pick_up(o):
    for st in ("preparing", "ready", "completed"):
        assert orders.transition(conn, 1, o["id"], st)[1] is None
def card(u): return loyalty.card(conn, 1, u["id"])

ola, jan = user("ola@example.pl"), user("jan@example.pl")
small_capp, large_latte = variant("Cappuccino", "Small")["price"], variant("Latte", "Large")["price"]
croissant = variant("Croissant", "")["price"]

# welcome gift: the cheapest marked item is free, a croissant (not marked) is always paid
o = order(ola, [("Latte", "Large", 1), ("Cappuccino", "Small", 1), ("Croissant", "", 1)])
assert (o["reward"], o["discount"], o["reward_item"]) == ("welcome", small_capp, "Cappuccino")
assert o["total"] == large_latte + croissant
assert o["stamps_earned"] == 1                      # 2 coffees, the free one earns nothing
assert loyalty.available_reward(conn, venue(), ola["id"]) == ""   # cannot be used twice at the same time

# cancelling gives the gift back; ordering again uses it again
assert orders.cancel_by_customer(conn, ola["id"], o["id"])
assert card(ola)["welcome_used"] == 0
o = order(ola, [("Latte", "Large", 3)])
assert o["reward"] == "welcome" and o["total"] == 2 * large_latte and o["stamps_earned"] == 2
assert card(ola)["stamps"] == 0                     # stamps only after pick-up
pick_up(o)
assert card(ola)["stamps"] == 2 and card(ola)["welcome_used"] == 1

# no more welcome gift; stamps fill the card (4 needed)
o = order(ola, [("Americano", "Small", 2), ("Cheesecake", "", 1)])
assert o["reward"] == "" and o["discount"] == 0 and o["stamps_earned"] == 2
pick_up(o)
assert card(ola)["stamps"] == 4
assert loyalty.available_reward(conn, venue(), ola["id"]) == "stamp"

# the stamp reward: 4 stamps are spent when ordering, given back when the venue declines
o = order(ola, [("Latte", "Small", 1)])
assert o["reward"] == "stamp" and o["total"] == 0 and o["reward_cost"] == 4 and card(ola)["stamps"] == 0
assert orders.transition(conn, 1, o["id"], "declined", "out of milk")[1] is None
assert card(ola)["stamps"] == 4
# ... but not after a no-show
o = order(ola, [("Latte", "Small", 1)])
conn.execute("UPDATE orders SET arrive_at = utc_text('-1 hour') WHERE id = ?", (o["id"],))
assert orders.transition(conn, 1, o["id"], "no_show")[1] is None
assert card(ola)["stamps"] == 0
conn.execute("DELETE FROM venue_customer_flags")

# expired orders give the reward back too
conn.execute("UPDATE loyalty_cards SET stamps = 5 WHERE user_id = ?", (ola["id"],))
o = order(ola, [("Cappuccino", "Medium", 1)])
assert o["reward"] == "stamp" and card(ola)["stamps"] == 1
conn.execute("UPDATE orders SET arrive_at = utc_text('-5 hours') WHERE id = ?", (o["id"],))
assert o["id"] in orders.expire_stale(conn)
assert card(ola)["stamps"] == 5

# the same form sent twice creates one order and uses the reward once
first = order(jan, [("Cappuccino", "Small", 1)], key="same-form-key-123")
again = order(jan, [("Cappuccino", "Small", 1)], key="same-form-key-123")
assert first["id"] == again["id"] and card(jan)["welcome_used"] == 1

# an order with only unmarked items gets nothing and uses nothing
assert orders.cancel_by_customer(conn, jan["id"], first["id"])
o = order(jan, [("Croissant", "", 2)])
assert o["reward"] == "" and o["total"] == 2 * croissant and card(jan)["welcome_used"] == 0

# switched off: nothing happens
conn.execute("UPDATE venues SET welcome_free = 0, stamp_every = 0 WHERE id = 1")
assert orders.cancel_by_customer(conn, jan["id"], o["id"])
o = order(jan, [("Cappuccino", "Small", 1)])
assert o["reward"] == "" and o["stamps_earned"] == 0 and o["total"] == small_capp

# a customer who already picked up orders is not "new" when the venue turns the gift on later
conn.execute("UPDATE venues SET welcome_free = 1 WHERE id = 1")
pick_up(o)
conn.execute("DELETE FROM loyalty_cards WHERE user_id = ?", (jan["id"],))
assert loyalty.available_reward(conn, venue(), jan["id"]) == ""

# hydrate shows the reward label; My account lists the stamp card
conn.execute("UPDATE venues SET stamp_every = 4 WHERE id = 1")
h = orders.hydrate(conn, conn.execute("SELECT * FROM orders WHERE reward = 'welcome' LIMIT 1").fetchall())[0]
assert h["reward_label"] == "Welcome gift"
cards = loyalty.user_cards(conn, ola["id"])
assert cards[0]["stamps"] == 5 and cards[0]["ready"]

conn.close()
print("loyalty: all checks passed")
