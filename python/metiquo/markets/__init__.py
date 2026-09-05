"""Plugins de marchés activés par capacités et modèles vérifiés."""

from metiquo.markets.game_winner import (
    GAME_WINNER_PLUGIN_VERSION,
    GameWinnerBenchmarkTrainer,
    GameWinnerCapabilityGate,
    GameWinnerLabel,
    GameWinnerMarketPlugin,
    GameWinnerPrediction,
    GameWinnerPrice,
    GameWinnerProbability,
    GameWinnerSettlement,
    GameWinnerTrainingBackend,
    MarketPlugin,
    PluginAvailability,
    PluginDisabledError,
)

__all__ = [
    "GAME_WINNER_PLUGIN_VERSION",
    "GameWinnerBenchmarkTrainer",
    "GameWinnerCapabilityGate",
    "GameWinnerLabel",
    "GameWinnerMarketPlugin",
    "GameWinnerPrediction",
    "GameWinnerPrice",
    "GameWinnerProbability",
    "GameWinnerSettlement",
    "GameWinnerTrainingBackend",
    "MarketPlugin",
    "PluginAvailability",
    "PluginDisabledError",
]
