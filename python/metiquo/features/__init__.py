"""Fabrication de features versionnées et strictement temporelles."""

from metiquo.features.rating import (
    EloParameters,
    EloRatingCalculator,
    RatingFeatureResult,
    RatingTransition,
    TeamRating,
    rating_feature_definitions,
)
from metiquo.features.registry import (
    FeatureDefinitionSpec,
    FeatureRegistry,
    FeatureRegistryConflictError,
    FeatureSetSpec,
    RegisteredFeatureDefinition,
    RegisteredFeatureSet,
    RegisteredFeatureVector,
    UnregisteredFeatureError,
)
from metiquo.features.temporal import (
    AsOfGameBatch,
    AsOfGameRepository,
    AsOfInputAudit,
    CutoffViolationError,
    FeatureCutoff,
    HistoricalGame,
    HistoricalTeamGame,
    latest_entity_revisions_as_of,
    polars_strictly_before,
    strictly_before_cutoff,
)

__all__ = [
    "AsOfGameBatch",
    "AsOfGameRepository",
    "AsOfInputAudit",
    "CutoffViolationError",
    "EloParameters",
    "EloRatingCalculator",
    "FeatureCutoff",
    "FeatureDefinitionSpec",
    "FeatureRegistry",
    "FeatureRegistryConflictError",
    "FeatureSetSpec",
    "HistoricalGame",
    "HistoricalTeamGame",
    "RatingFeatureResult",
    "RatingTransition",
    "RegisteredFeatureDefinition",
    "RegisteredFeatureSet",
    "RegisteredFeatureVector",
    "TeamRating",
    "UnregisteredFeatureError",
    "latest_entity_revisions_as_of",
    "polars_strictly_before",
    "rating_feature_definitions",
    "strictly_before_cutoff",
]
