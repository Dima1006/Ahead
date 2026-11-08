"""Loyalty rewards a venue can switch on in Settings → Loyalty:

* welcome gift: the first order of each customer at this venue has one item free;
* stamp card: every picked-up item marked "loyalty" adds a stamp; STAMP_EVERY stamps buy one free item.

The free item is always the cheapest marked item in the order (its size included, add-ons are paid).
A reward is taken when the order is placed and given back if the order does not happen (cancelled, declined,
expired). A no-show does not give it back. Stamps are added only when the venue marks the order "Picked up",
so fake orders never earn anything. The welcome gift is per venue: each venue pays for its own new guests."""
import sqlite3

STAMP_CHOICES = (0, 4, 5, 6, 7, 8, 9, 10, 12, 15)   # 0 = no stamp card
REWARD_LABELS = {"welcome": "Welcome gift", "stamp": "Loyalty card reward"}
GIVE_BACK = ("cancelled", "declined", "expired")


class RewardTaken(Exception):
    """The reward was used by another order a moment ago."""


def enabled(venue) -> bool:
    return bool(venue["welcome_free"] or venue["stamp_every"])


def card(conn: sqlite3.Connection, venue_id: int, user_id: int):
    return conn.execute("SELECT * FROM loyalty_cards WHERE venue_id = ? AND user_id = ?",
                        (venue_id, user_id)).fetchone()


def is_new_guest(conn, venue_id: int, user_id: int) -> bool:
    return not conn.execute("SELECT 1 FROM orders WHERE venue_id = ? AND user_id = ? AND status = 'completed' LIMIT 1",
                            (venue_id, user_id)).fetchone()


def available_reward(conn, venue, user_id: int) -> str:
    """'welcome', 'stamp' or '' for this customer's next order here."""
    c = card(conn, venue["id"], user_id)
    if venue["welcome_free"] and not (c and c["welcome_used"]) and is_new_guest(conn, venue["id"], user_id):
        return "welcome"
    if venue["stamp_every"] and c and c["stamps"] >= venue["stamp_every"]:
        return "stamp"
    return ""


def loyalty_item_ids(conn, venue_id: int) -> set[int]:
    return {r[0] for r in conn.execute("SELECT id FROM items WHERE venue_id = ? AND loyalty = 1", (venue_id,))}


def price_order(conn, venue, user_id: int, lines: list[dict]) -> dict:
    """lines: [{"item_id", "name", "base", "qty"}] where base = price of the chosen size without add-ons.
    Returns what the order gets: reward, discount, reward_item, reward_cost, stamps_earned."""
    out = {"reward": "", "discount": 0, "reward_item": "", "reward_cost": 0, "stamps_earned": 0}
    if not enabled(venue):
        return out
    marked = loyalty_item_ids(conn, venue["id"])
    eligible = [ln for ln in lines if ln["item_id"] in marked]
    if not eligible:
        return out
    count = sum(ln["qty"] for ln in eligible)
    reward = available_reward(conn, venue, user_id)
    if reward:
        free = min(eligible, key=lambda ln: ln["base"])
        out.update(reward=reward, discount=free["base"], reward_item=free["name"],
                   reward_cost=venue["stamp_every"] if reward == "stamp" else 0)
        count -= 1   # the free item earns no stamp
    if venue["stamp_every"]:
        out["stamps_earned"] = count
    return out


def take(conn, venue_id: int, user_id: int, priced: dict) -> None:
    """Inside the order's transaction: use the reward. Raises RewardTaken if it is no longer there."""
    if not priced["reward"]:
        return
    conn.execute("INSERT OR IGNORE INTO loyalty_cards (venue_id, user_id) VALUES (?, ?)", (venue_id, user_id))
    if priced["reward"] == "welcome":
        cur = conn.execute("UPDATE loyalty_cards SET welcome_used = 1 WHERE venue_id = ? AND user_id = ? AND welcome_used = 0",
                           (venue_id, user_id))
    else:
        cur = conn.execute("UPDATE loyalty_cards SET stamps = stamps - ? WHERE venue_id = ? AND user_id = ? AND stamps >= ?",
                           (priced["reward_cost"], venue_id, user_id, priced["reward_cost"]))
    if cur.rowcount != 1:
        raise RewardTaken


def on_status(conn, order, new_status: str) -> None:
    """Inside the transaction that changes the status: add stamps or give the reward back."""
    if not order["user_id"]:
        return
    venue_id, user_id = order["venue_id"], order["user_id"]
    if new_status == "completed" and order["stamps_earned"] > 0:
        conn.execute("INSERT INTO loyalty_cards (venue_id, user_id, stamps) VALUES (?, ?, ?) "
                     "ON CONFLICT(venue_id, user_id) DO UPDATE SET stamps = stamps + excluded.stamps",
                     (venue_id, user_id, order["stamps_earned"]))
    elif new_status in GIVE_BACK and order["reward"] == "welcome":
        conn.execute("UPDATE loyalty_cards SET welcome_used = 0 WHERE venue_id = ? AND user_id = ?", (venue_id, user_id))
    elif new_status in GIVE_BACK and order["reward"] == "stamp":
        conn.execute("UPDATE loyalty_cards SET stamps = stamps + ? WHERE venue_id = ? AND user_id = ?",
                     (order["reward_cost"], venue_id, user_id))


def user_cards(conn, user_id: int) -> list[dict]:
    """Stamp cards of a customer, for My account."""
    rows = conn.execute(
        "SELECT c.stamps, v.name, v.slug, v.stamp_every FROM loyalty_cards c JOIN venues v ON v.id = c.venue_id "
        "WHERE c.user_id = ? AND v.stamp_every > 0 AND v.status = 'approved' ORDER BY v.name", (user_id,)).fetchall()
    return [dict(r, ready=r["stamps"] >= r["stamp_every"]) for r in rows]
