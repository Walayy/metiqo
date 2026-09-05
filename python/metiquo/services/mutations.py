"""Mutations mock déterministes, idempotentes et auditées."""

import json
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from threading import Lock
from uuid import UUID, uuid5

from metiquo.contracts import (
    AliasRecord,
    AuditEntry,
    IngestionRunSummary,
    MappingReview,
    ModelSummary,
    PaperBet,
)
from metiquo.contracts.base import ContractModel
from metiquo.contracts.enums import (
    DataMode,
    GameTitle,
    MappingReviewStatus,
    MarketType,
    ModelStatus,
    PaperBetStatus,
)
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock
from metiquo.mock.scenarios import MockScenarioCatalog

_MUTATION_NAMESPACE = UUID("9d538db6-36e9-4bd5-b1b4-f99f3e06ccbb")


class MockMutationService:
    """État mock en mémoire ; aucune méthode ne contacte une source externe."""

    def __init__(self, catalog: MockScenarioCatalog, clock: Clock) -> None:
        self._catalog = catalog
        self._clock = clock
        self._lock = Lock()
        self._fingerprints: dict[tuple[str, str], str] = {}
        self._audit: list[AuditEntry] = []
        self._sync_cache: dict[str, IngestionRunSummary] = {}
        self._train_cache: dict[str, ModelSummary] = {}
        self._promote_cache: dict[str, ModelSummary] = {}
        self._retire_cache: dict[str, ModelSummary] = {}
        self._paper_create_cache: dict[str, PaperBet] = {}
        self._paper_settle_cache: dict[str, PaperBet] = {}
        self._mapping_cache: dict[str, MappingReview] = {}
        self._alias_cache: dict[str, AliasRecord] = {}
        self._models = {
            scenario.model_summary.model_version_id: scenario.model_summary
            for scenario in catalog.scenarios
        }
        self._paper_bets = {
            paper_bet.paper_bet_id: paper_bet
            for scenario in catalog.scenarios
            if (paper_bet := scenario.paper_bet) is not None
        }
        self._mappings = {
            mapping.mapping_review_id: mapping
            for scenario in catalog.scenarios
            if (mapping := scenario.mapping_review) is not None
        }

    @staticmethod
    def _stable_id(action: str, idempotency_key: str) -> UUID:
        return uuid5(_MUTATION_NAMESPACE, f"metiquo:mock:{action}:{idempotency_key}")

    @staticmethod
    def _payload_fingerprint(action: str, payload: dict[str, object]) -> str:
        encoded = json.dumps(
            {"action": action, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode()
        return sha256(encoded).hexdigest()

    def _execute[Result: ContractModel](
        self,
        *,
        action: str,
        idempotency_key: str,
        payload: dict[str, object],
        cache: dict[str, Result],
        operation: Callable[[], Result],
        resource_id: Callable[[Result], str | None],
    ) -> Result:
        normalized_key = idempotency_key.strip()
        if len(normalized_key) < 8:
            raise BusinessError(ErrorCode.INVALID_INPUT, "Idempotency-Key est trop courte")
        fingerprint = self._payload_fingerprint(action, payload)
        cache_key = (action, normalized_key)
        with self._lock:
            previous = self._fingerprints.get(cache_key)
            result_key = f"{action}:{normalized_key}"
            if previous is not None:
                if previous != fingerprint:
                    raise BusinessError(
                        ErrorCode.CONFLICT,
                        "Idempotency-Key déjà utilisée avec une autre requête",
                    )
                return cache[result_key]

            result = operation()
            self._fingerprints[cache_key] = fingerprint
            cache[result_key] = result
            self._audit.append(
                AuditEntry(
                    audit_id=self._stable_id(f"audit:{action}", normalized_key),
                    action=action,
                    resource_id=resource_id(result),
                    idempotency_fingerprint=sha256(normalized_key.encode()).hexdigest(),
                    occurred_at=self._clock.now().value,
                    data_mode=DataMode.MOCK,
                )
            )
            return result

    def sync(self, idempotency_key: str) -> IngestionRunSummary:
        def operation() -> IngestionRunSummary:
            now = self._clock.now().value
            return IngestionRunSummary(
                run_id=self._stable_id("sync", idempotency_key),
                source="mock-provider",
                status="succeeded",
                started_at=now - timedelta(seconds=2),
                completed_at=now,
                row_count=len(self._catalog.scenarios),
                data_mode=DataMode.MOCK,
            )

        return self._execute(
            action="mock.sync",
            idempotency_key=idempotency_key,
            payload={},
            cache=self._sync_cache,
            operation=operation,
            resource_id=lambda result: str(result.run_id),
        )

    def train(
        self,
        idempotency_key: str,
        game_title: GameTitle,
        market_type: MarketType,
    ) -> ModelSummary:
        def operation() -> ModelSummary:
            base = next(iter(self._models.values()))
            now = self._clock.now().value
            model_id = self._stable_id("train", idempotency_key)
            result = ModelSummary.model_validate(
                {
                    **base.model_dump(),
                    "model_version_id": model_id,
                    "model_version": f"mock-candidate-{model_id.hex[:8]}",
                    "game_title": game_title,
                    "market_type": market_type,
                    "status": ModelStatus.CANDIDATE,
                    "train_cutoff": now - timedelta(days=1),
                    "created_at": now,
                    "promoted_at": None,
                    "promotion_reason": None,
                }
            )
            self._models[result.model_version_id] = result
            return result

        return self._execute(
            action="model.train",
            idempotency_key=idempotency_key,
            payload={"gameTitle": game_title.value, "marketType": market_type.value},
            cache=self._train_cache,
            operation=operation,
            resource_id=lambda result: str(result.model_version_id),
        )

    def _change_model_status(
        self,
        *,
        idempotency_key: str,
        model_version_id: UUID,
        status: ModelStatus,
        reason: str,
        action: str,
        cache: dict[str, ModelSummary],
    ) -> ModelSummary:
        def operation() -> ModelSummary:
            current = self._models.get(model_version_id)
            if current is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Modèle introuvable")
            if status is ModelStatus.CHAMPION and current.status is not ModelStatus.CANDIDATE:
                raise BusinessError(ErrorCode.INVALID_STATE, "Seul un candidat peut être promu")
            promoted_at = self._clock.now().value if status is ModelStatus.CHAMPION else None
            result = ModelSummary.model_validate(
                {
                    **current.model_dump(),
                    "status": status,
                    "promoted_at": promoted_at,
                    "promotion_reason": reason if status is ModelStatus.CHAMPION else None,
                }
            )
            self._models[model_version_id] = result
            return result

        return self._execute(
            action=action,
            idempotency_key=idempotency_key,
            payload={"modelVersionId": str(model_version_id), "reason": reason},
            cache=cache,
            operation=operation,
            resource_id=lambda result: str(result.model_version_id),
        )

    def promote(self, key: str, model_version_id: UUID, reason: str) -> ModelSummary:
        return self._change_model_status(
            idempotency_key=key,
            model_version_id=model_version_id,
            status=ModelStatus.CHAMPION,
            reason=reason,
            action="model.promote",
            cache=self._promote_cache,
        )

    def retire(self, key: str, model_version_id: UUID, reason: str) -> ModelSummary:
        return self._change_model_status(
            idempotency_key=key,
            model_version_id=model_version_id,
            status=ModelStatus.RETIRED,
            reason=reason,
            action="model.retire",
            cache=self._retire_cache,
        )

    def create_paper_bet(
        self,
        key: str,
        signal_id: UUID,
        stake_amount: Decimal,
        currency: str,
    ) -> PaperBet:
        def operation() -> PaperBet:
            opportunity = next(
                (
                    scenario.opportunity
                    for scenario in self._catalog.scenarios
                    if scenario.opportunity.signal_id == signal_id
                ),
                None,
            )
            if opportunity is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Opportunité introuvable")
            if not opportunity.quality.publishable:
                raise BusinessError(
                    ErrorCode.INVALID_STATE,
                    "Une opportunité non publiable ne peut pas créer de paper bet",
                )
            result = PaperBet(
                paper_bet_id=self._stable_id("paper.create", key),
                signal_id=signal_id,
                prediction_id=opportunity.model.prediction_id,
                odds_snapshot_id=opportunity.book.odds_snapshot_id,
                entry_odds=opportunity.book.decimal_odds,
                stake_amount=stake_amount,
                currency=currency,
                placed_at=self._clock.now().value,
                status=PaperBetStatus.OPEN,
                settlement_rules_version=opportunity.market.settlement_rules_version or "unknown",
            )
            self._paper_bets[result.paper_bet_id] = result
            return result

        return self._execute(
            action="paper.create",
            idempotency_key=key,
            payload={
                "signalId": str(signal_id),
                "stakeAmount": str(stake_amount),
                "currency": currency,
            },
            cache=self._paper_create_cache,
            operation=operation,
            resource_id=lambda result: str(result.paper_bet_id),
        )

    def settle_paper_bet(
        self,
        key: str,
        paper_bet_id: UUID,
        status: PaperBetStatus,
        profit_loss: Decimal,
        reason: str,
    ) -> PaperBet:
        def operation() -> PaperBet:
            current = self._paper_bets.get(paper_bet_id)
            if current is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Paper bet introuvable")
            if current.status is not PaperBetStatus.OPEN:
                raise BusinessError(ErrorCode.INVALID_STATE, "Le paper bet n'est pas ouvert")
            if status not in {
                PaperBetStatus.WON,
                PaperBetStatus.LOST,
                PaperBetStatus.PUSH,
                PaperBetStatus.VOID,
            }:
                raise BusinessError(ErrorCode.INVALID_INPUT, "Statut de règlement invalide")
            result = PaperBet.model_validate(
                {
                    **current.model_dump(),
                    "status": status,
                    "settled_at": self._clock.now().value,
                    "profit_loss": profit_loss,
                    "settlement_reason": reason,
                }
            )
            self._paper_bets[paper_bet_id] = result
            return result

        return self._execute(
            action="paper.settle",
            idempotency_key=key,
            payload={
                "paperBetId": str(paper_bet_id),
                "status": status.value,
                "profitLoss": str(profit_loss),
                "reason": reason,
            },
            cache=self._paper_settle_cache,
            operation=operation,
            resource_id=lambda result: str(result.paper_bet_id),
        )

    def decide_mapping(
        self,
        key: str,
        mapping_review_id: UUID,
        status: MappingReviewStatus,
        reviewer: str,
        reason: str,
        candidate_event_id: UUID | None = None,
    ) -> MappingReview:
        def operation() -> MappingReview:
            current = self._mappings.get(mapping_review_id)
            if current is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Mapping introuvable")
            if current.status is not MappingReviewStatus.PENDING:
                raise BusinessError(ErrorCode.INVALID_STATE, "Le mapping est déjà décidé")
            if status is MappingReviewStatus.APPROVED:
                selected = candidate_event_id or current.candidates[0].event_id
                if all(candidate.event_id != selected for candidate in current.candidates):
                    raise BusinessError(ErrorCode.INVALID_INPUT, "Candidat de mapping inconnu")
            result = MappingReview.model_validate(
                {
                    **current.model_dump(),
                    "status": status,
                    "selected_event_id": selected
                    if status is MappingReviewStatus.APPROVED
                    else None,
                    "reviewed_at": self._clock.now().value,
                    "reviewer": reviewer,
                    "decision_reason": reason,
                }
            )
            self._mappings[mapping_review_id] = result
            return result

        return self._execute(
            action=f"mapping.{status.value}",
            idempotency_key=key,
            payload={
                "mappingReviewId": str(mapping_review_id),
                "reviewer": reviewer,
                "reason": reason,
                "candidateEventId": str(candidate_event_id) if candidate_event_id else None,
            },
            cache=self._mapping_cache,
            operation=operation,
            resource_id=lambda result: str(result.mapping_review_id),
        )

    def create_alias(
        self,
        key: str,
        provider: str,
        alias: str,
        canonical_id: UUID,
        entity_type: str = "team",
        reviewer: str = "admin-local",
        reason: str = "Alias créé manuellement",
    ) -> AliasRecord:
        def operation() -> AliasRecord:
            return AliasRecord(
                alias_id=self._stable_id("alias.create", key),
                provider=provider,
                alias=alias,
                canonical_id=canonical_id,
                created_at=self._clock.now().value,
                data_mode=DataMode.MOCK,
            )

        return self._execute(
            action="alias.create",
            idempotency_key=key,
            payload={
                "provider": provider,
                "alias": alias,
                "canonicalId": str(canonical_id),
                "entityType": entity_type,
                "reviewer": reviewer,
                "reason": reason,
            },
            cache=self._alias_cache,
            operation=operation,
            resource_id=lambda result: str(result.alias_id),
        )

    def audit_log(self) -> tuple[AuditEntry, ...]:
        with self._lock:
            return tuple(self._audit)
