"""Plugin fermé par défaut pour le vainqueur d'une game LoL."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from metiquo.canonical.capabilities import CapabilityState
from metiquo.contracts.enums import SelectionType
from metiquo.models.baselines import BaselineRun
from metiquo.models.benchmark import TabularBenchmarkRun, TabularBenchmarkRunner, TabularFeatureSpec
from metiquo.models.datasets import GAME_WINNER_LABEL, GAME_WINNER_MARKET
from metiquo.models.registry import CHAMPION, MODEL_GAME, ModelVersion
from metiquo.models.uncertainty import UncertaintyArtifact
from metiquo.models.validation import WalkForwardPlan

GAME_WINNER_PLUGIN_VERSION = "game-winner-plugin-v1"
_PROBABILITY_QUANTUM = Decimal("0.000001")
_ODDS_QUANTUM = Decimal("0.0001")
_REQUIRED_CAPABILITIES = (
    "label.match_winner",
    "feature.side_strength",
    "feature.team_form",
    "market.match_winner",
)


class PluginDisabledError(RuntimeError):
    """Le plugin ne peut pas agir tant que ses preuves ne sont pas valides."""


@dataclass(frozen=True, slots=True)
class GameWinnerLabel:
    name: str = GAME_WINNER_LABEL
    target: str = "team_a_win"
    positive_selection: SelectionType = SelectionType.TEAM_A
    negative_selection: SelectionType = SelectionType.TEAM_B


@dataclass(frozen=True, slots=True)
class PluginAvailability:
    enabled: bool
    reason_codes: tuple[str, ...]
    snapshot_id: UUID | None
    model_version_id: UUID | None

    def __post_init__(self) -> None:
        if self.enabled == bool(self.reason_codes):
            raise ValueError("un plugin activé ne doit porter aucune raison de blocage")


@dataclass(frozen=True, slots=True)
class GameWinnerProbability:
    selection: SelectionType
    p50: Decimal
    p_low: Decimal
    p_high: Decimal
    confidence: Decimal

    def __post_init__(self) -> None:
        if self.selection not in {SelectionType.TEAM_A, SelectionType.TEAM_B}:
            raise ValueError("GAME_WINNER accepte uniquement TEAM_A et TEAM_B")
        if not Decimal() <= self.p_low <= self.p50 <= self.p_high <= Decimal(1):
            raise ValueError("l'intervalle probabiliste doit être ordonné dans [0,1]")
        if not Decimal() <= self.confidence <= Decimal(1):
            raise ValueError("la confiance doit être dans [0,1]")


@dataclass(frozen=True, slots=True)
class GameWinnerPrediction:
    model_version_id: UUID
    uncertainty_artifact_id: UUID
    team_a: GameWinnerProbability
    team_b: GameWinnerProbability
    enabled: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.team_a.selection is not SelectionType.TEAM_A:
            raise ValueError("la première issue doit être TEAM_A")
        if self.team_b.selection is not SelectionType.TEAM_B:
            raise ValueError("la seconde issue doit être TEAM_B")
        if self.team_a.p50 + self.team_b.p50 != Decimal(1):
            raise ValueError("les probabilités centrales GAME_WINNER doivent sommer à 1")
        if self.team_a.p_low + self.team_b.p_high != Decimal(1):
            raise ValueError("les bornes basses/hautes doivent être complémentaires")
        if self.team_a.p_high + self.team_b.p_low != Decimal(1):
            raise ValueError("les bornes hautes/basses doivent être complémentaires")
        if self.enabled == bool(self.reason_codes):
            raise ValueError("une prédiction activée ne doit porter aucune abstention")


@dataclass(frozen=True, slots=True)
class GameWinnerPrice:
    enabled: bool
    team_a_fair_decimal_odds: Decimal | None
    team_b_fair_decimal_odds: Decimal | None
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.enabled:
            if self.reason_codes or self.team_a_fair_decimal_odds is None:
                raise ValueError("un prix actif doit exposer les deux cotes sans blocage")
            if self.team_b_fair_decimal_odds is None:
                raise ValueError("un prix actif doit exposer les deux cotes")
        elif self.team_a_fair_decimal_odds is not None or self.team_b_fair_decimal_odds is not None:
            raise ValueError("un prix désactivé ne doit pas publier de cote")


class GameWinnerSettlement(StrEnum):
    WON = "won"
    LOST = "lost"
    VOID = "void"


class GameWinnerTrainingBackend(Protocol):
    """Backend d'entraînement substituable sans élargir le contrat du marché."""

    def train(
        self,
        plan: WalkForwardPlan,
        *,
        dataset_id: UUID,
        baseline_runs: Sequence[BaselineRun],
    ) -> TabularBenchmarkRun: ...


@dataclass(frozen=True, slots=True)
class GameWinnerBenchmarkTrainer:
    runner: TabularBenchmarkRunner

    def train(
        self,
        plan: WalkForwardPlan,
        *,
        dataset_id: UUID,
        baseline_runs: Sequence[BaselineRun],
    ) -> TabularBenchmarkRun:
        return self.runner.benchmark(plan, dataset_id=dataset_id, baseline_runs=baseline_runs)


@runtime_checkable
class MarketPlugin(Protocol):
    """Surface minimale commune à tout marché déployable."""

    def required_capabilities(self) -> tuple[str, ...]: ...

    def labels(self) -> tuple[GameWinnerLabel, ...]: ...

    def features(self) -> TabularFeatureSpec: ...

    def train(
        self,
        plan: WalkForwardPlan,
        *,
        dataset_id: UUID,
        baseline_runs: Sequence[BaselineRun],
    ) -> TabularBenchmarkRun: ...

    def predict(
        self,
        champion: ModelVersion,
        uncertainty: UncertaintyArtifact,
        *,
        raw_team_a_probability: Decimal,
        data_coverage: Decimal,
        training_domain_distance: Decimal,
    ) -> GameWinnerPrediction: ...

    def price(self, prediction: GameWinnerPrediction) -> GameWinnerPrice: ...

    def settle(
        self,
        selection: SelectionType,
        *,
        winning_selection: SelectionType | None,
        voided: bool = False,
    ) -> GameWinnerSettlement: ...


class GameWinnerCapabilityGate:
    """Joindre l'état des données au champion réellement servi."""

    def evaluate(
        self,
        states: Sequence[CapabilityState],
        *,
        champion: ModelVersion | None,
        model_artifact_verified: bool,
    ) -> PluginAvailability:
        by_name = {state.capability: state for state in states}
        snapshots = {state.snapshot_id for state in states}
        reasons: list[str] = []
        if len(by_name) != len(states):
            reasons.append("CAPABILITY_STATE_DUPLICATED")
        if len(snapshots) > 1:
            reasons.append("CAPABILITY_SNAPSHOT_MISMATCH")
        for capability in _REQUIRED_CAPABILITIES:
            state = by_name.get(capability)
            if state is None:
                reasons.append(f"CAPABILITY_MISSING:{capability}")
                continue
            if state.status != "enabled":
                reasons.append(f"CAPABILITY_{state.status.upper()}:{capability}")
                reasons.extend(
                    f"CAPABILITY_REASON:{capability}:{reason}" for reason in state.reason_codes
                )
        if champion is None:
            reasons.append("CHAMPION_MISSING")
        else:
            if champion.status != CHAMPION:
                reasons.append("CHAMPION_NOT_ACTIVE")
            if champion.game != MODEL_GAME or champion.market != GAME_WINNER_MARKET:
                reasons.append("CHAMPION_SCOPE_MISMATCH")
        if not model_artifact_verified:
            reasons.append("MODEL_ARTIFACT_UNVERIFIED")
        unique_reasons = tuple(dict.fromkeys(reasons))
        snapshot_id = next(iter(snapshots)) if len(snapshots) == 1 else None
        return PluginAvailability(
            enabled=not unique_reasons,
            reason_codes=unique_reasons,
            snapshot_id=snapshot_id,
            model_version_id=champion.model_version_id if champion is not None else None,
        )


class GameWinnerMarketPlugin:
    """Entraîner, prédire, pricer et régler le marché binaire GAME_WINNER."""

    def __init__(
        self,
        *,
        training_backend: GameWinnerTrainingBackend | None = None,
        feature_spec: TabularFeatureSpec | None = None,
    ) -> None:
        self._training_backend = training_backend
        self._feature_spec = feature_spec or TabularFeatureSpec()

    def required_capabilities(self) -> tuple[str, ...]:
        return _REQUIRED_CAPABILITIES

    def labels(self) -> tuple[GameWinnerLabel, ...]:
        return (GameWinnerLabel(),)

    def features(self) -> TabularFeatureSpec:
        return self._feature_spec

    def train(
        self,
        plan: WalkForwardPlan,
        *,
        dataset_id: UUID,
        baseline_runs: Sequence[BaselineRun],
    ) -> TabularBenchmarkRun:
        if self._training_backend is None:
            raise PluginDisabledError("TRAINING_BACKEND_MISSING")
        return self._training_backend.train(
            plan,
            dataset_id=dataset_id,
            baseline_runs=baseline_runs,
        )

    def predict(
        self,
        champion: ModelVersion,
        uncertainty: UncertaintyArtifact,
        *,
        raw_team_a_probability: Decimal,
        data_coverage: Decimal,
        training_domain_distance: Decimal,
    ) -> GameWinnerPrediction:
        _validate_champion(champion, uncertainty)
        estimate = uncertainty.estimate(
            raw_team_a_probability,
            data_coverage=data_coverage,
            training_domain_distance=training_domain_distance,
        )
        p50_a = _probability(estimate.p50)
        low_a = _probability(estimate.p_low)
        high_a = _probability(estimate.p_high)
        reasons = estimate.reasons if "ABSTENTION_REQUIRED" in estimate.reasons else ()
        return GameWinnerPrediction(
            model_version_id=champion.model_version_id,
            uncertainty_artifact_id=uncertainty.artifact_id,
            team_a=GameWinnerProbability(
                selection=SelectionType.TEAM_A,
                p50=p50_a,
                p_low=low_a,
                p_high=high_a,
                confidence=estimate.confidence,
            ),
            team_b=GameWinnerProbability(
                selection=SelectionType.TEAM_B,
                p50=Decimal(1) - p50_a,
                p_low=Decimal(1) - high_a,
                p_high=Decimal(1) - low_a,
                confidence=estimate.confidence,
            ),
            enabled=not reasons,
            reason_codes=reasons,
        )

    def price(self, prediction: GameWinnerPrediction) -> GameWinnerPrice:
        if not prediction.enabled:
            return GameWinnerPrice(
                enabled=False,
                team_a_fair_decimal_odds=None,
                team_b_fair_decimal_odds=None,
                reason_codes=prediction.reason_codes,
            )
        if prediction.team_a.p50 == 0 or prediction.team_b.p50 == 0:
            return GameWinnerPrice(
                enabled=False,
                team_a_fair_decimal_odds=None,
                team_b_fair_decimal_odds=None,
                reason_codes=("ZERO_PROBABILITY_PRICE_UNDEFINED",),
            )
        return GameWinnerPrice(
            enabled=True,
            team_a_fair_decimal_odds=(Decimal(1) / prediction.team_a.p50).quantize(
                _ODDS_QUANTUM, rounding=ROUND_HALF_EVEN
            ),
            team_b_fair_decimal_odds=(Decimal(1) / prediction.team_b.p50).quantize(
                _ODDS_QUANTUM, rounding=ROUND_HALF_EVEN
            ),
            reason_codes=(),
        )

    def settle(
        self,
        selection: SelectionType,
        *,
        winning_selection: SelectionType | None,
        voided: bool = False,
    ) -> GameWinnerSettlement:
        _validate_selection(selection)
        if voided:
            return GameWinnerSettlement.VOID
        if winning_selection is None:
            raise ValueError("l'issue gagnante est requise hors void")
        _validate_selection(winning_selection)
        return (
            GameWinnerSettlement.WON
            if selection is winning_selection
            else GameWinnerSettlement.LOST
        )


def _validate_champion(champion: ModelVersion, uncertainty: UncertaintyArtifact) -> None:
    if champion.status != CHAMPION:
        raise PluginDisabledError("CHAMPION_NOT_ACTIVE")
    if champion.game != MODEL_GAME or champion.market != GAME_WINNER_MARKET:
        raise PluginDisabledError("CHAMPION_SCOPE_MISMATCH")
    if champion.uncertainty_artifact_id != uncertainty.artifact_id:
        raise PluginDisabledError("CHAMPION_UNCERTAINTY_MISMATCH")
    if champion.uncertainty_fingerprint != uncertainty.artifact_fingerprint:
        raise PluginDisabledError("CHAMPION_UNCERTAINTY_FINGERPRINT_MISMATCH")
    if champion.calibrator_artifact_id != uncertainty.calibrator_artifact_id:
        raise PluginDisabledError("CHAMPION_CALIBRATOR_MISMATCH")


def _validate_selection(selection: SelectionType) -> None:
    if selection not in {SelectionType.TEAM_A, SelectionType.TEAM_B}:
        raise ValueError("GAME_WINNER accepte uniquement TEAM_A et TEAM_B")


def _probability(value: Decimal) -> Decimal:
    if not value.is_finite() or not Decimal() <= value <= Decimal(1):
        raise ValueError("la probabilité doit être finie dans [0,1]")
    return value.quantize(_PROBABILITY_QUANTUM, rounding=ROUND_HALF_EVEN)
