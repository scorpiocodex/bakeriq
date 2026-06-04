# BakeriQ

WhatsApp-first order management platform for local bakeries. Built as a single-tenant internal tool that turns daily customer chatter on WhatsApp (and the occasional voice call) into structured orders, prep lists, and delivery tracking.

> **Status:** Active development — internship project. Phases 1 and 2 complete; Phase 3 (WhatsApp bot + LLM order parser) is next.

## What problem this solves

Local bakeries take orders informally — WhatsApp messages, voice calls, regulars who order "the usual" every morning. The owner mentally tracks who's getting what, the chef prepares based on a verbal handoff, and nothing is written down until billing time.

BakeriQ replaces that with a thin layer of structure:

- A customer-facing channel (WhatsApp bot — Phase 3) that parses natural language orders into structured order rows
- A web dashboard the owner uses to see today's pending orders, what's being prepared, and what's out for delivery
- Default order templates for regulars ("Anita's usual: 3 veg puffs + 2 ladoos")
- Snapshot-preserving order history so price changes don't rewrite past orders

The system is single-tenant by design (one bakery, one owner, one chef) and India-only.

## Tech stack

**Backend:** FastAPI 0.115 · Python 3.11 · SQLAlchemy 2.0 · Alembic · PostgreSQL 15 · Redis 7 · JWT auth (python-jose + bcrypt)
**Frontend:** React 18 · Vite 5 · TailwindCSS · TanStack Query v5 · react-router-dom v6 · axios · lucide-react
**Infrastructure:** Docker Compose orchestrating db / db_test / redis / api / frontend
**Testing:** pytest (96 backend tests passing as of Phase 2 close)

## Quick start

Prerequisites: Docker Desktop or Docker Engine + Docker Compose, Git, Python 3.11+ (for the secret-key one-liner only).

```bash
# Clone and enter
git clone git@github.com:scorpiocodex/bakeriq.git
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

- **Frontend:** http://localhost:5173
- **API docs (Swagger UI):** http://localhost:8000/docs
- **API docs (ReDoc):** http://localhost:8000/redoc

**Login credentials (seeded):**

| Email | Password |
|---|---|
| `owner@bakeriq.com` | `bakeriqowner` |

Full setup walkthrough including troubleshooting: [`docs/SETUP.md`](docs/SETUP.md).

## Documentation

All project documentation lives in [`docs/`](docs/):

| Doc | What's in it |
|---|---|
| [SETUP.md](docs/SETUP.md) | Full setup walkthrough from a clean clone, including troubleshooting |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the codebase is organised, layering rules, the data model |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Day-to-day workflow — tests, migrations, common gotchas, conventions |
| [ROADMAP.md](docs/ROADMAP.md) | What's done, what's next, phase-by-phase |
| [API.md](docs/API.md) | API reference summary (full schema lives at `/docs` when the API is running) |
| [DECISIONS.md](docs/DECISIONS.md) | Design decision log — the "why" behind non-obvious choices |

## What's currently working

As of the latest commit on `main`:

- **Authentication** — JWT login flow, protected routes, token refresh
- **Dashboard** — today's overview with order counts by status, revenue today, four-column status board (Received → Preparing → Ready → Delivering)
- **Customers** — full CRUD: create, edit, deactivate, reactivate; channel filter (WhatsApp / Voice / Inactive); search by name or phone; per-customer default-order templates
- **Products & Categories** — full CRUD; per-category filter chips; "Available today" toggle; soft deactivation with order-history preservation
- **Default order templates** — per-customer named templates that can be one-tap-loaded into a new order
- **Orders** — list / detail panel / create / edit / status transitions / cancellation; order-line snapshots preserve historical name/price/unit even after product changes
- **Settings → Categories** — manage category list, ordering, soft deactivation
- **Responsive UI** — works at desktop sizes and as a sidebar drawer on mobile

What's **not** built yet:

- WhatsApp bot (Phase 3)
- Voice bot and notifications (Phase 4)
- Inventory and stock pool (Phase 5)
- Billing and receipts (Phase 6)

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the full plan.

## Repository structure

```
bakeriq/
├── backend/                    # FastAPI app
│   ├── app/
│   │   ├── api/v1/             # Endpoint routes
│   │   ├── core/               # Config, database, deps, security
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   └── services/           # Business logic (service layer)
│   ├── alembic/                # Database migrations
│   ├── scripts/                # Seed scripts
│   ├── tests/                  # pytest suite
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                   # React + Vite app
│   └── src/
│       ├── api/                # Axios clients
│       ├── components/         # Shared components
│       ├── context/            # Auth context
│       ├── hooks/              # TanStack Query hooks
│       ├── lib/                # Formatters and utilities
│       └── pages/              # Top-level page components
├── scripts/                    # Bash wrappers behind Makefile
├── docs/                       # Project documentation
├── .devcontainer/              # VS Code dev container config (optional)
├── docker-compose.yml          # Service orchestration
├── Makefile                    # Day-to-day commands
└── README.md                   # You are here
```

## Common commands

```bash
make help              # List all available make targets
make reset-db          # Drop + recreate + migrate + seed the dev database
make seed              # Re-seed without dropping
make migrate           # Run pending migrations
make migration         # Generate a new migration from model changes
make test              # Run the full backend test suite
make test-fast         # Run tests without coverage / verbose
make ps                # docker compose ps
make logs              # Tail logs from all services
make shell-api         # Open a bash shell inside the api container
make shell-db          # Open a psql shell against the dev database
```

## License

Proprietary — internal project. Not for redistribution.

## Maintainer

San Shibu — GitHub [@scorpiocodex](https://github.com/scorpiocodex)
