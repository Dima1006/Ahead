# Deploying to Vercel

## 1. Project
Import the GitHub repository in Vercel and set **Root Directory = `web`**. `vercel.json` already sets the
region (`fra1`, Frankfurt), a 300 s function duration and a daily cron.

Plan: the free Hobby plan is for non-commercial, personal use only. Running Ahead for real venues needs Pro.

## 2. Database
Add a Postgres database (for example Neon, in the Vercel Marketplace) **in Frankfurt**, close to the function.
Use the **pooled** connection string as `DATABASE_URL`. Give *Preview* deployments a different database
than *Production*. Tables are created on the first start. The database starts empty: old SQLite data is not copied.

Optional, once, in the database's SQL editor (stops runaway queries):

    ALTER ROLE current_user SET statement_timeout = '5s';

## 3. Environment variables
| Variable | Value |
| --- | --- |
| `DATABASE_URL` | pooled PostgreSQL connection string |
| `SECRET_KEY` | long random string: `python3 -c "import secrets; print(secrets.token_hex(32))"` (required) |
| `BASE_URL` | the public address, `https://...`, no trailing slash |
| `ADMIN_PASSWORD`, `ADMIN_EMAIL` | admin panel |
| `CRON_SECRET` | another long random string |
| `BREVO_API_KEY` + `MAIL_FROM`, or `SMTP_*` | e-mail |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | optional; add `BASE_URL/auth/google/callback` in Google Console |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` | optional; the secret may use only A-Z a-z 0-9 _ - |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET` | optional CAPTCHA |

Do **not** set `DEMO_MODE` or `DEMO_SEED` in production. Redeploy after changing variables.

## 4. Telegram webhook
Once, from your computer, in `web/`:

    BASE_URL=https://... TELEGRAM_BOT_TOKEN=... TELEGRAM_WEBHOOK_SECRET=... python3 -m app.set_webhook

One bot has one webhook. While it is set, polling (local run, GitHub demo) does not work with the same token:
use a second bot for development.

## 5. Check on a preview deployment before production
- [ ] pages and styles load; `/healthz` answers `ok`
- [ ] register a venue, approve it in `/admin`, add an item with a photo
- [ ] place an order: the venue's live board updates within a few seconds
- [ ] leave the board open for more than 5 minutes: it reconnects and still updates
- [ ] sign-in code / password reset e-mails arrive
- [ ] Telegram: connect a chat, accept one order, decline another with a reason

## How it differs from a single server
- **Live updates:** each open page keeps a WebSocket that reads the database every 2 s. This costs database and
  function time while a panel is open, and keeps a scale-to-zero database awake. Watch the usage pages. If it
  gets expensive, raise `WS_POLL_SECONDS` or move to publish/subscribe (Redis).
- **Closing unhandled orders:** ordinary page requests do it (at most once a minute per instance), plus the daily
  cron. On Pro the cron in `vercel.json` can run more often, e.g. `*/5 * * * *`.
- **Photos** are in the database.
