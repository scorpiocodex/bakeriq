# Architecture

This document explains how the BakeriQ codebase is structured and the rules it follows. Intended for anyone reading or modifying the code.

For *day-to-day workflow* (running tests, creating migrations, etc.) see [`DEVELOPMENT.md`](DEVELOPMENT.md). For *why* specific choices were made, see [`DECISIONS.md`](DECISIONS.md).

## High-level shape

BakeriQ is a conventional two-tier web application:

```
┌──────────────────────────────┐
│  React frontend (Vite)       │
│  Port 5173                   │
└──────────────┬───────────────┘
               │  HTTP / JSON (axios)
               │  JWT Bearer auth
               ▼
┌──────────────────────────────┐
│  FastAPI backend (uvicorn)   │
│  Port 8000                   │
│                              │
│   api → service → model      │
└──────────────┬───────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
┌─────────────┐  ┌─────────────┐
│ PostgreSQL  │  │   Redis 7   │
│  Port 5432  │  │  Port 6379  │
└─────────────┘  └─────────────┘
```

Postgres holds all persistent state. Redis is currently unused but will become the conversation-state store in Phase 3 (WhatsApp bot).

Authentication is JWT — the frontend logs in once, gets a token, and includes it as `Authorization: Bearer <token>` on every subsequent request. There are no sessions, no cookies, no CSRF concerns.

The system is single-tenant by design: one bakery, one owner, one chef. There is no organisation or tenant concept — all data is global within a single deployment.

## Backend

### Layering

The backend follows a strict three-layer pattern:

```
api/v1/<resource>.py    ← Pydantic in/out, HTTP concerns, calls service
       │
       ▼
services/<resource>_service.py  ← Business logic, queries, validation
       │
       ▼
models/<resource>.py    ← SQLAlchemy ORM models
```

**API layer** (`backend/app/api/v1/`) — One file per resource: `customers.py`, `products.py`, `orders.py`, etc. These handle:

- Path/query parameter binding
- Pydantic input validation
- Calling the corresponding service function
- Pydantic output serialization
- HTTP status codes and `HTTPException`s

API layer files contain **no business logic**. If a function has more than a few lines of work between getting a request and returning a response, that work belongs in the service layer.

**Service layer** (`backend/app/services/`) — One file per resource: `customer_service.py`, `product_service.py`, `order_service.py`, etc. These contain:

- Database queries and joins
- Cross-table validation
- Business rules (e.g., "can't reactivate a cancelled order")
- Transactions

Services take a `db: Session` as their first parameter and return ORM model instances (or `None`). They don't touch HTTP concerns — they don't raise `HTTPException`, they raise domain exceptions or return sentinel values that the API layer translates.

**Model layer** (`backend/app/models/`) — SQLAlchemy declarative models. One file per table. Models can have computed properties and simple helper methods but **no querying** — that belongs in services.

### Why this layering matters

The reason for the strict separation is that it makes the codebase testable and survivable when requirements change. The service layer can be unit-tested without spinning up FastAPI. The API layer becomes thin enough that changes are mechanical. When the WhatsApp bot lands in Phase 3, the bot's message handler will call the same service functions the API uses — no business logic gets duplicated.

### Pydantic schemas

`backend/app/schemas/` — one file per resource. Each file typically defines:

- `*Create` schema (for POST request bodies)
- `*Update` schema (for PATCH bodies — all fields optional)
- `*Read` schema (for response bodies — includes IDs and timestamps)
- `*ListResponse` schema (paginated list wrapper with `items`, `total`)

Schemas are the contract with the frontend. The frontend types in `frontend/src/api/*.js` mirror these.

### Core

`backend/app/core/` — cross-cutting infrastructure:

- `config.py` — Pydantic Settings reading from `.env`
- `database.py` — SQLAlchemy engine, session factory, `get_db` dependency
- `deps.py` — FastAPI dependencies including `get_current_user`
- `security.py` — password hashing (bcrypt), JWT encoding/decoding

Imports are locked:

```python
from app.core.database import get_db
from app.core.deps import get_current_user
```

Don't shorten these or move `get_db` somewhere else.

### Migrations

`backend/alembic/versions/` — Alembic migrations, one per schema change. Generated via `make migration` (which runs `alembic revision --autogenerate`).

**Read [`DEVELOPMENT.md`](DEVELOPMENT.md) before creating a migration** — there's a recurring Alembic quirk with the `customers.secondary_phone` unique index that has to be cleaned up by hand on every migration.

### Tests

`backend/tests/` — pytest. One test module per service. Tests use a separate `db_test` database container (port 5433) so they never touch dev data. 96 tests pass as of Phase 2 close.

Test conventions:

- Fixtures live in `tests/conftest.py`
- Each test gets a fresh database state (transaction rollback after each test)
- Tests are organised by behaviour, not by endpoint shape — `test_snapshot_survives_price_change` rather than `test_get_order_returns_200`

## Frontend

### Layering

The frontend follows a four-layer pattern that mirrors the backend's three-layer one:

```
pages/<Page>.jsx          ← Page composition, UI state
   │
   ▼
hooks/use<Resource>.js    ← TanStack Query hooks, cache management
   │
   ▼
api/<resource>.js         ← Axios calls, request/response shaping
   │
   ▼
api/client.js             ← Shared axios instance with auth interceptor
```

**Page layer** (`frontend/src/pages/`) — Top-level components rendered by react-router. One file per route: `Dashboard.jsx`, `Customers.jsx`, `Orders.jsx`, etc. Pages own UI state (which filter chip is active, which modal is open) and compose hooks + components. Pages contain no `axios` calls and no business logic — they read data from hooks and call mutation functions.

**Hook layer** (`frontend/src/hooks/`) — TanStack Query hooks. One file per resource: `useCustomers.js`, `useProducts.js`, etc. Each file typically exports:

- A list-fetching hook (`useCustomersList(filters)`)
- A detail-fetching hook (`useCustomer(id)`)
- Mutation hooks (`useCreateCustomer()`, `useUpdateCustomer()`, `useDeactivateCustomer()`)

Hooks own caching, refetching, and invalidation. Pages just call them.

**API layer** (`frontend/src/api/`) — Plain axios functions. One file per resource. These return raw response data (or throw on error). They don't know about React Query, components, or state.

**Client layer** (`frontend/src/api/client.js`) — A single configured axios instance. This is where the JWT auth interceptor lives — every request automatically gets `Authorization: Bearer <token>` attached if a token is present.

### State management

There are two kinds of state in the frontend:

- **Server state** — anything that comes from the API (customer list, products, orders). Lives in TanStack Query cache.
- **UI state** — anything purely visual (which modal is open, what's in the search box, which chip is active). Lives in `useState` inside the relevant page or component.

There is **no Redux, Zustand, Context API for data, or any other global store**. Server state is in TanStack Query; UI state is local. The only React context used is `AuthContext` (for the logged-in user and token).

### Components

`frontend/src/components/` — shared components used across multiple pages:

- **Layout components**: `Layout.jsx` (root grid), `Sidebar.jsx`, `TopBar.jsx`, `BrandMark.jsx`
- **Reusable UI**: `StatusBadge.jsx` (status pills with icons), `RowActionsMenu.jsx` (⋯ popover), `ConfirmDialog.jsx`
- **Form modals**: `CustomerFormModal.jsx`, `ProductFormModal.jsx`, `OrderFormModal.jsx`, `DefaultOrderModal.jsx`
- **Order detail**: `OrderDetailPanel.jsx` (the slide-in panel on Orders page)
- **Routing**: `ProtectedRoute.jsx` (gates routes behind auth)

### Utilities

`frontend/src/lib/format.js` — display formatters:

- `formatPhone(e164)` — `+919999912345` → `+91 99999 12345`
- `formatUnitLabel(raw)` — `half_kg` → `Half Kg`
- `formatINR(amount)` — `742.5` → `₹742.50`

These exist so we never have one component formatting prices one way and another formatting them differently. If a display convention changes, edit `format.js`.

### Styling

Tailwind v3 with a small custom theme in `tailwind.config.js`:

- Brand colour ramp (`brand-50` through `brand-800`) — variants of the primary blue
- Inter font family
- `maxWidth.app: '1400px'` — the application content cap

No component library — components are built directly with Tailwind classes. Lucide-react for icons. Status colours use Tailwind's semantic palette (green for active/success, amber for in-progress, red for cancelled, etc.).

## Data model

The current schema (as of Phase 2 close):

```
users
  └─ id, email (unique), full_name, hashed_password, is_active, timestamps

customers
  └─ id, name, primary_phone (unique), secondary_phone, whatsapp_enabled,
     notes, is_active, timestamps

categories
  └─ id, name (unique), display_order, is_active, timestamps

products
  └─ id, name, description, category_id (FK → categories),
     unit_price, unit_label, is_available_today, is_active, timestamps

default_orders
  └─ id, customer_id (FK → customers), name, notes, timestamps
  └─ items: default_order_items[]
     └─ id, default_order_id (FK), product_id (FK), quantity

orders
  └─ id, customer_id (FK), order_date, status (enum), notes,
     total_amount, created_at, updated_at
  └─ items: order_items[]
     └─ id, order_id (FK), product_id (FK, nullable),
        product_name (snapshot), unit_price (snapshot), unit_label (snapshot),
        quantity, subtotal (snapshot)
```

### The snapshot pattern

The most important non-obvious design choice: **`order_items` snapshot product name, price, and unit at creation time**. The `product_id` is preserved as a soft reference, but the displayed values are always read from the snapshot columns.

Why: if a product's price changes from ₹84 to ₹90 next week, today's orders should still show ₹84 — that's what the customer was charged. Without snapshots, every historical order would silently update whenever a product changes, which is wrong both legally (receipts must match what was actually paid) and operationally (the chef would see different numbers from what the customer was quoted).

The test `test_snapshot_survives_price_change` is the guardrail. **Do not remove or alter it without a deliberate decision** that this invariant should change.

### Order status lifecycle

Orders move through a five-state enum stored natively in Postgres as `order_status`:

```
received → preparing → ready → delivering   (forward chain)
              ↓           ↓         ↓
                    cancelled  (terminal — no reactivation)
```

The status-transition logic in `order_service.transition_status()`:

- Forward transitions within the chain are allowed
- Backward transitions are allowed (we may discover an order was advanced too early)
- `cancelled` is reachable from any state
- `cancelled` is terminal — you can't reactivate a cancelled order; you create a new one

This is event-driven, not clock-driven — orders don't auto-advance based on time. A future automation could advance them when, say, the WhatsApp bot confirms delivery, but the clock alone is not enough signal.

### Active / inactive convention

Customers, products, and categories all have an `is_active` boolean. Filter parameters use a `status` enum with three values: `'active'`, `'inactive'`, `'all'`. Default is `'active'`. Regex-validated at the endpoint to prevent typos slipping through.

This is preferred to a deleted_at timestamp because operationally the bakery owner thinks in "active vs deactivated" not "soft-deleted vs visible." Reactivation is a normal operation, not an exception.

## Frontend ↔ backend protocol

The frontend and backend communicate over plain HTTP/JSON. There is no GraphQL, no tRPC, no WebSockets (yet — Phase 4 may add them for live notifications).

Response shapes are stable Pydantic schemas. List endpoints return a wrapper:

```json
{
  "items": [...],
  "total": 47
}
```

Detail endpoints return the bare resource. Errors return a standard FastAPI shape:

```json
{ "detail": "Customer not found" }
```

Or for validation failures:

```json
{ "detail": [
    { "loc": ["body", "primary_phone"], "msg": "field required", ... }
] }
```

The frontend's axios interceptor surfaces the `detail` string into UI toasts / form errors.

## What's *not* in the architecture yet

These will land in later phases — flagged here so you know they're missing by design, not by accident:

- **Celery / async task queue** — Phase 3. Will be needed for LLM order parsing latency and for scheduled jobs (Phase 4).
- **WebSockets** — Phase 4. For pushing new orders to the dashboard in real time.
- **Background scheduler** — Phase 4. For the 4 AM chef brief, 6 AM voice dialler, etc.
- **Twilio webhook handler** — Phase 3. Inbound message endpoint with signature verification.
- **Claude API client** — Phase 3. For parsing natural-language WhatsApp messages into structured orders.
- **Inventory module** — Phase 5. Adds `raw_materials`, `recipes`, `stock_movements` tables.
- **Billing** — Phase 6. Adds invoice generation and export adapters.

See [`ROADMAP.md`](ROADMAP.md) for the full plan and rationale.
