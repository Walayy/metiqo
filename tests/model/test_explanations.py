"""Templates structurés, contributions et données manquantes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid5

import pytest

from metiquo.features import StoredFeatureSnapshot
from metiquo.models.explanations import (
    ContributionEvidence,
    ContributionMethod,
    ExplanationKind,
    FeatureContribution,
    StructuredExplanationBuilder,
)
from metiquo.models.predictions import StoredPrematchPrediction

_NAMESPACE = UUID("5b1a1889-7ec6-418c-a70d-b81ca50c4d95")
_CUTOFF = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def test_shap_factors_are_structured_non_causal_and_deterministic() -> None:
    prediction = _prediction()
    snapshot = _snapshot(prediction.feature_snapshot_id)
    evidence = ContributionEvidence(
        method=ContributionMethod.SHAP,
        baseline_output=Decimal("0.50"),
        model_output=Decimal("0.60"),
        contributions=(
            FeatureContribution("rating.difference", Decimal("0.20")),
            FeatureContribution("roster.team_a.confidence", Decimal("-0.10")),
        ),
    )
    builder = StructuredExplanationBuilder()

    first = builder.build(prediction, snapshot, contributions=evidence)
    second = builder.build(prediction, snapshot, contributions=evidence)

    assert first == second
    assert first.reference == second.reference
    assert first.contribution_method is ContributionMethod.SHAP
    assert first.contribution_is_causal is False
    assert all(item.fields for item in first.items)
    factors = tuple(
        item
        for item in first.items
        if item.kind in {ExplanationKind.POSITIVE_FACTOR, ExplanationKind.NEGATIVE_FACTOR}
    )
    assert [item.kind for item in factors] == [
        ExplanationKind.POSITIVE_FACTOR,
        ExplanationKind.NEGATIVE_FACTOR,
    ]
    assert all(item.parameters["method"] == "shap" for item in factors)
    assert all(item.parameters["causal"] is False for item in factors)
    assert all("contribution n'est pas une cause" in item.text for item in factors)
    assert factors[0].fields[0].name == "rating.difference"


def test_uncertainty_missingness_and_age_are_rendered_only_from_fields() -> None:
    prediction = _prediction()
    snapshot = _snapshot(prediction.feature_snapshot_id)
    explanation = StructuredExplanationBuilder().build(prediction, snapshot)

    uncertainty = next(
        item for item in explanation.items if item.kind is ExplanationKind.UNCERTAINTY
    )
    missing = tuple(item for item in explanation.items if item.kind is ExplanationKind.MISSING_DATA)
    age = next(item for item in explanation.items if item.kind is ExplanationKind.DATA_AGE)
    combined_text = " ".join(item.text.casefold() for item in explanation.items)

    assert {field.name for field in uncertainty.fields} == {
        "prediction.team_a_probability",
        "prediction.team_a_low",
        "prediction.team_a_high",
        "prediction.confidence",
    }
    assert any(item.fields[0].name == "context.patch" for item in missing)
    assert age.parameters["age_seconds"] == "7200"
    assert "contenu non fiable" not in combined_text
    assert not any(token in combined_text for token in ("fatigue", "rumeur", "conflit interne"))


def test_contribution_contract_rejects_unknown_missing_or_incoherent_values() -> None:
    prediction = _prediction()
    snapshot = _snapshot(prediction.feature_snapshot_id)

    with pytest.raises(ValueError, match="non autorisée"):
        FeatureContribution("rumor.player_absence", Decimal("0.1"))
    with pytest.raises(ValueError, match="reconstruisent pas"):
        ContributionEvidence(
            method=ContributionMethod.SHAP,
            baseline_output=Decimal("0.5"),
            model_output=Decimal("0.8"),
            contributions=(FeatureContribution("rating.difference", Decimal("0.1")),),
        )
    with pytest.raises(ValueError, match="manquante"):
        StructuredExplanationBuilder().build(
            prediction,
            snapshot,
            contributions=ContributionEvidence(
                method=ContributionMethod.NATIVE,
                baseline_output=Decimal("0.5"),
                model_output=Decimal("0.6"),
                contributions=(FeatureContribution("context.patch", Decimal("0.1")),),
            ),
        )
    with pytest.raises(ValueError, match="partager le snapshot"):
        StructuredExplanationBuilder().build(
            prediction,
            _snapshot(uuid5(_NAMESPACE, "other-snapshot")),
        )


def _prediction() -> StoredPrematchPrediction:
    return StoredPrematchPrediction(
        prediction_id=uuid5(_NAMESPACE, "prediction"),
        market="game_winner",
        event_id=uuid5(_NAMESPACE, "event"),
        team_a_id=uuid5(_NAMESPACE, "team-a"),
        team_b_id=uuid5(_NAMESPACE, "team-b"),
        feature_snapshot_id=uuid5(_NAMESPACE, "snapshot"),
        model_version_id=uuid5(_NAMESPACE, "model"),
        calibrator_artifact_id=uuid5(_NAMESPACE, "calibrator"),
        uncertainty_artifact_id=uuid5(_NAMESPACE, "uncertainty"),
        cutoff_at=_CUTOFF,
        predicted_at=_CUTOFF + timedelta(minutes=1),
        team_a_probability=Decimal("0.60"),
        team_a_low=Decimal("0.52"),
        team_a_high=Decimal("0.68"),
        team_b_probability=Decimal("0.40"),
        team_b_low=Decimal("0.32"),
        team_b_high=Decimal("0.48"),
        confidence=Decimal("0.78"),
        enabled=True,
        reason_codes=(),
        code_commit="abcdef1",
        inference_fingerprint="a" * 64,
        prediction_fingerprint="b" * 64,
    )


def _snapshot(snapshot_id: UUID) -> StoredFeatureSnapshot:
    return StoredFeatureSnapshot(
        snapshot_id=snapshot_id,
        feature_set_id=uuid5(_NAMESPACE, "feature-set"),
        event_id=uuid5(_NAMESPACE, "event"),
        team_a_id=uuid5(_NAMESPACE, "team-a"),
        team_b_id=uuid5(_NAMESPACE, "team-b"),
        target_oe_snapshot_id=uuid5(_NAMESPACE, "oe-snapshot"),
        cutoff_at=_CUTOFF,
        max_input_time=_CUTOFF - timedelta(hours=2),
        max_knowledge_time=_CUTOFF - timedelta(hours=1),
        definition_versions=MappingProxyType(
            {
                "context.patch": "v1",
                "rating.difference": "v1",
                "roster.team_a.confidence": "v1",
            }
        ),
        values=MappingProxyType(
            {
                "context.patch": None,
                "rating.difference": Decimal("125"),
                "roster.team_a.confidence": "contenu non fiable",
            }
        ),
        missingness=MappingProxyType(
            {
                "context.patch": True,
                "rating.difference": False,
                "roster.team_a.confidence": False,
            }
        ),
        source_game_ids=(),
        target_game_ids=(uuid5(_NAMESPACE, "event"),),
        source_revision_ids=(),
        source_snapshot_ids=(uuid5(_NAMESPACE, "oe-snapshot"),),
        source_games_fingerprint="c" * 64,
        code_commit="abcdef1",
        leakage_checks=MappingProxyType(
            {
                "knowledge_time_cutoff": True,
                "source_time_strict_cutoff": True,
                "target_game_excluded": True,
                "train_only_transforms": True,
            }
        ),
        rebuild_invalidation_ids=(),
        vector_hash="d" * 64,
        snapshot_hash="e" * 64,
        supersedes_snapshot_id=None,
        generation=1,
        created_at=_CUTOFF,
    )
