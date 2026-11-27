"""Tell Telegram where to send updates. Run once after deploying (and when the address changes):

    BASE_URL=https://... TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... python -m app.set_webhook
"""
import asyncio
import sys

from . import config as cfg
from . import telegram


async def main() -> None:
    if not (cfg.HTTPS and cfg.TELEGRAM_BOT_TOKEN and cfg.TELEGRAM_WEBHOOK_SECRET):
        sys.exit("Set BASE_URL (https://...), TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET.")
    await telegram.call("setWebhook", url=cfg.BASE_URL + "/telegram/webhook",
                        secret_token=cfg.TELEGRAM_WEBHOOK_SECRET, allowed_updates=["message", "callback_query"])
    print("Webhook set:", cfg.BASE_URL + "/telegram/webhook")


if __name__ == "__main__":
    asyncio.run(main())
