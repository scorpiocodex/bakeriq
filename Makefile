# BakeriQ — Makefile
#
# Thin orchestration layer. Real work lives in scripts/, which can be
# read, edited, and run independently. Make handles target dispatch
# only.
#
# All targets are .PHONY because we don't produce output files —
# every target is just an action. .PHONY tells Make to always run
# the recipe, never check for a file of the same name.
#
# Conventions:
#   - One target per script, named to match: `make reset-db` -> scripts/reset-db.sh
#   - Default target is `help`, so bare `make` shows the menu
#   - All recipes are single-line `bash scripts/<name>.sh` calls so
#     Make doesn't add its own noise to the script's coloured output

.DEFAULT_GOAL := help

.PHONY: help
help:
	@bash scripts/help.sh

# === Dev stack ===============================================================

.PHONY: dev-up
dev-up:
	@bash scripts/dev-up.sh

# === Database ================================================================

.PHONY: reset-db
reset-db:
	@bash scripts/reset-db.sh

.PHONY: seed
seed:
	@bash scripts/seed.sh

.PHONY: migrate
migrate:
	@bash scripts/migrate.sh

.PHONY: migration
migration:
	@bash scripts/migration.sh

# === Tests ===================================================================

.PHONY: test
test:
	@bash scripts/test.sh

.PHONY: test-fast
test-fast:
	@bash scripts/test-fast.sh

# === Containers ==============================================================

.PHONY: ps
ps:
	@bash scripts/ps.sh

.PHONY: logs
logs:
	@bash scripts/logs.sh

.PHONY: shell-api
shell-api:
	@bash scripts/shell-api.sh

.PHONY: shell-db
shell-db:
	@bash scripts/shell-db.sh

# === WhatsApp / ngrok ========================================================

.PHONY: ngrok-check
ngrok-check:
	@bash scripts/ngrok-check.sh

.PHONY: templates-refresh
templates-refresh:
	@bash scripts/templates-refresh.sh

.PHONY: whatsapp-smoke
whatsapp-smoke:
	@bash scripts/whatsapp-smoke.sh
