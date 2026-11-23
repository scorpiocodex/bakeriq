# BakeriQ

WhatsApp-first order management platform for local bakeries. Built as a single-tenant internal tool that turns daily customer chatter on WhatsApp into structured orders, prep lists, stock counts and invoices.

> **Status:** Complete. Built during a full-stack internship at Digital Mesh Softech (16 May – 27 July 2026) and finished as a working end-to-end system: customers order on WhatsApp, the owner runs the bakery from a web dashboard. Phases 1–3.5 shipped as planned; inventory (Phase 5) and billing (Phase 6) shipped in a simpler form than first scoped; a few roadmap items were deliberately left unbuilt. See [What's currently working](#whats-currently-working) and [`docs/ROADMAP.md`](docs/ROADMAP.md) for the exact boundary.

## What problem this solves

Local bakeries take orders informally — WhatsApp messages, regulars who order "the usual" every morning. The owner mentally tracks who's getting what, the chef prepares based on a verbal handoff, and nothing is written down until billing time.

BakeriQ replaces that with a thin layer of structure:

- A customer-facing WhatsApp bot that parses natural-language orders (English and Manglish) into a pre-filled cart the customer confirms in a small web app
- A web dashboard the owner uses to see today's orders, approve new customers from their phone, watch stock, and read the day's prep list
- Default order templates for regulars ("Anita's usual: 3 veg puffs + 2 ladoos")
- Snapshot-preserving order history so price changes don't rewrite past orders
- Per-customer billing summaries and invoices, which a customer can also pull up from WhatsApp

The system is single-tenant by design (one bakery, one owner, one chef) and India-only. There is no voice channel; WhatsApp is the only ordering channel.

## Tech stack

**Backend:** FastAPI 0.165 · Python 3.11 · SQLAlchemy 2.0 · Alembic 1.13 · PostgreSQL 15 · Redis 7 · Celery 5.4 · JWT auth (PyJWT + bcrypt)
**Messaging and LLM:** Twilio WhatsApp (Python SDK 9.3, Content Templates for tappable buttons) · Ollama running `llama3.2:3b` on the host
**Frontends (two):** React 18 · Vite 5 · TailwindCSS 3 · TanStack Query v5 · react-router-dom v6 · axios · lucide-react — an owner dashboard (`frontend/`) and a token-authenticated customer web app (`frontend-customer/`)
**Infrastructure:** Docker Compose orchestrating db / db_test / redis / api / worker / frontend / frontend-customer; ngrok tunnel for Twilio's webhook in development
**Testing:** pytest — 395 backend tests, all passing (run in the Docker stack on 23 November 2026)

## Quick start

Prerequisites: Docker Desktop or Docker Engine + Docker Compose, Git, Python 3.11+ (for the secret-key one-liner only).

```bash
# Clone and enter
git clone https://github.com/scorpiocodex/bakeriq.git
cd bakeriq

# Set up environment file
cp .env.example .env

# Generate a JWT signing secret and paste it into .env as SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# Bring the stack up
docker compose up -d

# Reset and seed the database (first time only, or any time you want fresh data)
make reset-db
```

Then open:

- **Dashboard:** http://localhost:5173
- **Customer web app:** http://localhost:5174 (normally reached through a WhatsApp link, not directly)
- **API docs (Swagger UI):** http://localhost:8000/docs
- **API docs (ReDoc):** http://localhost:8000/redoc

**Login credentials (development seed only):**

| Email | Password |
|---|---|
| `owner@bakeriq.com` | `bakeriqowner` |

The seed script refuses to run unless `ENVIRONMENT` is a development value. That is a safety net for a deployment that sets `ENVIRONMENT` (the default is `development`), not a guarantee, so never run the seed against a real database. For a database that wasn't seeded, create the first account with `docker compose exec -it api python -m scripts.create_owner --email you@example.com --name "Your Name"`. After that, a superuser creates further accounts through `POST /api/v1/auth/register`, which is not open to the public.

That gets the dashboard and API running. The WhatsApp side additionally needs a Twilio sandbox, an ngrok tunnel and a local Ollama — the full walkthrough, including troubleshooting, is in [`docs/SETUP.md`](docs/SETUP.md).

## Documentation

All project documentation lives in [`docs/`](docs/):

| Doc | What's in it |
|---|---|
| [SETUP.md](docs/SETUP.md) | Full setup walkthrough from a clean clone, including Twilio, ngrok, Ollama and troubleshooting |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the codebase is organised, layering rules, the data model |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Day-to-day workflow — tests, migrations, common gotchas, conventions |
| [ROADMAP.md](docs/ROADMAP.md) | What shipped, what was built differently than planned, what was left unbuilt |
| [API.md](docs/API.md) | API reference summary (the live schema is at `/docs` when the API is running) |
| [DECISIONS.md](docs/DECISIONS.md) | Design decision log — the "why" behind non-obvious choices |

## What's currently working

As of the latest commit on `main`:

- **Authentication** — JWT login for the dashboard, protected routes; new accounts can only be created by a superuser
- **Dashboard** — today's overview: order counts, revenue today, and a status board (Received → Preparing → Ready → Delivering)
- **Customers** — create, edit, deactivate, reactivate; search and channel filters; per-customer default-order templates
- **Products & Categories** — full CRUD, availability toggle, aliases for the bot's matcher, soft deactivation with order-history preservation
- **Orders** — list / detail / create / edit / status transitions / cancellation; order-line snapshots preserve historical name, price and unit
- **WhatsApp bot** — Twilio webhook with signature verification; keyword and button fast paths (menu, order status, reorder last, new order); an LLM safety valve (Celery + Ollama) for free-text orders; interactive buttons through nine Twilio Content Templates
- **Customer web app** — token-authenticated pages for a new order, a reorder, registration and invoices (an edit-cart page also exists, but the bot doesn't issue edit links). A customer can place the order or save the cart and continue later
- **Registration and approval** — an unrecognised number registers through a web form; the owner is notified on WhatsApp and approves or rejects from the dashboard on their phone; an approved customer is told they can start ordering
- **Inventory (simplified Phase 5)** — optional stock counts for sealed, packaged goods with a low-stock threshold; stock is deducted when an order is placed and restored when it is cancelled or deleted; customers see a low-stock flag while ordering; the owner gets a stock page and a derived daily prep list for made-to-order items
- **Billing (simplified Phase 6)** — an owner billing summary, per-customer billing pages and invoices, and a customer-facing invoice page that a customer can open from WhatsApp
- **Responsive UI** — works at desktop sizes and as a sidebar drawer on mobile

What's **not** built:

- **Raw materials, recipes and stock movements** — the originally planned Phase 5 design. Inventory tracks stock on the product itself instead (see [ADR-24](docs/DECISIONS.md))
- **Order notifications** — owner alerts for new, cancelled or edited orders, status updates to customers as an order progresses, and a notification-preferences screen. Only registration and approval notifications exist
- **Background scheduler** — no scheduled jobs
- **Receipts as PDF, and CSV exports** — invoices are viewed on screen
- **Editable business details** — the bakery name, address and contact on invoices come from `.env`; the Settings page only manages categories
- **CI/CD, end-to-end tests and deployment configuration** — there is no `.github/` workflow, Playwright suite or hosting config; `nginx/` is an empty placeholder
- **Voice ordering** — dropped from scope

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the phase-by-phase detail.

## Repository structure

```
bakeriq/
├── backend/                    # FastAPI app + Celery worker (one Dockerfile, two services)
│   ├── app/
│   │   ├── api/v1/             # Endpoint routes
│   │   ├── core/               # Config, database, deps, security, Celery/Ollama/Twilio clients
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # Business logic (service layer)
│   │   └── tasks/              # Celery tasks (LLM order parsing)
│   ├── alembic/                # Database migrations
│   ├── scripts/                # Seed script, first-owner script, Twilio Content Template bootstrap
│   ├── tests/                  # pytest suite
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                   # Owner dashboard (React + Vite)
│   └── src/
│       ├── api/                # Axios clients
│       ├── components/         # Shared components
│       ├── context/            # Auth context
│       ├── hooks/              # TanStack Query hooks
│       ├── lib/                # Formatters and utilities
│       └── pages/              # Top-level page components
├── frontend-customer/          # Customer web app (React + Vite), token-authenticated
├── nginx/                      # Empty placeholder
├── scripts/                    # Bash wrappers behind the Makefile
├── docs/                       # Project documentation
├── .devcontainer/              # VS Code dev container config (optional)
├── docker-compose.yml          # Service orchestration
├── Makefile                    # Day-to-day commands
├── LICENSE                     # MIT (see NOTICE.md for the reserved items)
├── NOTICE.md                   # Items excluded from the MIT grant
└── README.md                   # You are here
```

## Common commands

```bash
make help              # List all available make targets
make dev-up            # Stack up + ngrok started if needed + tunnel hostname checked against PUBLIC_BASE_URL
make reset-db          # Drop + recreate + migrate + seed the dev database
make seed              # Re-seed without dropping
make migrate           # Run pending migrations
make migration         # Generate a new migration from model changes
make test              # Run the full backend test suite (pytest tests/ -v, in the api container)
make test-fast         # Same suite, but stop at the first failure (-x)
make ps                # docker compose ps
make logs              # Tail logs from all services
make shell-api         # Open a bash shell inside the api container
make shell-db          # Open a psql shell against the dev database
make ngrok-check       # Read-only: is ngrok up, and does its hostname match PUBLIC_BASE_URL in .env?
make templates-refresh # Create any missing Content Templates, restart api + worker, re-check (see docs/DEVELOPMENT.md for stale URLs)
make whatsapp-smoke    # Send the bakeriq_nav template to SMOKE_TEST_PHONE (required, no default; a real message)
```

## License and ownership

BakeriQ is **partly open source and partly all rights reserved.** The source code is released under the [MIT License](LICENSE) so it can be used, studied and adapted; the items listed in [NOTICE.md](NOTICE.md) are **excluded from that grant and remain all rights reserved**.

VERIFY: the list of reserved items in [`NOTICE.md`](NOTICE.md) is a draft for the author to confirm. The project was built during an internship for a client bakery, so ownership of the work should also be checked against the internship terms before relying on this notice.

## Maintainer

San Shibu — GitHub [@scorpiocodex](https://github.com/scorpiocodex)
