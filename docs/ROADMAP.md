# Roadmap

What shipped, what was built differently than planned, and what was left unbuilt. Last updated 23 November 2026. The code described here is `main` as the internship work left it (last commit 23 July 2026), plus the follow-up fixes of 23 November 2026 listed under [Known issues](#known-issues).

## Completion summary

BakeriQ was built during a full-stack internship (16 May – 27 July 2026, per the internship certificate) and is **complete as a working system**: a customer can message the bakery on WhatsApp, get a pre-filled cart link, place the order, and the owner can approve customers, manage orders, watch stock, read the prep list and see billing from the dashboard.

Not everything on the original plan was built, and two phases were built differently than planned. This document records each outcome as the code shows it — it does not claim anything that isn't there. Where a section says "not built", the code has no trace of it.

## At a glance

| Phase | Status | What's in it |
|---|---|---|
| 1 — Foundation | ✓ Complete | Project scaffold, Docker, auth, login, basic dashboard |
| 2 — Manual operations | ✓ Complete | Customers, products, orders, defaults — full CRUD |
| UI overhaul | ✓ Complete | Sidebar redesign, responsive layout, mobile drawer |
| UI polish pass | ✓ Complete | Formatters, brand mark, status icons, contrast |
| 3 — WhatsApp + LLM parser | ✓ Complete | The conversational ordering channel |
| 3.5 — Mobile owner approval | ✓ Complete | Owner approves new customer registrations from their phone |
| 4 — Notifications | Partly built | Registration and approval notifications only |
| 5 — Inventory | Built, simplified | Stock counts on products, stock deduction, prep list — not the raw-materials design |
| 6 — Billing | Built, simplified | Owner billing views and invoices, customer invoice link on WhatsApp — no PDF or CSV |
| Testing & deployment | Not built | No CI, end-to-end tests or deployment configuration |

## Phase 1 — Foundation ✓

**Goal:** A skeleton you can log into.

Built and shipped:

- Project scaffold (FastAPI app structure, React app via Vite, Docker Compose for the full stack)
- Docker images for backend and frontend with non-root users and bind-mounted code for hot reload
- User model + JWT-based authentication (bcrypt password hashing; python-jose for JWT at the time, replaced by PyJWT in November 2026, see ADR-29)
- Login page and protected route wrapper on the frontend
- Basic dashboard placeholder

## Phase 2 — Manual operations ✓

**Goal:** Everything the owner needs to manage by hand before any automation. The bot in Phase 3 sits on top of these; if the manual layer breaks, the whole thing breaks.

Built and shipped (9 tasks; 96 backend tests passing at the Phase 2 close):

- **Customers** — full CRUD with channel filter (WhatsApp / Voice / Inactive), search by name or phone, primary + secondary phone support, notes field
- **Categories** (Settings → Categories) — full CRUD, ordering field, soft deactivation
- **Products** — full CRUD with category relationship, unit pricing (e.g. ₹84 / piece, ₹320 / half_kg), availability toggle, aliases (comma-separated), image placeholder for Phase 3
- **Default order templates** — per-customer named templates that pre-fill an order in one click ("Anita's Sunday order", etc.), full CRUD, live totals
- **Orders** — full lifecycle: create, edit, list, detail panel, status transitions (received → preparing → ready → delivering, with cancel from any state — there is no separate "delivered" status), notes
- **Order snapshots** — historic orders preserve product name, price, and unit at the time of creation; edits to products don't rewrite history
- **Dashboard** — today's overview: four stat cards (Pending, In progress, Revenue today, Cancelled today), recent orders list, upcoming orders queue

## UI overhaul ✓ *(bonus, not in original plan)*

**Goal:** Make the app look like something a team lead is comfortable showing.

- Responsive layout — sidebar collapses to a drawer below `lg` breakpoint, hamburger trigger in TopBar
- Sidebar redesign — grouped sections (Operations / Setup), lucide icons, refined active state, footer with logout
- Shared StatusBadge component used consistently across all status displays
- Row actions menu (⋯) using `position: fixed` to escape table overflow clipping
- Empty-state cards on Inventory and Billing pages signalling "Phase 5 / Phase 6 coming" *(both pages are now real — see Phases 5 and 6)*

## UI polish pass ✓

**Goal:** The 80/20 of "small things that make a UI feel finished."

- Format helpers (phone numbers `+91 99999 12345`, unit labels `Half Kg`, INR currency)
- Single BrandMark component unifying the logo across login and sidebar
- Status badges now communicate state via colour + icon + text (accessibility — never colour alone)
- Route-aware TopBar subtitle (each page has its own descriptive subtitle)
- Live clock updating every minute, aligned to minute boundaries
- Container width capped to 1400px via named Tailwind token
- Currency columns right-aligned for vertical decimal scanning
- Selective contrast bumps to improve readability without flattening visual hierarchy
- VS Code dev container config (`.devcontainer/devcontainer.json`)

## Phase 3 — WhatsApp + LLM parser ✓

**Goal:** Customers place orders by sending a WhatsApp message in their own words. The bot parses, offers a link to review, and the order lands in the same admin system used for manual entry.

Built and shipped:

- **Inbound webhook** — Twilio WhatsApp Sandbox → ngrok → FastAPI, with HMAC signature verification and idempotency keying on `MessageSid`
- **Fast-path dispatcher** — `customer_handler` matches keyword phrases (menu, order status, reorder last, new order) and button labels; returns a list of Reply objects the webhook layer sends via Twilio's REST API
- **LLM safety valve** — Celery task that runs when the dispatcher returns None. Calls Ollama (llama3.2:3b) for structured JSON extraction of items + quantities, then a deterministic matcher against the real Product table with exact-match and alias resolution. Off-menu items are preserved so the "nothing available today" branch is reachable
- **Web-app cart handoff** — matched orders create a pre-populated cart in Redis, issue a URL-safe token, and send a link that opens the customer-facing web app with the cart already filled in. Token expires in 30 minutes
- **Interactive buttons via Twilio Content Templates** — the customer sees tappable buttons everywhere the bot offers next actions, instead of "Reply *menu* to see today's items" text prompts. Five templates came with Phase 3 (four more were added later — the registration link and owner notification with Phase 3.5, the invoice link with Phase 6, and the customer approval message as the one Phase 4 notification that was built — nine in total):
  - `bakeriq_greeting` — Hi {name}! + Reorder last / New order / Order status
  - `bakeriq_nav` — mid-conversation prompt, same three buttons
  - `bakeriq_cart_link` — CTA card with an Open cart URL button
  - `bakeriq_fallback` — LLM couldn't match items; Menu / New order / Order status
  - `bakeriq_order_confirmation` — post-order success card with itemized total + Order status / Invoice / New order buttons
- **Retry hardening on the LLM task** — autoretry covers both Ollama SDK exceptions and `httpx` connection errors with exponential backoff; a MaxRetriesExceededError branch sends a "we're having trouble processing your message, please try again in a moment" fallback so customers are never left in silence
- **Honest send-status reporting** — `parse_and_send` checks the `send_replies` return list and reports `sent` / `partial_send_failure` / `all_sends_failed` so monitoring reflects what actually reached the customer, not just whether the pipeline ran

Everything runs end-to-end against the real Twilio Sandbox: send any of `hi` / `menu` / `order status` / `reorder last` / `new order` / free text like `i want 2 veg puff` from a joined phone, and the appropriate flow completes with the customer receiving a tappable-buttons UX. See [`SETUP.md`](SETUP.md) for how to reproduce this on a fresh machine.

Test coverage at the Phase 3 close: 233 backend tests passing. The Celery worker uses `SessionLocal` for its own DB session; test fixtures monkeypatch this so worker code paths exercise the test DB.

## Phase 3.5 — Mobile owner approval ✓

**Goal:** A customer registers themselves; the owner approves from their phone without opening a laptop.

The old flow asked for name and area over two WhatsApp turns, then left the request sitting until the owner happened to check the dashboard. In practice approvals stalled and customers couldn't order.

Built and shipped:

- **Registration by webform.** An unrecognised number gets a `bakeriq_registration_link` Content Template with a "Register now" button. It opens `/web/register/{token}` — a form collecting name and a full delivery address, with the phone pre-filled and read-only. The old bot state machine is gone.
- **One-shot registration tokens.** New `RegistrationToken` model: bound to the phone that messaged the bot, valid 12 hours, consumed on submission. Kept separate from the cart-link `WebLink` table because registration happens before a Customer exists. Consumed on already-registered conflicts too, so a leaked token can't be replayed.
- **Owner notification.** Submitting the form sends the owner a `bakeriq_owner_notification` card carrying the registrant's name and phone plus an "Open dashboard" button. Fires synchronously but never raises — a Twilio failure can't fail the customer's registration.
- **Approvals API.** `GET /approvals`, `GET /approvals/count`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/reject`, all JWT-authed. Approve field-copies the address straight into a new Customer; both actions 409 if the row is already terminal, so a double-tap on mobile can't create duplicates.
- **Approvals page.** Mobile-first cards rather than a table, since the owner arrives from a phone notification. Each card carries everything needed to decide — name, phone, address, how long they've waited. Reject prompts for an optional reason.
- **Sidebar badge.** Pending count next to the Approvals nav item, polling every 30s, hidden at zero.
- **`/app` proxy.** The dashboard now serves under `/app` so the notification's CTA resolves through the single ngrok tunnel. Mirrors the existing `/web` proxy; the API now serves three prefixes — `/api`, `/web`, `/app`.

Verified end to end from a real phone: registration form → owner card → tap through to the approvals page → approve → Customer created. 274 backend tests passing at the Phase 3.5 close.

**Known gap — resolved.** `find_customer_by_phone` filtered on `is_active` but the registration endpoint's already-registered check did not, so a deactivated customer would have been routed to registration and then blocked at the form. Fixed afterwards: a deactivated customer can now re-register, and approving the registration reactivates the existing Customer rather than creating a new one.

## Phase 4 — Notifications *(partly built)*

**Goal as planned:** Real-time alerts to the owner when things happen, and status updates to customers as their orders progress, all on the Content Template infrastructure Phase 3 built.

**What shipped:**

- **Owner notification of new registrations** — the Phase 3.5 `bakeriq_owner_notification` card.
- **Customer notification on approval** — when the owner approves a registration, the customer receives a `bakeriq_approved` Content Template ("you're approved") with New order and Menu buttons. Best-effort: a Twilio failure never blocks the approval.
- **Low-stock visibility** — shown to customers in the menu and to the owner on the Inventory page (see Phase 5). There is no WhatsApp alert to the owner.

**Not built** — the code has no trace of these:

- Owner alerts when an order is placed, cancelled or edited
- Status updates to customers as an order moves preparing → ready → delivering
- A notification-preferences screen
- A background scheduler (nothing runs on a schedule)

## Phase 5 — Inventory ✓ *(built, simplified)*

**Goal as planned:** raw materials, recipes, stock movements and low-stock alerts.

**What was built instead.** Per the author, the raw-materials design wasn't finished before the internship ended, so a simpler design shipped. Only sealed, packaged goods (ladoo packets, bread, biscuits, some cakes) carry stock. Made-to-order items are baked and sold the same day, so their "inventory" is the chef's prep list, derived from the day's orders at read time rather than stored. The design is recorded in [ADR-24](DECISIONS.md).

Built and shipped:

- **Stock on the product.** Three nullable columns on `products` — `is_stockable`, `stock_quantity`, `low_stock_threshold` — and no new tables. `NULL` means "not tracked", which is distinct from "tracked, and zero".
- **Stock deduction at placement.** Stock is reserved when an order is created, not at delivery, so two customers can't both be promised the last packet; cancelling or deleting an order restores it. See [ADR-25](DECISIONS.md).
- **Owner Inventory page.** A stock table with set-count and per-product threshold controls, a "track stock for a product" dialog (tracking is opt-in per product), a low-stock banner, and the prep list.
- **Prep list.** `GET /api/v1/inventory/prep` sums quantities by product across the day's placed, non-cancelled orders for made-to-order items. Shown between 05:00 and 21:00 (orders for a day close at 05:00).
- **Low-stock warning to customers.** The customer app flags low-stock items while a customer builds a cart. It warns; it never blocks the order — the owner decides.
- **API.** `GET /inventory/stock`, `GET /inventory/prep`, `PATCH /inventory/stock/{product_id}`, `PATCH /inventory/settings/{product_id}`.

**Not built:** `raw_materials`, `recipes` and `stock_movements` tables; a purchase/consumption audit trail; WhatsApp low-stock alerts to the owner.

## Phase 6 — Billing ✓ *(built, simplified)*

**Goal as planned:** receipts, monthly invoices for regular customers, and exports.

Built and shipped:

- **Owner billing views.** A billing summary for a date range (revenue, order count, customer count, cancelled count), a customer list, per-customer billing dates, and an invoice drill-down for a customer on a given date.
- **Customer invoice on WhatsApp.** The order-confirmation card carries an Invoice button. Tapping it sends a `bakeriq_invoice_link` card that opens `/web/invoice/{token}` in the customer app. Invoice tokens last 24 hours.
- **Invoice header from `.env`.** The business name, address, phone and email on an invoice come from the `BUSINESS_*` environment variables.
- **API.** `GET /billing/summary`, `GET /billing/customers`, `GET /billing/customers/{id}/dates`, `GET /billing/customers/{id}/invoice/{date}`, and the token-authenticated `GET /invoice/{token}`.

**Not built:** monthly invoices for regular customers (per the author, there wasn't time to finish them before the internship ended), receipts as downloadable PDFs, CSV exports, and tax-year summaries. Invoices are viewed on screen, per customer per day. Analytics was dropped from this phase earlier — see ADR-12.

## Testing & deployment ✗ *(not built)*

**Goal as planned:** make it deployable and durable enough to run in production for the bakery.

The repository has no `.github/` workflows, no Playwright (or other end-to-end) tests, no hosting configuration, and no monitoring or backup setup; the `nginx/` folder is an empty placeholder. Verification during development was the backend pytest suite plus manual runs against the Twilio sandbox (`make whatsapp-smoke`).

---

## Known issues

Found while verifying this documentation against the code on 23 November 2026. Most were fixed the same day, in separate commits; the rest are listed under [Still open](#still-open).

### Fixed on 23 November 2026

- **`POST /api/v1/auth/register` was unauthenticated.** Anyone who could reach the API could create a dashboard account, log in with it, and read customer data (verified against a running stack). It now needs a superuser: 401 without a token, 403 for a normal user. Closing it left no way to make a first account on an unseeded database, so `python -m scripts.create_owner` was added, and the seed script now refuses to run outside a development `ENVIRONMENT`. See [ADR-28](DECISIONS.md#adr-28--account-creation-is-superuser-only-and-the-first-owner-comes-from-a-script).
- **`make whatsapp-smoke` defaulted to the original maintainer's own phone number.** `SMOKE_TEST_PHONE` is now required and the script exits before sending if it is unset. The number is still in the git history; only a history rewrite would remove it, and none was done.
- **Deleting an order did not restore its stock.** `DELETE /orders/{id}` now restores it like a cancel does (and skips an already-cancelled order so nothing is restored twice). See [ADR-25](DECISIONS.md#adr-25--reserve-stock-at-order-placement-allow-negative-warn-dont-block).
- **`CUSTOMER_WEB_BASE_URL` defaulted to a value that produced broken links.** The customer app is served under `/web/`, so the old default yielded a 404. The default now ends in `/web`. A deployment that sets the variable itself is unaffected.
- **`.env.example` was missing `OWNER_WHATSAPP_PHONE` and `CUSTOMER_WEB_BASE_URL`** and didn't explain that `CONTENT_SID_*` is written to `backend/.env`. It now covers all three, and gives the Ollama address per platform.
- **Comments and messages that overstated what `make dev-up` does.** They said it auto-recovers from a rotated ngrok hostname and recreates the cart-link template; it can't (see below). The scripts' comments and output now say what they actually do. Behaviour is unchanged.
- **Stale comments.** `register.py` described the owner notification as a TODO although it is implemented, and the template bootstrap's docstring listed five `CONTENT_SID_*` values and the root `.env` where it writes nine to `backend/.env`.

### Still open

- **`make dev-up` still can't repair a stale template URL.** `ngrok-check` compares the live tunnel with `PUBLIC_BASE_URL` in `.env` (never with Twilio), and `templates-refresh` runs the bootstrap, which skips templates that already exist. A real fix would have to read each template's URL from Twilio and then delete and recreate templates on the live account, which wasn't attempted. A static ngrok domain avoids the problem; otherwise follow [The ngrok hostname problem](DEVELOPMENT.md#the-ngrok-hostname-problem). Read from the scripts, not exercised against a live Twilio account.
- **The seeded owner login** (`owner@bakeriq.com`) is a development fixture with a published password. The seed script now only runs in a development `ENVIRONMENT`, but anyone who runs it there gets that password.
- **Superuser gates only account creation.** Every active account can use every dashboard endpoint, so any account is effectively staff-level. There is no role model beyond that.
- **Lint and format tooling isn't enforced.** The tools are installed and configured in the devcontainer, but there is no CI, pre-commit hook or `lint` script, and the existing code doesn't pass them (262 ruff findings, 10 files black would reformat, isort flags more than half). Enforcing them means a one-off formatting pass first; see [DEVELOPMENT.md](DEVELOPMENT.md#code-style).
- **No owner low-stock alert exists.** Low stock is shown on the dashboard and to the customer while ordering, but nothing messages the owner.

---

## If work continues

Nothing below is promised; this is the backlog the code points to, in roughly the order it would make sense:

1. **Order notifications** — owner alerts and customer status updates. The Content Template pattern and the "never fail the request on a Twilio error" rule from Phases 3.5 and 4 already cover how.
2. **Deployment and CI** — a hosted target, a CI workflow for the pytest suite, and the routing (`/api`, `/web`, `/app`) that the development proxy currently provides.
3. **Editable bakery details** — the `BusinessDetails` schema is already isolated so its source can move from `.env` to a table without changing the invoice shape.
4. **PDF receipts and CSV exports.**
5. **Raw-materials inventory** — only if recipe-level planning or costing is wanted. What shipped covers sealed goods through product-level stock and made-to-order items through the derived prep list (see ADR-24).
6. **Close what is [still open](#still-open)**, starting with a way to repair stale Content Template URLs.

Voice ordering was dropped from scope and is not on this list.
