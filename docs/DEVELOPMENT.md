# Development

Day-to-day workflow notes — how to actually work in this codebase. Read [`ARCHITECTURE.md`](ARCHITECTURE.md) first for the bigger picture.

## Where work happens

Almost everything runs inside containers. Open a shell into the api container for backend work:

```bash
make shell-api
```

You'll land at `/app` (the backend root) as the `app` user. Python venv is global to the container, packages are pre-installed, and the working dir is bind-mounted from your host so edits in your editor are visible immediately.

For frontend work, edits to files under `frontend/src/` are picked up by Vite's hot reload — no container shell needed. If you do need one (e.g., to add a dependency):

```bash
docker compose exec frontend sh
```

## Running tests

```bash
make test         # Full backend suite with coverage
make test-fast    # Same suite, no coverage
```

Tests run inside the api container against the `db_test` database on port 5433. Your dev data on port 5432 is untouched.

To run a single test or a single module:

```bash
make shell-api
pytest tests/test_order_service.py
pytest tests/test_order_service.py::test_snapshot_survives_price_change
pytest -k "snapshot"
```

If a test relies on the test database being clean, transactions are rolled back between tests automatically via the fixture in `conftest.py`. You should never need to manually wipe the test DB.

## Creating migrations

After changing a SQLAlchemy model:

```bash
make migration
# Prompts for a migration message
```

This generates a new file under `backend/alembic/versions/`. **Open it and inspect it before committing.** Alembic autogenerate is good but not perfect.

### Recurring Alembic quirk — read this every time

Every migration touching the `customers` table will spuriously include four lines trying to convert the `ix_customers_secondary_phone` unique index from one Alembic representation to another:

```python
# In upgrade():
op.drop_index('ix_customers_secondary_phone', table_name='customers')
op.create_index(op.f('ix_customers_secondary_phone'), 'customers', ['secondary_phone'], unique=True)

# In downgrade():
op.drop_index(op.f('ix_customers_secondary_phone'), table_name='customers')
op.create_index('ix_customers_secondary_phone', 'customers', ['secondary_phone'], unique=True)
```

**Delete all four lines from every new migration.** They're a no-op, but if left in they slow down migrations and clutter history.

### Native Postgres enums

Migrations that create native Postgres enums (currently just `order_status`) need an explicit drop in the downgrade. Autogenerate sometimes misses this. The pattern is:

```python
def downgrade():
    # ... other downgrade operations ...
    sa.Enum(name='order_status').drop(op.get_bind())
```

If you're adding a new enum, follow the same pattern.

### Applying migrations

```bash
make migrate
```

Applies all pending migrations against the dev database. The test database gets migrations applied automatically when the test suite runs.

## Resetting the database

```bash
make reset-db
```

Drops, recreates, migrates, and seeds the dev database. Wipes everything. Useful when:

- You've made a destructive schema change and just want a clean slate
- The seed data has changed and you want the new version
- You've manually edited data while debugging and want to get back to a known state

The seed script lives at `backend/scripts/seed_phase_2.py` (despite the name it currently covers everything through Phase 2 — it'll get renamed when Phase 3 adds bot-related seed data).

## Adding a new endpoint

The mechanical sequence:

1. **Add or modify the model** — `backend/app/models/<resource>.py`
2. **Generate a migration** — `make migration`, then clean it up (see the Alembic quirk above), then `make migrate`
3. **Add or update Pydantic schemas** — `backend/app/schemas/<resource>.py`
4. **Add the service function** — `backend/app/services/<resource>_service.py`. Pure business logic, no HTTP concerns. Takes `db: Session` as first arg.
5. **Add tests for the service** — `backend/tests/test_<resource>_service.py`. Aim for ~3-5 tests covering happy path + 1-2 edge cases.
6. **Add the API route** — `backend/app/api/v1/<resource>.py`. Thin — call the service, translate exceptions to `HTTPException`.
7. **Register the route** if it's a new file — add to `backend/app/api/v1/router.py`

Then on the frontend:

8. **Add the axios call** — `frontend/src/api/<resource>.js`
9. **Add the TanStack Query hook** — `frontend/src/hooks/use<Resource>.js`. Pay attention to query keys for cache invalidation.
10. **Use the hook in the page** — `frontend/src/pages/<Page>.jsx`

This is a lot for any single change, but each step is small and the layering pays for itself when something breaks.

## Adding a frontend page

If the new page is a new route:

1. Create `frontend/src/pages/<NewPage>.jsx`
2. Add the route in `frontend/src/App.jsx` (or wherever the router is configured)
3. Add a sidebar entry in `frontend/src/components/Sidebar.jsx` — pick a distinct lucide icon (do NOT duplicate an existing one — see [Sidebar icon collision](#sidebar-icon-collisions))
4. Add a `ROUTE_SUBTITLES` entry in `frontend/src/components/TopBar.jsx` so the top bar shows the right subtitle on that page

## Sidebar icon collisions

The sidebar uses lucide icons. **Each page must use a distinct icon.** Easy to break — there are lots of box-shaped icons in lucide. Current assignments (don't reuse these):

| Page | Icon |
|---|---|
| Dashboard | `LayoutDashboard` |
| Orders | `ShoppingCart` |
| Customers | `Users` |
| Products | `ShoppingBag` |
| Inventory | `Boxes` |
| Billing | `Receipt` |
| Settings | `Settings` |

If you add a new page, pick something visually distinct. Don't pick `Package` (too close to `Boxes`) or `Tag` (too close to category iconography).

## Commit conventions

Conventional Commits — every commit message starts with a type:

| Type | When |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code change without behaviour change |
| `docs` | Documentation only |
| `test` | Test additions / changes |
| `chore` | Build, deps, config, ci |

Subject line: present tense, no period, lowercase after the colon. Examples from the actual history:

- `feat(phase-2): orders backend - Task 4 Milestone A`
- `feat(ui): polish pass + devcontainer setup`
- `fix(layout): pin sidebar to viewport height`

For substantial commits, write a body explaining *what* and *why* — the diff already shows *how*. Look at the existing `git log` for examples of the level of detail we're aiming for.

## Branching

`main` is the deployable branch. Feature work happens on feature branches, named with a phase or task prefix:

- `phase-2-orders` for a Phase 2 task
- `phase-3-whatsapp-bot` for the upcoming WhatsApp work
- `fix-popover-clipping` for a focused bug fix
- `ui-polish-pass` for cosmetic improvements

Merge to `main` via `git merge --no-ff` for substantial branches (keeps the branch shape visible in history) or fast-forward for trivial single-commit fixes.

## Git identity

Pushes are rejected (`GH007`) if the committer email isn't the GitHub-noreply form. Configure once per clone:

```bash
git config user.name "scorpiocodex"
git config user.email "212041449+scorpiocodex@users.noreply.github.com"
```

Otherwise GitHub will block the push as a privacy violation.

## Code style

### Backend

- Black formatting (88-char line limit), enforced by Ruff
- Ruff for linting
- Imports sorted by isort (handled inside Ruff config)
- Type hints on function signatures — return types especially
- Docstrings on services (not always on simple API handlers)

### Frontend

- Prettier formatting (single quotes, trailing commas, 100-char width)
- ESLint with the React plugin
- Functional components only — no class components
- Hooks order: state hooks first, then derived values, then effects, then handlers, then render
- One default export per file; named exports for incidental utilities

VS Code with the included `.devcontainer/devcontainer.json` configures both automatically.

## Service patterns

### SQLAlchemy session

Services take `db: Session` and `db.flush()` rather than `db.commit()`. The endpoint commits at the end of a successful request via the `get_db` dependency. This means a service can compose multiple operations into one transaction without each one auto-committing.

```python
def create_order(db: Session, data: OrderCreate) -> Order:
    order = Order(...)
    db.add(order)
    db.flush()  # ← flushes to DB, gets the order ID, but doesn't commit
    for item_data in data.items:
        item = OrderItem(order_id=order.id, ...)
        db.add(item)
    db.flush()
    return order
```

### Parent-child relationships

Services that handle parent-child entities (orders + items, default_orders + items) use:

- `cascade="all, delete-orphan"` on the parent's `relationship()`
- `lazy="selectin"` for collections (issues a single follow-up query rather than N+1)
- `lazy="joined"` for to-one relationships (`Order.customer`)

To replace all children on an update, reassign the list:

```python
order.items = [OrderItem(...) for item_data in data.items]
db.flush()
```

The cascade handles deleting old items and inserting new ones.

### Soft deactivation

For customer / product / category deactivation:

```python
# Service
def deactivate_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise NotFoundError(...)
    customer.is_active = False
    db.flush()
    return customer
```

Reactivation goes through the normal update endpoint with `{"is_active": true}` — there's no separate `reactivate` endpoint.

## Frontend patterns

### TanStack Query keys

Use array keys with the resource name first, then identifying parameters:

```js
['customers', 'list', filters]
['customers', 'detail', id]
['orders', 'list', filters]
['orders', 'detail', id]
['dashboard', 'summary']
```

This lets us invalidate broadly (`['customers']` invalidates everything customer-related) or narrowly (`['customers', 'detail', 7]` invalidates one customer).

### Mutation cache invalidation

After a successful mutation, invalidate the relevant queries:

```js
const queryClient = useQueryClient();

useMutation({
  mutationFn: (data) => api.createCustomer(data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['customers'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  },
});
```

The dashboard summary depends on customer/product/order counts, so most mutations also invalidate it.

### Form modals

Form modals are controlled components — they receive `open`, `onClose`, and optionally a record to edit. State is local to the modal. On submit, they call a mutation hook and close themselves on success.

## What to check before a PR / merge

- [ ] All tests pass: `make test`
- [ ] Migrations are reviewed and cleaned (Alembic customer-index quirk)
- [ ] New endpoints have at least 2-3 service tests
- [ ] Frontend builds without warnings: `docker compose exec frontend npm run build`
- [ ] No `console.log`, `print`, or commented-out blocks left behind
- [ ] Commit messages follow Conventional Commits

## Common gotchas

### Async / await on endpoints

FastAPI endpoints can be `async def` or plain `def`. SQLAlchemy 2.0 sync sessions don't play nicely with `async def` unless you use the async engine. **All endpoints in this project are plain `def`** — don't switch one to `async def` without converting the database session to async too.

### Pydantic v2 model_config

Schemas use Pydantic v2 syntax:

```python
class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ...
```

Not `class Config:` — that's v1.

### docker-compose vs docker compose

The project uses Docker Compose v2 (`docker compose`, no hyphen). If your install is older (`docker-compose` with hyphen), update Docker.

### Frontend Vite cache

Occasionally Vite caches a stale build. Symptoms: fresh code, browser shows old behaviour. Fix: hard reload (Ctrl/Cmd + Shift + R), or `docker compose restart frontend`.

### Time zones

Everything runs in UTC inside the containers. Date display in the frontend uses `Intl.DateTimeFormat('en-IN', ...)` which renders in the user's local zone (IST for the team). Date *storage* is always UTC in Postgres — never store local times.

## When in doubt

- Look at existing code for the same resource. Customer / product / category / order all follow the same patterns — copy them.
- Read [`DECISIONS.md`](DECISIONS.md) before doing anything that seems to violate a convention. Most non-obvious choices have a documented reason.
- For uncertainty about scope or priority, see [`ROADMAP.md`](ROADMAP.md).
