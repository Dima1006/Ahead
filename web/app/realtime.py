"""Live updates over WebSockets.

Several server instances may be running, and the order can be changed by any of them (website,
Telegram, cron). So every open socket watches the database: when the status of a watched order
changes, the browser is told and re-fetches the (permission-checked) HTML."""
import asyncio
import logging
from collections import defaultdict

from starlette.websockets import WebSocketDisconnect

from . import config as cfg
from . import db

log = logging.getLogger("coffee")
MAX_MESSAGE_CHARS = 16  # clients only ever send "ping"
_per_ip: dict[str, int] = defaultdict(int)

# Active orders, plus those finished in the last 10 minutes (so that finishing is seen as a change).
_QUERY = ("SELECT id, status FROM orders WHERE {column} = ? AND (status IN ('new', 'preparing', 'ready') "
          "OR updated_at >= utc_text('-10 minutes')) ORDER BY id")
_COLUMNS = {"venue": "venue_id", "user": "user_id"}


class _Watcher:
    """One database connection per socket, reopened if it drops."""

    def __init__(self, kind: str, key: int):
        self.sql, self.key, self.conn = _QUERY.format(column=_COLUMNS[kind]), key, None

    def snapshot(self) -> dict[int, str]:
        try:
            self.conn = self.conn or db.connect()
            return {r["id"]: r["status"] for r in self.conn.execute(self.sql, (self.key,))}
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None


def changes(old: dict[int, str], new: dict[int, str]) -> list[dict]:
    return [{"type": "order", "order_id": i, "status": status, "new": i not in old and status == "new"}
            for i, status in new.items() if old.get(i) != status]


async def serve(ws, kind: str, key: int, ip: str = "") -> None:
    """Accept the socket and report order changes until the client goes away. kind: "venue" | "user"."""
    if ip and _per_ip[ip] >= cfg.WS_MAX_PER_IP:
        await ws.close(code=1013)  # too many connections from one address
        return
    if ip:
        _per_ip[ip] += 1
    watcher = _Watcher(kind, key)
    receiver = None
    try:
        known = await asyncio.to_thread(watcher.snapshot)  # before accept: nothing can be missed after it
        await ws.accept()
        receiver = asyncio.ensure_future(ws.receive())
        loop = asyncio.get_running_loop()
        next_poll = loop.time() + cfg.WS_POLL_SECONDS
        while True:
            done, _ = await asyncio.wait({receiver}, timeout=max(0, next_poll - loop.time()))
            if done:
                msg = receiver.result()
                if msg["type"] == "websocket.disconnect":
                    break
                text = msg.get("text")
                if msg.get("bytes") or (text is not None and len(text) > MAX_MESSAGE_CHARS):
                    await ws.close(code=1009)  # message too big: we never expect more than "ping"
                    break
                if text == "ping":  # client heartbeat keeps proxies from closing idle sockets
                    await ws.send_text("pong")
                receiver = asyncio.ensure_future(ws.receive())
            if loop.time() >= next_poll:
                current = await asyncio.to_thread(watcher.snapshot)
                for message in changes(known, current):
                    await ws.send_json(message)
                known = current
                next_poll = loop.time() + cfg.WS_POLL_SECONDS
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception as exc:  # database trouble: close, the browser reconnects and refreshes
        log.warning("live updates stopped: %s", type(exc).__name__)
        try:
            await ws.close(code=1011)
        except Exception:
            pass
    finally:
        if receiver:
            receiver.cancel()
        watcher.close()
        if ip:
            _per_ip[ip] -= 1
            if _per_ip[ip] <= 0:
                del _per_ip[ip]
