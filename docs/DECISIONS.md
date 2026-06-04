# Design Decisions

A log of the non-obvious choices made during the project, and the reasoning behind them. This is the "why" companion to [`ARCHITECTURE.md`](ARCHITECTURE.md)'s "what."

Each entry follows the format: *what was decided, what the alternatives were, why this choice won, what could change the answer later*.

## ADR-1 — Snapshot pattern on order items

**Decision:** `order_items` copy product name, unit price, and unit label at creation time. The `product_id` is preserved as a soft reference, but the displayed values are always read from the snapshot columns.

**Alternatives considered:**

- **Always join to the live product row** — simpler schema, no snapshot columns. But: editing a product's price retroactively rewrites every historic order, which is wrong both legally (receipts must match what was charged) and operationally (the chef would see different numbers from what the customer was quoted).
- **Versioned products table** — keep a history of product versions, reference them by `(product_id, version_id)` on the order. Cleaner conceptually but adds a whole subsystem. Overkill for a single-bakery internal tool.

**Why snapshots won:** Minimal schema cost (three extra columns), bulletproof correctness, and the order is the unit that matters operationally — losing the link back to the live product for old orders is acceptable, because old orders aren't going to be re-fulfilled.

**Test guardrail:** `test_snapshot_survives_price_change` is the load-bearing test. Don't remove it.

**What could change the answer:** If we ever needed to bulk-correct prices retroactively (e.g., a tax mistake), we'd need a migration path or a versioning system. Not currently in scope.

## ADR-2 — Status lifecycle is event-driven, not clock-driven

**Decision:** Orders move through statuses (`received → preparing → ready → delivering`, with `cancelled` from any state) only when something or someone explicitly transitions them. No automatic time-based advancement.

**Alternatives considered:**

- **Auto-advance based on elapsed time** (e.g., "after 30 minutes in `preparing`, auto-move to `ready`"). Initially proposed during dashboard design.
- **Hybrid** — auto-advance for some statuses, manual for others.

**Why event-driven won:** A clock has no idea whether the bread is actually ready. Auto-advance lies when reality drifts — a power cut, a chef calling in sick, an oven malfunction — and the dashboard would show "Ready" while there's nothing on the rack. Event-driven means the status reflects what someone actually confirmed.

**What could change the answer:** In Phase 4, the voice/SMS bot could auto-advance status when it gets a delivery confirmation from the customer ("yes, received") — that's still event-driven, just the event is "customer confirmed delivery" rather than "owner clicked the button." Adding genuine event sources is fine. Adding clocks isn't.

## ADR-3 — `is_active` boolean with `active|inactive|all` filter

**Decision:** Customers, products, and categories all use an `is_active` boolean. List endpoints take a `status` query param with values `'active'`, `'inactive'`, or `'all'`, defaulting to `'active'`. Regex-validated at the endpoint.

**Alternatives considered:**

- `deleted_at` timestamp (soft delete pattern) — common in many ORMs. Implicitly hides deactivated records from default queries.
- Hard delete with no soft state at all — simplest, but loses history.

**Why this won:** The bakery owner thinks in "active vs deactivated," not "soft-deleted vs visible." Reactivation is a normal operation, not an exception. A `deleted_at` timestamp also implies the row is going away eventually (cleanup queries, etc.), which we don't want — orders reference past customers and products forever via snapshots.

**Regex validation rationale:** A simple typo (`?status=actve`) would silently default to one of the values without a regex match — better to 422 the request and surface the error to the developer.

## ADR-4 — Service layer separated from API layer

**Decision:** All business logic lives in `backend/app/services/`. API routes in `backend/app/api/v1/` are thin — they parse input, call a service, serialize output, and translate exceptions.

**Alternatives considered:**

- Fat controllers — put queries and validation directly in the API route. Faster to write initially.
- Repository pattern — separate the data-access layer from the service layer. More layers, more discipline, more value at large scale.

**Why this won:** The Phase 3 WhatsApp bot will need to create orders, look up customers, transition statuses — all the same operations the API exposes. With service separation, the bot calls `order_service.create_order(db, data)` directly; no business logic gets duplicated, no HTTP fakery is needed. The repository pattern would be overkill for a single-database app; we can add it later if it becomes a pain point.

## ADR-5 — Frontend: TanStack Query for server state, useState for UI state, nothing else

**Decision:** No Redux, no Zustand, no Jotai, no Context API for data. Server state lives in TanStack Query cache, UI state in `useState`. The only React context used is `AuthContext` for the logged-in user.

**Why:** Every state library introduces concepts the team has to learn and a layer where bugs can hide. TanStack Query already solves the hard parts (caching, invalidation, background refetch, optimistic updates) for server state. UI state is local — which modal is open, which filter chip is active — and `useState` is fine.

**What could change the answer:** If we end up with a complex shared UI state that crosses many pages (e.g., a multi-step wizard that spans routes), we'd reach for a small library. Not yet.

## ADR-6 — Tailwind, no component library

**Decision:** Tailwind utility classes directly in components. No shadcn/ui, no Headless UI, no Radix, no Material UI, no Chakra.

**Why:** Component libraries pull in styling conventions that fight the design system we want, and most BakeriQ components are simple enough that the savings are minimal. Tailwind's utility approach lets the design system live in `tailwind.config.js` (brand colours, named max-widths, font family) and the components stay readable.

**What could change the answer:** If we add a feature with serious accessibility complexity (combo boxes, command palettes, complex dialogs), Radix primitives would be worth pulling in for the a11y plumbing alone. Not yet.

## ADR-7 — JWT, no sessions

**Decision:** Authentication uses JWT bearer tokens. No server-side sessions, no Redis-backed session store, no cookies.

**Why:** Single-tenant internal tool, single user (the owner), no SSO requirements. JWT is enough — the frontend stores the token in `localStorage`, includes it on every request, and gets a 401 if it expires. No CSRF concerns because there are no cookies.

**Token lifetime:** Currently long-lived (8 hours). Short enough that a stolen token doesn't grant indefinite access, long enough that the owner isn't logging in every hour.

**What could change the answer:** If we ever add multi-user or chef-role separation, we'd want refresh tokens and shorter access token lifetimes. Probably with the chef role in Phase 4.

## ADR-8 — Twilio first, Meta WhatsApp Business Platform later

**Decision:** Phase 3 uses Twilio's WhatsApp Sandbox for development, with migration to Twilio's production WhatsApp Sender for the live deployment. Meta's WhatsApp Business Platform (direct integration) is deferred to post-MVP.

**Alternatives considered:**

- **Meta WhatsApp Business Platform directly** — better unit economics at scale, official path. But requires Meta Business Manager verification, a Meta-approved phone number, a WhatsApp Business Account (WABA), and template approval — days to weeks of setup before the first "hello world."
- **Hybrid** — develop on Twilio, switch providers later.

**Why Twilio first:**

| Factor | Twilio | Meta direct |
|---|---|---|
| Time to first working message | ~15 minutes (Sandbox join phrase) | Days |
| Sandbox for development | Yes, free | No |
| Webhook signature verification | Single HMAC-SHA1 header | OAuth-style + verify_token handshake |
| Python SDK | Mature `twilio` package | Raw requests or community wrappers |
| Cost per message at our scale | Negligible (~₹0.4 / message) | Slightly cheaper at scale |

For an internship project with 42 days remaining, the time-to-first-message difference is the deciding factor. Twilio also abstracts over the WhatsApp Business API, so if we migrate to Meta later we keep most of the application code and just swap the outbound message client.

**What could change the answer:** If BakeriQ goes to real production with serious volume (thousands of messages/day across multiple bakeries), Twilio's per-message premium starts to matter and direct Meta integration becomes worth the setup pain. That's a Phase 7+ concern.

## ADR-9 — `RowActionsMenu` uses `position: fixed`, not `absolute`

**Decision:** The `⋯` row-actions popover uses `position: fixed` with viewport-relative coordinates computed from the trigger button's bounding rect at open time. It is not nested in the table cell.

**Alternatives considered:**

- `position: absolute` inside the cell — simplest, but gets clipped by parent `overflow-hidden` (used on the table wrapper for rounded corners).
- React portal to `document.body` — works, escapes overflow cleanly. Slightly more machinery than needed.
- Remove `overflow-hidden` from the table wrapper — breaks the rounded-corner clipping.

**Why fixed positioning won:** Escapes any parent overflow without React portals, computes its own coordinates so it stays aligned to the trigger, and closes on scroll/resize to avoid floating away from its anchor. Single component, no portal API.

**Concrete bug it fixed:** Before this, the ⋯ menu was invisible on inactive customer/product rows when the inactive list was short — the menu rendered below the table's visible area and got clipped by `overflow-hidden`.

## ADR-10 — `RoutesSUBTITLES` in TopBar, not per-page subtitle prop

**Decision:** The TopBar reads the current pathname and looks up a per-route subtitle from a static map defined in `TopBar.jsx`.

**Alternatives considered:**

- Each page passes a `subtitle` prop up via context or a layout pattern. Cleaner separation but adds prop drilling for a one-line-per-page change.
- Route metadata in the router config. Cleaner but spreads the subtitle definition between two files.

**Why this won:** Adding a new page's subtitle is one line in one file. If we add nested routes later (e.g., `/orders/:id`), we'd switch to `pathname.startsWith()` matching, but right now the flat map is enough.

## ADR-11 — Native Postgres enum for `order_status`, not Python enum on application side

**Decision:** Order status is a native Postgres enum (`order_status` type) with values `received`, `preparing`, `ready`, `delivering`, `cancelled`.

**Alternatives considered:**

- String column with a Python-side enum validator. More portable across databases.
- Lookup table referenced by foreign key. More flexibility for adding metadata per status, but heavier.

**Why native enum won:** Database-enforced constraint — a status can never be set to a bad value at the row level, even if the application has a bug. Postgres-only is fine because we're not portable; this is going to run on Postgres in dev and prod.

**Migration cost:** Adding a new status requires an Alembic migration that does `ALTER TYPE order_status ADD VALUE 'new_status'`. Slightly more friction than appending to a Python enum, but appropriate friction for a value that affects every existing row.

## ADR-12 — Analytics dropped from Phase 6

**Decision:** Phase 6 scope reduced to billing only. Analytics dashboards (revenue trends, product performance, customer frequency) were removed.

**Reasoning:** Analytics doesn't have a clear daily user. The bakery owner uses the dashboard for today's overview (already built); a chef doesn't need historical trend graphs to prepare today's orders. Building analytics would consume substantial Phase 6 time for marginal operational value.

**What could change the answer:** If post-MVP the owner asks "I wish I could see how Veg Puffs are trending over the last month," we add it then with real user feedback rather than guessing.

## ADR-13 — Single-tenant by design

**Decision:** There is no organisation, tenant, or workspace concept. All data is global within a deployment. Multi-tenancy is not on the roadmap.

**Why:** BakeriQ is a tool for one bakery. The technical complexity of multi-tenancy (row-level security, tenant isolation, billing per tenant, support overhead) would dominate the development time. If we ever wanted to operate BakeriQ as a SaaS for multiple bakeries, we'd fork the codebase for the SaaS version rather than try to retrofit multi-tenancy onto this one.

## ADR-14 — UI polish branched separately from feature work

**Decision:** UI/UX work happens on its own branches (`ui-responsive-overhaul`, `ui-polish-pass`) rather than being folded into feature branches.

**Why:** Mixing visual polish into a feature commit makes the diff hard to review and harder to revert. Separate branches with clear scope ("just the sidebar redesign," "just the format helpers and badges") give the team lead a cleaner review surface. Each polish branch also closes with a single squash-able commit if needed.

**Historical note:** The h-screen Layout fix accidentally landed directly on `main` once. Caught, but flagged as a process slip — UI changes should always branch.

---

## Adding new decisions

When you make a non-obvious choice during development, log it here with the same format. Future you and the next developer will thank you.

Particularly worth logging:

- Architectural patterns (layering, state management)
- Library or service choices
- Trade-offs where the obvious answer wasn't taken
- Decisions that closed off a previously-considered option

Not worth logging:

- Naming conventions (those go in `DEVELOPMENT.md`)
- Specific bug fixes
- Routine refactors
