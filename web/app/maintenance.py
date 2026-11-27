"""Close orders nobody handled and tell whoever needs to know."""
import asyncio
import logging
import time

from . import config as cfg
from . import db, events, orders

log = logging.getLogger("coffee")
_last_run = 0.0


def _expire_once() -> list[int]:
    conn = db.connect()
    try:
        conn.execute("DELETE FROM waitlist WHERE created_at < utc_text(make_interval(days => ?))",
                     (-cfg.WAITLIST_KEEP_DAYS,))
        return orders.expire_stale(conn)
    finally:
        conn.close()


async def expire() -> int:
    ids = await asyncio.to_thread(_expire_once)
    for order_id in ids:
        await events.announce(order_id)
    return len(ids)


async def expire_if_due(interval: float = 60) -> None:
    """Without a background loop (serverless), ordinary traffic does the job, at most once a minute."""
    global _last_run
    if time.monotonic() - _last_run < interval and _last_run:
        return
    _last_run = time.monotonic()
    try:
        await expire()
    except Exception as exc:
        log.error("expiry failed: %s", type(exc).__name__)
