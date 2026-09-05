"""Contrat et propriétés du plugin GAME_WINNER."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import cast
from uuid import UUID, uuid5

import pytest
from tests.model.test_uncertainty import _calibrator

from metiquo.canonical.capabilities import (
    CapabilityKind,
    CapabilityState,
    CapabilityStateStatus,
)
from metiquo.contracts.enums import SelectionType
from metiquo.markets import (
    GameWinnerCapabilityGate,
    GameWinnerMarketPlugin,
    GameWinnerSettlement,
    MarketPlugin,
    PluginDisabledError,
)
from metiquo.models import (
    CHAMPION,
    BaselineRun,
    ModelArtifactReference,
    ModelVersion,
    TabularBenchmarkRun,
    UncertaintyArtifact,
    UncertaintyArtifactBuilder,
    WalkForwardPlan,
)

_NAMESPACE = UUID("7d411db6-3b96-4cf1-a85e-eb886a459877")
_NOW = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)


def test_plugin_contract_declares_closed_labels_features_and_training() -> None:
    expected_run = cast(TabularBenchmarkRun, object())
    backend = _TrainingBackend(expected_run)
    plugin = GameWinnerMarketPlugin(training_backend=backend)
    plan = cast(WalkForwardPlan, object())
    baselines = cast(tuple[BaselineRun, ...], ())

    assert isinstance(plugin, MarketPlugin)
    assert plugin.labels()[0].name == "oe.game_team_stats.result:team_a_win@v1"
    assert plugin.labels()[0].positive_selection is SelectionType.TEAM_A
    assert plugin.features().version == "game-winner-tabular-features-v1"
    assert "market.match_winner" in plugin.required_capabilities()
    assert (
        plugin.train(plan, dataset_id=uuid5(_NAMESPACE, "dataset"), baseline_runs=baselines)
        is expected_run
    )
    assert backend.called

    with pytest.raises(PluginDisabledError, match="TRAINING_BACKEND_MISSING"):
        GameWinnerMarketPlugin().train(
            plan,
            dataset_id=uuid5(_NAMESPACE, "dataset"),
            baseline_runs=baselines,
        )


def test_capability_gate_requires_valid_data_and_verified_champion() -> None:
    artifact = _uncertainty()
    champion = _model(artifact)
    plugin = GameWinnerMarketPlugin()
    gate = GameWinnerCapabilityGate()
    states = tuple(_state(name) for name in plugin.required_capabilities())

    enabled = gate.evaluate(
        states,
        champion=champion,
        model_artifact_verified=True,
    )
    assert enabled.enabled
    assert enabled.reason_codes == ()
    assert enabled.model_version_id == champion.model_version_id

    disabled = gate.evaluate(
        (*states[:-1], _state(states[-1].capability, status="disabled")),
        champion=None,
        model_artifact_verified=False,
    )
    assert not disabled.enabled
    assert "CAPABILITY_DISABLED:market.match_winner" in disabled.reason_codes
    assert "CHAMPION_MISSING" in disabled.reason_codes
    assert "MODEL_ARTIFACT_UNVERIFIED" in disabled.reason_codes


def test_team_probabilities_are_exact_complements_for_full_domain() -> None:
    artifact = _uncertainty()
    champion = _model(artifact)
    plugin = GameWinnerMarketPlugin()

    for index in range(101):
        prediction = plugin.predict(
            champion,
            artifact,
            raw_team_a_probability=Decimal(index) / Decimal(100),
            data_coverage=Decimal(1),
            training_domain_distance=Decimal(),
        )
        assert prediction.team_a.p50 + prediction.team_b.p50 == Decimal(1)
        assert prediction.team_a.p_low + prediction.team_b.p_high == Decimal(1)
        assert prediction.team_a.p_high + prediction.team_b.p_low == Decimal(1)
        assert Decimal() <= prediction.team_b.p_low <= prediction.team_b.p_high <= Decimal(1)


def test_prediction_price_abstention_and_settlement_are_safe() -> None:
    artifact = _uncertainty()
    champion = _model(artifact)
    plugin = GameWinnerMarketPlugin()
    prediction = plugin.predict(
        champion,
        artifact,
        raw_team_a_probability=Decimal("0.60"),
        data_coverage=Decimal(1),
        training_domain_distance=Decimal(),
    )
    price = plugin.price(prediction)

    assert price.enabled
    assert price.team_a_fair_decimal_odds == Decimal("1.6667")
    assert price.team_b_fair_decimal_odds == Decimal("2.5000")
    assert (
        plugin.settle(
            SelectionType.TEAM_A,
            winning_selection=SelectionType.TEAM_A,
        )
        is GameWinnerSettlement.WON
    )
    assert (
        plugin.settle(
            SelectionType.TEAM_B,
            winning_selection=SelectionType.TEAM_A,
        )
        is GameWinnerSettlement.LOST
    )
    assert (
        plugin.settle(
            SelectionType.TEAM_A,
            winning_selection=None,
            voided=True,
        )
        is GameWinnerSettlement.VOID
    )

    abstained = plugin.predict(
        champion,
        artifact,
        raw_team_a_probability=Decimal("0.60"),
        data_coverage=Decimal("0.40"),
        training_domain_distance=artifact.search.abstention_distance,
    )
    assert not abstained.enabled
    assert not plugin.price(abstained).enabled
    assert "ABSTENTION_REQUIRED" in abstained.reason_codes


def test_prediction_rejects_registry_artifact_mismatches() -> None:
    artifact = _uncertainty()
    plugin = GameWinnerMarketPlugin()

    with pytest.raises(PluginDisabledError, match="CHAMPION_NOT_ACTIVE"):
        plugin.predict(
            _model(artifact, status="candidate"),
            artifact,
            raw_team_a_probability=Decimal("0.5"),
            data_coverage=Decimal(1),
            training_domain_distance=Decimal(),
        )
    with pytest.raises(PluginDisabledError, match="CHAMPION_UNCERTAINTY_MISMATCH"):
        plugin.predict(
            _model(artifact, uncertainty_artifact_id=uuid5(_NAMESPACE, "other")),
            artifact,
            raw_team_a_probability=Decimal("0.5"),
            data_coverage=Decimal(1),
            training_domain_distance=Decimal(),
        )


class _TrainingBackend:
    def __init__(self, result: TabularBenchmarkRun) -> None:
        self._result = result
        self.called = False

    def train(
        self,
        plan: WalkForwardPlan,
        *,
        dataset_id: UUID,
        baseline_runs: Sequence[BaselineRun],
    ) -> TabularBenchmarkRun:
        del plan, dataset_id, baseline_runs
        self.called = True
        return self._result


def _state(capability: str, *, status: str = "enabled") -> CapabilityState:
    kind: CapabilityKind = (
        "label"
        if capability.startswith("label.")
        else "market"
        if capability.startswith("market.")
        else "feature"
    )
    return CapabilityState(
        snapshot_id=uuid5(_NAMESPACE, "snapshot"),
        capability=capability,
        capability_kind=kind,
        status=cast(CapabilityStateStatus, status),
        reason_codes=("UPSTREAM_BLOCK",) if status != "enabled" else (),
        threshold_version="test-v1",
        evaluation_revision=1,
        required_columns=("result",),
        observed_columns=("result",),
        minimum_completeness=Decimal("0.95"),
        observed_completeness=Decimal(1),
        minimum_sample_size=100,
        observed_sample_size=200,
        gates=MappingProxyType({}),
        evaluated_at=_NOW,
    )


def _uncertainty() -> UncertaintyArtifact:
    return UncertaintyArtifactBuilder(code_commit="abcdef1").build(_calibrator())


def _model(
    uncertainty: UncertaintyArtifact,
    *,
    status: str = CHAMPION,
    uncertainty_artifact_id: UUID | None = None,
) -> ModelVersion:
    model_id = uuid5(_NAMESPACE, f"model:{status}:{uncertainty_artifact_id}")
    return ModelVersion(
        model_version_id=model_id,
        game="lol",
        market="game_winner",
        segment="global",
        algorithm="hist_gradient_boosting",
        hyperparameters=MappingProxyType({"seed": 42}),
        feature_set_version="p3-reproducible-v1",
        dataset_id=uuid5(_NAMESPACE, "dataset"),
        dataset_hash="a" * 64,
        training_cutoff_min=_NOW,
        training_cutoff_max=_NOW,
        evaluation_report=MappingProxyType({"metrics": {}}),
        evaluation_report_fingerprint="b" * 64,
        calibrator_artifact_id=uncertainty.calibrator_artifact_id,
        uncertainty_artifact_id=uncertainty_artifact_id or uncertainty.artifact_id,
        uncertainty_fingerprint=uncertainty.artifact_fingerprint,
        artifact=ModelArtifactReference(
            year=2026,
            object_key=f"year=2026/sha256={'c' * 64}/source.bin",
            sha256="c" * 64,
            size_bytes=10,
            artifact_format="application/octet-stream",
        ),
        code_commit="abcdef1",
        status=status,
        registered_by="reviewer",
        registered_at=_NOW,
        registration_reason="validated",
        status_changed_by="reviewer",
        status_changed_at=_NOW,
        status_reason="validated",
        registration_fingerprint="d" * 64,
    )
