"""Persistance et reproduction des signaux de value append-only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.contracts.enums import (
    AbstentionReason,
    FreshnessStatus,
    SelectionType,
    ValueGrade,
)
from metiquo.db.ml_models import PrematchPrediction
from metiquo.db.odds_models import (
    EventMappingAttempt,
    EventMappingCandidateScore,
    MappingReviewRecord,
    OddsSnapshotRecord,
    ProviderOddsSelection,
)
from metiquo.db.pricing_models import SignalRecord, ValuePolicyRecord
from metiquo.foundation.finance import DecimalOdds, Probability
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.pricing.abstention import ValueDecision
from metiquo.pricing.no_vig import NoVigQuote, implied_probability
from metiquo.pricing.value import ValuePrice, ValuePricingEngine, ValuePricingInput

_METRIC_QUANTUM = Decimal("1E-28")
_CONFIDENCE_QUANTUM = Decimal("1E-8")
_ADMITTED_GRADES = frozenset((ValueGrade.STRONG_VALUE, ValueGrade.VALUE, ValueGrade.WATCH))
_ABSTAINED_GRADES = frozenset((ValueGrade.NO_EDGE, ValueGrade.BLOCKED))
_STORED_VALUE_KEYS = (
    "odds_snapshot_id",
    "prediction_id",
    "event_mapping_attempt_id",
    "policy_version",
    "selection_type",
    "offered_odds",
    "raw_implied_probability",
    "model_probability",
    "model_probability_low",
    "model_probability_high",
    "value_computed",
    "pricing_policy_version",
    "no_vig_policy_version",
    "no_vig_probability",
    "fair_odds",
    "edge",
    "expected_value",
    "conservative_expected_value",
    "grade",
    "abstention_reasons",
    "mapping_confidence",
    "source_freshness",
    "odds_age_seconds",
    "computed_at",
)


class SignalIntegrityError(ValueError):
    """Les références d'un signal ne reproduisent pas sa décision."""


@dataclass(frozen=True, slots=True)
class SignalPublication:
    odds_snapshot_id: UUID
    prediction_id: UUID
    event_mapping_attempt_id: UUID
    selection: SelectionType
    grade: ValueGrade
    decision: ValueDecision
    mapping_confidence: Probability
    source_freshness: FreshnessStatus
    odds_age_seconds: int
    no_vig_policy_version: str | None = None

    def __post_init__(self) -> None:
        if self.selection not in {SelectionType.TEAM_A, SelectionType.TEAM_B}:
            raise SignalIntegrityError("seules les sélections équipe sont prises en charge")
        if not isinstance(self.decision, ValueDecision):
            raise TypeError("decision doit être une ValueDecision")
        if not isinstance(self.mapping_confidence, Probability):
            raise TypeError("mapping_confidence doit être une Probability")
        if not isinstance(self.source_freshness, FreshnessStatus):
            raise TypeError("source_freshness doit être une FreshnessStatus")
        if self.odds_age_seconds < 0:
            raise SignalIntegrityError("odds_age_seconds ne peut pas être négatif")
        if self.decision.is_opportunity and self.grade not in _ADMITTED_GRADES:
            raise SignalIntegrityError("une value admise exige un grade publiable")
        if not self.decision.is_opportunity and self.grade not in _ABSTAINED_GRADES:
            raise SignalIntegrityError("une abstention exige un grade NO_EDGE ou BLOCKED")
        if self.decision.evaluated_value is None and self.grade is not ValueGrade.BLOCKED:
            raise SignalIntegrityError("une abstention sans calcul doit être BLOCKED")
        if (self.no_vig_policy_version is None) == (self.decision.evaluated_value is not None):
            raise SignalIntegrityError(
                "la version no-vig est requise exactement quand la value est calculée"
            )
        if self.no_vig_policy_version is not None:
            version = self.no_vig_policy_version.strip()
            if not version or len(version) > 128:
                raise SignalIntegrityError("no_vig_policy_version est invalide")
            object.__setattr__(self, "no_vig_policy_version", version)


@dataclass(frozen=True, slots=True)
class StoredSignal:
    signal_id: UUID
    odds_snapshot_id: UUID
    prediction_id: UUID
    event_mapping_attempt_id: UUID
    policy_version: str
    selection: SelectionType
    offered_odds: Decimal
    raw_implied_probability: Decimal
    model_probability: Decimal
    model_probability_low: Decimal
    model_probability_high: Decimal
    value_computed: bool
    pricing_policy_version: str | None
    no_vig_policy_version: str | None
    no_vig_probability: Decimal | None
    fair_odds: Decimal | None
    edge: Decimal | None
    expected_value: Decimal | None
    conservative_expected_value: Decimal | None
    grade: ValueGrade
    abstention_reasons: tuple[AbstentionReason, ...]
    mapping_confidence: Decimal
    source_freshness: FreshnessStatus
    odds_age_seconds: int
    computed_at: datetime
    signal_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "computed_at", normalize_utc_datetime(self.computed_at))


@dataclass(frozen=True, slots=True)
class _SignalSources:
    offered_odds: Decimal
    captured_at: datetime
    selection: SelectionType
    mapping_confidence: Decimal
    predicted_at: datetime
    prediction_enabled: bool
    model_probability: Decimal
    model_probability_low: Decimal
    model_probability_high: Decimal


class PostgresSignalRepository:
    """Ajouter un signal une seule fois et en vérifier les preuves immuables."""

    def __init__(self, engine: Engine, clock: Clock | None = None) -> None:
        self.engine = engine
        self._clock = clock or SystemClock()

    def append(self, publication: SignalPublication) -> StoredSignal:
        computed_at = self._clock.now().value
        signals = cast(Table, SignalRecord.__table__)
        with self.engine.begin() as connection:
            _require_policy(connection, publication.decision.policy_version)
            sources = _load_sources(
                connection,
                publication.odds_snapshot_id,
                publication.prediction_id,
                publication.event_mapping_attempt_id,
            )
            values = _build_values(publication, sources, computed_at)
            fingerprint = _content_hash(values)
            signal_id = uuid5(NAMESPACE_URL, f"metiquo:signal:{fingerprint}")
            connection.execute(
                insert(signals)
                .values(id=signal_id, signal_fingerprint=fingerprint, **values)
                .on_conflict_do_nothing(index_elements=[signals.c.signal_fingerprint])
            )
            row = (
                connection.execute(
                    select(signals).where(signals.c.signal_fingerprint == fingerprint)
                )
                .mappings()
                .one()
            )
        return _stored(row)

    def get(self, signal_id: UUID) -> StoredSignal:
        row = self._row(signal_id)
        if row is None:
            raise KeyError(signal_id)
        return _stored(row)

    def list_for_prediction(self, prediction_id: UUID) -> tuple[StoredSignal, ...]:
        signals = cast(Table, SignalRecord.__table__)
        with self.engine.connect() as connection:
            rows = tuple(
                connection.execute(
                    select(signals)
                    .where(signals.c.prediction_id == prediction_id)
                    .order_by(signals.c.computed_at, signals.c.id)
                ).mappings()
            )
        return tuple(_stored(row) for row in rows)

    def reproduce(self, signal_id: UUID) -> StoredSignal:
        signals = cast(Table, SignalRecord.__table__)
        with self.engine.connect() as connection:
            row = (
                connection.execute(select(signals).where(signals.c.id == signal_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise KeyError(signal_id)
            _require_policy(connection, cast(str, row["policy_version"]))
            sources = _load_sources(
                connection,
                cast(UUID, row["odds_snapshot_id"]),
                cast(UUID, row["prediction_id"]),
                cast(UUID, row["event_mapping_attempt_id"]),
            )
        _verify_row(row, sources)
        values = {key: row[key] for key in _STORED_VALUE_KEYS}
        if _content_hash(values) != row["signal_fingerprint"]:
            raise SignalIntegrityError("l'empreinte du signal ne reproduit pas son contenu")
        return _stored(row)

    def _row(self, signal_id: UUID) -> RowMapping | None:
        signals = cast(Table, SignalRecord.__table__)
        with self.engine.connect() as connection:
            return (
                connection.execute(select(signals).where(signals.c.id == signal_id))
                .mappings()
                .one_or_none()
            )


def _require_policy(connection: Connection, version: str) -> None:
    policies = cast(Table, ValuePolicyRecord.__table__)
    if (
        connection.execute(
            select(policies.c.id).where(policies.c.version == version)
        ).scalar_one_or_none()
        is None
    ):
        raise SignalIntegrityError("la politique de value est introuvable")


def _load_sources(
    connection: Connection,
    odds_snapshot_id: UUID,
    prediction_id: UUID,
    event_mapping_attempt_id: UUID,
) -> _SignalSources:
    snapshots = cast(Table, OddsSnapshotRecord.__table__)
    selections = cast(Table, ProviderOddsSelection.__table__)
    predictions = cast(Table, PrematchPrediction.__table__)
    attempts = cast(Table, EventMappingAttempt.__table__)
    candidates = cast(Table, EventMappingCandidateScore.__table__)
    reviews = cast(Table, MappingReviewRecord.__table__)
    odds_row = connection.execute(
        select(
            snapshots.c.decimal_odds,
            snapshots.c.captured_at,
            snapshots.c.timestamp_reliable,
            snapshots.c.event_id,
            selections.c.selection_type,
        )
        .select_from(snapshots.join(selections, selections.c.id == snapshots.c.selection_id))
        .where(snapshots.c.id == odds_snapshot_id)
    ).one_or_none()
    if odds_row is None:
        raise SignalIntegrityError("le snapshot de cote est introuvable")
    captured_at = odds_row.captured_at
    if not isinstance(captured_at, datetime) or not bool(odds_row.timestamp_reliable):
        raise SignalIntegrityError("le snapshot de cote doit avoir un timestamp fiable")
    mapping = (
        connection.execute(select(attempts).where(attempts.c.id == event_mapping_attempt_id))
        .mappings()
        .one_or_none()
    )
    if mapping is None or mapping["provider_event_id"] != odds_row.event_id:
        raise SignalIntegrityError("le mapping ne correspond pas au snapshot de cote")
    canonical_event_id = cast(UUID | None, mapping["selected_event_id"])
    mapping_confidence = cast(Decimal, mapping["top_score"])
    selections_inverted = bool(mapping["selections_inverted"])
    if mapping["result_status"] != "auto_matched":
        review = (
            connection.execute(
                select(reviews).where(
                    reviews.c.attempt_id == event_mapping_attempt_id,
                    reviews.c.status == "approved",
                )
            )
            .mappings()
            .one_or_none()
        )
        if review is None:
            raise SignalIntegrityError("le mapping d'événement n'est pas résolu")
        canonical_event_id = cast(UUID, review["selected_event_id"])
        candidate = (
            connection.execute(
                select(candidates).where(
                    candidates.c.attempt_id == event_mapping_attempt_id,
                    candidates.c.canonical_event_id == canonical_event_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if candidate is None:
            raise SignalIntegrityError("le candidat approuvé du mapping est introuvable")
        mapping_confidence = cast(Decimal, candidate["total_score"])
        selections_inverted = bool(candidate["selections_inverted"])
    if canonical_event_id is None:
        raise SignalIntegrityError("le mapping d'événement n'est pas résolu")
    prediction = (
        connection.execute(select(predictions).where(predictions.c.id == prediction_id))
        .mappings()
        .one_or_none()
    )
    if prediction is None:
        raise SignalIntegrityError("la prédiction est introuvable")
    if prediction["event_id"] != canonical_event_id:
        raise SignalIntegrityError("la prédiction ne correspond pas à l'événement résolu")
    selection = SelectionType(str(odds_row.selection_type))
    if selections_inverted:
        selection = _invert_team_selection(selection)
    if selection is SelectionType.TEAM_A:
        probability_keys = ("team_a_probability", "team_a_low", "team_a_high")
    elif selection is SelectionType.TEAM_B:
        probability_keys = ("team_b_probability", "team_b_low", "team_b_high")
    else:
        raise SignalIntegrityError("la sélection du snapshot ne correspond pas au modèle binaire")
    return _SignalSources(
        offered_odds=cast(Decimal, odds_row.decimal_odds),
        captured_at=normalize_utc_datetime(captured_at),
        selection=selection,
        mapping_confidence=mapping_confidence,
        predicted_at=normalize_utc_datetime(cast(datetime, prediction["predicted_at"])),
        prediction_enabled=bool(prediction["enabled"]),
        model_probability=cast(Decimal, prediction[probability_keys[0]]),
        model_probability_low=cast(Decimal, prediction[probability_keys[1]]),
        model_probability_high=cast(Decimal, prediction[probability_keys[2]]),
    )


def _build_values(
    publication: SignalPublication,
    sources: _SignalSources,
    computed_at: datetime,
) -> dict[str, object]:
    if publication.selection is not sources.selection:
        raise SignalIntegrityError("la sélection demandée ne correspond pas au snapshot")
    if publication.decision.is_opportunity and not sources.prediction_enabled:
        raise SignalIntegrityError("une value admise exige une prédiction activée")
    if _confidence(publication.mapping_confidence.value) != _confidence(sources.mapping_confidence):
        raise SignalIntegrityError("la confiance déclarée ne correspond pas au mapping")
    age_seconds = int((computed_at - sources.captured_at).total_seconds())
    if age_seconds < 0 or publication.odds_age_seconds != age_seconds:
        raise SignalIntegrityError("l'âge déclaré ne correspond pas au snapshot utilisé")
    raw_implied = implied_probability(DecimalOdds(sources.offered_odds)).value
    value = publication.decision.evaluated_value
    if value is not None:
        _verify_value(value, publication.selection, sources, raw_implied)
    return {
        "odds_snapshot_id": publication.odds_snapshot_id,
        "prediction_id": publication.prediction_id,
        "event_mapping_attempt_id": publication.event_mapping_attempt_id,
        "policy_version": publication.decision.policy_version,
        "selection_type": publication.selection.value,
        "offered_odds": _metric(sources.offered_odds),
        "raw_implied_probability": _metric(raw_implied),
        "model_probability": _metric(sources.model_probability),
        "model_probability_low": _metric(sources.model_probability_low),
        "model_probability_high": _metric(sources.model_probability_high),
        "value_computed": value is not None,
        "pricing_policy_version": value.policy_version if value is not None else None,
        "no_vig_policy_version": publication.no_vig_policy_version,
        "no_vig_probability": (
            _metric(value.input.book_quote.no_vig_probability.value) if value is not None else None
        ),
        "fair_odds": (
            _metric(value.fair_odds.value)
            if value is not None and value.fair_odds is not None
            else None
        ),
        "edge": _metric(value.edge) if value is not None else None,
        "expected_value": _metric(value.expected_value) if value is not None else None,
        "conservative_expected_value": (
            _metric(value.conservative_expected_value) if value is not None else None
        ),
        "grade": publication.grade.value,
        "abstention_reasons": [reason.value for reason in publication.decision.reasons],
        "mapping_confidence": _confidence(sources.mapping_confidence),
        "source_freshness": publication.source_freshness.value,
        "odds_age_seconds": publication.odds_age_seconds,
        "computed_at": normalize_utc_datetime(computed_at),
    }


def _verify_value(
    value: ValuePrice,
    selection: SelectionType,
    sources: _SignalSources,
    raw_implied: Decimal,
) -> None:
    quote = value.input.book_quote
    if quote.selection is not selection or quote.decimal_odds.value != sources.offered_odds:
        raise SignalIntegrityError("la value ne référence pas la cote sélectionnée")
    if _metric(quote.raw_implied_probability.value) != _metric(raw_implied):
        raise SignalIntegrityError("la probabilité implicite ne correspond pas à la cote")
    if value.input.model_probability.value != sources.model_probability:
        raise SignalIntegrityError("la probabilité modèle ne correspond pas à la prédiction")
    if value.input.model_probability_low.value != sources.model_probability_low:
        raise SignalIntegrityError("la borne prudente ne correspond pas à la prédiction")


def _verify_row(row: RowMapping, sources: _SignalSources) -> None:
    if SelectionType(str(row["selection_type"])) is not sources.selection:
        raise SignalIntegrityError("la sélection persistée ne reproduit pas le snapshot")
    comparisons = (
        ("offered_odds", sources.offered_odds),
        ("model_probability", sources.model_probability),
        ("model_probability_low", sources.model_probability_low),
        ("model_probability_high", sources.model_probability_high),
    )
    if any(_metric(cast(Decimal, row[key])) != _metric(value) for key, value in comparisons):
        raise SignalIntegrityError("les entrées persistées divergent de leurs références")
    if _confidence(cast(Decimal, row["mapping_confidence"])) != _confidence(
        sources.mapping_confidence
    ):
        raise SignalIntegrityError("la confiance persistée diverge du mapping")
    computed_at = normalize_utc_datetime(cast(datetime, row["computed_at"]))
    age_seconds = int((computed_at - sources.captured_at).total_seconds())
    if age_seconds != row["odds_age_seconds"]:
        raise SignalIntegrityError("l'âge de cote persisté n'est pas reproductible")
    raw = implied_probability(DecimalOdds(sources.offered_odds)).value
    if _metric(cast(Decimal, row["raw_implied_probability"])) != _metric(raw):
        raise SignalIntegrityError("la probabilité implicite persistée n'est pas reproductible")
    if not bool(row["value_computed"]):
        return
    no_vig_probability = cast(Decimal, row["no_vig_probability"])
    reproduced = ValuePricingEngine().calculate(
        ValuePricingInput(
            NoVigQuote(
                selection=sources.selection,
                decimal_odds=DecimalOdds(sources.offered_odds),
                raw_implied_probability=Probability(raw),
                no_vig_probability=Probability(no_vig_probability),
            ),
            Probability(sources.model_probability),
            Probability(sources.model_probability_low),
        )
    )
    expected = {
        "fair_odds": reproduced.fair_odds.value if reproduced.fair_odds is not None else None,
        "edge": reproduced.edge,
        "expected_value": reproduced.expected_value,
        "conservative_expected_value": reproduced.conservative_expected_value,
    }
    for key, value in expected.items():
        stored = cast(Decimal | None, row[key])
        if stored is None or value is None:
            if stored is not value:
                raise SignalIntegrityError("la cote juste persistée n'est pas reproductible")
        elif _metric(stored) != _metric(value):
            raise SignalIntegrityError(f"la métrique {key} n'est pas reproductible")
    if row["pricing_policy_version"] != reproduced.policy_version:
        raise SignalIntegrityError("la politique de calcul n'est pas reproductible")


def _stored(row: RowMapping) -> StoredSignal:
    return StoredSignal(
        signal_id=cast(UUID, row["id"]),
        odds_snapshot_id=cast(UUID, row["odds_snapshot_id"]),
        prediction_id=cast(UUID, row["prediction_id"]),
        event_mapping_attempt_id=cast(UUID, row["event_mapping_attempt_id"]),
        policy_version=str(row["policy_version"]),
        selection=SelectionType(str(row["selection_type"])),
        offered_odds=cast(Decimal, row["offered_odds"]),
        raw_implied_probability=cast(Decimal, row["raw_implied_probability"]),
        model_probability=cast(Decimal, row["model_probability"]),
        model_probability_low=cast(Decimal, row["model_probability_low"]),
        model_probability_high=cast(Decimal, row["model_probability_high"]),
        value_computed=bool(row["value_computed"]),
        pricing_policy_version=cast(str | None, row["pricing_policy_version"]),
        no_vig_policy_version=cast(str | None, row["no_vig_policy_version"]),
        no_vig_probability=cast(Decimal | None, row["no_vig_probability"]),
        fair_odds=cast(Decimal | None, row["fair_odds"]),
        edge=cast(Decimal | None, row["edge"]),
        expected_value=cast(Decimal | None, row["expected_value"]),
        conservative_expected_value=cast(Decimal | None, row["conservative_expected_value"]),
        grade=ValueGrade(str(row["grade"])),
        abstention_reasons=tuple(
            AbstentionReason(reason) for reason in cast(list[str], row["abstention_reasons"])
        ),
        mapping_confidence=cast(Decimal, row["mapping_confidence"]),
        source_freshness=FreshnessStatus(str(row["source_freshness"])),
        odds_age_seconds=cast(int, row["odds_age_seconds"]),
        computed_at=cast(datetime, row["computed_at"]),
        signal_fingerprint=str(row["signal_fingerprint"]),
    )


def _metric(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return value.quantize(_METRIC_QUANTUM, rounding=ROUND_HALF_EVEN)


def _confidence(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 40
        return value.quantize(_CONFIDENCE_QUANTUM, rounding=ROUND_HALF_EVEN)


def _invert_team_selection(selection: SelectionType) -> SelectionType:
    if selection is SelectionType.TEAM_A:
        return SelectionType.TEAM_B
    if selection is SelectionType.TEAM_B:
        return SelectionType.TEAM_A
    return selection


def _content_hash(values: dict[str, object]) -> str:
    payload = json.dumps(
        {key: _primitive(value) for key, value in values.items()},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _primitive(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return normalize_utc_datetime(value).isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
