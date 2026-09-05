"""Capture transactionnelle et historisation append-only des cotes fournisseur."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, Table, select
from sqlalchemy.dialects.postgresql import insert

from metiquo.contracts import OddsSnapshot
from metiquo.contracts.enums import ProviderStatus
from metiquo.contracts.odds_provider import ProviderEvent, ProviderMarket, ProviderSelection
from metiquo.db.odds_models import (
    OddsProviderHealth,
    OddsProviderRecord,
    OddsSnapshotRecord,
    ProviderOddsEvent,
    ProviderOddsMarket,
    ProviderOddsSelection,
)
from metiquo.foundation.time import Clock, SystemClock
from metiquo.providers import OddsProvider, provider_entity_uuid, provider_market_uuid

type OddsProviderType = Literal["mock", "manual_import", "licensed_feed"]

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class OddsCaptureValidationError(ValueError):
    """La capture fournisseur ne peut pas être reliée sans ambiguïté."""


@dataclass(frozen=True, slots=True)
class OddsCaptureSource:
    """Contexte traçable du payload ayant produit une capture."""

    provider_type: OddsProviderType
    provider_display_name: str
    raw_payload_reference: str
    raw_payload_sha256: str | None = None

    def __post_init__(self) -> None:
        display_name = self.provider_display_name.strip()
        raw_reference = self.raw_payload_reference.strip()
        if not display_name or len(display_name) > 128:
            raise ValueError("provider_display_name doit contenir entre 1 et 128 caractères")
        if not raw_reference or len(raw_reference) > 1024:
            raise ValueError("raw_payload_reference doit contenir entre 1 et 1024 caractères")
        if self.raw_payload_sha256 is not None and not _SHA256_PATTERN.fullmatch(
            self.raw_payload_sha256
        ):
            raise ValueError("raw_payload_sha256 doit être un SHA-256 hexadécimal minuscule")
        object.__setattr__(self, "provider_display_name", display_name)
        object.__setattr__(self, "raw_payload_reference", raw_reference)


@dataclass(frozen=True, slots=True)
class OddsCaptureReport:
    """Résultat d'une transaction de capture et de sa déduplication idempotente."""

    provider_id: UUID
    event_id: UUID
    captured_at: datetime
    received_snapshots: int
    inserted_snapshots: int
    duplicate_snapshots: int
    inserted_snapshot_ids: tuple[UUID, ...]
    markets: tuple[ProviderMarket, ...]


@dataclass(frozen=True, slots=True)
class _Observation:
    snapshot: OddsSnapshot
    market: ProviderMarket
    selection: ProviderSelection
    fingerprint: str


class OddsCaptureService:
    """Normaliser une capture `OddsProvider` puis la publier en une transaction."""

    def __init__(self, engine: Engine, clock: Clock | None = None) -> None:
        self.engine = engine
        self._clock = clock or SystemClock()

    def capture_event(
        self,
        provider: OddsProvider,
        event: ProviderEvent,
        source: OddsCaptureSource,
    ) -> OddsCaptureReport:
        """Capturer un événement et ajouter uniquement de nouvelles observations."""

        recorded_at = self._clock.now().value
        try:
            markets = provider.get_event_markets(event.provider_event_id)
            capture = provider.capture_snapshot(event.provider_event_id)
            observations = _normalize_observations(
                provider,
                event,
                markets,
                capture.provider_event_id,
                capture.captured_at,
                capture.snapshots,
                source,
                recorded_at,
            )
        except Exception as error:
            self._record_failure(provider, source, recorded_at, error)
            raise
        event_snapshot_id = observations[0].snapshot.event_id
        with self.engine.begin() as connection:
            provider_id = _upsert_provider(connection, provider.provider_code, source, recorded_at)
            event_id = _upsert_event(
                connection,
                provider_id,
                event_snapshot_id,
                event,
                recorded_at,
            )
            inserted_ids = _persist_observations(
                connection,
                provider_id,
                event_id,
                event,
                observations,
                source,
                recorded_at,
            )
            _insert_health(
                connection,
                provider_id,
                ProviderStatus.OPERATIONAL,
                recorded_at,
                capture.captured_at,
                None,
            )
        return OddsCaptureReport(
            provider_id=provider_id,
            event_id=event_id,
            captured_at=capture.captured_at,
            received_snapshots=len(observations),
            inserted_snapshots=len(inserted_ids),
            duplicate_snapshots=len(observations) - len(inserted_ids),
            inserted_snapshot_ids=inserted_ids,
            markets=tuple(
                {
                    observation.market.provider_market_id: observation.market
                    for observation in observations
                }.values()
            ),
        )

    def _record_failure(
        self,
        provider: OddsProvider,
        source: OddsCaptureSource,
        checked_at: datetime,
        error: Exception,
    ) -> None:
        """Historiser l'échec séparément sans toucher aux snapshots déjà publiés."""

        with self.engine.begin() as connection:
            provider_id = _upsert_provider(connection, provider.provider_code, source, checked_at)
            snapshots = cast(Table, OddsSnapshotRecord.__table__)
            last_success_at = connection.execute(
                select(snapshots.c.captured_at)
                .where(
                    snapshots.c.provider_id == provider_id,
                    snapshots.c.captured_at.is_not(None),
                )
                .order_by(snapshots.c.captured_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            _insert_health(
                connection,
                provider_id,
                (
                    ProviderStatus.DEGRADED
                    if last_success_at is not None
                    else ProviderStatus.UNAVAILABLE
                ),
                checked_at,
                cast(datetime | None, last_success_at),
                f"Capture échouée ({type(error).__name__}) ; historique valide conservé",
            )


def _insert_health(
    connection: Connection,
    provider_id: UUID,
    status: ProviderStatus,
    checked_at: datetime,
    last_success_at: datetime | None,
    detail: str | None,
) -> None:
    health = cast(Table, OddsProviderHealth.__table__)
    connection.execute(
        health.insert().values(
            id=uuid4(),
            provider_id=provider_id,
            status=status,
            checked_at=checked_at,
            last_success_at=last_success_at,
            detail=detail,
        )
    )


def _normalize_observations(
    provider: OddsProvider,
    event: ProviderEvent,
    markets: tuple[ProviderMarket, ...],
    captured_event_id: str,
    captured_at: datetime,
    snapshots: tuple[OddsSnapshot, ...],
    source: OddsCaptureSource,
    recorded_at: datetime,
) -> tuple[_Observation, ...]:
    if captured_event_id != event.provider_event_id:
        raise OddsCaptureValidationError("La capture ne correspond pas à l'événement demandé")
    if captured_at > recorded_at:
        raise OddsCaptureValidationError("La capture fournisseur ne peut pas être future")
    if not snapshots:
        raise OddsCaptureValidationError("La capture fournisseur ne contient aucun snapshot")
    if len({snapshot.event_id for snapshot in snapshots}) != 1:
        raise OddsCaptureValidationError("Une capture ne peut pas mélanger plusieurs événements")

    market_by_id: dict[UUID, ProviderMarket] = {}
    for market in markets:
        if market.provider_event_id != event.provider_event_id:
            raise OddsCaptureValidationError(
                "Un marché appartient à un autre événement fournisseur"
            )
        identity = provider_market_uuid(
            provider.provider_code,
            event.provider_event_id,
            market.provider_market_id,
        )
        if identity in market_by_id:
            raise OddsCaptureValidationError("Identité de marché fournisseur ambiguë")
        market_by_id[identity] = market

    observations: list[_Observation] = []
    for snapshot in snapshots:
        if snapshot.provider != provider.provider_code:
            raise OddsCaptureValidationError("Le snapshot appartient à un autre fournisseur")
        snapshot_market = market_by_id.get(snapshot.market_id)
        if snapshot_market is None:
            raise OddsCaptureValidationError("Marché du snapshot introuvable dans le provider")
        selection = next(
            (item for item in snapshot_market.selections if item.selection is snapshot.selection),
            None,
        )
        if selection is None:
            raise OddsCaptureValidationError("Sélection du snapshot introuvable dans le marché")
        observations.append(
            _Observation(
                snapshot=snapshot,
                market=snapshot_market,
                selection=selection,
                fingerprint=_observation_fingerprint(
                    provider.provider_code,
                    event,
                    snapshot_market,
                    selection,
                    snapshot,
                    source,
                ),
            )
        )
    return tuple(observations)


def _upsert_provider(
    connection: Connection,
    provider_code: str,
    source: OddsCaptureSource,
    recorded_at: datetime,
) -> UUID:
    providers = cast(Table, OddsProviderRecord.__table__)
    statement = insert(providers).values(
        id=provider_entity_uuid(provider_code, "provider", provider_code),
        code=provider_code,
        display_name=source.provider_display_name,
        provider_type=source.provider_type,
        enabled=True,
        created_at=recorded_at,
    )
    row = connection.execute(
        statement.on_conflict_do_update(
            index_elements=[providers.c.code],
            set_={"display_name": statement.excluded.display_name, "enabled": True},
        ).returning(providers.c.id, providers.c.provider_type)
    ).one()
    if row.provider_type != source.provider_type:
        raise OddsCaptureValidationError("Le code fournisseur existe avec un autre type")
    return cast(UUID, row.id)


def _upsert_event(
    connection: Connection,
    provider_id: UUID,
    suggested_id: UUID,
    event: ProviderEvent,
    recorded_at: datetime,
) -> UUID:
    events = cast(Table, ProviderOddsEvent.__table__)
    statement = insert(events).values(
        id=suggested_id,
        provider_id=provider_id,
        provider_event_id=event.provider_event_id,
        game_title=event.game_title,
        competition_name=event.competition,
        participants=list(event.participants),
        starts_at=event.starts_at,
        best_of=event.best_of,
        status=event.status,
        collected_at=event.collected_at,
        source_reference=event.source_reference,
        created_at=recorded_at,
    )
    event_id = connection.execute(
        statement.on_conflict_do_update(
            index_elements=[events.c.provider_id, events.c.provider_event_id],
            set_={
                "game_title": statement.excluded.game_title,
                "competition_name": statement.excluded.competition_name,
                "participants": statement.excluded.participants,
                "starts_at": statement.excluded.starts_at,
                "best_of": statement.excluded.best_of,
                "status": statement.excluded.status,
                "collected_at": statement.excluded.collected_at,
                "source_reference": statement.excluded.source_reference,
            },
            where=statement.excluded.collected_at >= events.c.collected_at,
        ).returning(events.c.id)
    ).scalar_one_or_none()
    if event_id is None:
        event_id = connection.execute(
            select(events.c.id).where(
                events.c.provider_id == provider_id,
                events.c.provider_event_id == event.provider_event_id,
            )
        ).scalar_one()
    return cast(UUID, event_id)


def _persist_observations(
    connection: Connection,
    provider_id: UUID,
    event_id: UUID,
    event: ProviderEvent,
    observations: tuple[_Observation, ...],
    source: OddsCaptureSource,
    recorded_at: datetime,
) -> tuple[UUID, ...]:
    market_ids: dict[str, UUID] = {}
    selection_ids: dict[tuple[str, str], UUID] = {}
    inserted: list[UUID] = []
    snapshots = cast(Table, OddsSnapshotRecord.__table__)
    for observation in observations:
        market = observation.market
        market_id = market_ids.get(market.provider_market_id)
        if market_id is None:
            market_id = _upsert_market(
                connection,
                event_id,
                observation.snapshot.market_id,
                market,
                recorded_at,
            )
            market_ids[market.provider_market_id] = market_id
        selection_key = (market.provider_market_id, observation.selection.provider_selection_id)
        selection_id = selection_ids.get(selection_key)
        if selection_id is None:
            selection_id = _upsert_selection(
                connection,
                event_id,
                market_id,
                market,
                observation.selection,
                recorded_at,
            )
            selection_ids[selection_key] = selection_id
        snapshot = observation.snapshot
        inserted_id = connection.execute(
            insert(snapshots)
            .values(
                id=snapshot.odds_snapshot_id,
                provider_id=provider_id,
                event_id=event_id,
                market_id=market_id,
                selection_id=selection_id,
                provider_status=snapshot.provider_status,
                event_status=event.status,
                market_status=snapshot.market_status,
                selection_label=observation.selection.label,
                line=market.line,
                decimal_odds=snapshot.decimal_odds,
                captured_at=snapshot.captured_at,
                recorded_at=recorded_at,
                timestamp_reliable=not snapshot.informational_only,
                informational_only=snapshot.informational_only,
                raw_payload_reference=source.raw_payload_reference,
                raw_payload_sha256=source.raw_payload_sha256,
                provenance_reference=snapshot.provenance_reference,
                observation_fingerprint=observation.fingerprint,
            )
            .on_conflict_do_nothing()
            .returning(snapshots.c.id)
        ).scalar_one_or_none()
        if inserted_id is not None:
            inserted.append(cast(UUID, inserted_id))
    return tuple(inserted)


def _upsert_market(
    connection: Connection,
    event_id: UUID,
    suggested_id: UUID,
    market: ProviderMarket,
    recorded_at: datetime,
) -> UUID:
    markets = cast(Table, ProviderOddsMarket.__table__)
    statement = insert(markets).values(
        id=suggested_id,
        event_id=event_id,
        provider_market_id=market.provider_market_id,
        raw_label=market.raw_label,
        market_type=market.market_type,
        period=market.period,
        line=market.line,
        settlement_rules_version=market.settlement_rules_version,
        created_at=recorded_at,
    )
    return cast(
        UUID,
        connection.execute(
            statement.on_conflict_do_update(
                index_elements=[markets.c.event_id, markets.c.provider_market_id],
                set_={
                    "raw_label": statement.excluded.raw_label,
                    "market_type": statement.excluded.market_type,
                    "period": statement.excluded.period,
                    "line": statement.excluded.line,
                    "settlement_rules_version": statement.excluded.settlement_rules_version,
                },
            ).returning(markets.c.id)
        ).scalar_one(),
    )


def _upsert_selection(
    connection: Connection,
    event_id: UUID,
    market_id: UUID,
    market: ProviderMarket,
    selection: ProviderSelection,
    recorded_at: datetime,
) -> UUID:
    selections = cast(Table, ProviderOddsSelection.__table__)
    suggested_id = provider_entity_uuid(
        "odds",
        "selection",
        f"{event_id}:{market.provider_market_id}:{selection.provider_selection_id}",
    )
    statement = insert(selections).values(
        id=suggested_id,
        market_id=market_id,
        provider_selection_id=selection.provider_selection_id,
        raw_label=selection.label,
        selection_type=selection.selection,
        created_at=recorded_at,
    )
    return cast(
        UUID,
        connection.execute(
            statement.on_conflict_do_update(
                index_elements=[selections.c.market_id, selections.c.provider_selection_id],
                set_={
                    "raw_label": statement.excluded.raw_label,
                    "selection_type": statement.excluded.selection_type,
                },
            ).returning(selections.c.id)
        ).scalar_one(),
    )


def _observation_fingerprint(
    provider_code: str,
    event: ProviderEvent,
    market: ProviderMarket,
    selection: ProviderSelection,
    snapshot: OddsSnapshot,
    source: OddsCaptureSource,
) -> str:
    payload = {
        "capturedAt": snapshot.captured_at.isoformat(),
        "decimalOdds": _decimal(snapshot.decimal_odds),
        "eventStatus": event.status,
        "informationalOnly": snapshot.informational_only,
        "line": _decimal(market.line),
        "marketLabel": market.raw_label,
        "marketStatus": snapshot.market_status,
        "oddsSnapshotId": str(snapshot.odds_snapshot_id),
        "provenanceReference": snapshot.provenance_reference,
        "provider": provider_code,
        "providerEventId": event.provider_event_id,
        "providerMarketId": market.provider_market_id,
        "providerSelectionId": selection.provider_selection_id,
        "providerStatus": snapshot.provider_status,
        "rawPayloadReference": source.raw_payload_reference,
        "rawPayloadSha256": source.raw_payload_sha256,
        "selection": snapshot.selection,
        "selectionLabel": selection.label,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else str(value)
