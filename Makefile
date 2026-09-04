.DEFAULT_GOAL := help

PYTHON_PATHS := python services infra tests
OE_TARGETS := oe-catalog oe-backfill oe-sync oe-sync-current oe-validate oe-diff oe-rebuild-canonical

.PHONY: help up down db-migrate docker-build format lint typecheck test test-migrations test-e2e openapi openapi-check check $(OE_TARGETS)

help:
	@echo "Metiquo - commandes développeur"
	@echo "  make up             Démarre la stack locale mock"
	@echo "  make down           Arrête la stack locale"
	@echo "  make db-migrate     Applique les migrations dans la stack"
	@echo "  make docker-build   Valide et construit les images Compose"
	@echo "  make format         Formate les sources"
	@echo "  make lint           Vérifie format, lint et orthographe"
	@echo "  make typecheck      Vérifie les types TypeScript et Python"
	@echo "  make test           Exécute les tests Python"
	@echo "  make test-migrations Exécute les tests sur PostgreSQL réel"
	@echo "  make test-e2e       Exécute les tests Playwright"
	@echo "  make openapi        Régénère le contrat OpenAPI"

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
	uv run --frozen pytest

test-migrations:
	$(if $(strip $(TEST_DATABASE_URL)),,$(error TEST_DATABASE_URL est requis pour les tests de migration))
	uv run --frozen pytest tests/integration/test_migrations.py -vv

test-e2e:
	pnpm run test:e2e

openapi:
	uv run --frozen python infra/scripts/export_openapi.py

openapi-check: openapi
	git diff --exit-code -- packages/contracts/openapi/v1.json

check: lint typecheck test openapi-check

$(OE_TARGETS):
	@echo "ERREUR : la cible '$@' est réservée et sera implémentée par son ticket Oracle's Elixir." 1>&2
	@exit 2
