"""Vocabulaires canoniques partagés par les modes mock et réel."""

from enum import StrEnum


class DataMode(StrEnum):
    """Origine isolée des données applicatives."""

    MOCK = "mock"
    REAL = "real"


class GameTitle(StrEnum):
    """Jeux activés dans le périmètre courant."""

    LEAGUE_OF_LEGENDS = "lol"


class MarketType(StrEnum):
    """Marchés canoniques actuellement contractuels."""

    MATCH_WINNER = "MATCH_WINNER"


class MarketPeriod(StrEnum):
    """Période canonique d'un marché LoL."""

    SERIES = "SERIES"
    GAME_1 = "GAME_1"
    GAME_2 = "GAME_2"
    GAME_3 = "GAME_3"
    GAME_4 = "GAME_4"
    GAME_5 = "GAME_5"


class SelectionType(StrEnum):
    """Issue normalisée indépendamment du libellé fournisseur."""

    TEAM_A = "TEAM_A"
    TEAM_B = "TEAM_B"
    DRAW = "DRAW"
    OVER = "OVER"
    UNDER = "UNDER"


class ValueGrade(StrEnum):
    """Classement non promotionnel d'un écart de prix."""

    STRONG_VALUE = "STRONG_VALUE"
    VALUE = "VALUE"
    WATCH = "WATCH"
    NO_EDGE = "NO_EDGE"
    BLOCKED = "BLOCKED"


class FreshnessStatus(StrEnum):
    """Fraîcheur normative d'une source ou d'un résultat."""

    FRESH = "fresh"
    STALE = "stale"
    DEGRADED = "degraded"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class AbstentionReason(StrEnum):
    """Raisons d'abstention définies par la SFG."""

    ODDS_STALE = "ODDS_STALE"
    MARKET_SUSPENDED = "MARKET_SUSPENDED"
    EVENT_MAPPING_AMBIGUOUS = "EVENT_MAPPING_AMBIGUOUS"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    ROSTER_UNCERTAIN = "ROSTER_UNCERTAIN"
    SOURCE_STALE = "SOURCE_STALE"
    MODEL_STALE = "MODEL_STALE"
    OUT_OF_DISTRIBUTION = "OUT_OF_DISTRIBUTION"
    CALIBRATION_FAILED = "CALIBRATION_FAILED"
    EDGE_TOO_SMALL = "EDGE_TOO_SMALL"
    EXPECTED_VALUE_TOO_SMALL = "EXPECTED_VALUE_TOO_SMALL"
    CONSERVATIVE_EV_NEGATIVE = "CONSERVATIVE_EV_NEGATIVE"
    CONSERVATIVE_EV_TOO_SMALL = "CONSERVATIVE_EV_TOO_SMALL"
    MARKET_RULES_UNKNOWN = "MARKET_RULES_UNKNOWN"
    PATCH_CONTEXT_UNKNOWN = "PATCH_CONTEXT_UNKNOWN"
    EVENT_ALREADY_STARTED = "EVENT_ALREADY_STARTED"
    CAPABILITY_DISABLED = "CAPABILITY_DISABLED"
    SELECTION_MISSING = "SELECTION_MISSING"
    MARKET_OUTCOMES_INCOMPLETE = "MARKET_OUTCOMES_INCOMPLETE"
    ODDS_TEMPORAL_ORDER_INVALID = "ODDS_TEMPORAL_ORDER_INVALID"
    LIVE_BETTING_OUT_OF_SCOPE = "LIVE_BETTING_OUT_OF_SCOPE"
    ODDS_INFORMATIONAL_ONLY = "ODDS_INFORMATIONAL_ONLY"


SFG_ABSTENTION_REASONS: tuple[AbstentionReason, ...] = (
    AbstentionReason.ODDS_STALE,
    AbstentionReason.MARKET_SUSPENDED,
    AbstentionReason.EVENT_MAPPING_AMBIGUOUS,
    AbstentionReason.INSUFFICIENT_HISTORY,
    AbstentionReason.ROSTER_UNCERTAIN,
    AbstentionReason.SOURCE_STALE,
    AbstentionReason.MODEL_STALE,
    AbstentionReason.OUT_OF_DISTRIBUTION,
    AbstentionReason.CALIBRATION_FAILED,
    AbstentionReason.EDGE_TOO_SMALL,
    AbstentionReason.CONSERVATIVE_EV_NEGATIVE,
    AbstentionReason.MARKET_RULES_UNKNOWN,
    AbstentionReason.PATCH_CONTEXT_UNKNOWN,
    AbstentionReason.EVENT_ALREADY_STARTED,
    AbstentionReason.CAPABILITY_DISABLED,
)

_ABSTENTION_REASON_PRIORITY = {reason: index for index, reason in enumerate(AbstentionReason)}


def order_abstention_reasons(
    reasons: tuple[AbstentionReason, ...],
) -> tuple[AbstentionReason, ...]:
    """Dédupliquer et ordonner les raisons selon le contrat public."""

    if any(not isinstance(reason, AbstentionReason) for reason in reasons):
        raise TypeError("chaque raison doit être une AbstentionReason")
    return tuple(sorted(set(reasons), key=_ABSTENTION_REASON_PRIORITY.__getitem__))


class OddsPhase(StrEnum):
    """Phase d'utilisation d'une cote, le live restant hors du MVP."""

    PREMATCH = "prematch"
    LIVE = "live"


class ProviderStatus(StrEnum):
    """Disponibilité d'un fournisseur de cotes."""

    OPERATIONAL = "operational"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class MarketStatus(StrEnum):
    """État observé d'un marché fournisseur."""

    OPEN = "open"
    SUSPENDED = "suspended"
    SETTLED = "settled"
    VOID = "void"


class EventStatus(StrEnum):
    """État annoncé d'un événement."""

    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class ModelStatus(StrEnum):
    """Cycle de vie d'une version de modèle."""

    CANDIDATE = "candidate"
    CHAMPION = "champion"
    RETIRED = "retired"
    BLOCKED = "blocked"


class BacktestKind(StrEnum):
    """Nature statistique ou financière d'un backtest."""

    STATISTICAL = "statistical"
    FINANCIAL = "financial"


class PaperBetStatus(StrEnum):
    """Cycle de règlement d'un pari fictif."""

    OPEN = "open"
    WON = "won"
    LOST = "lost"
    PUSH = "push"
    VOID = "void"
    PENDING_REVIEW = "pending_review"


class MappingReviewStatus(StrEnum):
    """Cycle de décision d'une ambiguïté de mapping."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
