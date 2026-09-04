"""Contrats publics canoniques de Metiquo."""

from pydantic import BaseModel

from metiquo.contracts.entities import Event, Market, OddsSnapshot
from metiquo.contracts.mapping import MappingCandidate, MappingReview
from metiquo.contracts.ml import BacktestSummary, ModelSummary
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
)

__all__ = [
    "DOMAIN_CONTRACT_MODELS",
    "BacktestSummary",
    "ContractMetadata",
    "Event",
    "MappingCandidate",
    "MappingReview",
    "Market",
    "ModelSummary",
    "OddsSnapshot",
    "Opportunity",
    "PaperBet",
    "Prediction",
    "Quality",
    "Value",
]
