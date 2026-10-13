SHELL := /bin/sh
COMPOSE_FILES ?= -f infra/compose.yaml -f infra/compose.local.yaml
COMPOSE := docker compose --env-file .env $(COMPOSE_FILES)
export UV_CACHE_DIR := $(CURDIR)/.cache/uv

.PHONY: setup dev down logs seed seed-smoke migrate lint typecheck test test-integration test-web worker-smoke contracts contracts-check compose-check verify
setup:
	uv sync
	npm install --no-audit --no-fund
	npx playwright install chromium

dev:
	@test -f .env || (echo 'Copy .env.example to .env first.'; exit 1)
	$(COMPOSE) up --build --wait --wait-timeout 180

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs --tail=100

migrate:
	$(COMPOSE) run --rm bootstrap uv run --no-sync alembic upgrade head

seed:
	$(COMPOSE) run --rm bootstrap uv run --no-sync python -m app.db.seed

seed-smoke:
	$(COMPOSE) run --rm bootstrap uv run --no-sync python -m app.db.seed --count 10

lint:
	uv run --frozen ruff check apps tests scripts
	uv run --frozen ruff format --check apps tests scripts
	npm run lint
	node --test tests/contracts.test.mjs

typecheck:
	uv run --frozen mypy
	npm run typecheck

test:
	uv run --frozen pytest tests/unit
	node --test tests/contracts.test.mjs

test-integration:
	$(COMPOSE) --profile checks run --rm checks

worker-smoke:
	$(COMPOSE) exec worker uv run --no-sync python scripts/worker_smoke.py

contracts:
	npm run contracts

contracts-check:
	npm run contracts:check

compose-check:
	docker compose --env-file .env.example -f infra/compose.yaml config --quiet
	docker compose --env-file .env.example -f infra/compose.yaml -f infra/compose.local.yaml config --quiet

test-web:
	npm run test:web

verify: lint typecheck test contracts-check compose-check
	$(MAKE) dev
	$(MAKE) test-integration
	$(MAKE) worker-smoke
	$(MAKE) test-web
	npm run build
