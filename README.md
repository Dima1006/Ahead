# Ahead

**Pickup pre-ordering for small cafés and takeaway venues.** Customers find a venue, order from their phone and choose when they will arrive. The venue sees the order live and has it ready: order, pick up, leave. No queues, no payment in the app (yet).

Ahead grew out of the *Wood Coffee* Telegram bot and is aimed at small venues in Poland that do not have a pickup ordering system: cafés first, but pizzerias and sushi places work the same way.

> Status: MVP. It is used for demos and a free pilot with real venues; online payments are planned for later.

## What it does

**For customers**
- Sign up with e-mail or Google, search for a venue, browse the menu with photos
- Choose sizes and add-ons (milk, syrup, toppings, sauces) and an arrival time
- Cancel an order, repeat a previous one, see order history in *My account*
- Loyalty cards: a welcome gift and every N-th item free
- Polish and English interface

**For venues**
- Self-service registration (approved by the owner in `/admin`)
- Menu editor: categories, items, photos, option groups with extra prices
- Live order board over WebSockets, with optional Telegram notifications and buttons
- Opening hours, preparation time, pause and capacity limits
- No-show handling: grace period and per-venue blocking of repeat no-shows
- Loyalty settings: which items count for the welcome gift and the stamp card

## Tech stack

Python 3.12, Starlette + uvicorn, Jinja2 templates, SQLite, WebSockets, Pillow for photos. Plain JavaScript on the front end, no third-party scripts. Docker image included.

## Quick start

```bash
git clone https://github.com/Dima1006/Ahead.git
cd Ahead/web
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
DEMO_SEED=1 DEMO_MODE=1 ADMIN_PASSWORD=change-me-please uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The admin panel is at `/admin`.

`DEMO_SEED=1` creates three ready venues (a café, a pizzeria and a sushi place) so you can show every kind of menu right away. Always run **one** server process: live updates and rate limits are kept in memory.

### Docker

```bash
cd web
docker build -t ahead .
docker run -p 8000:8000 -v ahead-data:/data \
  -e BASE_URL=https://your-domain -e SECRET_KEY=<long random string> \
  -e ADMIN_PASSWORD=<long password> ahead
```

### Public demo on GitHub Actions

Actions → **Run web demo**. The workflow starts the site behind a temporary Cloudflare tunnel and prints the URL in the run summary. The database is temporary and the address changes on every run.

## Configuration

Everything is configured with environment variables: `BASE_URL`, `SECRET_KEY`, `ADMIN_PASSWORD`, SMTP or Brevo for e-mail, Google sign-in, `TELEGRAM_BOT_TOKEN`, optional Cloudflare Turnstile CAPTCHA and more. The full table is in [web/README.md](web/README.md).

## Tests

```bash
cd web
pip install httpx
python3 -I tests/test_smoke.py
python3 -I tests/test_features.py
python3 -I tests/test_auth.py
python3 -I tests/test_loyalty.py
```

## Project layout

```
web/            the application
  app/          routes, database, orders, loyalty, mail, Telegram, templates, static files
  tests/        test scripts
  Dockerfile
  SECURITY.md   security review and known limits
.github/        demo workflow
```

## More

- [web/README.md](web/README.md): detailed setup, settings, demo venues, e-mail and loyalty
- [web/SECURITY.md](web/SECURITY.md): security notes and known limits
