# Telegram SMS & SMM Marketplace Bot

A button-driven Telegram marketplace for virtual numbers (SMS verification) and
SMM panel services, built as a layered application: swappable providers,
auditable money, and no business logic inside a callback handler.

---

## Features

**Users**
- 🛍 Buy a number — service search, country search, live prices and availability
- ⏳ Rent a number — real per-duration provider rates, preset or custom
- 📈 SMM panel — Instagram, Telegram, YouTube, TikTok and more, with order tracking
- 📦 Order history with receipts, plus refresh and cancel on live SMS orders
- ⭐ Favourites — saved service+country pairs, re-priced live
- 💳 Wallet — deposits, filterable transaction history, promo codes, optional transfers
- 📲 UPI deposits with a scannable QR, reviewed by a human before any balance moves
- 🎟 Promo codes — a flat bonus, or a percentage credited on the next deposit
- 🎁 Referral programme with commission on invitees' deposits
- 👤 Profile with lifetime statistics, notification and language settings
- ℹ️ Help centre with FAQ, refund policy, terms and privacy — all editable text

**Admins**
- 📊 Dashboard: users, orders, revenue, deposits, refunds, conversion, top services
- 🔍 One search box across users, orders, provider order ids, payments and phone numbers
- 💰 Balance adjustments that always write a transaction and an audit row
- 🎟 Promo creation accepting either `50` (flat) or `10%` (of next deposit)
- 💵 Deposit requests reviewed from a channel with Approve / Decline
- 📲 Payment QR uploaded from inside the bot, no redeploy
- 🚫 Ban/unban, 🎟 promo management, 📢 rate-limited broadcasts
- 📡 Live provider/database health, 🔧 maintenance mode, 🧾 audit log
- ⏳ Pending deposits reviewable from the panel, not only the channel
- 💾 Database backups on demand and on a schedule
- Role-based access: `owner`, `admin`, `finance`, `support`, `viewer`

---

## Requirements

- Python 3.11+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An SMS provider API key (SMS-Activate out of the box)
- A UPI id and a private Telegram channel for reviewing deposits — no payment
  gateway account is needed

---

## Installation

```bash
git clone <your-repo-url>
cd <repo>

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then fill it in — see below
alembic upgrade head      # create the database schema
python main.py
```

The bot validates its configuration before it starts. A missing or invalid
setting prints exactly what is wrong and exits, rather than failing later on a
user's first purchase.

---

## Configuration

Everything lives in `.env`; `.env.example` documents every key. `.env` is
gitignored — never commit real credentials.

Minimum viable configuration:

```env
BOT_TOKEN=123456:ABC-your-token
ADMIN_IDS=123456789
SMS_ACTIVATE_API_TOKEN=your-provider-key

MANUAL_PAYMENT_ENABLED=true
UPI_ID=yourshop@okaxis
MANUAL_PAYMENT_CHANNEL_ID=-1001234567890
```

The settings that shape the business:

| Key | Meaning |
| --- | --- |
| `SERVICE_FEE_PERCENT` / `SERVICE_FEE_FIXED` | Markup on the provider's cost |
| `MIN_PRICE` / `MAX_PRICE` | Clamp the final user-facing price (0 = unset) |
| `PROVIDER_CURRENCY_RATE` | Multiplier from provider currency to yours |
| `SMS_POLL_INTERVAL` / `SMS_TIMEOUT` | Polling cadence and refund deadline |
| `SMM_MARKUP_PERCENT` | Markup on SMM panel rates |
| `REFERRAL_PERCENT` | Commission paid to an inviter on each deposit |
| `MIN_DEPOSIT` / `MAX_DEPOSIT` | Deposit bounds |
| `PAYMENT_GRACE_HOURS` | How long past expiry an unreported invoice is still checked |
| `MANUAL_PAYMENT_ENABLED` | UPI deposits reviewed by a human (on by default) |
| `UPI_ID` | Your VPA; the QR is generated from it with the amount filled in |
| `UPI_QR_IMAGE` | Your own QR image, used instead of a generated one |
| `MANUAL_PAYMENT_CHANNEL_ID` | Channel where deposit requests are posted for review |
| `ADMIN_ROLES` | Per-admin roles, e.g. `123:finance,456:support` |

### Database

SQLite by default. To use Postgres, set `DATABASE_URL` and add `asyncpg`:

```env
DATABASE_URL=postgresql+asyncpg://bot:password@db:5432/bot
```

Schema changes are always migrations — never delete a database file:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
alembic downgrade -1
```

### SMS provider setup

Set `SMS_ACTIVATE_API_TOKEN` and keep the account funded. The bot alerts admins
when the provider balance drops below `SMS_PROVIDER_LOW_BALANCE_THRESHOLD`.

### SMM panel setup

```env
SMM_ENABLED=true
SMM_API_URL=https://your-panel.com/api/v2
SMM_API_KEY=your-panel-key
SMM_MARKUP_PERCENT=20
```

Then verify the panel actually answers before going live:

```bash
python -m scripts.check_providers --smm
```

It makes read-only calls — no orders, no money — and prints the panel balance,
how many services it returned, how they bucket into platform tabs, and a sample
price at your markup. Run it without a flag to check the SMS and payment
providers too.

The bundled adapter speaks the Perfect-Panel API dialect (`action=services`,
`add`, `status`, `balance`) that most SMM panels implement, so pointing
`SMM_API_URL` at a different panel is usually all that is needed. The panel's
free-text categories are bucketed automatically into the platform tabs shown in
the menu.

### Payment setup

**UPI (default)** — see [UPI deposits](#upi-deposits) below. No gateway
account needed; the bot generates a QR and a human approves each request.

**Telegram Stars** (off by default) — set `TELEGRAM_STARS_ENABLED=true` and the
Stars-per-unit rate. Checkout happens inside Telegram; no API key is required.

**CryptoBot** (off by default) — note that `CRYPTOBOT_RATE` is a fixed rate,
not a live market one, so it needs updating as the asset moves. Get a token
from [@CryptoBot](https://t.me/CryptoBot) → Crypto
Pay → Create App:

```env
CRYPTOBOT_ENABLED=true
CRYPTOBOT_API_TOKEN=12345:AAxxxx
CRYPTOBOT_ASSET=USDT
CRYPTOBOT_RATE=90
```

---

## UPI deposits

The primary deposit method, and the one `.env.example` ships enabled.

The user enters an amount and the bot shows the QR with the amount and your UPI
id beside it. They pay, tap **I Have Paid**, then send the UTR and a
screenshot. The request goes to a review channel with Approve and Decline
buttons. **No balance moves until a reviewer approves it.**

The reference is only asked for after **I Have Paid** is tapped, so a message
sent while the QR is still up is never mistaken for a UTR.

```env
MANUAL_PAYMENT_ENABLED=true
UPI_ID=yourshop@okaxis
UPI_PAYEE_NAME=Your Shop
MANUAL_PAYMENT_CHANNEL_ID=-1001234567890
MANUAL_PAYMENT_MAX_PENDING=3
```

Setup:

1. Create a private channel and add the bot as an administrator with permission
   to post.
2. Put its id in `MANUAL_PAYMENT_CHANNEL_ID` (it starts with `-100`).
3. Reviewers must be listed in `ADMIN_IDS`, or given a role in `ADMIN_ROLES`
   that carries the `balance` permission — `owner`, `admin` or `finance`.
   Approving creates money, so `support` and `viewer` can read the payment
   list but cannot credit from it.

### The QR

Generated per request as a `upi://pay` link, so GPay, PhonePe, Paytm and BHIM
all open it with the amount already filled in. That closes the most common
reason a deposit gets declined — the payer sending a different sum from the one
they asked the bot for.

#### Finding your UPI id

It is the `name@bank` handle your payment app shows on its profile or "receive
money" screen — for example `9876543210@paytm` or `yourshop@okaxis`.

If you have a QR image but not the handle, read it out of the image:

```bash
python -m scripts.read_qr assets/qr.png
```

It prints the `UPI_ID` and `UPI_PAYEE_NAME` lines to paste into `.env`.

#### Adding your QR from the bot (easiest)

`/admin` → **📲 Payment QR** → **Upload QR** → send the image.

Every deposit screen shows it from the next message on. Nothing to copy to a
server, nothing to redeploy, and you can change it from your phone.

Owner only — this decides where every user's money goes — and both setting and
removing it are written to the audit log.

#### Using one QR for every deposit

Put your own image in `assets/` and point at it:

```env
UPI_ID=yourshop@okaxis
UPI_QR_IMAGE=assets/qr.png
```

When `UPI_QR_IMAGE` is set it is what users see — you branded a code and expect
everyone to get the same one. `UPI_ID` is still worth setting: it appears as
copyable text beside the QR for anyone who would rather paste than scan.

An upload made in the admin panel overrides this, so the most recent deliberate
choice is always the live one.

`assets/` is mounted into the container, so swapping the image needs no
rebuild.

The trade-off: a static code carries no amount, so the payer types it in and
can send a different figure. The caption states the amount in bold, and the
review step is where a mismatch gets caught. Leaving `UPI_QR_IMAGE` empty makes
the bot generate a code per request with the amount inside it, which removes
the mismatch entirely.

`UPI_ID` is validated at startup, and the generated codes are decoded back in
the test suite to prove they actually scan.

### What the flow guarantees

| Risk | Mechanism |
| --- | --- |
| Someone redirecting deposits to their own QR | Changing the payment QR needs the `settings` permission — the owner alone — and is audited |
| The same payment claimed twice | The UTR is stored as the payment's `invoice_id`, so the unique `(provider, invoice_id)` index rejects it — whoever submits it, in any letter case |
| A stranger tapping Approve in the channel | The reviewer's permission is resolved from `ADMIN_IDS`/`ADMIN_ROLES`, never from the callback |
| Two reviewers approving at once | Approval runs through the same idempotent settlement as a gateway payment; the balance moves once |
| A decision being reversed later | `PAID` and `FAILED` are terminal — an approved request cannot then be declined, or the reverse |
| A user flooding the queue | `MANUAL_PAYMENT_MAX_PENDING` open requests per user |
| A request going stale | UPI requests are never auto-expired; they wait for a human |

Every decision writes an audit row naming the reviewer, the amount and the UTR,
and the user is messaged either way — a decline carries the reviewer's reason.

Balance transfers and broadcasts are also confirmed before they happen: both
are irreversible, so neither fires straight off a typed message.

**What this cannot check** is whether a UTR is genuine. A fabricated screenshot
with a reference nobody has used before will not be caught as a duplicate — the
reviewer's own bank or UPI app is the last check. Verify the UTR there before
approving.

### Other methods

CryptoBot and Telegram Stars are implemented and tested but off by default.
Turn either on in `.env` if you want it; see
[Payment setup](#payment-setup).

---

## Backups

The database holds every balance. Losing it means being unable to honour a
single deposit, so backups are on by default.

- **On demand:** `/admin` → **💾 Backup** sends a snapshot to whoever asked.
  Owner only — the file contains every user's data — and audited.
- **Scheduled:** a snapshot goes to `BACKUP_CHAT_ID` every
  `BACKUP_INTERVAL_HOURS`. Leave the chat id empty and it goes to the owner's
  DM; a private channel is better, since it survives losing the phone.

Snapshots use SQLite's `VACUUM INTO`, so the bot keeps serving while one is
taken. Copying the file directly would not be safe: with WAL enabled the copy
can land mid-transaction, and recent writes live in a separate `-wal` file a
naive copy leaves behind.

If a backup cannot be delivered — wrong chat id, bot removed from the channel —
admins are told, once per problem rather than on every attempt. A backup nobody
receives is the same as no backup.

On PostgreSQL the panel says so plainly rather than pretending to cover it; use
`pg_dump`.

### Restoring

```bash
docker compose down
cp bot-backup-2026-09-08_11-14.sqlite data/bot.db
docker compose up -d
```

Run `alembic upgrade head` afterwards if the backup predates a schema change.

---

## Shutdown

`SIGTERM` — what `docker compose down`, a restart or a deploy sends — stops
polling and then waits up to `SHUTDOWN_DRAIN_SECONDS` for handlers that are
still running, so a deploy landing mid-purchase does not abandon one between
the wallet debit and the provider call. `stop_grace_period` in
`docker-compose.yml` is set above that window.

An abandoned purchase is still recoverable — the SMS worker sweeps orders that
never reached the provider and refunds them — but draining means the user gets
their number rather than a refund three minutes later.

---

## Running in production

### Docker

```bash
cp .env.example .env    # fill it in
docker compose up -d --build
docker compose logs -f bot
```

Migrations run automatically on container start. `docker-compose.yml` contains
a commented Postgres service if you want it.

### systemd

```ini
[Unit]
Description=Telegram SMS Marketplace Bot
After=network-online.target

[Service]
Type=simple
User=bot
WorkingDirectory=/opt/sms-bot
ExecStartPre=/opt/sms-bot/.venv/bin/alembic upgrade head
ExecStart=/opt/sms-bot/.venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Updating

```bash
git pull
pip install -r requirements.txt
alembic upgrade head
systemctl restart sms-bot     # or: docker compose up -d --build
```

---

## Architecture

```
app/
├── core/                  config, logging, exceptions, money, constants
├── database/
│   ├── models.py          the schema
│   ├── engine.py          engine and session factory
│   └── repositories/      all SQL, one module per entity
├── providers/             SMS / payment / SMM adapters behind ABCs
├── services/
│   ├── wallet.py          the only place a balance changes
│   ├── orders.py          the purchase path
│   ├── payments.py        deposit settlement
│   ├── manual_payments.py reviewed UPI / bank deposits
│   ├── …                  pricing, catalog, promo, referrals, smm, admin
│   └── workers/           one module per background loop
├── bot/
│   ├── handlers/          one module per screen area; admin/ is a package
│   ├── keyboards/         one module per screen area
│   ├── middlewares.py     session, user, throttle, maintenance, errors
│   ├── texts.py           locale rendering
│   ├── callbacks.py       callback data schemas
│   └── setup.py           wiring
└── utils/                 pagination, validators, HTTP, cache, tokens
locales/en/messages.yaml   every user-facing string
scripts/                   provider connectivity checks
```

Some handler modules have no router of their own: `deposits` and `transfers`
register on the wallet router, `favorites`, `referrals` and `help_center` on
the profile router, and `manual_review` on the manual-payments router. They are
imported in `app/bot/handlers/__init__.py` purely so that registration happens.


Dependencies point one way: `bot → services → repositories → database`, and
`services → providers`. A handler never runs SQL, never calls a provider, and
never contains prose.

### Money handling

Balances, prices and transaction amounts are **integer minor units** (paise)
throughout. Floats are never used for money; the only float that exists is the
raw price a provider sends over HTTP, converted at the adapter boundary.

Every movement writes a `Transaction` row recording type, signed amount,
balance before, balance after and the operation that caused it. Nothing changes
a balance silently — not a refund, not a referral payout, not an admin
adjustment.

### How duplicate money operations are prevented

| Risk | Mechanism |
| --- | --- |
| Replayed payment webhook credits twice | `payments` unique on `(provider, invoice_id)`; credit keyed `deposit:<provider>:<invoice_id>` |
| Double-tapped confirm buys twice | Single-use callback token, plus a duplicate in-flight order check, plus a `purchase:order:<id>` key |
| Refund issued twice | `orders.refunded_at` plus a `refund:order:<id>` key |
| Referral commission paid twice | `referral:payment:<id>` key |
| Promo redeemed twice | Unique `(promo_id, user_id)` plus a `promo:<id>:<user>` key |
| Deposit-percentage promo paid twice | `promo:<id>:payment:<payment_id>` key, and the promo is disarmed once honoured |
| Money taken but never credited | Invoices are polled past their expiry for `PAYMENT_GRACE_HOURS`, and an abandoned invoice the gateway later confirms is still settled — `PAID` is the only terminal state |
| A manual deposit approved twice, or by a stranger | Terminal statuses, server-side reviewer permission, and a unique UTR per payment |
| A charge with nothing to show for it | An order that never reached the provider — a crash between the debit and the call — is swept and refunded by the SMS worker |
| A refund on a delivered SMM order | SMM orders have no cancel path; the release call is chosen by order kind, never by the keyboard |
| Concurrent duplicates racing past a check | Unique index on `transactions.idempotency_key`, applied inside a SAVEPOINT |

Every one of these has a test in `tests/`.

### Callback data is never trusted

Telegram callback payloads carry only short identifiers. A country button holds
an opaque token; the service, country and quoted price behind it live
server-side and are looked up by that token, which is scoped to the user who
was issued it and can be redeemed once. Prices are re-read from the provider
immediately before the wallet is touched, and order ids from callbacks are
resolved through ownership-scoped queries, so one user cannot reach another
user's order.

---

## Adding a provider

Implement the interface and register it. Nothing else changes.

```python
# app/providers/my_provider.py
from app.providers.base import Activation, ActivationStatus, BaseSMSProvider

class MyProvider(BaseSMSProvider):
    name = "my_provider"

    async def get_services(self): ...
    async def get_countries(self, service_code): ...
    async def get_price(self, service_code, country_id): ...
    async def create_activation(self, service_code, country_id): ...
    async def get_activation_status(self, provider_order_id): ...
    async def cancel_activation(self, provider_order_id): ...
    async def finish_activation(self, provider_order_id): ...
    async def get_balance(self): ...
```

Add a branch to `build_sms_provider` in `app/providers/registry.py`, then set
`SMS_PROVIDER=my_provider`. Payment gateways follow the same pattern with
`BasePaymentProvider` (`create_invoice`, `check_payment`, `cancel_invoice`).

Return prices in **minor units of your currency** — convert at the adapter
boundary — and never retry a state-creating call, or a timeout can double-buy.

---

## Customising text

All user-facing wording lives in `locales/en/messages.yaml`, including the
welcome message, FAQ entries, refund policy, terms and privacy text. Edit and
restart; no Python changes required.

To add a language, copy `locales/en/` to `locales/<code>/`, translate it, and it
appears in ⚙️ Settings automatically.

---

## Testing

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite covers money conversion, pricing and markup, wallet idempotency
(including a concurrency race), the purchase path (stale prices, double clicks,
provider failure refunds, cross-user access), payment replay, promo limits,
referral rules, SMM ordering, pagination, validators, callback tokens, locale
rendering and configuration validation.

---

## Rentals

Providers price a rental for a whole (country, duration) pair rather than per
hour, so the flow asks for the country and the duration first and only then
shows services with their real prices for that period. `MIN_RENTAL_HOURS` and
`MAX_RENTAL_HOURS` bound both the preset buttons and custom input.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Exits with a configuration error | The message names the key — fix it in `.env` |
| `startup.sms_provider_failed` | Wrong API key, or the provider is unreachable |
| No SMS arrives | Check 📡 Status in the admin panel; a timed-out activation refunds automatically |
| Payments do not credit | Confirm the provider is enabled; check 💳 Payments in the admin panel for the invoice status. An invoice paid late, or while the bot was down, is still polled for `PAYMENT_GRACE_HOURS` and credited when the gateway reports it |
| "Price changed" on confirm | The provider raised the price mid-session — re-confirm at the new price |
| Users report "Maintenance" | Maintenance mode is on — toggle it in 📡 Status |
| `no such table` | Migrations were not run: `alembic upgrade head` |
| SMM menu shows one "Other" tab | The panel's category names are unfamiliar; `scripts/check_providers.py --smm` warns about this. Extend `SMM_CATEGORY_KEYWORDS` in `app/core/constants.py` |
| SMM orders rejected | Run the check script — usually a wrong `SMM_API_URL` (it must be the API endpoint, often ending `/api/v2`) or a revoked key |

---

## Security

- Credentials live only in `.env`, which is gitignored; logs redact
  credential-shaped keys and never print a token.
- Admin permissions are resolved from configured ids and roles, server-side.
- Users only ever see friendly errors; the real exception is logged.
- If a credential was ever committed, rotate it — removing it from a later
  commit does not un-leak it.

## Legal

This software is for lawful verification and marketing use only. It must not be
used for fraud, impersonation, spam, account takeover, or bypassing platform
security. Operators are responsible for compliance in their jurisdiction.
