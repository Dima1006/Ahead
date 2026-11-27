# Ahead: pre-order for cafes (MVP)

Venues register, get approved, build their menu and receive pickup orders live (website + optional Telegram).
Customers sign up (e-mail or Google), find a venue, order, choose an arrival time. No payments yet.

Stack: Starlette + uvicorn, Jinja2 templates, PostgreSQL, WebSockets. Python 3.12.

## Run locally
```bash
cd web
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ahead
DEMO_SEED=1 DEMO_MODE=1 ADMIN_PASSWORD=change-me-please uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000. Admin: `/admin`. Tables are created on start. Deploying to Vercel: [DEPLOY_VERCEL.md](DEPLOY_VERCEL.md).

## Settings (environment variables)
| Variable | Purpose |
| --- | --- |
| `BASE_URL` | Public address (e-mail links, Google redirect). Required in production. |
| `SECRET_KEY` | Signs sessions. Required in production, otherwise sessions reset on restart. |
| `ADMIN_PASSWORD` | Turns on `/admin` (approve venues). `ADMIN_EMAIL` gets a mail for each new venue. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Outgoing mail (Gmail works with an app password). Without it mails are only logged. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in. Redirect URI: `BASE_URL/auth/google/callback`. |
| `TELEGRAM_BOT_TOKEN` | Create a bot with @BotFather. Venues connect chats in Settings → Telegram. |
| `TRUST_PROXY=1` | Only behind Cloudflare: real client IP from `CF-Connecting-IP` (for rate limits). Behind another proxy use `uvicorn --proxy-headers` instead. |
| `DEMO_MODE=1` | Demo only: no e-mail confirmation needed to order. |
| `DEMO_SEED=1` | Creates three ready demo venues with full menus (see below). `DEMO_PASSWORD` sets their password, otherwise a random one is printed in the log. |
| `DATABASE_URL` | PostgreSQL connection string. Required. |
| `TELEGRAM_WEBHOOK_SECRET`, `CRON_SECRET` | Webhook and cron authentication (Vercel). Without a webhook secret the bot polls. |

## Demo venues
With `DEMO_SEED=1` the site starts with three approved venues, so every kind of venue can be shown to an owner right away.
They are created once; restarting does not duplicate them. The menus are in `app/seed.py`.

| Venue | Page | Venue login | What it shows |
| --- | --- | --- | --- |
| Wood Coffee | `/v/wood-coffee` | `demo@woodcoffee.pl` | Sizes, loyalty on coffee, 5 min prep |
| Bella Napoli (pizzeria) | `/v/bella-napoli` | `demo-pizza@woodcoffee.pl` | 32/40 cm sizes, paid extra toppings, 20 min prep |
| Sushi Hana | `/v/sushi-hana` | `demo-sushi@woodcoffee.pl` | Sets, required chopsticks choice, paid sauces, 30 min prep |

## GitHub Actions demo
Actions → **Run web demo**. The URL is in the run summary. Add secrets `ADMIN_PASSWORD` (required to approve venues), and optionally `DEMO_PASSWORD`, `SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, `ADMIN_EMAIL`, `SMTP_*`.
The address changes every run, so Google sign-in does not work there (use e-mail sign-up); the database is temporary.

## Tests
Need `pip install httpx` and a PostgreSQL server in `TEST_DATABASE_URL`: `python3 tests/test_smoke.py` (and the other `tests/test_*.py`).

See `SECURITY.md` for the security review.

## Stage 2 update
New: opening hours, preparation time, pause and capacity limits per venue; no-show grace period and per-venue blocking; order cancel by customer; automatic expiry of stale orders; venue password reset and change; navigation menu and category chips; protection against floods. Run tests: `cd web && python3 tests/test_smoke.py`.

## Add-ons and photos
Panel → **Add-ons**: create groups (Milk, Syrup...) with options and extra prices, then tick them for items in **Menu**. Photos: item editor (Menu) and venue photo (Settings). Photos are stored in the database (`photos` table), at most 4 MB per upload. Needs `Pillow` (in `requirements.txt`). Tests: `python3 tests/test_smoke.py` and `python3 tests/test_features.py`.

## E-mail (password reset, confirmation, sign-in code)
All of it needs the `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` (and `ADMIN_EMAIL`) secrets. For Gmail: host `smtp.gmail.com`, your address, and an **App Password**. After adding them open `/admin` and press **Send a test email**: it shows the exact error if something is wrong. Tests: `python3 tests/test_auth.py`.

If SMTP is blocked on your network, use Brevo's HTTPS API instead: secrets `BREVO_API_KEY` and `MAIL_FROM` (an address verified as a sender in Brevo). The workflow file must pass them to the app (`BREVO_API_KEY: ${{ secrets.BREVO_API_KEY }}`).

## Loyalty rewards
Panel → **Settings → Loyalty**: a *welcome gift* (the first order of each new customer at this venue has one item free) and a *stamp card* (every N-th item free). The venue ticks which items count. The free item is the cheapest ticked item in the order (size included, add-ons paid) and is shown on the order, in the live board and in Telegram. A reward is used when the order is placed and given back if it is cancelled, declined or expires (not after a no-show); stamps are added only when the order is marked "Picked up". Customers see their cards in **My account**. Tests: `python3 tests/test_loyalty.py` (no HTTP client needed).
