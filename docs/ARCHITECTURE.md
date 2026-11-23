# Architecture

This document explains how the BakeriQ codebase is structured and the rules it follows. Intended for anyone reading or modifying the code.

For *day-to-day workflow* (running tests, creating migrations, etc.) see [`DEVELOPMENT.md`](DEVELOPMENT.md). For *why* specific choices were made, see [`DECISIONS.md`](DECISIONS.md). For *getting it running from a clean clone*, see [`SETUP.md`](SETUP.md).

## High-level shape

BakeriQ has two front ends, one API, and an async worker:

```
   WhatsApp (Twilio)                    Owner's browser
         |                                     |
         | webhook (HMAC-verified)             |
         v                                     v
+----------------------------------------------------------+
|  FastAPI (uvicorn) - port 8000                           |
|                                                          |
|   /api/v1/*   api -> service -> model                    |
|   /web/*      reverse proxy ------+                      |
|   /app/*      reverse proxy ------|--+                   |
+-------+----------------------+----|--|-------------------+
        |                      |    |  |
        |              enqueue |    |  |
        v                      v    |  |
+-------------+  +-------------+    |  |
| PostgreSQL  |  |   Redis 7   |    |  |
|  port 5432  |  |  port 6379  |    |  |
+-------------+  +------+------+    |  |
                        |           |  |
                 +------v------+    |  |
                 |   Celery    |    |  |
                 |   worker    +----|--|--> Ollama (host, :11434)
                 +-------------+    |  |
                                    |  |
        +---------------------------+  +--------------+
        v                                             v
+----------------------+                  +----------------------+
| frontend-customer    |                  | frontend (dashboard) |
| Vite, base=/web/     |                  | Vite, base=/app/     |
| port 5174            |                  | port 5173            |
+----------------------+                  +----------------------+
```

**Why the API proxies both front ends.** Twilio needs one public URL, and ngrok's free tier gives one tunnel. Routing `/web` and `/app` through FastAPI means a single hostname reaches the API, the customer app, and the dashboard. Each Vite config declares a matching `base` so paths forward verbatim — stripping the prefix instead would break asset URLs. The API therefore serves three prefixes: `/api`, `/web`, `/app`. A production deployment would put a web server such as nginx in front of the built bundles to do the same routing; that is not built — the `nginx/` folder is an empty placeholder (see [`ROADMAP.md`](ROADMAP.md)).

**Redis** carries three things on separate databases: Celery's broker (DB 1), Celery's result backend (DB 2), and the in-progress cart cache (DB 0). Separate DBs so flushing the queue can't wipe cart state.

**Ollama** runs natively on the host rather than in a container — the model is ~2 GB and would need re-pulling on every rebuild. How containers reach it depends on the platform. On Linux it is the Docker bridge gateway (`172.17.0.1:11434`), which requires `OLLAMA_HOST=0.0.0.0` on the host and a UFW rule if the firewall is up. On Docker Desktop for Windows (tested) the bridge address is refused and `host.docker.internal:11434` works, with Ollama left on its default loopback binding. See [`SETUP.md`](SETUP.md).

Authentication is JWT, but only for the dashboard. Customer-facing flows have no login — a URL-safe token in the path *is* the credential, scoped to one action. See [The WhatsApp channel](#the-whatsapp-channel).

The system is single-tenant by design: one bakery, one owner, one chef. There is no organisation or tenant concept — all data is global within a single deployment.

## Backend

### Layering

The backend follows a strict three-layer pattern:

```
api/v1/<resource>.py    <- Pydantic in/out, HTTP concerns, calls service
       |
       v
services/<resource>_service.py  <- Business logic, queries, validation
       |
       v
models/<resource>.py    <- SQLAlchemy ORM models
```

**API layer** (`backend/app/api/v1/`) — One file per resource: `customers.py`, `products.py`, `orders.py`, etc. These handle:

- Path/query parameter binding
- Pydantic input validation
- Calling the corresponding service function
- Pydantic output serialization
- HTTP status codes and `HTTPException`s

API layer files contain **no business logic**. If a function has more than a few lines of work between getting a request and returning a response, that work belongs in the service layer.

**Service layer** (`backend/app/services/`) — Business logic, queries, cross-table validation, transactions. Services take a `db: Session` as their first parameter and return ORM model instances (or `None`). They don't touch HTTP concerns — they don't raise `HTTPException`, they raise domain exceptions or return sentinel values that the API layer translates.

The service layer is no longer one-file-per-resource. Phase 3 added a cluster of services with no corresponding REST resource:

| Service | Role |
|---|---|
| `customer_service`, `product_service`, `order_service`, `category_service`, `default_order_service` | CRUD + business rules for the dashboard resources |
| `customer_handler` | Fast-path dispatcher for inbound WhatsApp — keywords and button taps |
| `registration_handler` | Issues a webform token for unrecognised numbers |
| `llm_parser_service` | Ollama call, structured-JSON extraction of items + quantities |
| `product_matcher_service` | Deterministic resolution of parsed names against the product table |
| `llm_cart_handoff_service` | Turns matched items into a cart + web link |
| `reply` | The `Reply` primitive (text XOR template) |
| `template_replies` | Factories building `Reply` objects for each Content Template |
| `whatsapp_sender` | Twilio REST sends + audit logging of every attempt |
| `twilio_content_service` | Content Template CRUD (the SDK can't create templates) |
| `conversation_log` | Conversation + message persistence, customer lookup by phone |
| `conversation_state` | Redis-backed short-lived conversation state |
| `cart_cache` | Redis-backed in-progress cart contents |
| `token_service`, `web_link_service` | Cart-link tokens and their URLs |
| `registration_token_service` | Registration webform tokens |
| `pending_registration_service` | The approval queue; approve/reject transitions |
| `owner_notification_service` | Outbound alerts to the owner's phone |

**Model layer** (`backend/app/models/`) — SQLAlchemy declarative models. One file per table. Models can have computed properties and simple helper methods but **no querying** — that belongs in services.

### Why this layering matters

The strict separation makes the codebase testable and survivable when requirements change. The service layer can be unit-tested without spinning up FastAPI. The API layer stays thin enough that changes are mechanical.

Phase 3 is the payoff: the WhatsApp bot creates orders through `order_service`, exactly as the dashboard API does. No business logic is duplicated across the two channels.

### Pydantic schemas

`backend/app/schemas/` — one file per resource. Each file typically defines:

- `*Create` schema (for POST request bodies)
- `*Update` schema (for PATCH bodies — all fields optional)
- `*Read` / `*Out` schema (for response bodies — includes IDs and timestamps)
- `*ListResponse` schema (paginated list wrapper with `items`, `total`)

Schemas are the contract with the frontend. The frontend's `frontend/src/api/*.js` functions mirror them.

One trap worth knowing: `CustomerBase` requires `address_line_1`, `city`, `state`, and `pincode`. Anything that creates a Customer has to supply all four, or the row inserts fine and then breaks `CustomerOut` serialization — which 500s the entire customers list, not just the offending row. This is why the registration webform requires a full address.

### Core

`backend/app/core/` — cross-cutting infrastructure:

- `config.py` — Pydantic Settings reading from `.env`
- `database.py` — SQLAlchemy engine, session factory, `get_db` dependency
- `deps.py` — FastAPI dependencies including `get_current_user`
- `security.py` — password hashing (bcrypt), JWT encoding/decoding
- `twilio_client.py` — Twilio SDK client + webhook signature verification
- `ollama_client.py` — Ollama client
- `redis_client.py` — Redis connection
- `celery_app.py` — Celery application and task discovery

Imports are locked:

```python
from app.core.database import get_db
from app.core.deps import get_current_user
```

Don't shorten these or move `get_db` somewhere else.

Note that `.env` changes need `docker compose up -d --force-recreate`, not `restart` — a restarted container keeps the environment it was created with.

### Migrations

`backend/alembic/versions/` — Alembic migrations, one per schema change. Generated via `make migration` (which runs `alembic revision --autogenerate`).

**Read [`DEVELOPMENT.md`](DEVELOPMENT.md) before creating a migration.** Autogenerate is noisy on this schema: it reliably re-detects the `customers.secondary_phone` unique index, and it emits cosmetic `VARCHAR(n)` length changes for columns that haven't actually changed. It has also produced `op.drop_constraint(None, ...)`, which crashes at migration time. Read every generated migration before applying it; hand-writing is often faster than cleaning up.

### Tests

`backend/tests/` — pytest. Tests use a separate `db_test` database container (port 5433) so they never touch dev data. **396 tests pass** (run inside the `api` container, 23 November 2026).

Test conventions:

- Fixtures live in `tests/conftest.py`
- Each test starts from truncated tables (faster than drop/create, same isolation)
- Tests are organised by behaviour, not by endpoint shape — `test_snapshot_survives_price_change` rather than `test_get_order_returns_200`

`conftest.py` carries an autouse fixture (`mute_outbound_notifications`) that stubs out `owner_notification_service.notify_new_registration` and `customer_notification_service.notify_approved`. Without it, every suite run fires real WhatsApp messages at the owner's and a customer's phone and burns Twilio sandbox quota.

## The WhatsApp channel

Phase 3 added an inbound channel that reuses the same service layer the dashboard API calls.

### Inbound path

```
Twilio POST /api/v1/webhooks/twilio
    |  HMAC signature verified as a FastAPI dependency
    |  MessageSid checked for replay (Twilio retries on failure)
    v
_dispatch() - decides which handler runs
    |
    +- known active Customer --> customer_handler
    |                              |
    |                              +- keyword or button match --> list[Reply]
    |                              +- no match --> None --> Celery
    |
    +- awaiting_approval --> "still under review"
    +- rejected          --> polite decline
    +- unknown phone     --> registration_handler (issues a webform token)
```

Every handler returns `list[Reply] | None`. `None` means exactly one thing: the fast-path dispatcher found no match, so the message goes to the LLM.

Replies go back by one of two paths. A single plain-text reply is returned inline as TwiML, saving a round-trip. Anything else — multiple messages, or any Content Template — goes out through Twilio's REST API, because TwiML can't carry a template.

### The LLM safety valve

Unmatched messages are handed to a Celery task (`tasks.llm.parse_and_send`) rather than parsed inline — inference takes seconds and would hold the webhook past Twilio's timeout.

The task runs a two-stage parse:

1. **`llm_parser_service`** asks Ollama for structured JSON — item names and quantities. Ollama's `format` parameter constrains output at the sampling level, so the response is guaranteed-parseable without stripping markdown fences. Handles English, Malayalam, and Manglish (Malayalam written in Latin script).
2. **`product_matcher_service`** resolves those names against the real product table using exact matches and aliases. Deterministic; the LLM never decides what's orderable.

The split matters. The parser extracts *everything the customer named*, including off-menu items, and the matcher decides what's available. An earlier version had the LLM filter off-menu items itself, which erased the signal needed to tell a customer "we don't have that today" — the `nothing_available` branch became unreachable, and a message mixing on- and off-menu items sometimes returned nothing at all.

Retries cover both Ollama SDK errors and the `httpx` connection failures the SDK raises (the app's own calls use `httpx2`; see ADR-31). When they exhaust, a `MaxRetriesExceededError` handler sends a degraded-service message, so the customer is never left in silence.

### Outbound: Reply and Content Templates

`Reply` is a frozen dataclass with a body-XOR-content_sid invariant — an outbound message is unambiguously either plain text or a Content Template, never both. `Reply.text()` and `Reply.template()` are the factories.

Content Templates are how the bot renders tappable buttons instead of "reply MENU to see today's items". Nine live on Twilio, created idempotently by `scripts/bootstrap_content_templates.py`, with their SIDs written into `.env`:

| Template | Purpose |
|---|---|
| `bakeriq_greeting` | Personalised hello + Reorder / New / Status |
| `bakeriq_nav` | Mid-conversation prompt, same three buttons |
| `bakeriq_cart_link` | CTA opening the cart web app |
| `bakeriq_fallback` | Nothing matched — Menu / New / Status |
| `bakeriq_order_confirmation` | Itemised total + Status / Invoice / New |
| `bakeriq_registration_link` | CTA opening the registration webform |
| `bakeriq_owner_notification` | New-registration alert + CTA to the approvals page |
| `bakeriq_invoice_link` | CTA opening the customer's invoice page (sent when they tap Invoice) |
| `bakeriq_approved` | Welcome after the owner approves a registration — New order / Menu |

Two constraints worth knowing before touching them:

- **Button titles are load-bearing.** Twilio delivers the button's *title* as the inbound message body, and `customer_handler` matches on those strings. Renaming a button silently breaks its route.
- **URLs are baked in at creation time.** Changing `PUBLIC_BASE_URL` — which happens whenever an ngrok free-tier hostname rotates — leaves the cart-link, invoice-link and owner-notification templates pointing at a dead host. `make ngrok-check` detects when `PUBLIC_BASE_URL` in `.env` no longer matches the live tunnel, but it does not inspect Twilio. Neither editing the URL nor `make templates-refresh` replaces an existing template: the bootstrap script skips templates that already exist, so the old one has to be deleted on Twilio first. The full sequence is in [`DEVELOPMENT.md`](DEVELOPMENT.md#the-ngrok-hostname-problem); a static ngrok domain avoids the problem.

`whatsapp_sender` sends each `Reply` and logs every attempt to `conversation_messages`, including failures (with a null `twilio_sid`), so the audit trail records intent as well as delivery. `send_replies` returns `list[str | None]`, letting callers report honestly whether a message actually reached the customer.

### Token-based customer auth

Customers never log in. Two token types, both URL-safe random strings that appear in a URL path:

- **`web_session_tokens`** — customer sessions. Bound to a Customer. A `kind` column (`new` / `reorder` / `edit` / `invoice`) tells the customer app which flow to render. Cart kinds expire after 30 minutes and are consumed when the order is placed; `invoice` tokens, which open the invoice page, expire after 24 hours. The token string is the primary key.
- **`registration_tokens`** — the registration webform. Bound to a *phone* rather than a Customer, since registration happens before a Customer exists. 12-hour expiry, one-shot. Has a separate UUID `id` alongside the token.

They're separate tables rather than one polymorphic one: `web_session_tokens.customer_id` is non-null and load-bearing for the well-tested cart flow, and making it nullable to accommodate registration would risk silent bugs there.

The threat model is deliberately modest. WhatsApp is the identity layer — receiving the token on that number is the proof of ownership. A stolen token grants one action for one phone, and the registration form's phone field is read-only from the token, so an attacker can't register as someone else. Worst case is one junk row the owner rejects. This is the same pattern as a "click this link to confirm" email.

### Registration and approval

An unrecognised number gets a CTA card, taps through to `/web/register/{token}`, and fills a form (name plus a full delivery address — see the `CustomerBase` note above). Submitting creates a `pending_registrations` row in `awaiting_approval` and fires a WhatsApp card to the owner.

The owner taps that card's button, lands on `/app/approvals` on their phone, and approves or rejects. Approving copies the address field-for-field into a Customer — the two models share the same shape deliberately, so no re-parsing is needed. If a deactivated Customer already exists on that phone, approval reactivates it in place rather than inserting a second row, since `primary_phone` is unique.

Both transitions return 409 if the row is already terminal, so a double-tap on a phone can't create duplicates.

### Inventory and the prep list

Inventory is two small mechanisms, not a module with its own tables (see [ADR-24](DECISIONS.md)).

**Stock on the product.** Only sealed, packaged goods carry stock. Three nullable columns on `products` — `is_stockable`, `stock_quantity`, `low_stock_threshold` — are all it takes. `NULL` means "not tracked", which is deliberately different from "tracked, and zero". Stock is always counted in the product's own unit.

**Deduct at placement, restore on cancel or delete** (`inventory_service`, called from `order_service`):

- Creating an order deducts its stockable items immediately, rather than at delivery, so two customers can't both be promised the last packet.
- Editing an order's items restores the old lines and deducts the new ones.
- Moving an order into `cancelled` restores what it held. Drafts never deduct or restore.
- Hard-deleting an order (`DELETE /orders/{id}`) restores what it held too, unless it was already cancelled (that restored it at cancel time). Until 23 November 2026 deleting left the stock deducted; see ADR-25.
- Stock is allowed to go **negative**. The count drifts from reality anyway (someone sells a packet over the counter without touching the dashboard), so refusing an order on a possibly-stale zero would be worse than showing the owner a negative to correct. Low stock is a *warning* — `is_low_stock` on the product payload — shown to the customer while they build a cart and to the owner on the Inventory page. It never blocks an order.
- Non-stockable products, products never counted (`stock_quantity` is `NULL`) and hard-deleted products are skipped rather than erroring.

**The prep list.** Made-to-order items are baked and sold the same day, so there is nothing to count; what the chef needs is how many to make. `GET /api/v1/inventory/prep` derives that at read time — the sum of quantities by product across the day's orders for active, non-stockable products, excluding drafts and cancelled orders. Nothing is stored and no scheduler runs. The list is marked visible between 05:00 and 21:00: orders for a day close at 05:00, and after the baking window it's history.

### Billing and invoices

There are no billing tables. `billing_service` runs aggregate queries over `orders` and `order_items`, which already snapshot product name, price and unit.

Two filters apply to every query: `is_draft = false` (a cart isn't revenue) and `status != cancelled` for totals. Cancelled orders still *appear* on an invoice, greyed out, so the owner can see what was voided, but contribute nothing to the total. Dates use `order_date` (the business date the order is for), not `created_at`, matching `dashboard_service`.

An invoice is **per customer per day**, numbered `INV-YYYYMMDD-<first 8 characters of the customer id>`. The invoice header (business name, address, phone, email) is read from the `BUSINESS_*` environment variables through the `BusinessDetails` schema, so its source can later move to a table without changing the invoice shape.

Two ways in:

- **Owner:** the dashboard's Billing pages call the JWT-authed `/api/v1/billing/*` endpoints (summary, customer list, a customer's invoice dates, one invoice).
- **Customer:** the order-confirmation card carries an **Invoice** button. Tapping it sends a `bakeriq_invoice_link` card; the link carries an `invoice` token (24-hour expiry) and opens `/web/invoice/{token}`, which calls the unauthenticated, token-authenticated `GET /api/v1/invoice/{token}` and shows the customer's latest invoice.

## Frontend

There are two React apps.

**`frontend/`** — the owner dashboard. JWT-authed, served under `/app`, the larger of the two. Pages: Dashboard, Orders, Approvals, Customers, Products, Inventory (a stock table, a "track stock for a product" dialog and the prep list), Billing (plus per-customer and per-invoice pages) and Settings. Settings only manages categories.

**`frontend-customer/`** — the customer-facing app. No auth beyond the path token, served under `/web`, five routes: cart (`/new`, `/reorder`, `/edit`), registration (`/register`) and invoice (`/invoice`). On a cart page the customer can place the order or save the cart and continue later; the saved cart lives in Redis under the same token, so reopening the link within its 30-minute life resumes it. The `edit` kind and `/edit` route exist in the API and the customer app, but the bot does not currently issue `edit` links — its "modify", "edit", "confirm" and "cancel" keywords fall through to the LLM path.

Both are Vite + React 18 + TanStack Query + Tailwind, and follow the same layering.

### Layering

```
pages/<Page>.jsx          <- Page composition, UI state
   |
   v
hooks/use<Resource>.js    <- TanStack Query hooks, cache management
   |
   v
api/<resource>.js         <- Axios calls, request/response shaping
   |
   v
api/client.js             <- Shared axios instance with auth interceptor
```

**Page layer** (`src/pages/`) — Top-level components rendered by react-router. Pages own UI state (which filter chip is active, which modal is open) and compose hooks + components. Pages contain no `axios` calls and no business logic.

**Hook layer** (`src/hooks/`) — TanStack Query hooks. One file per resource. Each exports a list hook, sometimes a detail hook, and mutation hooks. Query keys are defined once per resource as a `*Keys` object — mistyped keys are the most common cause of "why didn't my list refresh?" bugs.

**API layer** (`src/api/`) — Plain axios functions returning raw response data. They don't know about React Query, components, or state.

**Client layer** (`src/api/client.js`) — A single configured axios instance. The dashboard's version attaches the JWT and redirects to login on 401.

### The /app basename

The dashboard's Vite `base` is `/app/`, and `BrowserRouter` takes a matching `basename`. Route paths stay unprefixed (`/orders`, not `/app/orders`) — React Router handles the prefix.

React Router respects the basename automatically; **raw `window.location` assignments do not**. Three places manipulate location directly (the 401 interceptor in `client.js`, `AuthContext`, and `api/auth.js`) and each hardcodes `/app/login`. Adding a fourth means remembering the prefix.

In dev the dashboard is at `localhost:5173/app/`; bare `localhost:5173` redirects there, but other unprefixed paths (for example `/login`) return 404.

### State management

Two kinds of state:

- **Server state** — anything from the API. Lives in TanStack Query cache.
- **UI state** — anything purely visual. Lives in `useState` inside the relevant page or component.

There is **no Redux, Zustand, Context API for data, or any other global store**. The only React context is `AuthContext`, for the logged-in user and token.

### Components

`frontend/src/components/` — shared components:

- **Layout**: `Layout.jsx` (root grid), `Sidebar.jsx`, `TopBar.jsx`, `BrandMark.jsx`
- **Reusable UI**: `StatusBadge.jsx`, `RowActionsMenu.jsx` (⋯ popover), `ConfirmDialog.jsx`
- **Form modals**: `CustomerFormModal.jsx`, `ProductFormModal.jsx`, `OrderFormModal.jsx`, `DefaultOrderModal.jsx`
- **Order detail**: `OrderDetailPanel.jsx`
- **Routing**: `ProtectedRoute.jsx`

`ConfirmDialog` has no text input. The approvals page needs a reason field on reject, so it carries a small local modal instead of extending the shared one.

### Utilities

`frontend/src/lib/format.js` — display formatters:

- `formatPhone(e164)` — `+919999912345` → `+91 99999 12345`
- `formatUnitLabel(raw)` — `half_kg` → `Half Kg`
- `formatINR(amount)` — `742.5` → `₹742.50`

These exist so we never have one component formatting prices one way and another differently. If a display convention changes, edit `format.js`.

### Styling

Tailwind v3 with a small custom theme in `tailwind.config.js`:

- Brand colour ramp (`brand-50` through `brand-800`)
- Inter font family
- `maxWidth.app: '1400px'` — the application content cap

No component library — components are built directly with Tailwind classes. Lucide-react for icons. Status colours use Tailwind's semantic palette (green for active/success, amber for in-progress, red for cancelled).

## Data model

```
users
  +- id, email (unique), full_name, password_hash, is_active,
     is_superuser, timestamps

customers
  +- id, name, primary_phone (unique), secondary_phone,
     preferred_channel_phone, whatsapp_enabled,
     address_line_1, address_line_2, city, state, pincode,
     notes, is_active, timestamps

categories
  +- id, name (unique), display_order, is_active, timestamps

products
  +- id, name, description, category_id (FK -> categories),
     unit_price, unit_label, aliases, is_available_today,
     is_stockable, stock_quantity (nullable), low_stock_threshold (nullable),
     is_active, timestamps

default_orders
  +- id, customer_id (FK -> customers), notes, is_active, timestamps
  +- items: default_order_items[]
     +- id, default_order_id (FK), product_id (FK), quantity, timestamps

orders
  +- id, customer_id (FK), status (enum), is_draft, order_date, notes,
     total_amount, timestamps
  +- items: order_items[]
     +- id, order_id (FK), product_id (FK, nullable),
        product_name (snapshot), unit_price (snapshot),
        unit_label (snapshot), quantity, subtotal (snapshot), timestamps

-- Phase 3: the WhatsApp channel --

conversations
  +- id, phone, customer_id (FK, nullable), current_order_id (FK, nullable),
     created_at, last_message_at
  +- messages: conversation_messages[]
     +- id, conversation_id (FK), direction, body,
        twilio_sid (nullable), intent (nullable), created_at

web_session_tokens
  +- token (PK), customer_id (FK), kind (new | reorder | edit | invoice),
     consumed_at, expires_at, created_at

-- Phase 3.5: registration + approval --

pending_registrations
  +- id, phone, name, address_line_1, address_line_2, city, state,
     pincode, status, customer_id (FK, nullable, set on approval),
     created_at, approved_at, updated_at

registration_tokens
  +- id, phone, token (unique), consumed_at, expires_at, created_at
```

### The snapshot pattern

The most important non-obvious design choice: **`order_items` snapshot product name, price, and unit at creation time**. The `product_id` is preserved as a soft reference, but displayed values always come from the snapshot columns.

Why: if a product's price changes from ₹84 to ₹90 next week, today's orders should still show ₹84 — that's what the customer was charged. Without snapshots, every historical order would silently update whenever a product changes, which is wrong both legally (receipts must match what was paid) and operationally (the chef would see different numbers from what the customer was quoted).

The test `test_snapshot_survives_price_change` is the guardrail. **Do not remove or alter it without a deliberate decision** that this invariant should change.

### Order status lifecycle

Orders move through a five-state enum stored natively in Postgres as `order_status`:

```
received -> preparing -> ready -> delivering   (forward chain)
    |           |          |          |
    +-----------+----------+----------+---> cancelled (terminal)
```

The status-transition logic in `order_service.change_status()`:

- Forward transitions within the chain are allowed
- Backward transitions are allowed (we may discover an order was advanced too early)
- `cancelled` is reachable from any state
- `cancelled` is terminal — you can't reactivate a cancelled order; you create a new one

This is event-driven, not clock-driven — orders don't auto-advance based on time. A clock has no idea whether the bread is actually ready.

### Registration status

`pending_registrations.status` is a plain string column with three values:

```
awaiting_approval -> approved   (Customer created or reactivated)
                  -> rejected   (no Customer; row kept for audit)
```

Both terminal states are kept on record. A rejected row lets the bot decline politely if that number messages again, rather than restarting registration in a loop.

### Active / inactive convention

Customers, products, and categories all have an `is_active` boolean. Filter parameters use a `status` enum with three values: `'active'`, `'inactive'`, `'all'`. Default is `'active'`, regex-validated at the endpoint to prevent typos slipping through.

Preferred to a `deleted_at` timestamp because operationally the owner thinks in "active vs deactivated", not "soft-deleted vs visible". Reactivation is a normal operation, not an exception — which is why approving a registration for a previously-deactivated phone reactivates that Customer rather than creating a new one.

## Frontend ↔ backend protocol

Plain HTTP/JSON. No GraphQL, no tRPC, no WebSockets.

Response shapes are stable Pydantic schemas. List endpoints return a wrapper:

```json
{
  "items": [],
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
    { "loc": ["body", "primary_phone"], "msg": "field required" }
] }
```

Status codes carry meaning in the token-based flows, and the customer app renders different UI for each: `404` (no such token), `410` (consumed or expired), `409` (already registered), `422` (validation).

## What's *not* in the architecture yet

Flagged here so you know they're missing by design, not by accident:

- **WebSockets** — the approvals badge polls every 30 seconds instead. Fine for a signal that arrives a few times a day; revisit if live order push lands.
- **Background scheduler** — nothing runs on a schedule. The prep list is derived at read time precisely so it needs none.
- **Order notifications** — no owner alerts when an order is placed, cancelled or edited, and no status updates to customers as an order moves through the chain. Only registration and approval send WhatsApp messages from a request handler. The Content Template infrastructure is in place for adding them.
- **Raw-materials inventory** — no `raw_materials`, `recipes` or `stock_movements` tables. Stock lives on the product for sealed goods only (see [Inventory and the prep list](#inventory-and-the-prep-list) and ADR-24).
- **Receipts and exports** — invoices are viewed on screen; there is no PDF or CSV generation.
- **Editable business details** — the invoice header comes from `.env`; Settings has no bakery-info section.
- **Production routing, CI and deployment** — the `/api`, `/web`, `/app` routing is done by the API's development proxy; there is no nginx configuration, CI workflow or hosting setup.
- **Voice ordering** — dropped. WhatsApp is the only ordering channel.

See [`ROADMAP.md`](ROADMAP.md) for the full plan and rationale.
