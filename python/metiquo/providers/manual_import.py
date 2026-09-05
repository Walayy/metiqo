"""Fournisseur de cotes alimenté par documents CSV ou JSON validés atomiquement."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Self, cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, ValidationError, model_validator

from metiquo.contracts import OddsCaptureResult, OddsSnapshot
from metiquo.contracts.base import (
    ContractModel,
    DecimalOddsValue,
    NonEmptyText,
    UtcDateTime,
    VersionText,
)
from metiquo.contracts.enums import (
    EventStatus,
    GameTitle,
    MarketPeriod,
    MarketStatus,
    MarketType,
    ProviderStatus,
    SelectionType,
)
from metiquo.contracts.odds_provider import (
    ProviderEvent,
    ProviderHealth,
    ProviderMarket,
    ProviderSelection,
)
from metiquo.foundation.time import Clock, SystemClock
from metiquo.providers.identity import provider_entity_uuid

type ManualImportFormat = Literal["csv", "json"]

MANUAL_IMPORT_COLUMNS = (
    "provider",
    "provider_event_id",
    "game_title",
    "competition",
    "participant_a",
    "participant_b",
    "starts_at",
    "best_of",
    "event_status",
    "provider_market_id",
    "market_label",
    "market_type",
    "period",
    "line",
    "provider_selection_id",
    "selection",
    "selection_label",
    "decimal_odds",
    "market_status",
    "captured_at",
    "timestamp_reliable",
    "settlement_rules_version",
    "provenance_reference",
)


class _ManualOddsRow(ContractModel):
    provider: NonEmptyText
    provider_event_id: NonEmptyText
    game_title: GameTitle
    competition: NonEmptyText
    participant_a: NonEmptyText
    participant_b: NonEmptyText
    starts_at: UtcDateTime
    best_of: int | None = Field(default=None, ge=1, le=9)
    event_status: EventStatus
    provider_market_id: NonEmptyText
    market_label: NonEmptyText
    market_type: MarketType
    period: MarketPeriod
    line: Decimal | None = Field(default=None, allow_inf_nan=False)
    provider_selection_id: NonEmptyText
    selection: SelectionType
    selection_label: NonEmptyText
    decimal_odds: DecimalOddsValue
    market_status: MarketStatus
    captured_at: UtcDateTime
    timestamp_reliable: bool
    settlement_rules_version: VersionText
    provenance_reference: VersionText

    @model_validator(mode="after")
    def participants_are_distinct(self) -> Self:
        if self.participant_a.strip().casefold() == self.participant_b.strip().casefold():
            raise ValueError("les participants de l'événement doivent être distincts")
        return self


@dataclass(frozen=True, slots=True)
class ManualImportIssue:
    """Erreur structurée rattachée à la ligne source qui l'a produite."""

    row_number: int | None
    code: str
    field: str | None
    message: str


@dataclass(frozen=True, slots=True)
class ManualImportResult:
    """Décision atomique et clé d'idempotence d'un document."""

    import_key: str
    received_rows: int
    imported_rows: int
    committed: bool
    duplicate: bool
    issues: tuple[ManualImportIssue, ...]


@dataclass(frozen=True, slots=True)
class _ImportedRow:
    value: _ManualOddsRow
    import_key: str
    row_number: int


class ManualImportOddsProvider:
    """Adapter sans réseau dont chaque document valide devient visible en une seule étape."""

    def __init__(self, provider_code: str, *, clock: Clock | None = None) -> None:
        normalized_code = provider_code.strip()
        if not normalized_code:
            raise ValueError("provider_code est requis")
        self.provider_code = normalized_code
        self._clock = clock or SystemClock()
        self._rows: tuple[_ImportedRow, ...] = ()
        self._import_keys: frozenset[str] = frozenset()

    @property
    def imported_document_count(self) -> int:
        return len(self._import_keys)

    @property
    def observation_count(self) -> int:
        return len(self._rows)

    def import_document(
        self,
        payload: bytes,
        *,
        document_format: ManualImportFormat,
    ) -> ManualImportResult:
        """Valider toutes les lignes puis publier le document, ou ne rien modifier."""

        import_key = f"sha256:{hashlib.sha256(payload).hexdigest()}"
        if import_key in self._import_keys:
            return ManualImportResult(import_key, 0, 0, False, True, ())

        documents, document_issues = _decode_document(payload, document_format)
        staged: list[_ImportedRow] = []
        issues = list(document_issues)
        for row_number, document in documents:
            try:
                row = _validate_row(document, document_format)
            except ValidationError as error:
                issues.extend(_validation_issues(row_number, error))
                continue
            if row.provider != self.provider_code:
                issues.append(
                    ManualImportIssue(
                        row_number,
                        "PROVIDER_MISMATCH",
                        "provider",
                        f"provider attendu : {self.provider_code}",
                    )
                )
            if row.captured_at > self._clock.now().value:
                issues.append(
                    ManualImportIssue(
                        row_number,
                        "CAPTURE_IN_FUTURE",
                        "captured_at",
                        "captured_at ne peut pas être postérieur à l'import",
                    )
                )
            staged.append(_ImportedRow(row, import_key, row_number))

        issues.extend(_consistency_issues((*self._rows, *staged), len(self._rows)))
        if issues or not staged:
            if not staged and not issues:
                issues.append(
                    ManualImportIssue(None, "EMPTY_DOCUMENT", None, "aucune ligne à importer")
                )
            return ManualImportResult(
                import_key,
                len(documents),
                0,
                False,
                False,
                tuple(issues),
            )

        self._rows = (*self._rows, *staged)
        self._import_keys = self._import_keys | {import_key}
        return ManualImportResult(import_key, len(documents), len(staged), True, False, ())

    def list_events(
        self,
        starts_from: datetime,
        starts_to: datetime,
        game_title: GameTitle,
    ) -> tuple[ProviderEvent, ...]:
        if starts_to < starts_from:
            raise ValueError("startsTo doit être postérieur ou égal à startsFrom")
        events: list[ProviderEvent] = []
        for event_id in sorted({item.value.provider_event_id for item in self._rows}):
            rows = [item for item in self._rows if item.value.provider_event_id == event_id]
            latest = max(rows, key=lambda item: (item.value.captured_at, item.row_number))
            value = latest.value
            if (
                value.game_title is not game_title
                or not starts_from <= value.starts_at <= starts_to
            ):
                continue
            events.append(
                ProviderEvent(
                    provider_event_id=event_id,
                    game_title=value.game_title,
                    competition=value.competition,
                    participants=(value.participant_a, value.participant_b),
                    starts_at=value.starts_at,
                    best_of=value.best_of,
                    status=value.event_status,
                    collected_at=value.captured_at,
                    source_reference=value.provenance_reference,
                )
            )
        return tuple(events)

    def get_event_markets(self, provider_event_id: str) -> tuple[ProviderMarket, ...]:
        event_rows = [
            item for item in self._rows if item.value.provider_event_id == provider_event_id
        ]
        markets: list[ProviderMarket] = []
        for market_id in sorted({item.value.provider_market_id for item in event_rows}):
            rows = [item for item in event_rows if item.value.provider_market_id == market_id]
            latest_by_selection: dict[str, _ImportedRow] = {}
            for item in rows:
                selection_id = item.value.provider_selection_id
                current = latest_by_selection.get(selection_id)
                if current is None or (item.value.captured_at, item.row_number) > (
                    current.value.captured_at,
                    current.row_number,
                ):
                    latest_by_selection[selection_id] = item
            selected = tuple(latest_by_selection[key] for key in sorted(latest_by_selection))
            latest = max(selected, key=lambda item: (item.value.captured_at, item.row_number))
            value = latest.value
            markets.append(
                ProviderMarket(
                    provider_event_id=provider_event_id,
                    provider_market_id=market_id,
                    raw_label=value.market_label,
                    market_type=value.market_type,
                    period=value.period,
                    line=value.line,
                    selections=tuple(
                        ProviderSelection(
                            provider_selection_id=item.value.provider_selection_id,
                            selection=item.value.selection,
                            label=item.value.selection_label,
                            decimal_odds=item.value.decimal_odds,
                        )
                        for item in selected
                    ),
                    status=value.market_status,
                    captured_at=value.captured_at,
                    settlement_rules_version=value.settlement_rules_version,
                )
            )
        return tuple(markets)

    def capture_snapshot(self, provider_event_id: str) -> OddsCaptureResult:
        rows = [item for item in self._rows if item.value.provider_event_id == provider_event_id]
        if not rows:
            raise LookupError(f"Événement fournisseur inconnu : {provider_event_id}")
        captured_at = self._clock.now().value
        snapshots = tuple(
            _snapshot(self.provider_code, item, captured_at)
            for item in sorted(rows, key=lambda item: (item.value.captured_at, item.row_number))
        )
        return OddsCaptureResult(
            provider_event_id=provider_event_id,
            captured_at=captured_at,
            snapshots=snapshots,
        )

    def health(self) -> ProviderHealth:
        checked_at = self._clock.now().value
        return ProviderHealth(
            provider_code=self.provider_code,
            status=ProviderStatus.OPERATIONAL if self._rows else ProviderStatus.UNAVAILABLE,
            checked_at=checked_at,
            last_success_at=max((item.value.captured_at for item in self._rows), default=None),
            detail=None if self._rows else "Aucun document manuel valide importé",
        )


def _decode_document(
    payload: bytes,
    document_format: ManualImportFormat,
) -> tuple[tuple[tuple[int, Mapping[str, Any]], ...], tuple[ManualImportIssue, ...]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        return (), (ManualImportIssue(None, "ENCODING_INVALID", None, str(error)),)
    if document_format == "csv":
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if tuple(reader.fieldnames or ()) != MANUAL_IMPORT_COLUMNS:
            return (), (
                ManualImportIssue(
                    1,
                    "CSV_HEADER_INVALID",
                    None,
                    "l'en-tête CSV doit correspondre exactement au contrat manuel",
                ),
            )
        return tuple(
            (line, cast(Mapping[str, Any], _coerce_csv_row(row)))
            for line, row in enumerate(reader, start=2)
        ), ()
    if document_format == "json":
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as error:
            return (), (ManualImportIssue(None, "JSON_INVALID", None, str(error)),)
        if not isinstance(decoded, list):
            return (), (
                ManualImportIssue(
                    None, "JSON_ROOT_INVALID", None, "la racine JSON doit être une liste"
                ),
            )
        documents: list[tuple[int, Mapping[str, Any]]] = []
        issues: list[ManualImportIssue] = []
        for row_number, value in enumerate(decoded, start=1):
            if isinstance(value, dict):
                documents.append((row_number, cast(Mapping[str, Any], value)))
            else:
                issues.append(
                    ManualImportIssue(
                        row_number,
                        "JSON_ROW_INVALID",
                        None,
                        "chaque ligne JSON doit être un objet",
                    )
                )
        return tuple(documents), tuple(issues)
    raise ValueError(f"format manuel non supporté : {document_format}")


def _coerce_csv_row(row: Mapping[str, str | None]) -> dict[str, object]:
    converted: dict[str, object] = dict(row)
    for key in ("best_of", "line"):
        if converted.get(key) == "":
            converted[key] = None
    best_of = converted.get("best_of")
    if isinstance(best_of, str) and best_of.isdecimal():
        converted["best_of"] = int(best_of)
    reliable = converted.get("timestamp_reliable")
    if isinstance(reliable, str) and reliable.casefold() in {"true", "false"}:
        converted["timestamp_reliable"] = reliable.casefold() == "true"
    return converted


def _validate_row(
    document: Mapping[str, Any], document_format: ManualImportFormat
) -> _ManualOddsRow:
    del document_format
    return _ManualOddsRow.model_validate_json(
        json.dumps(dict(document), ensure_ascii=False, separators=(",", ":"))
    )


def _validation_issues(row_number: int, error: ValidationError) -> tuple[ManualImportIssue, ...]:
    return tuple(
        ManualImportIssue(
            row_number,
            str(item["type"]).upper(),
            ".".join(str(part) for part in item["loc"]) or None,
            str(item["msg"]),
        )
        for item in error.errors(include_url=False)
    )


def _consistency_issues(
    rows: Sequence[_ImportedRow],
    existing_count: int,
) -> tuple[ManualImportIssue, ...]:
    issues: list[ManualImportIssue] = []
    event_signatures: dict[str, tuple[object, ...]] = {}
    market_signatures: dict[tuple[str, str], tuple[object, ...]] = {}
    selection_signatures: dict[tuple[str, str, str], tuple[object, ...]] = {}
    observation_keys: set[tuple[str, str, str, datetime]] = set()
    for index, item in enumerate(rows):
        value = item.value
        event_key = value.provider_event_id
        market_key = (event_key, value.provider_market_id)
        selection_key = (*market_key, value.provider_selection_id)
        event_signature = (
            value.game_title,
            value.competition,
            value.participant_a,
            value.participant_b,
            value.starts_at,
            value.best_of,
        )
        market_signature = (
            value.market_label,
            value.market_type,
            value.period,
            value.line,
            value.settlement_rules_version,
        )
        selection_signature = (value.selection, value.selection_label)
        previous_event = event_signatures.setdefault(event_key, event_signature)
        if index >= existing_count and previous_event != event_signature:
            issues.append(
                ManualImportIssue(item.row_number, "EVENT_CONFLICT", None, "identité incohérente")
            )
        previous_market = market_signatures.setdefault(market_key, market_signature)
        if index >= existing_count and previous_market != market_signature:
            issues.append(
                ManualImportIssue(item.row_number, "MARKET_CONFLICT", None, "identité incohérente")
            )
        previous_selection = selection_signatures.setdefault(selection_key, selection_signature)
        if index >= existing_count and previous_selection != selection_signature:
            issues.append(
                ManualImportIssue(
                    item.row_number,
                    "SELECTION_CONFLICT",
                    None,
                    "identité incohérente",
                )
            )
        observation_key = (*selection_key, value.captured_at)
        if observation_key in observation_keys and index >= existing_count:
            issues.append(
                ManualImportIssue(
                    item.row_number,
                    "OBSERVATION_DUPLICATE",
                    None,
                    "observation déjà présente pour cet instant",
                )
            )
        observation_keys.add(observation_key)
    return tuple(issues)


def _snapshot(provider_code: str, item: _ImportedRow, observed_at: datetime) -> OddsSnapshot:
    value = item.value
    raw_probability = (Decimal(1) / value.decimal_odds).quantize(Decimal("0.00000001"))
    identity = (
        f"{provider_code}:{value.provider_event_id}:{value.provider_market_id}:"
        f"{value.provider_selection_id}:{value.captured_at.isoformat()}:{item.import_key}"
    )
    return OddsSnapshot(
        odds_snapshot_id=uuid5(NAMESPACE_URL, f"metiquo:manual:snapshot:{identity}"),
        event_id=provider_entity_uuid(provider_code, "event", value.provider_event_id),
        market_id=provider_entity_uuid(
            provider_code,
            "market",
            f"{value.provider_event_id}:{value.provider_market_id}",
        ),
        selection=value.selection,
        provider=provider_code,
        provider_status=ProviderStatus.OPERATIONAL,
        market_status=value.market_status,
        decimal_odds=value.decimal_odds,
        captured_at=value.captured_at,
        age_seconds=int((observed_at - value.captured_at).total_seconds()),
        raw_implied_probability=raw_probability,
        no_vig_probability=None,
        informational_only=not value.timestamp_reliable,
        provenance_reference=value.provenance_reference,
    )
