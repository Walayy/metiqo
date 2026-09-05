"""Résolution explicite des identités fournisseurs vers le canonique."""

from metiquo.mapping.event_matching import (
    MATCHING_WEIGHTS_VERSION,
    EventCandidateScore,
    EventMappingDecision,
    EventMappingReason,
    EventMappingStatus,
    EventMatchingPolicy,
    EventMatchingScorer,
    EventMatchingWeights,
    PostgresEventMatchingService,
    UnresolvedEventMappingError,
)
from metiquo.mapping.normalization import (
    NORMALIZATION_VERSION,
    normalize_entity_name,
    typographically_equal,
)

__all__ = [
    "MATCHING_WEIGHTS_VERSION",
    "NORMALIZATION_VERSION",
    "EventCandidateScore",
    "EventMappingDecision",
    "EventMappingReason",
    "EventMappingStatus",
    "EventMatchingPolicy",
    "EventMatchingScorer",
    "EventMatchingWeights",
    "PostgresEventMatchingService",
    "UnresolvedEventMappingError",
    "normalize_entity_name",
    "typographically_equal",
]
