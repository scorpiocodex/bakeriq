# Roadmap

What's done, what's next, and the reasoning behind the order. Last updated 13 July 2026.

## At a glance

| Phase | Status | What's in it |
|---|---|---|
| 1 — Foundation | ✓ Complete | Project scaffold, Docker, auth, login, basic dashboard |
| 2 — Manual operations | ✓ Complete | Customers, products, orders, defaults — full CRUD |
| UI overhaul | ✓ Complete | Sidebar redesign, responsive layout, mobile drawer |
| UI polish pass | ✓ Complete | Formatters, brand mark, status icons, contrast |
| 3 — WhatsApp + LLM parser | ✓ Complete | The conversational ordering channel |
| **3.5 — Mobile owner approval** | **Next** | Owner approves new customer registrations from their phone |
| 4 — Notifications | Planned | Owner alerts + customer status updates, all via WhatsApp |
| 5 — Inventory | Planned | Raw materials, recipes, stock movements, low-stock alerts |
| 6 — Billing | Planned | Receipts, invoices, exports |
| Testing & deployment | Planned | E2E tests, Railway deploy, CI, monitoring, onboarding docs |

## Phase 1 — Foundation ✓

**Goal:** A skeleton you can log into.

Built and shipped:

- Project scaffold (FastAPI app structure, React app via Vite, Docker Compose for the full stack)
- Docker images for backend and frontend with non-root users and bind-mounted code for hot reload
- User model + JWT-based authentication (bcrypt password hashing, python-jose for JWT)
- Login page and protected route wrapper on the frontend
- Basic dashboard placeholder

## Phase 2 — Manual operations ✓

**Goal:** Everything the owner needs to manage by hand before any automation. The bot in Phase 3 sits on top of these; if the manual layer breaks, the whole thing breaks.

Built and shipped (9 tasks, 96 backend tests passing):

- **Customers** — full CRUD with channel filter (WhatsApp / Voice / Inactive), search by name or phone, primary + secondary phone support, notes field
- **Categories** (Settings → Categories) — full CRUD, ordering field, soft deactivation
- **Products** — full CRUD with category relationship, unit pricing (e.g. ₹84 / piece, ₹320 / half_kg), availability toggle, aliases (comma-separated), image placeholder for Phase 3
- **Default order templates** — per-customer named templates that pre-fill an order in one click ("Anita's Sunday order", etc.), full CRUD, live totals
- **Orders** — full lifecycle: create, edit, list, detail panel, status transitions (received → preparing → ready → delivering → delivered), cancel with reason, notes
- **Order snapshots** — historic orders preserve product name, price, and unit at the time of creation; edits to products don't rewrite history
- **Dashboard** — today's overview: four stat cards (Pending, In progress, Revenue today, Cancelled today), recent orders list, upcoming orders queue

## UI overhaul ✓ *(bonus, not in original plan)*

**Goal:** Make the app look like something a team lead is comfortable showing.

- Responsive layout — sidebar collapses to a drawer below `lg` breakpoint, hamburger trigger in TopBar
- Sidebar redesign — grouped sections (Operations / Setup), lucide icons, refined active state, footer with logout
- Shared StatusBadge component used consistently across all status displays
- Row actions menu (⋯) using `position: fixed` to escape table overflow clipping
- Empty-state cards on Inventory and Billing pages signalling "Phase 5 / Phase 6 coming"

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
- **Interactive buttons via Twilio Content Templates** — the customer sees tappable buttons everywhere the bot offers next actions, instead of "Reply *menu* to see today's items" text prompts. Five templates live on Twilio:
  - `bakeriq_greeting` — Hi {name}! + Reorder last / New order / Order status
  - `bakeriq_nav` — mid-conversation prompt, same three buttons
  - `bakeriq_cart_link` — CTA card with an Open cart URL button
  - `bakeriq_fallback` — LLM couldn't match items; Menu / New order / Order status
  - `bakeriq_order_confirmation` — post-order success card with itemized total + Order status / Menu / New order buttons
- **Retry hardening on the LLM task** — autoretry covers both Ollama SDK exceptions and `httpx` connection errors with exponential backoff; a MaxRetriesExceededError branch sends a "we're having trouble processing your message, please try again in a moment" fallback so customers are never left in silence
- **Honest send-status reporting** — `parse_and_send` checks the `send_replies` return list and reports `sent` / `partial_send_failure` / `all_sends_failed` so monitoring reflects what actually reached the customer, not just whether the pipeline ran

Everything runs end-to-end against real Twilio Sandbox: send any of `hi` / `menu` / `order status` / `reorder last` / `new order` / free text like `i want 2 veg puff` from a joined phone, and the appropriate flow completes with the customer receiving a tappable-buttons UX. See [`SETUP.md`](SETUP.md) for how to reproduce this on a fresh machine.

Test coverage: 233 backend tests passing. The Celery worker uses `SessionLocal` for its own DB session; test fixtures monkeypatch this so worker code paths exercise the test DB.

## Phase 3.5 — Mobile owner approval (next)

**Goal:** The owner approves new customer registrations from their phone, without needing to switch to a laptop.

Context: currently when a new customer sends `join <sandbox-code>` and messages the bot, they're marked "pending owner approval." The owner sees a notification, then has to open the dashboard on a laptop to approve. In practice the owner is often on the go — approvals stall, customers can't order.

Planned:

- **Notification card via WhatsApp** — new registrations trigger a Content Template message to the owner's phone with an "Open dashboard" button, deep-linking to the pending-approvals page
- **Persistent login on mobile** — the dashboard's JWT handling keeps the owner logged in across sessions so tapping the notification button doesn't require re-authenticating every time
- **Pending-approvals page** — dedicated view listing all customers awaiting approval, with per-row Approve / Reject actions. Shows the customer's name, phone, and any notes they included in their first message
- **Notification badge** — count of pending approvals visible in the dashboard sidebar and TopBar, always. Tapping navigates to the approvals page

Design notes: the "in-app browser" question (webview vs PWA vs deep link into a native install) needs a decision before implementation. Free-tier webviews on Android and iOS both have some cookie-isolation caveats worth prototyping. Notification-badge count updates should use the existing TanStack Query patterns (`refetchInterval` on the dashboard, invalidation on approval action).

## Phase 4 — Notifications (later)

**Goal:** Real-time alerts to the owner when things happen, and status updates to customers as their orders progress. Everything rides on the Content Template infrastructure Phase 3 built.

Big rocks:

- **Owner order alerts** — real-time WhatsApp Content Template to the owner's phone when a new order lands, when an order is cancelled, and when an order is edited by a customer. Complements the mobile-approval flow from Phase 3.5 rather than replacing it (registration approval stays there because it's coupled to the approvals UI).
- **Customer status updates** — outbound WhatsApp when order status transitions: preparing → ready → delivered. Uses the same Content Template pattern as the confirmation card, so customers get consistent tappable-buttons UX for status-check follow-ups.
- **Low-stock alerts (deferred until Phase 5)** — technically fits here, but there's nothing to alert on until inventory tracking exists. Called out for planning; actual work happens after Phase 5.
- **Notification preferences** — a small settings surface where the owner can opt into/out of specific alert types. Prevents notification fatigue when order volume grows.

## Phase 5 — Inventory (later)

**Goal:** Track raw materials, recipes, and stock movements so the owner knows what to buy and can be alerted before running out.

Big rocks:

- **Raw materials** — ingredients as first-class entities with units, unit prices, and current stock levels
- **Recipes** — many-to-many between products and raw materials, with per-unit quantities. `1 Veg Puff = 30g maida + 20g potato + …`
- **Stock movements** — record of every purchase (increase) and consumption (decrease from order fulfillment). Historical audit trail
- **Low-stock alerts** — configurable threshold per raw material; alerts land in the owner's notification channel

## Phase 6 — Billing (later)

**Goal:** Generate receipts, invoices, and export historical data.

Big rocks:

- **Receipts** — auto-generated per order, downloadable PDF, matches the frontend snapshot
- **Invoices** — monthly summary invoices for regular customers (e.g. hotels, offices that order daily)
- **Exports** — CSV export of orders, revenue reports by date range, tax-year summary

## Testing & deployment (final polish before shipping)

**Goal:** Make it deployable and durable enough to run in production for the bakery.

Big rocks:

- **End-to-end tests** — Playwright scenarios covering the full customer journey (WhatsApp message → cart link → order → status updates)
- **Deployment target** — Railway (or Fly.io), with Postgres + Redis managed services, GitHub Actions CI/CD
- **Monitoring** — structured logging aggregated to a hosted service (Better Stack / Papertrail), uptime pings, error tracking (Sentry free tier)
- **Backup + restore** — nightly Postgres dumps, verified restore drill
- **Onboarding docs** — beyond `SETUP.md`, a runbook for common operator tasks (new user provisioning, updating menu, seasonal product management)

---

## What could still change the order

**If notifications become urgent:** Phase 4 could interleave with 3.5 if the mobile-approval flow blocks. Real-time customer status updates ("your order is ready") have direct business value even without the approval UI landing first.

**If inventory becomes critical:** the owner has raised this a few times. Phase 5 could jump ahead of 4 if we hit a "we ran out during a rush" story that forces the conversation.

**If a specific integration is asked for:** e.g. WhatsApp Business API graduation, custom Zomato/Swiggy connectors. These would slot in after the current phase completes rather than blocking mid-phase.

The order above reflects the *default* prioritisation: customer-visible impact first (Phase 3 → 4), operational leverage next (5, 6), infrastructure last (deployment). This isn't sacred — it's what makes sense given no external forcing function today. As soon as a real forcing function shows up (e.g. team lead needs the voice bot for a demo, or the bakery hits an inventory blow-up), we re-plan.
