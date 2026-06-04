# API Reference

Human-readable summary of the BakeriQ HTTP API. For the complete machine-readable schema (full request/response shapes, every validation rule), run the API and visit **http://localhost:8000/docs** (Swagger UI) or **http://localhost:8000/redoc** (ReDoc).

This document is the "what exists and roughly what it does" view. Use Swagger when you need exact field names and types.

## Conventions

- **Base URL** in dev: `http://localhost:8000`
- **All endpoints** are under the prefix `/api/v1`
- **Content type:** JSON in, JSON out
- **Auth:** JWT Bearer token in the `Authorization` header on every request except `POST /api/v1/auth/login`
- **Errors:** standard FastAPI shape — `{ "detail": "<message>" }` for explicit errors, structured array for Pydantic validation failures
- **List endpoints** return a wrapper: `{ "items": [...], "total": <int> }`
- **Soft deactivation:** customers, products, and categories use an `is_active` flag (not deletion). Filter via `?status=active|inactive|all` (default `active`).
- **Pagination:** list endpoints accept `?skip=<int>&limit=<int>` (defaults: skip=0, limit=50, max limit=100)

## Authentication

### `POST /api/v1/auth/login`

Exchange email + password for a JWT.

**Request:**

```json
{ "email": "owner@bakeriq.com", "password": "bakeriqowner" }
```

**Response 200:**

```json
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "email": "owner@bakeriq.com",
    "full_name": "Bakery Owner"
  }
}
```

**Response 401:** `{ "detail": "Invalid credentials" }`

### `GET /api/v1/auth/me`

Returns the currently authenticated user. Used by the frontend to confirm a token is still valid on app load.

**Response 200:** same `user` shape as above.

---

## Customers

### `GET /api/v1/customers`

List customers with optional filters.

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | `active` / `inactive` / `all` | `active` | Soft-deactivation filter |
| `whatsapp_only` | boolean | (none) | True → only WhatsApp customers, False → only voice-only |
| `search` | string | (none) | Substring match on name and primary phone |
| `skip`, `limit` | int | 0, 50 | Pagination |

**Response 200:** `{ "items": [Customer], "total": <int> }`

### `POST /api/v1/customers`

Create a new customer.

**Request:**

```json
{
  "name": "Anita Menon",
  "primary_phone": "+919999912345",
  "secondary_phone": "+919988800001",
  "whatsapp_enabled": true,
  "notes": "Daily order — usual time 9 AM"
}
```

**Response 201:** the created `Customer` record.

### `GET /api/v1/customers/{id}`

Get one customer by ID.

**Response 200:** `Customer`
**Response 404:** `{ "detail": "Customer not found" }`

### `PATCH /api/v1/customers/{id}`

Update any subset of fields. Used for both edits and reactivation (`{"is_active": true}`).

### `POST /api/v1/customers/{id}/deactivate`

Soft-deactivate. Equivalent to `PATCH /customers/{id}` with `{"is_active": false}`, but more explicit.

---

## Categories

Used to group products (savoury / sweet / cake / bread / other).

### `GET /api/v1/categories`

**Query parameters:** `status`, `skip`, `limit` (same conventions as customers).

### `POST /api/v1/categories`

```json
{ "name": "sweet", "display_order": 20 }
```

### `GET /api/v1/categories/{id}` · `PATCH /api/v1/categories/{id}` · `POST /api/v1/categories/{id}/deactivate`

Standard CRUD pattern. See customers above.

---

## Products

### `GET /api/v1/products`

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | `active` / `inactive` / `all` | `active` | |
| `category_id` | int | (none) | Filter by category |
| `available_today_only` | boolean | (none) | True → only products marked available today |
| `search` | string | (none) | Substring match on name and description |
| `skip`, `limit` | int | 0, 50 | |

### `POST /api/v1/products`

```json
{
  "name": "Veg Puff",
  "description": "Crispy savoury pastry with vegetable filling",
  "category_id": 1,
  "unit_price": 18.0,
  "unit_label": "piece",
  "is_available_today": true
}
```

**Unit labels** are conventional strings (`piece`, `kg`, `half_kg`, `loaf`, etc.) — formatted for display in the frontend via `formatUnitLabel`. No DB-side enum because new units (e.g. `dozen`) shouldn't require a migration.

### `GET /api/v1/products/{id}` · `PATCH /api/v1/products/{id}` · `POST /api/v1/products/{id}/deactivate`

Standard CRUD pattern.

---

## Default order templates

Per-customer named templates that pre-fill an order in one click.

### `GET /api/v1/customers/{customer_id}/default-orders`

List a customer's templates.

### `POST /api/v1/customers/{customer_id}/default-orders`

```json
{
  "name": "Usual morning order",
  "notes": "Calls between 8-9 AM",
  "items": [
    { "product_id": 1, "quantity": 3 },
    { "product_id": 4, "quantity": 2 }
  ]
}
```

### `PATCH /api/v1/default-orders/{id}` · `DELETE /api/v1/default-orders/{id}`

Update or delete a template. Updates replace items wholesale — pass the full `items` array.

---

## Orders

The heart of the system. Read [`ARCHITECTURE.md`](ARCHITECTURE.md) for the snapshot pattern and status lifecycle before integrating against these endpoints.

### `GET /api/v1/orders`

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | `received` / `preparing` / `ready` / `delivering` / `cancelled` | (none) | Filter by current status |
| `customer_id` | int | (none) | Filter by customer |
| `date_from`, `date_to` | ISO date | (none) | Filter by order_date range |
| `skip`, `limit` | int | 0, 50 | |

**Response 200:**

```json
{
  "items": [
    {
      "id": 1,
      "customer": { "id": 1, "name": "Anita Menon", "primary_phone": "+919999912345" },
      "order_date": "2026-06-03",
      "status": "delivering",
      "total_amount": 84.00,
      "item_count": 2,
      "item_summary": "1 Egg Puff · 1 Veg Puff",
      "notes": "Office order",
      "created_at": "2026-06-03T08:15:32Z"
    }
  ],
  "total": 6
}
```

`item_summary` is a server-computed string for the list view; the full items array comes back on the detail endpoint.

### `POST /api/v1/orders`

```json
{
  "customer_id": 1,
  "order_date": "2026-06-03",
  "notes": "Office order",
  "items": [
    { "product_id": 1, "quantity": 3 },
    { "product_id": 4, "quantity": 2 }
  ]
}
```

At creation, each line item **snapshots** the product's name, unit price, and unit label. The `product_id` is preserved as a soft reference, but the displayed values come from the snapshot columns — see [`ARCHITECTURE.md`](ARCHITECTURE.md).

**Response 201:** the full order with items.

### `GET /api/v1/orders/{id}`

Full order detail including items array.

**Response shape:**

```json
{
  "id": 1,
  "customer": { ... },
  "order_date": "2026-06-03",
  "status": "delivering",
  "total_amount": 84.00,
  "notes": "Office order",
  "items": [
    {
      "id": 1,
      "product_id": 1,
      "product_name": "Veg Puff",
      "unit_price": 18.00,
      "unit_label": "piece",
      "quantity": 3,
      "subtotal": 54.00
    },
    ...
  ],
  "created_at": "2026-06-03T08:15:32Z",
  "updated_at": "2026-06-03T10:42:11Z"
}
```

### `PATCH /api/v1/orders/{id}`

Update an order. Items array is replace-wholesale — pass all items.

**Note on snapshots:** when you update items, the *new* items get fresh snapshots from the current product prices. Existing items retain their original snapshots if their `id` is preserved in the request, but if you just send a new items array, they're treated as new and re-snapshotted. The frontend's edit-order modal preserves IDs for unchanged rows.

### `POST /api/v1/orders/{id}/transition`

Move an order through its status lifecycle.

**Request:**

```json
{ "to_status": "preparing" }
```

**Allowed transitions:**

- Forward chain: `received` → `preparing` → `ready` → `delivering`
- Backward within chain: any reverse direction (for correcting mistakes)
- To `cancelled`: from any non-terminal state
- From `cancelled`: not allowed — cancelled orders are terminal

**Response 200:** the updated order.
**Response 400:** `{ "detail": "Invalid transition from cancelled to preparing" }`

### `DELETE /api/v1/orders/{id}`

Hard-delete an order (no soft deactivation here — cancelled is the soft state). Used mainly for cleaning up test data.

---

## Dashboard

### `GET /api/v1/dashboard/summary`

Aggregated today's-overview metrics.

**Response 200:**

```json
{
  "today_orders": 4,
  "orders_by_status": {
    "received": 1,
    "preparing": 1,
    "ready": 1,
    "delivering": 1,
    "cancelled": 0
  },
  "revenue_today": 1447.00,
  "active_customers_count": 8,
  "active_products_count": 8,
  "unavailable_products_count": 1,
  "today_board": [
    {
      "status": "received",
      "orders": [
        { "id": 5, "customer_name": "Anita Menon", "item_summary": "2 Bread", "total_amount": 96.00 }
      ]
    },
    ...
  ]
}
```

`revenue_today` excludes cancelled orders. `today_board` returns up to 5 orders per status column for the dashboard's visual board.

---

## Authentication header on every authenticated call

All endpoints except `POST /auth/login` require:

```
Authorization: Bearer <jwt-from-login>
```

A missing or invalid token returns:

```
401 Unauthorized
{ "detail": "Not authenticated" }
```

An expired token returns the same. The frontend's axios interceptor catches 401s and redirects to login.

## Future endpoints (Phase 3+)

These don't exist yet but are scoped for upcoming phases — flagged here so you know they're coming:

| Endpoint | Phase | Purpose |
|---|---|---|
| `POST /api/v1/webhooks/twilio` | 3 | Twilio inbound message webhook |
| `GET /api/v1/conversations/{customer_id}` | 3 | Conversation transcript |
| `WS /api/v1/ws/dashboard` | 4 | WebSocket for live dashboard updates |
| `POST /api/v1/notifications/send` | 4 | Manual notification trigger |
| `GET /api/v1/inventory/...` | 5 | Inventory endpoints |
| `GET /api/v1/billing/...` | 6 | Billing endpoints |

See [`ROADMAP.md`](ROADMAP.md) for the full plan.
