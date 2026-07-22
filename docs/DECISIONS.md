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

**Token lifetime:** 7 days (`ACCESS_TOKEN_EXPIRE_MINUTES=10080`). Long by general standards, and deliberately so: there is no refresh-token flow, so a shorter lifetime translates directly into the owner re-authenticating. Since Phase 3.5 the owner often reaches the dashboard by tapping a WhatsApp notification on their phone, and hitting a login screen at that moment defeats the point of the notification.

The blast radius is one bakery's order list, on a single-user internal tool, with no payment capability. That's the trade being made.

**What could change the answer:** a refresh-token flow would let the access token drop to an hour or less without costing the owner anything — worth doing alongside the chef role, when there's more than one account to protect. Payment capability would force it.

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

## ADR-15 — Self-hosted Ollama, not a cloud LLM API

**Decision:** Natural-language order parsing runs on `llama3.2:3b` via Ollama, installed natively on the host. No Claude, OpenAI, or other hosted API.

**Alternatives considered:**

- **Claude API** — the original plan, and better at the task. Dropped when the project's API credits ran out mid-Phase-3.
- **A larger local model** — better accuracy, but the dev machine is an Intel Core Ultra 5 125H with 16 GB RAM and an Arc iGPU. 3B parameters at Q4 is what fits comfortably alongside Postgres, Redis, and two Vite servers.

**Why local won, beyond the forcing function:** No per-message cost, so smoke-testing is free. No customer message leaves the machine, which matters for a system holding names, phones, and delivery addresses. And Ollama's `format` parameter constrains generation to a JSON schema at the sampling level, so the output is guaranteed parseable — no markdown-fence stripping or repair logic, which a plain-text cloud completion would need.

**What it costs:** 3-5 seconds per inference on CPU, versus sub-second for a hosted API. That latency is why parsing runs in Celery rather than inline (ADR-16). Accuracy is also lower — the model needed explicit few-shot examples for Manglish quantity words (`oru` = 1, `randu` = 2) that a larger model would infer.

**Runs on the host, not in a container:** the model is ~2 GB and would need re-pulling on every image rebuild. Containers reach it via the Docker bridge gateway, which requires `OLLAMA_HOST=0.0.0.0` and a UFW rule. See [`SETUP.md`](SETUP.md).

**What could change the answer:** If parse quality becomes the limiting factor on customer experience, a hosted model is the fix — the interface is narrow enough (`llm_parser_service` in, JSON out) that swapping is a contained change.

## ADR-16 — LLM parsing runs in Celery, not inline in the webhook

**Decision:** When the fast-path dispatcher can't match a message, the webhook enqueues `tasks.llm.parse_and_send` and returns empty TwiML immediately. The worker sends the real reply through Twilio's REST API seconds later.

**Alternatives considered:**

- **Parse inline and return the reply as TwiML** — one round trip, much simpler. But Twilio's webhook timeout is ~10 seconds and local inference takes 3-5, leaving no headroom for a slow first token or a retry.
- **Respond immediately with "one moment…" then follow up** — same async machinery, plus an extra message against the sandbox's 50/day quota.

**Why Celery won:** It decouples reply latency from webhook latency entirely. It also gives retries for free, which matters because Ollama can be temporarily unreachable — the container restarts, the host service reloads, the bridge rule gets dropped.

**Consequence worth knowing:** the worker runs with its own DB session (`SessionLocal`, not the request-scoped `get_db`), so the webhook has to commit the inbound message *before* enqueuing. Otherwise the worker starts, queries for a conversation that isn't visible yet, and fails.

**Retry hardening:** `autoretry_for` covers Ollama SDK errors and `httpx.ConnectError` / `ConnectTimeout` / `ReadTimeout`. When retries exhaust, a `MaxRetriesExceededError` handler sends a degraded-service message rather than leaving the customer in silence.

## ADR-17 — The parser extracts everything; the matcher decides availability

**Decision:** `llm_parser_service` returns every food item the customer named, including ones not on today's menu. `product_matcher_service` then resolves those names against the product table and decides what's orderable.

**Alternatives considered:**

- **Have the LLM filter** — give it the menu and ask it to return only available items. This is what the first implementation did.

**Why the split won — and the bug that proved it:** The original prompt said "if the customer asks for something NOT in the catalog, OMIT it entirely." That worked, in the sense that the model obeyed. But it destroyed the signal the rest of the system needed:

- `i want 1 samosa and 1 pizza` (neither available) returned `items: []`, indistinguishable from `how are you today`. The customer got "sorry, I didn't catch that" when the bot had understood perfectly and simply couldn't serve them. The `nothing_available` branch was unreachable.
- Worse, `i want 2 veg puff and 1 samosa` also sometimes returned `[]` — the presence of one off-menu item made the model drop the whole order.

Inverting the rule fixed both. Verified against eight cases covering on-menu, off-menu, mixed, Manglish quantities, alias resolution, and non-order chitchat.

**The general principle:** don't ask a stochastic component to make a decision a deterministic one can make. The LLM is good at language and bad at exactness; the matcher is the reverse. Extraction is a language problem, availability is a lookup.

**Guardrail:** the prompt still says "do NOT invent items the customer didn't mention," with a `do you have brownies?` → `[]` example. Loosening the filter risked over-extraction from questions; the example holds that line.

## ADR-18 — Content Templates for interactive buttons

**Decision:** Bot replies that offer choices use Twilio Content Templates with quick-reply or CTA buttons, not plain text with keyword instructions.

**Alternatives considered:**

- **Plain text prompts** — "Reply *menu* to see today's items". No Twilio-side setup, works everywhere. This is what Phase 3 shipped with initially.

**Why templates won:** Typing a keyword correctly is friction, and the failure mode is the LLM safety valve — a 3-5 second wait and a possible misparse for what should be a single tap. Buttons remove the failure mode entirely.

**The two sharp edges:**

1. **Button titles are load-bearing.** Twilio delivers the button's *title* as the inbound message body, and `customer_handler` matches on those strings. Renaming a button silently breaks its route with no error anywhere.
2. **URLs are baked in at creation time.** A template carrying a link stores the URL as it was when created. When the ngrok free-tier hostname rotates, those templates point at a dead host. Editing the bootstrap script isn't enough — it skips templates that already exist, so the old one must be deleted on Twilio first. `make ngrok-check` detects the drift; `make templates-refresh` repairs it.

**Also:** the Twilio Python SDK can send templates but cannot create them. `twilio_content_service` wraps the Content API with raw `httpx` calls for CRUD.

## ADR-19 — Customers never log in; a path token is the credential

**Decision:** The customer-facing web app has no authentication. A URL-safe random token in the path grants exactly one capability, and receiving it over WhatsApp is the proof of identity.

**Alternatives considered:**

- **Customer accounts with passwords** — conventional, and completely wrong for the context. A bakery customer ordering twice a week will not maintain a password, and every forgotten one becomes a support call to the owner.
- **OTP on each visit** — no password to forget, but adds a round trip and burns Twilio quota on every order.
- **Long-lived signed cookie after first WhatsApp verification** — better repeat-visit UX, but cookie lifetime becomes the security boundary and phone handoff gets murky.

**Why the token won:** WhatsApp is already the identity layer. Delivering a token to a number proves control of that number as well as any OTP does, and it costs nothing extra because we're sending a message anyway. This is the same pattern as "click this link to confirm your email" — the inbox is the credential.

**The threat model, stated plainly.** A stolen token grants one action, for one phone, once, within a short window. Registration tokens are phone-bound with the form's phone field read-only, so an attacker can't register as someone else. Cart tokens are customer-bound and consumed on order placement. Worst case is one junk row the owner rejects, or one unwanted order the owner cancels.

**What we deliberately don't defend against:** someone who already controls the customer's WhatsApp account. They have larger problems than a bakery order.

**What could change the answer:** payment. The moment a token can move money, this reasoning stops holding and real authentication is required.

## ADR-20 — Registration by webform, not bot conversation

**Decision:** An unrecognised number gets a CTA card linking to a web form. The previous multi-turn bot conversation (`collecting_name` → `collecting_area` → `awaiting_approval`) was deleted outright.

**Alternatives considered:**

- **Keep the conversation** — no new surface area, works without a browser.
- **Keep both, webform preferred with conversation as fallback** — most forgiving, but doubles the code paths and the failure modes for a flow that runs once per customer.

**Why the webform won:** The conversation collected a name and a free-text "area", which wasn't a real address. Approving one produced a Customer with null address fields — and since `CustomerBase` requires them, that row then broke serialization for the entire customers list. A form collects structured fields with validation in one shot, matching the Customer schema exactly so approval is a straight field copy.

It also matches the cart flow the codebase already had, so there's one pattern for "bot sends a link, customer fills something in" rather than two.

**What it costs:** the customer needs a browser and has to type a full postal address. For a bakery whose customers are mostly local, that's more friction than two questions. If real customers drop off at the form, the fix is a shorter form or a delivery-vs-pickup toggle — not nullable addresses, which is what caused the original bug.

**Deleted rather than retired:** the state machine is gone, along with its `conversation_state` column and its tests. Half-retired code becomes a graveyard that confuses the next reader. Git history has it if anyone needs it.

## ADR-21 — Separate token tables, not one polymorphic table

**Decision:** `web_session_tokens` (cart) and `registration_tokens` (webform) are distinct tables with distinct services, despite near-identical shapes.

**Alternatives considered:**

- **One table with a nullable `customer_id` and a `kind` discriminator** — less duplication, one service.

**Why separate won:** `web_session_tokens.customer_id` is non-null and load-bearing for the cart flow, which is well-tested and working. Registration happens *before* a Customer exists, so unifying them means making that column nullable — and every cart code path that currently trusts it would need re-auditing for a null case that can't actually occur there.

The semantics differ too: cart tokens are customer-bound with a 30-minute expiry; registration tokens are phone-bound with 12 hours and one-shot consumption. Roughly 60 lines of mirrored service code is cheaper than the risk of introducing a null into a working flow.

**What could change the answer:** a third token type. Two mirrored tables is fine; four would be a smell worth refactoring.

## ADR-22 — Owner notification is synchronous and best-effort

**Decision:** Submitting the registration form sends the owner's WhatsApp card inline in the request, wrapped in a broad `try/except` that logs and swallows every failure.

**Alternatives considered:**

- **Celery task** — consistent with the LLM path, retries for free. But it adds a moving part for a single ~500 ms Twilio call.
- **Let failures propagate** — the customer would see an error for something that isn't their problem, after their registration had already been committed.

**Why sync-and-swallow won:** The customer is looking at a success page; 500 ms is invisible. And the notification is genuinely optional — if Twilio is down, the owner still sees the request via the approvals badge, which polls independently. Failing the customer's registration because a *notification* failed would be strictly worse.

**Ordering matters:** the notification fires *after* the registration commits. A Twilio exception can't roll back the customer's data.

**If `OWNER_WHATSAPP_PHONE` is unset**, the whole thing is a logged no-op — which keeps local dev quiet without needing a real phone.

## ADR-23 — Both front ends proxied through the API

**Decision:** FastAPI reverse-proxies `/web/*` to the customer app and `/app/*` to the dashboard. Each Vite config declares a matching `base` so paths forward verbatim.

**Alternatives considered:**

- **A second ngrok tunnel** — free tier allows it, but it's another process to babysit and another URL to keep in sync with the templates.
- **Serve built bundles from FastAPI's StaticFiles** — production-shaped, but gives up hot reload in dev.

**Why the proxy won:** Twilio needs one public URL and ngrok's free tier gives one tunnel. Everything a phone reaches — the API, the cart, the registration form, the approvals page — has to sit behind one hostname. This mirrors what nginx will do in production, so the topology is the same shape in both.

**What it costs:**

- The dashboard's dev URL becomes `localhost:5173/app/`; bare `localhost:5173` no longer serves it.
- `BrowserRouter` needs a matching `basename`. React Router respects it; raw `window.location` assignments don't, so three files hardcode `/app/login`.
- Vite dev mode serves every import as a separate request. Through a tunnel with ~250 ms latency, a cold dashboard load is slow. Serving a built bundle would fix it if this becomes painful.
- Each Vite server needs its docker service name in `allowedHosts`, because the proxy strips the original `Host` header.

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
