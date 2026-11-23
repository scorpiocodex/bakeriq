# API Reference

Human-readable summary of the BakeriQ HTTP API. For the complete machine-readable schema (full request/response shapes, every validation rule), run the API and visit **http://localhost:8000/docs** (Swagger UI) or **http://localhost:8000/redoc** (ReDoc).

This document is the "what exists and roughly what it does" view. Use Swagger when you need exact field names and types. It lists every route in the OpenAPI schema (50 at the time of writing), checked against the running API on 23 November 2026.

## Conventions

- **Base URL** in dev: `http://localhost:8000`
- **JSON API** lives under the prefix `/api/v1`. Outside it: `GET /health` (liveness probe, returns `{"status": "ok"}`) and the `/web/*` and `/app/*` reverse proxies to the customer app and the dashboard (not part of the API schema — see [`ARCHITECTURE.md`](ARCHITECTURE.md))
- **Content type:** JSON in, JSON out — except `POST /api/v1/auth/login`, which takes a form-encoded body
- **Three kinds of authentication:**
  - **JWT Bearer** — every dashboard endpoint. Header `Authorization: Bearer <token>`
  - **Path token** — the customer-facing endpoints (`/cart`, `/register`, `/invoice`). The URL-safe token in the path *is* the credential, scoped to one customer and one purpose
  - **Twilio signature** — `POST /api/v1/webhooks/twilio`
- **Errors:** standard FastAPI shape — `{ "detail": "<message>" }` for explicit errors, a structured array for Pydantic validation failures (422)
- **List endpoints** return a wrapper. Customers, products and categories return `{ "items": [...], "total": <int>, "skip": <int>, "limit": <int> }`; the stock, approvals and billing lists return `{ "items": [...], "total": <int> }` plus any extras noted below
- **Pagination:** `?skip=<int>&limit=<int>` on customers, products, categories and orders. `skip` defaults to 0; `limit` defaults to 50 (100 for categories) and is capped at 200
- **Soft deactivation:** customers, products and categories use an `is_active` flag. `DELETE` on them *deactivates* the row and returns it. Filter via `?status=active|inactive|all` (default `active`)

## Authentication

### `POST /api/v1/auth/login`

Exchange email + password for a JWT. The body is **form-encoded** (OAuth2 password flow), and the email goes in the `username` field.

```
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

username=owner@bakeriq.com&password=bakeriqowner
```

**Response 200:** `{ "access_token": "<JWT>", "token_type": "bearer" }`. Tokens last 7 days.

**Response 401:** `{ "detail": "Incorrect email or password" }` — the same message for an unknown email and a wrong password, so accounts can't be enumerated. **403:** `{ "detail": "Account disabled" }`.

### `GET /api/v1/auth/me`

Returns the authenticated user: `id`, `email`, `full_name`, `is_active`, `is_superuser`, `created_at`. The dashboard uses it to confirm a token is still valid on load.

### `POST /api/v1/auth/register`

Creates a dashboard user from `{ email, password, full_name? }` and returns it (201); 409 if the email exists. The password must be 8–72 characters. The new account is never a superuser.

**Requires a superuser's JWT.** **401** without a token, **403** for a signed-in user who isn't a superuser. The seeded owner is a superuser.

> **History.** Until 23 November 2026 this route had no authentication at all: anyone who could reach the API could register an account, log in and read customer data. It was closed in the same change that added the first-account script (see [ADR-28](DECISIONS.md#adr-28--account-creation-is-superuser-only-and-the-first-owner-comes-from-a-script)). The dashboard never calls the route.

The first account on a database nobody has logged in to can't be created through the API, so it comes from the command line: `docker compose exec -it api python -m scripts.create_owner --email <email> --name "<name>"` (hidden password prompt, or `BAKERIQ_OWNER_PASSWORD` when there is no terminal). It creates a superuser and refuses an email that already exists.

---

## Customers

All JWT-authed.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/customers` | List. Query: `skip`, `limit`, `search` (name or phone), `whatsapp_only` (bool), `status` |
| `POST /api/v1/customers` | Create. Required: `name`, `primary_phone`, `address_line_1`, `city`, `state`, `pincode`. Optional: `secondary_phone`, `address_line_2`, `preferred_channel_phone`, `whatsapp_enabled`, `notes` |
| `GET /api/v1/customers/{customer_id}` | Detail |
| `PUT /api/v1/customers/{customer_id}` | Update — every field optional; includes `is_active`, so it also reactivates |
| `DELETE /api/v1/customers/{customer_id}` | Deactivate (soft); returns the customer |

### Default order templates

One template per customer.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/customers/{customer_id}/default-order` | The template: `notes`, `is_active`, and `items[]` each with `product_id`, `quantity` and the full `product` |
| `PUT /api/v1/customers/{customer_id}/default-order` | Create or replace. Body: `{ notes?, is_active?, items: [{ product_id, quantity }] }` |
| `DELETE /api/v1/customers/{customer_id}/default-order` | Remove (204) |
| `GET /api/v1/customers/{customer_id}/order-prefill` | Suggested order lines built from the template, at **current** prices. Returns `{ items: [...], skipped_count: N }` — inactive products are skipped and counted. Empty if there is no template |

---

## Categories

All JWT-authed.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/categories` | List. Query: `skip`, `limit`, `status` |
| `POST /api/v1/categories` | Create: `{ name, display_order? }` (`name` is unique) |
| `GET /api/v1/categories/{category_id}` | Detail |
| `PUT /api/v1/categories/{category_id}` | Update: `name`, `display_order`, `is_active` (all optional) |
| `DELETE /api/v1/categories/{category_id}` | Deactivate (soft); returns the category |
| `DELETE /api/v1/categories/{category_id}/hard` | Permanently delete (204). Only allowed when no products reference the category |

---

## Products

All JWT-authed. Product payloads **do not include stock fields** — stock is read and written through the [Inventory](#inventory) endpoints.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/products` | List. Query: `skip`, `limit`, `search`, `category_id`, `available_today` (bool), `status` |
| `POST /api/v1/products` | Create. Required: `name`, `category_id`, `unit_price`. Optional: `unit_label`, `is_available_today`, `aliases[]`, `description` |
| `GET /api/v1/products/{product_id}` | Detail, with the full `category` |
| `PUT /api/v1/products/{product_id}` | Update — every field optional, including `is_active` |
| `DELETE /api/v1/products/{product_id}` | Deactivate (soft); returns the product |

`aliases` are the extra names the WhatsApp matcher recognises for a product.

---

## Orders

All JWT-authed.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/orders` | List newest-first. Query: `skip`, `limit`, `status`, `customer_id`, `order_date`. Returns compact rows (each with an `item_count`, no line items) plus pagination info |
| `POST /api/v1/orders` | Create: `{ customer_id, items: [{ product_id, quantity }], order_date?, status?, notes? }`. Lines are snapshotted (name, price, unit) and stock for stockable items is deducted. Returns 201 |
| `GET /api/v1/orders/{order_id}` | Detail, with the customer summary and full line items |
| `PUT /api/v1/orders/{order_id}` | Edit `order_date`, `notes` and/or `items`. If `items` is sent, the lines are rebuilt and re-snapshotted, the total recomputed, and stock restored then re-deducted. Status is **not** changed here |
| `PATCH /api/v1/orders/{order_id}/status` | Move the order: body `{ "status": "received" \| "preparing" \| "ready" \| "delivering" \| "cancelled" }`. Moving into `cancelled` restores stock |
| `DELETE /api/v1/orders/{order_id}` | Hard-delete the order and its lines (204). Meant for genuine mistakes such as a test order; prefer cancelling, which keeps the record. Stock the order held is restored first, as on cancel (a cancelled order already restored it, so it isn't restored twice) |

Status rules are in [`ARCHITECTURE.md`](ARCHITECTURE.md#order-status-lifecycle): forward and backward moves along the chain are allowed, `cancelled` is reachable from any state and is terminal.

---

## Dashboard

### `GET /api/v1/dashboard/summary` (JWT)

Returns `today_orders`, `pending`, `in_progress`, `cancelled_today`, `revenue_today` (excludes cancelled orders), `active_customers`, `active_products`, `unavailable_products`, `summary_date`, and `board` — the orders grouped by status column for the dashboard's board, each card carrying `id`, `customer_name`, `item_summary` and `status`.

---

## Approvals

JWT-authed. These back the owner's mobile approval page (see [Registration and approval](ARCHITECTURE.md#registration-and-approval)).

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/approvals` | Registrations awaiting approval: `{ items: [{ id, phone, name, address…, status, created_at }], total }` |
| `GET /api/v1/approvals/count` | `{ "count": <int> }` — the sidebar badge polls this every 30 seconds |
| `POST /api/v1/approvals/{registration_id}/approve` | Creates the Customer (or reactivates the existing one on that phone) and tells the customer on WhatsApp. Returns `{ message, customer_id }` |
| `POST /api/v1/approvals/{registration_id}/reject` | Body `{ reason? }`. Returns `{ message, registration_id }` |

404 if the registration doesn't exist. Approve and reject return **409** if the row is already terminal, so a double-tap can't create duplicates.

---

## Customer-facing endpoints (path-token auth)

These have no JWT. See [Token-based customer auth](ARCHITECTURE.md#token-based-customer-auth).

### Registration

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/register/{token}` | Look the token up. Returns `{ phone, already_registered }` so the form can pre-fill the phone and switch to an "already registered" view |
| `POST /api/v1/register/{token}` | Submit `{ name, address_line_1, address_line_2?, city, state, pincode }`. Creates a pending registration, consumes the token and notifies the owner. Returns `{ message, registration_id }` |

Errors: **404** no such token, **410** consumed or expired, **409** the phone is already a customer (the token is still consumed), **422** validation.

### Cart

Tokens of kind `new`, `reorder` and `edit` last 30 minutes.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/cart/{token}` | Load the cart: `{ token, kind, customer: { id, name }, items, total, menu }`. `menu` is today's available products, each with an `is_low_stock` flag |
| `POST /api/v1/cart/{token}` | Save the in-progress cart (`{ items: [{ product_id, quantity }] }`) to Redis. Does **not** create an order. Returns `{ ok, items, total }` |
| `POST /api/v1/cart/{token}/place` | Same body. Drops unavailable products, rejects an empty cart (422), creates the real order, consumes the token, clears the cart and sends the WhatsApp confirmation (best-effort). Returns `{ ok, order_id, total, items }` |

A bad, expired or consumed token returns **404**.

### Invoice

`GET /api/v1/invoice/{token}` — the **latest** invoice for the customer who holds an `invoice` token (24-hour life). Returns the invoice shape below. Every failure returns **404**, so the status never reveals whether a token ever existed: a bad, expired or wrong-kind token gets "This invoice link has expired or is no longer valid. Message BakeriQ on WhatsApp for a fresh one."; a valid token whose customer has no orders yet gets "No invoice found — you haven't placed any orders yet." (so that one case is distinguishable by its message, but only to someone holding a valid token).

---

## Inventory

All JWT-authed. See [Inventory and the prep list](ARCHITECTURE.md#inventory-and-the-prep-list).

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/inventory/stock` | Tracked (stockable) products: `{ items: [{ id, name, unit_label, stock_quantity, low_stock_threshold, is_low_stock }], total, low_stock_count }`. Query: `low_only` (bool) |
| `GET /api/v1/inventory/prep` | The day's prep list for made-to-order items: `{ items: [{ product_id, product_name, unit_label, quantity, order_count }], total, is_visible }`. `is_visible` is true between 05:00 and 21:00 |
| `PATCH /api/v1/inventory/stock/{product_id}` | Set the count to an absolute figure (what you get after counting a shelf): `{ "quantity": <int> }`. Returns the stock item. 404 if the product doesn't exist; 422 if the product isn't tracked (made to order) or the quantity is negative. Orders can still drive the count negative — only a manual set is refused |
| `PATCH /api/v1/inventory/settings/{product_id}` | `{ is_stockable?, low_stock_threshold? }` — start or stop tracking a product, or set its low-stock threshold |

---

## Billing

All JWT-authed. Dates are `YYYY-MM-DD`. `start` and `end` are optional and default to the first of the current month through today; 422 if `start` is after `end`.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/billing/summary` | `{ start_date, end_date, revenue, order_count, customer_count, cancelled_count }` |
| `GET /api/v1/billing/customers` | Customers with billable orders in the range: `{ items: [{ customer_id, customer_name, primary_phone, order_count, invoice_count, total, first_order_date, last_order_date }], total }` |
| `GET /api/v1/billing/customers/{customer_id}/dates` | One customer's invoice dates in the range: `{ customer, items: [{ order_date, order_count, total, invoice_number }], total }`. 404 if the customer doesn't exist |
| `GET /api/v1/billing/customers/{customer_id}/invoice/{invoice_date}` | The invoice for that customer on that date |

Billing excludes drafts and cancelled orders from totals; cancelled orders still appear on an invoice, greyed out.

### Invoice shape

Returned by both the owner endpoint above and `GET /api/v1/invoice/{token}`:

An illustrative example (values are made up):

```json
{
  "invoice_number": "INV-20260722-8294dceb",
  "invoice_date": "2026-07-22",
  "business": { "name": "…", "address_line_1": "…", "city": "…", "phone": "…", "email": "…" },
  "customer": { "id": "…", "name": "…", "primary_phone": "…", "city": "…" },
  "orders": [
    {
      "id": "…", "short_id": "…", "status": "delivering", "is_cancelled": false,
      "notes": null, "total_amount": 72.0,
      "items": [{ "product_name": "Veg Puff", "unit_price": 18.0, "unit_label": "piece", "quantity": 4, "subtotal": 72.0 }]
    }
  ],
  "order_count": 1,
  "cancelled_count": 0,
  "total": 72.0
}
```

The `business` block is read from the `BUSINESS_*` environment variables, not from the database.

---

## WhatsApp webhook

### `POST /api/v1/webhooks/twilio`

Twilio's inbound-message webhook. Not for human callers: the request must carry a valid `X-Twilio-Signature` (verified with the account auth token). It runs the fast-path dispatcher, enqueues the LLM task when nothing matches, and answers with empty TwiML. See [The WhatsApp channel](ARCHITECTURE.md#the-whatsapp-channel).

---

## Authentication header on every dashboard call

All JWT endpoints require:

```
Authorization: Bearer <jwt-from-login>
```

A missing token returns `401` with `{ "detail": "Not authenticated" }`; an invalid or expired one returns `401` with `{ "detail": "Could not validate credentials" }`. The dashboard's axios interceptor catches 401s and redirects to login.

## Not built

There is no WebSocket endpoint, no notifications endpoint, no conversation-transcript endpoint, and no export (PDF/CSV) endpoint. See [`ROADMAP.md`](ROADMAP.md) for what was and wasn't built.
