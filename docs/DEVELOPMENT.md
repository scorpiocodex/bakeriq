# Development

Day-to-day workflow notes — how to actually work in this codebase. Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first for the bigger picture, and [`SETUP.md`](SETUP.md) if the stack isn't running yet.

## Where work happens

Almost everything runs inside containers. Open a shell into the api container for backend work:

```bash
make shell-api
```

You'll land at `/app` (the backend root) as the `app` user. Python venv is global to the container, packages are pre-installed, and the working dir is bind-mounted from your host so edits in your editor are visible immediately.

For frontend work, edits under `frontend/src/` or `frontend-customer/src/` are picked up by Vite's hot reload — no container shell needed. If you do need one (e.g., to add a dependency):

```bash
docker compose exec frontend sh           # dashboard
docker compose exec frontend-customer sh  # customer app
```

**Dev URLs:**

| App | Direct | Through the API proxy |
|---|---|---|
| Dashboard | `localhost:5173/app/` | `localhost:8000/app/` |
| Customer app | `localhost:5174/web/` | `localhost:8000/web/` |
| API docs | — | `localhost:8000/docs` |

Both Vite servers declare a `base`, so bare `localhost:5173` and `localhost:5174` will **not** serve the apps — Vite returns a "configured with a public base URL" message instead. Use the `/app/` and `/web/` paths.

Use the proxied URLs when you need the same request path a phone would take. Use the direct ones for normal work — hot reload doesn't survive the proxy, since HMR's WebSocket isn't forwarded.

**React Router handles the prefix; raw `window.location` does not.** Route paths are declared unprefixed and `BrowserRouter`'s `basename` resolves them. But three files navigate by assigning to `window.location` directly, and each has to spell `/app/login` out in full: the 401 interceptor in `api/client.js`, `context/AuthContext.jsx`, and `api/auth.js`. Add a fourth and it needs the prefix too, or an expired token will bounce the owner to an unserved origin root.

## Starting the stack

```bash
make dev-up
```

Brings up Docker, starts ngrok if it isn't running, and checks whether the Content Templates' baked URLs still match the current tunnel — auto-repairing them if not. This is the one command to run after a reboot or a long break.

```bash
make ps        # container status
make logs      # tail api logs
make help      # every available target
```

## Running tests

```bash
make test         # Full backend suite with coverage
make test-fast    # Same suite, stop at first failure
```

Tests run inside the api container against the `db_test` database on port 5433. Your dev data on port 5432 is untouched. **276 tests as of Phase 3.5.**

To run a single test or module:

```bash
make shell-api
pytest tests/test_order_service.py
pytest tests/test_order_service.py::test_snapshot_survives_price_change
pytest -k "snapshot"
```

Tables are truncated between tests by the fixture in `conftest.py`. You should never need to manually wipe the test DB.

### Tests and real WhatsApp messages

`conftest.py` has an autouse fixture that stubs out `owner_notification_service.notify_new_registration`. Without it, the registration endpoint tests fire **real** WhatsApp messages at the owner's phone — roughly five per suite run, against a sandbox quota of 50/day.

If you add a code path that sends outbound WhatsApp from a request handler, either mock it in the test or extend that fixture. A test suite that costs money and spams a phone is a test suite people stop running.

## Creating migrations

After changing a SQLAlchemy model:

```bash
make migration
# Prompts for a migration message
```

This generates a file under `backend/alembic/versions/`. **Open it and read it before applying.** Autogenerate on this schema is noisy enough that hand-writing is sometimes faster than cleaning up.

### Known autogenerate noise

Three things recur:

**1. The `customers.secondary_phone` index.** Every migration touching `customers` spuriously includes four lines converting `ix_customers_secondary_phone` from one Alembic representation to another:

```python
# In upgrade():
op.drop_index('ix_customers_secondary_phone', table_name='customers')
op.create_index(op.f('ix_customers_secondary_phone'), 'customers', ['secondary_phone'], unique=True)

# In downgrade():
op.drop_index(op.f('ix_customers_secondary_phone'), table_name='customers')
op.create_index('ix_customers_secondary_phone', 'customers', ['secondary_phone'], unique=True)
```

Delete all four. They're a no-op that clutters history.

**2. Cosmetic `VARCHAR` length changes.** Autogenerate emits `op.alter_column(...)` for columns whose declared length differs from what's in the database, even when nothing meaningful changed — usually an artifact of SQLAlchemy 2.0 metadata. If the column's actual constraint isn't changing, drop the line.

**3. `op.drop_constraint(None, ...)`.** When Alembic can't resolve a constraint name it emits a literal `None`, which crashes at migration time. If you see `None` as a constraint name, either supply the real name or delete the operation.

### Native Postgres enums

Migrations creating native enums (currently just `order_status`) need an explicit drop in the downgrade — autogenerate misses this:

```python
def downgrade():
    # ... other downgrade operations ...
    sa.Enum(name='order_status').drop(op.get_bind())
```

### Applying migrations

```bash
make migrate
```

Applies pending migrations against the dev database. The test database gets them automatically when the suite runs.

## Resetting the database

```bash
make reset-db
```

Drops, recreates, migrates, and seeds the dev database. Wipes everything. Useful when a destructive schema change has left you somewhere odd, or when you want a known-good state back.

The seed script is `backend/scripts/seed_phase_2.py`. It still only covers through Phase 2 — no seeded conversations, registrations, or tokens. If you need those, create them by hand or via the bot.

## Working on the WhatsApp channel

### The ngrok hostname problem

The free ngrok tier can hand you a different hostname after a restart. When that happens, two things break at once: Twilio's webhook points at a dead host, and any Content Template with a baked-in URL (cart link, owner notification) sends customers to a dead link.

```bash
make ngrok-check        # is ngrok up, and do templates match the current tunnel?
make templates-refresh  # re-bootstrap templates against the current PUBLIC_BASE_URL
```

`make dev-up` runs the check automatically and repairs drift.

If the hostname changed you also need to update Twilio's webhook URL by hand, in the Console under Messaging → Try it out → Sandbox settings.

### Content Templates

Seven templates live on Twilio, created by:

```bash
docker compose exec api python scripts/bootstrap_content_templates.py
```

The script is idempotent — it skips templates that already exist and writes SIDs into `.env`. **That idempotency is a trap when editing an existing template:** changing the body or URL in the script does nothing, because the script sees the template already exists. You have to delete it on Twilio first:

```bash
docker compose exec api python -c "
import httpx
from app.core.config import settings
r = httpx.delete(
    'https://content.twilio.com/v1/Content/HX_the_sid_here',
    auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
)
print(r.status_code)
"
```

Then re-run the bootstrap and recreate the containers so the new SID is picked up.

**Never rename a button title** without changing the matching constant in `customer_handler`. Twilio delivers the button's title as the inbound message body — a renamed button routes nowhere, silently.

### Smoke testing

```bash
make whatsapp-smoke
```

Sends one nav template to `SMOKE_TEST_PHONE`, confirming Twilio credentials, template SIDs, and the tunnel are all working. Asks for confirmation first, since it costs quota.

Watch messages arrive and dispatch:

```bash
docker compose logs -f api worker
```

The ngrok pane also shows every inbound request with its status code, which is the fastest way to see whether a webhook actually landed.

### Testing registration

The bot only routes to registration for numbers that aren't active Customers, so you can't test the flow from a phone that's already registered. Options:

- Use a second phone (send `join <sandbox-phrase>` to the sandbox number first)
- Create the registration directly and skip the WhatsApp leg:

```bash
docker compose exec api python -c "
from app.core.database import SessionLocal
from app.services import pending_registration_service as pr_svc
from app.services import owner_notification_service
db = SessionLocal()
reg = pr_svc.create_from_webform(
    db, phone='+919777888999', name='Test User',
    address_line_1='1 Test Road', city='Kochi', state='Kerala', pincode='682020',
)
db.commit()
owner_notification_service.notify_new_registration(db, name=reg.name, phone=reg.phone)
db.close()
"
```

Or issue a token and open the form in a desktop browser:

```bash
docker compose exec api python -c "
from app.core.database import SessionLocal
from app.services.registration_token_service import issue_token
db = SessionLocal()
token, url = issue_token(db, phone='+919777888999')
db.commit()
print(url)
db.close()
"
```

## Adding a new endpoint

1. **Add or modify the model** — `backend/app/models/<resource>.py`
2. **Generate a migration** — `make migration`, clean it up, `make migrate`
3. **Add or update Pydantic schemas** — `backend/app/schemas/<resource>.py`
4. **Add the service function** — `backend/app/services/`. Pure business logic, `db: Session` first arg.
5. **Add tests for the service** — `backend/tests/`. Happy path plus 1-2 edge cases.
6. **Add the API route** — `backend/app/api/v1/<resource>.py`. Thin.
7. **Register the route** if it's a new file — `backend/app/api/v1/router.py`

Then on the frontend:

8. **Add the axios call** — `src/api/<resource>.js`
9. **Add the TanStack Query hook** — `src/hooks/use<Resource>.js`, with a `*Keys` object for cache invalidation
10. **Use the hook in the page** — `src/pages/<Page>.jsx`

## Adding a frontend page

There are two React apps — make sure you're in the right one. `frontend/` is the owner dashboard (JWT-authed, served under `/app`); `frontend-customer/` is the customer app (token-authed, served under `/web`).

For a new dashboard route:

1. Create `frontend/src/pages/<NewPage>.jsx`
2. Add the route in `frontend/src/App.jsx` — paths are declared **without** the `/app` prefix; `BrowserRouter`'s basename handles it
3. Add a sidebar entry in `frontend/src/components/Sidebar.jsx` with a distinct lucide icon (see below)
4. Add a `ROUTE_SUBTITLES` entry in `frontend/src/components/TopBar.jsx`

### Sidebar icon collisions

Each page must use a distinct icon. Easy to break — lucide has many box-shaped icons. Current assignments:

| Page | Icon |
|---|---|
| Dashboard | `LayoutDashboard` |
| Orders | `ShoppingCart` |
| Approvals | `ClipboardCheck` |
| Customers | `Users` |
| Products | `ShoppingBag` |
| Inventory | `Boxes` |
| Billing | `Receipt` |
| Settings | `Settings` |

Don't pick `Package` (too close to `Boxes`), `Tag` (reads as category), or `ClipboardList` (too close to `ClipboardCheck`).

## Commit conventions

Conventional Commits — every message starts with a type:

| Type | When |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code change without behaviour change |
| `docs` | Documentation only |
| `test` | Test additions / changes |
| `chore` | Build, deps, config, ci |

Subject line: present tense, no period, lowercase after the colon.

For substantial commits, write a body explaining *what* and *why* — the diff already shows *how*. Where a change was motivated by a bug, say what the bug was; that's the part nobody can reconstruct later.

**Long messages and the shell.** Pasting a multi-paragraph `-m` string into a terminal frequently mangles it — lines interleave, the closing quote gets eaten. Use bare `git commit`, write the message in your editor, save and close. Several commits in this repo's history have visible paste damage from doing it the other way.

## Branching

`main` is the deployable branch. Feature work happens on feature branches with a phase or task prefix:

- `phase-3-whatsapp-bot` — Phase 3 and 3.5 work
- `fix-popover-clipping` — a focused bug fix
- `ui-polish-pass` — cosmetic improvements

Merge to `main` via `git merge --no-ff` for substantial branches, or fast-forward for trivial single-commit fixes.

## Git identity

Pushes are rejected (`GH007`) if the committer email isn't the GitHub-noreply form:

```bash
git config user.name "scorpiocodex"
git config user.email "212041449+scorpiocodex@users.noreply.github.com"
```

## Code style

### Backend

- Black formatting (88-char line limit), enforced by Ruff
- Ruff for linting; imports sorted by isort (inside Ruff config)
- Type hints on function signatures — return types especially
- Docstrings on services (not always on simple API handlers)

### Frontend

- Prettier (single quotes, trailing commas, 100-char width)
- ESLint with the React plugin
- Functional components only
- Hooks order: state, then derived values, then effects, then handlers, then render
- One default export per file; named exports for incidental utilities

VS Code with the included `.devcontainer/devcontainer.json` configures both automatically.

### Pylance and Optional narrowing

Pylance flags `reportOptionalMemberAccess` when a value could be `None`, even where a preceding line guarantees it isn't. This shows up constantly in tests that fetch a row they just created. Fix with an explicit assert:

```python
row = get_valid_token(db, token)
assert row is not None
consume_token(db, row)
```

Runtime-neutral, and it silences a diagnostic that otherwise trains you to ignore the squigglies.

## Service patterns

### SQLAlchemy session

Services take `db: Session` and call `db.flush()`, not `db.commit()`. The endpoint commits at the end of a successful request. This lets a service compose several operations into one transaction.

```python
def create_order(db: Session, data: OrderCreate) -> Order:
    order = Order(...)
    db.add(order)
    db.flush()  # gets the order ID without committing
    for item_data in data.items:
        db.add(OrderItem(order_id=order.id, ...))
    db.flush()
    return order
```

**The Celery worker is the exception.** It uses its own `SessionLocal`, not the request-scoped `get_db`. Anything the worker needs to see must be committed *before* the task is enqueued — otherwise the worker queries for a row that isn't visible yet.

### Parent-child relationships

- `cascade="all, delete-orphan"` on the parent's `relationship()`
- `lazy="selectin"` for collections (one follow-up query, not N+1)
- `lazy="joined"` for to-one relationships

To replace all children on update, reassign the list — the cascade handles deletes and inserts:

```python
order.items = [OrderItem(...) for item_data in data.items]
db.flush()
```

### Soft deactivation

```python
def deactivate_customer(db: Session, customer_id: UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise NotFoundError(...)
    customer.is_active = False
    db.flush()
    return customer
```

Reactivation goes through the normal update endpoint with `{"is_active": true}` — there's no separate endpoint.

**When adding an `is_active` check, add it everywhere.** `find_customer_by_phone` filtered on it and the registration endpoint's already-registered check didn't, which left deactivated customers routed to a form that then rejected them — a dead end with no way back in.

### Bot handler contract

Every inbound WhatsApp handler returns `list[Reply] | None`.

`None` means exactly one thing: the fast-path dispatcher found no keyword or button match, so the message goes to the LLM safety valve. **Don't return `None` for "nothing to say"** — return an empty list. The webhook branches on that distinction to decide whether to enqueue a Celery task.

`Reply` is frozen and enforces body XOR content_sid, so an outbound is unambiguously text or template, never both. Build them with `Reply.text()` / `Reply.template()`, or — preferably — the factories in `template_replies`, which handle the "template SID not bootstrapped yet" fallback for you.

## Frontend patterns

### TanStack Query keys

Define keys once per resource, in the hooks file:

```js
export const customerKeys = {
    all: ['customers'],
    lists: () => [...customerKeys.all, 'list'],
    list: (filters) => [...customerKeys.lists(), filters],
    detail: (id) => [...customerKeys.all, 'detail', id],
};
```

Mistyped inline keys are the most common cause of "why didn't my list refresh?" bugs. The hierarchy lets you invalidate broadly or narrowly.

### Mutation cache invalidation

After a successful mutation, invalidate what the mutation actually affected — including other resources:

```js
useMutation({
  mutationFn: approveRegistration,
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: approvalKeys.all });
    queryClient.invalidateQueries({ queryKey: ['customers'] });
  },
});
```

Approving a registration creates a Customer, so any mounted customer list is stale too.

### Polling

There are no WebSockets. When something needs to feel live, poll — but poll something cheap.

The approvals badge uses `refetchInterval: 30_000` on a **count-only** endpoint, kept as a separate query from the list. Polling the full list every 30 seconds would drag back every pending row on each tick for a number that fits in a badge.

```js
export function useApprovalsCount() {
    return useQuery({
        queryKey: approvalKeys.count(),
        queryFn: getApprovalsCount,
        refetchInterval: 30_000,
    });
}
```

30 seconds is a deliberate middle ground: fast enough that the badge feels responsive, slow enough that an idle dashboard isn't hammering the API all day. React Query also refetches on window focus by default, which covers the common case of the owner tabbing back after reading a WhatsApp notification.

### Form modals

Controlled components taking `open`, `onClose`, and optionally a record to edit. State is local. On submit they call a mutation hook and close on success.

`ConfirmDialog` has no text input. If you need one (the approvals page's reject reason, for instance), write a small local modal rather than extending the shared component.

## What to check before a PR / merge

- [ ] All tests pass: `make test`
- [ ] Migrations reviewed and cleaned (see autogenerate noise above)
- [ ] New endpoints have at least 2-3 service tests
- [ ] Frontend builds without warnings: `docker compose exec frontend npm run build`
- [ ] No `console.log`, `print`, or commented-out blocks left behind
- [ ] Commit messages follow Conventional Commits
- [ ] If you touched Content Templates, the affected one was deleted on Twilio and recreated

## Common gotchas

### `.env` changes need `--force-recreate`

`docker compose restart` keeps the environment the container was created with. A new or changed variable in `.env` won't be visible:

```bash
docker compose up -d --force-recreate api worker
```

This bites hardest after running the template bootstrap, which writes new SIDs into `.env`. Symptom: the config still reads `None` for a variable you can see in the file.

### Async / await on endpoints

FastAPI endpoints can be `async def` or plain `def`. SQLAlchemy 2.0 sync sessions don't play nicely with `async def` unless you use the async engine. **All endpoints here are plain `def`** — don't switch one without converting the session too.

The webhook is the exception: it's `async def` because it awaits the request body, but it uses the sync session and does no other awaiting.

### Pydantic v2 model_config

```python
class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

Not `class Config:` — that's v1.

### Required address fields on Customer

`CustomerBase` requires `address_line_1`, `city`, `state`, and `pincode`. Anything creating a Customer must supply all four. A row with nulls inserts fine and then breaks `CustomerOut` serialization — which 500s the **entire** customers list, not just that row. This is why the registration webform requires a full address.

### docker-compose vs docker compose

The project uses Compose v2 (`docker compose`, no hyphen). If your install is older, update Docker.

### Frontend Vite cache

Occasionally Vite caches a stale build. Symptoms: fresh code, old behaviour. Fix: hard reload (Ctrl/Cmd + Shift + R), or `docker compose restart frontend`.

### Don't unpin the Docker bridge name

`docker-compose.yml` pins the network to `bakeriq` with bridge interface `bakeriq0`. Before that pin, Docker generated a fresh `br-<hash>` interface on every `down`/`up`, which silently invalidated the UFW rule letting containers reach Ollama on the host.

The symptom was "the worker can't reach the LLM", with nothing in any log pointing at the firewall. It cost hours across several sessions before the pattern was spotted. Leave the pin alone, and if you add a host-reaching service, scope its UFW rule to `bakeriq0`.

### Time zones

Everything runs in UTC inside the containers. Frontend date display uses `Intl.DateTimeFormat('en-IN', ...)`, which renders in the viewer's local zone. Storage is always UTC — never store local times.

### ngrok's free-tier interstitial

The first time any browser hits the ngrok hostname it gets an interstitial page with a "Visit Site" button. It can be skipped with an `ngrok-skip-browser-warning` header, but you can't set headers on a link tapped from WhatsApp — so a phone will always see one extra tap. Not fixable without a paid plan.

## When in doubt

- Look at existing code for the same resource. Customer / product / category / order all follow the same patterns — copy them.
- Read [`DECISIONS.md`](DECISIONS.md) before doing anything that seems to violate a convention. Most non-obvious choices have a documented reason.
- For scope and priority, see [`ROADMAP.md`](ROADMAP.md).
