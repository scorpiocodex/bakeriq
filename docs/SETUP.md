# BakeriQ setup

This walks you through bringing BakeriQ up from a fresh clone to a running WhatsApp bot on your phone.

It's written for someone who's never touched the project before. If you've done this once already and just need a reference, jump to the [Daily workflow](#daily-workflow) section at the end — everything else here is one-time.

Expect **60-90 minutes** end-to-end on your first pass, most of that waiting for Docker builds and the Ollama model download.

---

## What you'll end up with

- Docker Compose stack running seven containers (API, worker, two Postgres databases, Redis, two frontend dev servers)
- An Ollama LLM running on your host machine
- An ngrok tunnel exposing your local API to the public internet so Twilio can reach it
- WhatsApp Content Templates registered on your Twilio account
- The bakery dashboard at `http://localhost:5173`
- A working WhatsApp bot: send "hi" from your phone, get a greeting card with three tappable buttons back

---

## Prerequisites

**Operating system:** Debian 13, Ubuntu 22.04+, or another modern Linux. macOS should also work but hasn't been tested — a few of the host-side steps (systemd override for Ollama, UFW rules) are Linux-specific. Windows users should run under WSL2.

**Required software** (install these first if you don't have them):

- **Docker Engine + Docker Compose v2.** `docker --version` should print 24+ and `docker compose version` should print v2.20+.
- **Python 3.11+** on the host — only used for one setup helper (`secrets.token_urlsafe`); not the runtime.
- **Ollama.** [Install from ollama.com](https://ollama.com/download/linux). We deliberately run Ollama on the host, not in Docker — the 2GB model would need re-downloading on every `docker compose up`, and Ollama's install ships with its own systemd unit that plays well with GPU access.
- **`make`.** Standard on every Linux distro; verify with `make --version`.
- **`ngrok`.** [Install from ngrok.com](https://ngrok.com/download). Free tier is fine.

**Accounts you'll need:**

- **ngrok** account — sign up free at ngrok.com. You'll authenticate the CLI in a later step.
- **Twilio** account — sign up free at twilio.com. The WhatsApp Sandbox we use is included in every free account; no billing setup required. There's a 50-messages-per-day limit on the sandbox.

---

## 1. Clone and configure `.env`

```bash
git clone git@github.com:scorpiocodex/bakeriq.git
cd bakeriq
cp .env.example .env
```

Now edit `.env`. Most values work out of the box; five need real values:

**`SECRET_KEY`** — JWT signing secret. Generate one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the output as the value.

**`TWILIO_ACCOUNT_SID`** and **`TWILIO_AUTH_TOKEN`** — from the [Twilio Console home page](https://console.twilio.com). Both appear in the "Account Info" panel.

**`TWILIO_WHATSAPP_FROM`** — the default `whatsapp:+14155238886` is Twilio's shared sandbox sender and is correct for most people. Only change this if you've upgraded to a dedicated WhatsApp Business number.

**`PUBLIC_BASE_URL`** — leave as `http://localhost:8000` for now. We'll update it after starting ngrok in step 5.

---

## 2. Host-side one-time configuration

These are host-machine changes that live outside the repo. You do them once per dev machine. Skip any step whose target file already exists with the right content.

### 2a. Docker DNS

Container DNS breaks in a specific Linux + Docker + systemd-resolved combination — containers stop resolving external hostnames after `systemd-resolved` restarts. Pinning DNS servers in Docker's daemon config fixes it.

```bash
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "dns": ["8.8.8.8", "1.1.1.1"]
}
EOF
sudo systemctl restart docker
```

If the file already exists with other settings, merge the `dns` key rather than overwriting.

### 2b. Ollama listens on all interfaces

Ollama defaults to binding `127.0.0.1:11434` — only reachable from the host itself. Our containers reach Ollama via the Docker bridge, so we need it on `0.0.0.0`.

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Verify:

```bash
sudo ss -tlnp | grep 11434
# Should show *:11434 or 0.0.0.0:11434, not 127.0.0.1:11434
```

### 2c. Firewall (only if UFW is active)

Check whether UFW is running:

```bash
sudo ufw status
```

If it says `Status: inactive`, skip this step. If active, containers on the `bakeriq0` bridge need explicit permission to reach Ollama on the host:

```bash
sudo ufw allow in on bakeriq0 to any port 11434 proto tcp comment 'Ollama from bakeriq containers'
sudo ufw allow in on docker0 to any port 11434 proto tcp comment 'Ollama from default docker containers'
sudo ufw reload
```

The `bakeriq0` interface won't exist until you've run `docker compose up` at least once (step 4), but adding the rule now is fine — it will apply as soon as the interface appears.

### 2d. Pull the Ollama model

```bash
ollama pull llama3.2:3b
```

This downloads about 2GB. Takes 5-15 minutes depending on your connection. Verify:

```bash
curl -s http://localhost:11434/api/tags
# Should print JSON listing llama3.2:3b
```

---

## 3. Authenticate ngrok

If this is your first time using ngrok on this machine, get an authtoken from your [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken) and register it:

```bash
ngrok config add-authtoken <YOUR_AUTHTOKEN>
```

Then configure a tunnel for the API. Open `~/.config/ngrok/ngrok.yml` and add or update the `tunnels` section:

```yaml
version: "3"
agent:
  authtoken: <YOUR_AUTHTOKEN>
tunnels:
  api:
    proto: http
    addr: 8000
```

**Optional but recommended:** claim a free static hostname from your ngrok dashboard (Cloud Edge → Domains → Create Domain). It'll look like `some-words-here.ngrok-free.dev`. Add `domain: some-words-here.ngrok-free.dev` under `api:` in the config. Without this, ngrok gives you a fresh random hostname each session, which means re-bootstrapping the cart-link WhatsApp template every time.

---

## 4. First stack bring-up

```bash
docker compose up -d
```

First time this runs it builds four images (~5-10 min). Subsequent runs use the cache and take a few seconds.

Wait for everything to be healthy:

```bash
make ps
```

All seven containers should show status `Up ... (healthy)` or plain `Up`. If any show `unhealthy` or keep restarting, check `make logs`.

Now initialize the database with a schema, admin user, and seed data:

```bash
make reset-db
```

This prompts for confirmation, then drops the schema, re-runs all migrations, and seeds an owner user plus sample customers, categories, products, and default orders.

**Log in to verify:**

Visit `http://localhost:5173` and log in with:

- Email: `owner@bakeriq.com`
- Password: `bakeriqowner`

You should see the dashboard with today's overview cards and seeded orders.

---

## 5. Start ngrok, update `.env`

```bash
ngrok start api &
```

The `&` backgrounds the process so you can keep using the terminal. If you configured a static domain in step 3, it'll appear on the ngrok status page immediately. Otherwise, find the assigned hostname:

```bash
make ngrok-check
```

This prints the current tunnel URL. Copy it (looks like `https://something-something.ngrok-free.dev`) and paste it into `.env` as the value of `PUBLIC_BASE_URL`, replacing `http://localhost:8000`.

Also configure Twilio to send incoming WhatsApp messages to this URL. In the [Twilio Console](https://console.twilio.com):

1. Go to **Messaging → Try it out → Send a WhatsApp message → Sandbox settings**
2. Set **"When a message comes in"** to `<your-ngrok-url>/api/v1/webhooks/twilio`
3. Method: `POST`
4. Save

Restart api and worker so they pick up the new `PUBLIC_BASE_URL`:

```bash
docker compose restart api worker
```

---

## 6. Bootstrap WhatsApp Content Templates

BakeriQ uses four Twilio Content Templates for interactive button UX (greeting card, mid-conversation nav, cart-link CTA, fallback with menu). These live on the Twilio side and are referenced by SID from `.env`. A helper script creates them idempotently:

```bash
docker compose exec api python scripts/bootstrap_content_templates.py
```

This creates four templates on your Twilio account, writes the resulting `CONTENT_SID_*` values to `.env`, and prints what it did. Safe to re-run — existing templates aren't recreated, only missing ones.

Restart api and worker so pydantic-settings re-reads `.env`:

```bash
docker compose restart api worker
```

**Shortcut:** you can also do steps 5 + 6 together with `make dev-up`, which starts ngrok if it isn't running and auto-refreshes templates if the ngrok hostname has drifted from what's baked in `.env`.

---

## 7. Join the Twilio sandbox from your phone

Twilio's WhatsApp Sandbox requires each phone that wants to test to send a one-time join code to Twilio's WhatsApp number.

In the [Twilio Console](https://console.twilio.com):

1. Go to **Messaging → Try it out → Send a WhatsApp message → Sandbox settings**
2. Find your unique join phrase — looks like `join example-word`
3. From your phone's WhatsApp, message `+1 415 523 8886` (Twilio's sandbox number) with that exact phrase

You'll get a confirmation from Twilio. Now every subsequent message from this phone will go through your ngrok tunnel to your local API.

---

## 8. Verify end-to-end

The smoke helper sends one WhatsApp message to a configured phone to verify Twilio + Content Templates + ngrok are all wired up:

```bash
SMOKE_TEST_PHONE=+91XXXXXXXXXX make whatsapp-smoke
```

Replace `+91XXXXXXXXXX` with the phone that joined the sandbox in step 7. The script asks for confirmation (costs 1 message of your daily 50), then sends the nav-card template. Within 5 seconds you should see on your phone:

> **What would you like to do next?**
> [Reorder last] [New order] [Order status]

Tap any button. The bot should reply appropriately — status pulls up your latest order, new order sends a cart link, reorder shows your last cart items.

If the message arrives with three tappable buttons and the buttons work, **BakeriQ is fully set up.**

---

## Troubleshooting

### Container can't reach Ollama

Symptom: worker logs show `httpx.ConnectError`, `httpx.ConnectTimeout`, or `Failed to resolve host` when trying to call the LLM.

Check in order:

1. Is Ollama running? `sudo systemctl status ollama` — should be active.
2. Is it on all interfaces? `sudo ss -tlnp | grep 11434` — must show `*:11434` or `0.0.0.0:11434`, not `127.0.0.1:11434`. If wrong, re-do step 2b.
3. Can the container reach it? `docker compose exec api curl -sS --max-time 5 http://172.17.0.1:11434/api/tags` — should return the model list JSON.
4. If curl times out (not "refused"), the firewall is blocking. Re-do step 2c.

### ngrok webhook returns 502

Symptom: Twilio Console shows delivery attempts with a 502 error, or WhatsApp messages don't get bot responses.

Usually means the ngrok hostname changed and Twilio is now pointing at a dead tunnel. Fix:

```bash
make ngrok-check
```

If it reports drift, update Twilio's webhook URL to the new hostname (step 5). If ngrok isn't running at all, `make dev-up` starts it and auto-recovers.

### "Open cart" button leads to a 404

Symptom: WhatsApp cart-link buttons open the browser but hit a "Link no longer valid" page or 404.

The cart-link Content Template has a baked-in URL that's now stale. Fix:

```bash
make templates-refresh
```

This re-runs the bootstrap script, which recreates the cart-link template with the current `PUBLIC_BASE_URL`.

### Twilio quota exceeded (code 63038)

Symptom: worker logs show `Unable to create record: Account ... exceeded the 50 daily messages limit`.

The Twilio Sandbox has a 50-messages-per-day limit. Resets rolling per-message over ~24 hours. Options:

- Wait and pick up tomorrow.
- Upgrade to a paid Twilio WhatsApp Business number (removes the cap).

### Tests fail with DNS resolution errors

Symptom: pytest output includes `NameResolutionError` or `Temporary failure in name resolution`.

Container DNS is broken. Re-do step 2a and restart Docker:

```bash
sudo systemctl restart docker
docker compose up -d
```

### `make dev-up` says "ngrok started but no tunnel detected after 10s"

Check the log:

```bash
tail /tmp/ngrok-bakeriq.log
```

Common causes: expired ngrok authtoken (re-authenticate per step 3), or your account hit the simultaneous-session cap (kill other ngrok processes with `pkill -f ngrok`).

### Devcontainer rebuild fails with "network bakeriq_default not found"

The VS Code Dev Containers extension may cache the old network name. Solution: reopen the folder locally (not in devcontainer), then rebuild the devcontainer. It picks up the current `bakeriq` network name.

---

## Daily workflow

Once setup is complete, the day-to-day is short:

```bash
make dev-up    # brings docker + ngrok up; auto-recovers template URLs if ngrok rotated
make test      # runs the full test suite
make logs      # tails api logs
make help      # lists all available commands
```

For anything not covered by `make help`, see [DEVELOPMENT.md](DEVELOPMENT.md).

---

## Where things live

- **Application code:** `backend/app/` (FastAPI) and `frontend/` + `frontend-customer/` (React)
- **Tests:** `backend/tests/`
- **Migrations:** `backend/alembic/versions/`
- **Content Template bootstrap:** `backend/scripts/bootstrap_content_templates.py`
- **Dev workflow scripts:** `scripts/` (wrapped by `Makefile` targets)
- **Design docs:** `docs/`

---

## Support

Something not working after following these steps? [Open an issue](https://github.com/scorpiocodex/bakeriq/issues) with:

- The step you're stuck on
- The exact command you ran
- The full error output
- `docker compose ps` and `docker compose logs --tail=50 api worker`
