# Roadmap

What's done, what's next, and the reasoning behind the order. Last updated 3 June 2026.

## At a glance

| Phase | Status | What's in it |
|---|---|---|
| 1 — Foundation | ✓ Complete | Project scaffold, Docker, auth, login, basic dashboard |
| 2 — Manual operations | ✓ Complete | Customers, products, orders, defaults — full CRUD |
| UI overhaul | ✓ Complete | Sidebar redesign, responsive layout, mobile drawer |
| UI polish pass | ✓ Complete | Formatters, brand mark, status icons, contrast |
| **3 — WhatsApp + LLM parser** | **In progress** | The conversational ordering channel |
| 4 — Voice + notifications | Planned | Voice bot for non-WhatsApp customers, owner notifications |
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

**Goal:** Everything the owner needs to manage by hand before any automation. The bot in Phase 3 sits on top of this foundation.

Built and shipped (9 tasks, 96 backend tests passing):

- **Customers** — full CRUD with channel filter (WhatsApp / Voice / Inactive), search by name or phone, secondary phone support
- **Categories** (Settings → Categories) — full CRUD, ordering field, soft deactivation
- **Products** — full CRUD with category relationship, unit pricing (e.g. ₹84 / piece, ₹320 / half_kg), "available today" toggle for daily menu management
- **Default order templates** — per-customer named templates that pre-fill an order in one click (Anita Menon: "3 Veg Puffs + 2 Ladoos" etc.)
- **Orders** — full lifecycle: create, edit, list, detail panel, status transitions (received → preparing → ready → delivering, with cancellation from any state)
- **Order snapshots** — historic orders preserve product name, price, and unit at the time of creation, so later product edits don't rewrite past orders
- **Dashboard** — today's overview: four stat cards (Pending, In progress, Revenue today, Cancelled), four-column status board, reference row for active customer / product counts

## UI overhaul ✓ (bonus, not in original plan)

**Goal:** Make the app look like something a team lead is comfortable showing.

- Responsive layout — sidebar collapses to a drawer below `lg` breakpoint, hamburger trigger in TopBar
- Sidebar redesign — grouped sections (Operations / Setup), lucide icons, refined active state, footer with owner identity + logout
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

## Phase 3 — WhatsApp + LLM parser (next)

**Goal:** Customers can place orders by sending a WhatsApp message in their own words. The bot parses it, confirms, and creates the order.

Planned tasks (estimates in hours; see [`DECISIONS.md`](DECISIONS.md) for why Twilio first):

1. **Twilio Sandbox + ngrok + webhook signature verification** (~32 hr)
   - Set up Twilio Sandbox for WhatsApp
   - Expose the dev API via ngrok for webhook delivery
   - Implement signature verification per Twilio's HMAC scheme
   - First echo-bot smoke test: inbound message → echoed reply

2. **Conversation state machine + Redis storage** (~36 hr)
   - Define states (idle / greeting sent / awaiting confirmation / etc.)
   - Store per-customer-phone state in Redis with TTLs
   - State transitions driven by incoming message events

3. **Today's menu + bot reply sending + greeting flow** (~36 hr)
   - "What's available today" reply for new conversations
   - Time-of-day-appropriate greeting
   - Outbound message helpers wrapping Twilio's API

4. **Claude API client + LLM order parser via Celery** (~60 hr)
   - Celery worker for async parsing (LLM calls are slow)
   - Prompt engineering for natural-language → structured order
   - Confidence handling — when does the bot ask for confirmation vs proceed?
   - Cross-reference product catalog so the bot only confirms real items

5. **Confirmation flow — grace window + YES/NO/SKIP/Modify** (~60 hr)
   - 2-minute grace window after order creation for customer to amend
   - Standard confirmation phrases mapped to actions
   - Modification flow (add item, remove item, change quantity)

6. **Owner instant notification + WebSocket dashboard update** (~36 hr)
   - Real-time push to the dashboard when a new bot order arrives
   - WebSocket connection from the React app to a FastAPI WebSocket endpoint
   - Audible notification option

7. **Conversation history viewer + Phase 3 testing** (~8 hr)
   - Per-customer conversation transcript page
   - End-to-end manual tests with real WhatsApp messages

**Why Twilio first, Meta later:** see [`DECISIONS.md`](DECISIONS.md). Twilio Sandbox gets us a working bot in 15 minutes; Meta WhatsApp Business Platform requires business verification, a WABA, and a provisioned phone number — days of setup. We'll migrate to Meta when we go to real production.

## Phase 4 — Voice bot + notifications

**Goal:** Customers who aren't on WhatsApp (still common in Kerala — older generation) can place orders by voice. Owner gets push notifications.

Planned:

- Twilio Voice + outbound dialler + TwiML IVR
- Google Cloud STT (speech-to-text) + TTS (text-to-speech) + voice → LLM pipeline
- Missed-call retry logic + 6 AM scheduled voice dialler for default-order regulars
- Chef brief (4 AM scheduled prep list) + owner summary notifications
- Notifications history page + manual trigger UI

## Phase 5 — Inventory module

**Goal:** Know what raw materials we have, what we'll need for today's orders, and warn before running out.

Planned:

- `raw_materials`, `recipes`, `stock_movements` tables
- Stock-in (purchases) + production deduction (per order) + wastage tracking
- Inventory page UI with three tabs (Available / Pending / Stock movements)
- Low-stock checker + alerts + recipe-aware demand forecasting

The Phase 5 UI replaces the current Inventory empty-state placeholder.

## Phase 6 — Billing

**Goal:** Receipts, daily/monthly invoice rollups, exportable summaries.

Planned:

- Billing data flow (orders → line-item totals → invoices)
- Export adapters (CSV, Excel, PDF)
- Auto-export schedule for daily/monthly summaries
- Billing page UI with history table

(Analytics was originally scoped but was scrapped — see [`DECISIONS.md`](DECISIONS.md).)

The Phase 6 UI replaces the current Billing empty-state placeholder.

## Testing & deployment hardening

**Goal:** Ship to a real environment that won't break.

Planned:

- End-to-end test suite (manual order flow, WhatsApp bot from real phone, voice bot, scheduled jobs, inventory + low-stock, billing)
- Bug fixes from end-to-end testing findings
- Railway deployment with SSL, production config, secrets management
- CI/CD pipeline (GitHub Actions)
- Centralised logging, Sentry error tracking, scheduled backups
- Owner + chef onboarding docs and final regression test
- Buffer week for last-mile fixes

## Timeline context

Internship runs 16 April 2026 → 16 July 2026 (91 days). As of 3 June (today):

- 49 days elapsed (54%)
- 42 days remaining (46%)
- Phases 1, 2, UI overhaul, UI polish: **complete**
- 4 phases + testing/deployment **remaining**

Pace is on track. Phase 2 was the heaviest foundational lift; later phases compound on existing infrastructure (the same service layer the API uses will back the WhatsApp bot, the same UI patterns extend to inventory/billing). The main risk is Phase 3 — most new external integrations (Twilio, ngrok, Claude API, Celery) in a single phase, each with their own setup friction. Expect to spend extra buffer on the first Phase 3 task.

## What's *not* on the roadmap (by design)

- **Multi-tenant** — single bakery, no organisations
- **Customer-facing app** — customers use WhatsApp / phone, not the BakeriQ UI
- **Payment processing** — receipts only, payments collected outside the system
- **Analytics dashboards beyond the daily overview** — descoped from Phase 6
- **Mobile app** — the responsive web UI covers mobile use cases
- **Internationalisation** — single-language (English UI, English/Malayalam customer messages in Phase 3)
