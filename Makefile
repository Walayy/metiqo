.DEFAULT_GOAL := help

PYTHON_PATHS := python services infra tests
OE_TARGETS := oe-catalog oe-backfill oe-sync oe-sync-current oe-validate oe-diff oe-rebuild-canonical features-rebuild model-train
INGESTION_INTEGRATION_TESTS := tests/integration/test_backfill.py tests/integration/test_catalog_repository.py tests/integration/test_ingestion_gate.py tests/integration/test_migrations.py tests/integration/test_oe_cli.py tests/integration/test_quarantine.py tests/integration/test_raw_loader.py tests/integration/test_raw_migration.py tests/integration/test_snapshot_promotion.py
OE_JSON_FLAG = $(if $(filter 1 true yes,$(JSON)),--json,)
OE_FIXTURE_FLAG = $(if $(strip $(FIXTURE)),--fixture $(FIXTURE),)

.PHONY: help up down db-migrate docker-build mock-seed mock-demo format lint typecheck test test-leakage test-migrations test-ingestion test-e2e openapi openapi-check check backup $(OE_TARGETS)

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
	@echo "  make test-leakage   Exécute la suite anti-fuite bloquante"
	@echo "  make test-migrations Exécute les tests sur PostgreSQL réel"
	@echo "  make test-ingestion Valide le gate Oracle's Elixir sur PostgreSQL réel"
	@echo "  make test-e2e       Exécute les tests Playwright"
	@echo "  make openapi        Régénère le contrat OpenAPI"
	@echo "  make oe-catalog     Rafraîchit le catalogue Oracle's Elixir"
	@echo "  make oe-backfill FROM=2014 TO=2026 [FIXTURE=...]"
	@echo "  make oe-sync YEAR=2026 [ALLOW_STALE=1|REQUIRE_FRESH=1]"
	@echo "  make oe-sync-current [REQUIRE_FRESH=1]"
	@echo "  make oe-validate SNAPSHOT=<uuid>"
	@echo "  make oe-diff LEFT=<uuid> RIGHT=<uuid>"
	@echo "  make oe-rebuild-canonical FROM=2025-01-01"
	@echo "  make features-rebuild FROM=2025-01-01 [CODE_COMMIT=<hash>]"
	@echo "  make model-train MARKET=game_winner [DATASET=<uuid>] [CODE_COMMIT=<hash>]"
	@echo "  make backup JSON=1  Sauvegarde DB, raw, modèles et quarantaine en mode réel"
	@echo "  make release-check AUDIENCE=personal|public|commercial Vérifie les portes de publication"

up: docker-build
	docker compose --profile mock run --rm --no-deps mock-mode-check
	docker compose --profile mock up -d --wait --wait-timeout 120 postgres api worker web

down:
	docker compose --profile "*" down --remove-orphans

db-migrate:
	docker compose exec -T api alembic upgrade head

docker-build:
	uv run --frozen python infra/scripts/build_images.py

mock-seed:
	uv run --frozen python infra/scripts/seed_mock_demo.py --check

mock-demo:
	$(MAKE) mock-seed
	$(MAKE) up
	$(MAKE) db-migrate
	@echo "Démo mock prête : ouvrir APP_PUBLIC_ORIGIN (défaut http://localhost:3000)"

format:
	pnpm run format
	uv run --frozen ruff format $(PYTHON_PATHS)

lint:
	pnpm run format:check
	pnpm run lint
	pnpm run spellcheck
	uv run --frozen ruff format --check $(PYTHON_PATHS)
	uv run --frozen ruff check $(PYTHON_PATHS)
	uv run --frozen python infra/scripts/check_provider_compliance.py

typecheck:
	pnpm run typecheck
	uv run --frozen mypy

test:
	pnpm run test:components
	uv run --frozen python -m pytest

test-leakage:
	uv run --frozen python -m pytest tests/leakage tests/model/test_rating_features.py tests/model/test_champion_meta_features.py tests/model/test_prior_missingness_features.py -vv

test-migrations:
	$(if $(strip $(TEST_DATABASE_URL)),,$(error TEST_DATABASE_URL est requis pour les tests de migration))
	uv run --frozen python -m pytest tests/integration -vv

test-ingestion:
	$(if $(strip $(TEST_DATABASE_URL)),,$(error TEST_DATABASE_URL est requis pour le gate ingestion))
	uv run --frozen python -m pytest tests/ingestion $(INGESTION_INTEGRATION_TESTS) -vv

.PHONY: test-value value-evaluate test-paper paper-settle paper-report paper-gate
.PHONY: backup
.PHONY: scan-secrets
.PHONY: scan-security
.PHONY: test-ops
.PHONY: benchmark-reads
.PHONY: release-check
release-check:
	$(if $(strip $(AUDIENCE)),,$(error AUDIENCE=personal|public|commercial est requis))
	uv run --frozen python -m infra.scripts.check_release --audience $(AUDIENCE)

benchmark-reads:
	$(if $(strip $(TEST_DATABASE_URL)),,$(error TEST_DATABASE_URL est requis pour créer la base de benchmark jetable))
	uv run --frozen python -m infra.scripts.benchmark_reads

test-ops:
	$(if $(strip $(TEST_DATABASE_URL)),,$(error TEST_DATABASE_URL est requis pour le gate exploitation))
	$(if $(strip $(TEST_PG_CONTAINER)),,$(error TEST_PG_CONTAINER est requis pour les backups réels))
	$(if $(strip $(TEST_OPS_IMAGE)),,$(error TEST_OPS_IMAGE est requis pour les tests du worker packagé))
	$(if $(strip $(TEST_BACKUP_IMAGE)),,$(error TEST_BACKUP_IMAGE est requis pour la restauration packagée))
	$(if $(strip $(TEST_SECURITY_IMAGE)),,$(error TEST_SECURITY_IMAGE est requis pour les permissions API))
	$(if $(strip $(TEST_SECURITY_WEB_IMAGE)),,$(error TEST_SECURITY_WEB_IMAGE est requis pour le web packagé))
	$(if $(strip $(TEST_SECURITY_GATEWAY_IMAGE)),,$(error TEST_SECURITY_GATEWAY_IMAGE est requis pour TLS))
	uv run --frozen python -m pytest tests/worker tests/operations tests/api/test_lifespan.py tests/integration/test_ops_gate.py tests/integration/test_ops_containers.py tests/integration/test_migration_dry_run.py tests/integration/test_job_queue.py tests/integration/test_job_recovery.py tests/integration/test_business_locks.py tests/integration/test_scheduled_sync.py tests/integration/test_alerts.py tests/integration/test_backups.py tests/integration/test_restore.py tests/integration/test_backup_container.py tests/integration/test_security_gateway.py tests/integration/test_secret_containers.py tests/integration/test_ops_audit.py tests/integration/test_system_observability.py -q

scan-security:
	uv run --frozen python -m infra.scripts.scan_security

scan-secrets:
	uv run --frozen python infra/scripts/scan_secrets.py

backup:
	uv run --frozen oe backup $(OE_JSON_FLAG)

paper-gate:
	uv run --frozen python infra/scripts/demo_paper_gate.py --output $(or $(OUTPUT),data/paper-gate-example.json)

test-paper:
	$(if $(strip $(TEST_DATABASE_URL)),,$(error TEST_DATABASE_URL est requis pour le ledger paper))
	uv run --frozen python -m pytest tests/paper tests/integration/test_paper_ledger.py tests/integration/test_paper_creation.py tests/integration/test_paper_settlement_job.py tests/integration/test_paper_clv.py tests/integration/test_paper_reporting.py tests/integration/test_paper_reporting_audit.py tests/integration/test_real_paper_api.py tests/integration/test_paper_gate.py -vv

paper-report:
	uv run --frozen oe paper-report --currency $(or $(CURRENCY),EUR) $(OE_JSON_FLAG)

paper-settle:
	uv run --frozen oe paper-settle $(if $(strip $(PAPER_BET)),--paper-bet $(PAPER_BET),) $(OE_JSON_FLAG)

test-value:
	$(if $(strip $(TEST_DATABASE_URL)),,$(error TEST_DATABASE_URL est requis pour le gate value))
	uv run --frozen python -m pytest tests/pricing tests/integration/test_value_pipeline.py tests/integration/test_signal_persistence.py tests/integration/test_migrations.py -vv

value-evaluate:
	$(if $(strip $(ODDS_SNAPSHOT)),,$(error ODDS_SNAPSHOT est requis))
	$(if $(strip $(EVENT_MAPPING)),,$(error EVENT_MAPPING est requis))
	$(if $(strip $(MARKET_MAPPING)),,$(error MARKET_MAPPING est requis))
	$(if $(strip $(POLICY)),,$(error POLICY est requis))
	uv run --frozen oe value-evaluate --odds-snapshot $(ODDS_SNAPSHOT) --event-mapping $(EVENT_MAPPING) --market-mapping $(MARKET_MAPPING) --policy $(POLICY) $(if $(strip $(PREDICTION)),--prediction $(PREDICTION),) $(OE_JSON_FLAG)

test-e2e:
	pnpm run test:e2e

openapi:
	uv run --frozen python infra/scripts/export_openapi.py
	pnpm run contracts:generate

openapi-check:
	uv run --frozen python infra/scripts/export_openapi.py --check
	pnpm run contracts:check

check: lint typecheck test-leakage test openapi-check

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

features-rebuild:
	$(if $(strip $(FROM)),,$(error FROM est requis, par exemple FROM=2025-01-01))
	uv run --frozen oe features-rebuild --from $(FROM) $(if $(strip $(CODE_COMMIT)),--code-commit $(CODE_COMMIT),) $(OE_JSON_FLAG)

model-train:
	$(if $(strip $(MARKET)),,$(error MARKET est requis, par exemple MARKET=game_winner))
	uv run --frozen oe model-train --market $(MARKET) $(if $(strip $(DATASET)),--dataset $(DATASET),) $(if $(strip $(CODE_COMMIT)),--code-commit $(CODE_COMMIT),) $(OE_JSON_FLAG)
