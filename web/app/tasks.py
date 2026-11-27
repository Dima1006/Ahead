"""Fire-and-forget background tasks that cannot be garbage-collected or crash a request.

A serverless instance may be frozen as soon as it has answered, so there the tasks started during a
request are awaited before the response is sent (see SecurityMiddleware)."""
import asyncio
import logging
from contextvars import ContextVar

log = logging.getLogger("coffee")
_tasks: set = set()
request_tasks: ContextVar[list | None] = ContextVar("request_tasks", default=None)


async def _safe(coro):
    try:
        await coro
    except Exception as exc:
        log.error("background task failed: %s", type(exc).__name__)


def spawn(coro) -> None:
    task = asyncio.ensure_future(_safe(coro))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    pending = request_tasks.get()
    if pending is not None:
        pending.append(task)


async def drain(pending: list) -> None:
    """Wait for the tasks of one request, including the ones those tasks start."""
    while pending:
        batch = pending[:]
        pending.clear()
        await asyncio.gather(*batch)
