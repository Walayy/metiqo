.DEFAULT_GOAL := help

PYTHON_PATHS := python services infra tests
OE_TARGETS := oe-catalog oe-backfill oe-sync oe-sync-current oe-validate oe-diff oe-rebuild-canonical
OE_JSON_FLAG = $(if $(filter 1 true yes,$(JSON)),--json,)
OE_FIXTURE_FLAG = $(if $(strip $(FIXTURE)),--fixture $(FIXTURE),)

.PHONY: help up down db-migrate docker-build mock-seed mock-demo format lint typecheck test test-migrations test-e2e openapi openapi-check check $(OE_TARGETS)

help:
	@echo "Metiquo - commandes développeur"
	@echo "  make up             Démarre la stack locale mock"
	@echo "  make down           Arrête la stack locale"
	@echo "  make db-migrate     Applique les migrations dans la stack"
	@echo "  make docker-build   Valide et construit les images Compose"
	@echo "  make mock-seed      Vérifie les 12 scénarios de la graine mock"
	@echo "  make mock-demo      Prépare et démarre la démo mock complète"
	@echo "  make format         Formate les sources"
	@echo "  make lint           Vérifie format, lint et orthographe"
	@echo "  make typecheck      Vérifie les types TypeScript et Python"
	@echo "  make test           Exécute les tests frontend et Python"
	@echo "  make test-migrations Exécute les tests sur PostgreSQL réel"
	@echo "  make test-e2e       Exécute les tests Playwright"
	@echo "  make openapi        Régénère le contrat OpenAPI"
	@echo "  make oe-catalog     Rafraîchit le catalogue Oracle's Elixir"
	@echo "  make oe-backfill FROM=2014 TO=2026 [FIXTURE=...]"
	@echo "  make oe-sync YEAR=2026 [ALLOW_STALE=1|REQUIRE_FRESH=1]"
	@echo "  make oe-sync-current [REQUIRE_FRESH=1]"
	@echo "  make oe-validate SNAPSHOT=<uuid>"
	@echo "  make oe-diff LEFT=<uuid> RIGHT=<uuid>"
	@echo "  make oe-rebuild-canonical FROM=2025-01-01"

up:
	docker compose --profile mock run --rm --no-deps --build mock-mode-check
	docker compose --profile mock up -d --build --wait --wait-timeout 120 postgres api worker web

down:
	docker compose --profile "*" down --remove-orphans

db-migrate:
	docker compose exec -T api alembic upgrade head

docker-build:
	docker compose config --quiet
	docker compose --profile mock build

mock-seed:
	uv run --frozen python infra/scripts/seed_mock_demo.py --check

mock-demo:
	$(MAKE) mock-seed
	$(MAKE) up
	$(MAKE) db-migrate
	@echo "Démo mock prête : http://127.0.0.1:3000"

format:
	pnpm run format
	uv run --frozen ruff format $(PYTHON_PATHS)

lint:
	pnpm run format:check
	pnpm run lint
	pnpm run spellcheck
	uv run --frozen ruff format --check $(PYTHON_PATHS)
	uv run --frozen ruff check $(PYTHON_PATHS)

typecheck:
	pnpm run typecheck
	uv run --frozen mypy

test:
	pnpm run test:components
	uv run --frozen pytest

test-migrations:
	$(if $(strip $(TEST_DATABASE_URL)),,$(error TEST_DATABASE_URL est requis pour les tests de migration))
	uv run --frozen pytest tests/integration -vv

test-e2e:
	pnpm run test:e2e

openapi:
	uv run --frozen python infra/scripts/export_openapi.py
	pnpm run contracts:generate

openapi-check:
	uv run --frozen python infra/scripts/export_openapi.py --check
	pnpm run contracts:check

check: lint typecheck test openapi-check

oe-catalog:
	uv run --frozen oe catalog refresh $(OE_JSON_FLAG)

oe-backfill:
	$(if $(strip $(FROM)),,$(error FROM est requis, par exemple FROM=2014))
	$(if $(strip $(TO)),,$(error TO est requis, par exemple TO=2026))
	uv run --frozen oe backfill --from-year $(FROM) --to-year $(TO) $(OE_FIXTURE_FLAG) $(OE_JSON_FLAG)

oe-sync:
	$(if $(strip $(YEAR)),,$(error YEAR est requis, par exemple YEAR=2026))
	$(if $(and $(filter 1 true yes,$(ALLOW_STALE)),$(filter 1 true yes,$(REQUIRE_FRESH))),$(error ALLOW_STALE et REQUIRE_FRESH sont incompatibles),)
	uv run --frozen oe sync --year $(YEAR) $(if $(filter 1 true yes,$(ALLOW_STALE)),--allow-stale,) $(if $(filter 1 true yes,$(REQUIRE_FRESH)),--require-fresh,) $(OE_FIXTURE_FLAG) $(OE_JSON_FLAG)

oe-sync-current:
	$(if $(and $(filter 1 true yes,$(ALLOW_STALE)),$(filter 1 true yes,$(REQUIRE_FRESH))),$(error ALLOW_STALE et REQUIRE_FRESH sont incompatibles),)
	uv run --frozen oe sync $(if $(filter 1 true yes,$(ALLOW_STALE)),--allow-stale,) $(if $(filter 1 true yes,$(REQUIRE_FRESH)),--require-fresh,) $(OE_FIXTURE_FLAG) $(OE_JSON_FLAG)

oe-validate:
	$(if $(strip $(SNAPSHOT)),,$(error SNAPSHOT est requis))
	uv run --frozen oe verify --snapshot $(SNAPSHOT) $(OE_JSON_FLAG)

oe-diff:
	$(if $(strip $(LEFT)),,$(error LEFT est requis))
	$(if $(strip $(RIGHT)),,$(error RIGHT est requis))
	uv run --frozen oe diff --left $(LEFT) --right $(RIGHT) $(OE_JSON_FLAG)

oe-rebuild-canonical:
	$(if $(strip $(FROM)),,$(error FROM est requis, par exemple FROM=2025-01-01))
	uv run --frozen oe rebuild-canonical --from $(FROM) $(OE_JSON_FLAG)
