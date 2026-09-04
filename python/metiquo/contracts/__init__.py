"""Contrats publics canoniques de Metiquo."""

from pydantic import BaseModel

from metiquo.contracts.entities import Event, Market, OddsSnapshot
from metiquo.contracts.mapping import MappingCandidate, MappingReview
from metiquo.contracts.ml import BacktestSummary, ModelSummary
from metiquo.contracts.odds_provider import (
    OddsCaptureResult,
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
    ProviderSelection,
)
from metiquo.contracts.operations import (
    AliasRecord,
    AuditEntry,
    DataQualityIssue,
    IngestionRunSummary,
    JobSummary,
)
from metiquo.contracts.paper import PaperBet
from metiquo.contracts.pricing import (
    ContractMetadata,
    Opportunity,
    Prediction,
    Quality,
    Value,
)

DOMAIN_CONTRACT_MODELS: tuple[type[BaseModel], ...] = (
    Event,
    Market,
    OddsSnapshot,
    Prediction,
    Value,
    Quality,
    ContractMetadata,
    Opportunity,
    ModelSummary,
    BacktestSummary,
    PaperBet,
    MappingCandidate,
    MappingReview,
    ProviderEvent,
    ProviderSelection,
    ProviderMarket,
    OddsCaptureResult,
    ProviderHealth,
    IngestionRunSummary,
    DataQualityIssue,
    JobSummary,
    AuditEntry,
    AliasRecord,
)

__all__ = [
    "DOMAIN_CONTRACT_MODELS",
    "AliasRecord",
    "AuditEntry",
    "BacktestSummary",
    "ContractMetadata",
    "DataQualityIssue",
    "Event",
    "IngestionRunSummary",
    "JobSummary",
    "MappingCandidate",
    "MappingReview",
    "Market",
    "ModelSummary",
    "OddsCaptureResult",
    "OddsSnapshot",
    "Opportunity",
    "PaperBet",
    "Prediction",
    "ProviderEvent",
    "ProviderHealth",
    "ProviderMarket",
    "ProviderSelection",
    "Quality",
    "Value",
]
