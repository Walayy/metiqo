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
from metiquo.mapping.market_mapping import (
    CanonicalMarketMapping,
    MarketMappingDecision,
    MarketMappingEngine,
    MarketMappingReason,
    MarketMappingStatus,
    MarketRulesReference,
    PostgresMarketMappingService,
    RawProviderMarket,
    SettlementPolicy,
    UnresolvedMarketMappingError,
    raw_market_from_provider,
)
from metiquo.mapping.normalization import (
    NORMALIZATION_VERSION,
    normalize_entity_name,
    typographically_equal,
)

__all__ = [
    "MATCHING_WEIGHTS_VERSION",
    "NORMALIZATION_VERSION",
    "CanonicalMarketMapping",
    "EventCandidateScore",
    "EventMappingDecision",
    "EventMappingReason",
    "EventMappingStatus",
    "EventMatchingPolicy",
    "EventMatchingScorer",
    "EventMatchingWeights",
    "MarketMappingDecision",
    "MarketMappingEngine",
    "MarketMappingReason",
    "MarketMappingStatus",
    "MarketRulesReference",
    "PostgresEventMatchingService",
    "PostgresMarketMappingService",
    "RawProviderMarket",
    "SettlementPolicy",
    "UnresolvedEventMappingError",
    "UnresolvedMarketMappingError",
    "normalize_entity_name",
    "raw_market_from_provider",
    "typographically_equal",
]
