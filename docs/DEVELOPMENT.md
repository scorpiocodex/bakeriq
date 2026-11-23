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

Both Vite servers declare a `base`, so the apps live under `/app/` and `/web/`. Bare `localhost:5173` and `localhost:5174` redirect there (a 302, checked on 23 November 2026), so either form works in a browser — but other paths, such as `localhost:5173/login`, are not served, and links and scripts should use the prefixed URLs.

Use the proxied URLs when you need the same request path a phone would take. Use the direct ones for normal work — hot reload doesn't survive the proxy, since HMR's WebSocket isn't forwarded.

**React Router handles the prefix; raw `window.location` does not.** Route paths are declared unprefixed and `BrowserRouter`'s `basename` resolves them. But three files navigate by assigning to `window.location` directly, and each has to spell `/app/login` out in full: the 401 interceptor in `api/client.js`, `context/AuthContext.jsx`, and `api/auth.js`. Add a fourth and it needs the prefix too, or an expired token will bounce the owner to an unserved origin root.

## Starting the stack

```bash
make dev-up
```

Brings up Docker, starts ngrok if it isn't running, and checks whether `PUBLIC_BASE_URL` in `.env` still matches the current tunnel; on a mismatch it runs `make templates-refresh`. This is the one command to run after a reboot or a long break. (What that recovery does and doesn't fix is spelled out under [The ngrok hostname problem](#the-ngrok-hostname-problem) — with a static ngrok domain you never hit it.)

```bash
make ps        # container status
make logs      # tail api logs
make help      # every available target
```

## Running tests

```bash
make test         # Full backend suite, verbose
make test-fast    # Same suite, stop at the first failure (-x)
```

Tests run inside the api container against the `db_test` database on port 5433. Your dev data on port 5432 is untouched. **396 tests, all passing** (run in the Docker stack on 23 November 2026, about 85 seconds). There is no coverage tooling configured.

To run a single test or module:

```bash
make shell-api
pytest tests/test_order_service.py
pytest tests/test_order_service.py::test_snapshot_survives_price_change
pytest -k "snapshot"
```

Tables are truncated between tests by the fixture in `conftest.py`. You should never need to manually wipe the test DB.

### Tests and real WhatsApp messages

`conftest.py` has an autouse fixture (`mute_outbound_notifications`) that stubs out `owner_notification_service.notify_new_registration` and `customer_notification_service.notify_approved`. Without it, the registration and approval endpoint tests fire **real** WhatsApp messages at the owner's phone and a customer's, against a sandbox quota of 50/day.

When you run the suite against a `.env` that holds real Twilio credentials and you want certainty that nothing can be sent, override them for the run: `docker compose exec -T -e TWILIO_ACCOUNT_SID=ACdummy -e TWILIO_AUTH_TOKEN=dummy api pytest tests/ -q`.

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

The seed script is `backend/scripts/seed_phase_2.py`. It creates the owner user, customers, categories, products, default-order templates and orders — the Phase 2 data set. It does **not** seed stock tracking (no product is stockable), conversations, registrations or tokens. If you need those, create them from the dashboard, by hand or via the bot.

The owner it creates has a fixed, published password (see the README), so the script refuses to run unless `ENVIRONMENT` is `development`, `dev`, `local` or `test`. A database that isn't seeded gets its first account from `docker compose exec -it api python -m scripts.create_owner --email you@example.com --name "Your Name"`; after that, a superuser adds accounts through `POST /api/v1/auth/register` (see [ADR-28](DECISIONS.md#adr-28--account-creation-is-superuser-only-and-the-first-owner-comes-from-a-script)).

## Working on the WhatsApp channel

### The ngrok hostname problem

The free ngrok tier can hand you a different hostname after a restart. When that happens, two things break at once: Twilio's webhook points at a dead host, and any Content Template with a baked-in URL (cart link, invoice link, owner notification) sends customers to a dead link.

```bash
make ngrok-check        # read-only: does PUBLIC_BASE_URL in .env match the live ngrok tunnel?
make templates-refresh  # run the template bootstrap, restart api + worker, re-run the check
```

Know what these do and don't do — read from the scripts, not exercised against a live Twilio account:

- `make ngrok-check` compares the live tunnel URL with `PUBLIC_BASE_URL` in `.env`. It never looks at the URLs stored on Twilio.
- `make templates-refresh` runs the bootstrap script, which **skips templates that already exist**, then restarts `api` and `worker` and repeats the check. It does not edit `.env`, does not delete anything on Twilio, and a plain `restart` does not re-read `.env`.
- `make dev-up` runs the check and, on a mismatch, runs `templates-refresh`.

So after the hostname actually changes, the working sequence is:

1. Put the new hostname in `PUBLIC_BASE_URL` in the root `.env`.
2. `docker compose up -d --force-recreate api worker`. The bootstrap runs *inside* the api container, which only sees the new `PUBLIC_BASE_URL` after it is recreated (the root `.env` reaches the container as environment variables fixed at creation).
3. Delete the stale link templates on Twilio (`bakeriq_cart_link`, `bakeriq_registration_link`, `bakeriq_owner_notification`, `bakeriq_invoice_link`) — see the delete snippet below.
4. `make templates-refresh` to recreate them. The new template IDs are written to `backend/.env`, and the target restarts `api` and `worker`, which re-read that file at startup.
5. Update Twilio's webhook URL by hand, in the Console under Messaging → Try it out → Sandbox settings.

Claiming a free static ngrok domain (see [`SETUP.md`](SETUP.md#3-authenticate-ngrok)) avoids all of this. VERIFY: the sequence above is reasoned from the scripts and should be confirmed the next time a hostname rotates.

### Content Templates

Nine templates live on Twilio (`bakeriq_greeting`, `_nav`, `_cart_link`, `_fallback`, `_order_confirmation`, `_registration_link`, `_owner_notification`, `_invoice_link`, `_approved`), created by:

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

Then re-run the bootstrap, which writes the new SID to `backend/.env`, and restart `api` and `worker` so it is read.

**Never rename a button title** without changing the matching constant in `customer_handler`. Twilio delivers the button's title as the inbound message body — a renamed button routes nowhere, silently.

### Smoke testing

```bash
make whatsapp-smoke
```

Sends one nav template to the phone in `SMOKE_TEST_PHONE`, confirming Twilio credentials, template SIDs, and the tunnel are all working. Asks for confirmation first, since it costs quota. **`SMOKE_TEST_PHONE` is required and has no default**: set it to your own number, for example `SMOKE_TEST_PHONE=+91XXXXXXXXXX make whatsapp-smoke`. Without it the script exits before sending anything. (Until 23 November 2026 it defaulted to the original maintainer's own number, which is why that number is still in the git history.) The variable is read by the script only; it is not in `.env.example`.

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

- Black-style formatting (88-char line limit); Ruff is the formatter and linter in the devcontainer, with isort-style import ordering
- Type hints on function signatures — return types especially
- Docstrings on services (not always on simple API handlers)

`black`, `isort`, `ruff` and `mypy` are installed from `requirements.txt`, but there is **no `pyproject.toml`, Ruff or mypy config, and no CI or pre-commit hook** — the conventions are applied by editor format-on-save and by habit, so they are not enforced.

How far the existing code is from them, measured on 23 November 2026 with the versions in the `api` image (ruff 0.17.6, black 24.10.0): `ruff check app tests scripts` reports 262 findings, `black --check` would reformat 10 files, and `isort --check-only` flags more than half of the files. Adding a `make lint` target today would therefore start red, and turning on enforcement means a one-off formatting pass over the codebase first. That pass hasn't been done. New code in the fix commits of that date is black-formatted.

### Frontend

- Prettier (single quotes, trailing commas, 100-char width), set in the devcontainer's VS Code settings
- ESLint — a config exists for the dashboard (`frontend/eslint.config.js`) but not the customer app, and neither `package.json` has a `lint` script
- Functional components only
- Hooks order: state, then derived values, then effects, then handlers, then render
- One default export per file; named exports for incidental utilities

VS Code with the included `.devcontainer/devcontainer.json` applies the formatter settings automatically. Nothing runs them in CI.

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

Services take `db: Session` first. Two commit conventions coexist in the code, split roughly by age (checked 23 November 2026):

- **The CRUD services commit themselves.** `category_service`, `customer_service`, `product_service`, `default_order_service` and `order_service` call `db.commit()` (and `db.refresh()`) at the end of each write, and their endpoints don't commit. `owner_notification_service` and `customer_notification_service` also commit, to persist the outbound-message log.
- **The newer building-block services flush and leave the commit to the caller.** `token_service`, `registration_token_service`, `pending_registration_service`, `conversation_log` and `inventory_service` call `db.flush()` — `web_link_service.issue_link` documents "caller is responsible for `db.commit()`" — and the endpoints that use them (`cart`, `register`, `approvals`, `inventory`, `auth`, `webhooks`) commit. This lets one request compose several operations into a single transaction.

When you add to an existing service, follow that service's convention; for a new building-block service prefer flush-and-let-the-caller-commit. Either way, the order-stock changes in `order_service` run inside the same transaction as the order write, so a failure rolls both back.

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
    """Soft-delete via is_active=False. We never DELETE because of order history FKs."""
    customer = get_customer(db, customer_id)
    if not customer.is_active:
        return customer  # idempotent
    customer.is_active = False
    db.commit()
    db.refresh(customer)
    return customer
```

Reactivation goes through the normal update endpoint with `{"is_active": true}` — there's no separate endpoint. The one other path is registration: approving a registration for a phone that belongs to a deactivated customer reactivates that customer instead of creating a duplicate.

**When adding an `is_active` check, add it everywhere.** `find_customer_by_phone` filtered on it and the registration endpoint's already-registered check didn't, which left deactivated customers routed to a form that then rejected them — a dead end with no way back in. That gap is fixed now, but it is the pattern to watch for.

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

The inventory page's prep list polls too, every 5 minutes, so a dashboard left open overnight notices the 05:00–21:00 visibility window without a manual reload.

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

There are two env files, and they behave differently:

- **The root `.env`** reaches the containers through Compose's `env_file`, as environment variables fixed when the container is *created*. `docker compose restart` keeps the old values, so a new or changed variable here (`PUBLIC_BASE_URL`, `OWNER_WHATSAPP_PHONE`, `BUSINESS_*`, …) needs:

  ```bash
  docker compose up -d --force-recreate api worker
  ```

- **`backend/.env`** (git-ignored; created by the template bootstrap, which writes the `CONTENT_SID_*` values there) is read by the app itself at process start, so a plain `restart` is enough. Checked on 23 November 2026: inside the container the `CONTENT_SID_*` values are not in the environment and `settings` still reads them from this file. A real environment variable wins over the file, so if you also put a `CONTENT_SID_*` in the root `.env`, that copy overrides the bootstrap's.

Symptom of getting this wrong: the config still reads the old value (or `None`) for a variable you can see in the file.

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
