"""Transactional publication of public pre-match and live Stake snapshots."""

from datetime import UTC, datetime
from uuid import UUID, uuid5

from metiquo_core.models import (
    BookmakerEvent,
    BookmakerMarket,
    BookmakerPayload,
    BookmakerQuote,
    BookmakerSelection,
    BookmakerSnapshot,
)
from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metiquo_worker.reconciliation import lock_identities, observe_event, reconcile_in_session
from metiquo_worker.stake_types import (
    PARSER_VERSION,
    Capture,
    EventMetadata,
    decimal,
    fingerprint,
    identity_text,
    market_identity,
    selection_identity,
)


def _upsert_event(db: Session, metadata: EventMetadata) -> BookmakerEvent:
    values = {
        "id": metadata.id,
        "bookmaker": "stake",
        "game": metadata.game,
        "source_id": metadata.source_id,
        "source_url": metadata.url,
        "competition_key": metadata.competition_key,
        "competition_name": metadata.competition_name,
        "category_name": metadata.category_name,
        "participants": [p.model_dump(mode="json") for p in metadata.participants],
        "participant_keys": sorted(identity_text(p.name) for p in metadata.participants),
        "starts_at": metadata.starts_at,
        "status": metadata.status,
        "first_seen_at": metadata.observed_at,
        "last_seen_at": metadata.observed_at,
        "metadata_raw": metadata.raw,
    }
    db.execute(insert(BookmakerEvent).values(**values).on_conflict_do_nothing())
    event = db.get(BookmakerEvent, metadata.id, with_for_update=True)
    assert event is not None
    observe_event(db, metadata)
    if metadata.observed_at >= event.last_seen_at:
        for key, value in values.items():
            if key in {"id", "first_seen_at"}:
                continue
            if value is None or value == [] or value == "":
                continue
            # A listing has less identity evidence than a dated event document.
            # Retain its observation, but don't replace complete names/time with
            # abbreviated/empty list fields. Later complete documents can correct them.
            if (
                metadata.starts_at is None
                and event.starts_at is not None
                and key
                in {
                    "participants",
                    "participant_keys",
                    "competition_key",
                    "competition_name",
                    "metadata_raw",
                }
            ):
                continue
            setattr(event, key, value)
    return event


def remember_event(
    engine: Engine, metadata: EventMetadata, *, stop_reason: str | None = None
) -> None:
    with Session(engine) as db, db.begin():
        lock_identities(db)
        event = _upsert_event(db, metadata)
        if stop_reason and event.stopped_at is None:
            event.stopped_at = datetime.now(UTC)
            event.stop_reason = stop_reason
        reconcile_in_session(db, event_ids={metadata.id})


def remember_events(engine: Engine, metadata: list[EventMetadata]) -> None:
    """Persist a discovery page before any detail navigation can fail or exhaust the budget."""
    with Session(engine) as db, db.begin():
        lock_identities(db)
        for item in metadata:
            _upsert_event(db, item)
        reconcile_in_session(db, event_ids={item.id for item in metadata})


def known_events(engine: Engine, game: str) -> dict[str, tuple[datetime | None, bool, float]]:
    with Session(engine) as db:
        last = (
            select(BookmakerSnapshot.event_id, func.max(BookmakerSnapshot.finished_at).label("at"))
            .group_by(BookmakerSnapshot.event_id)
            .subquery()
        )
        rows = db.execute(
            select(BookmakerEvent, last.c.at)
            .outerjoin(last, last.c.event_id == BookmakerEvent.id)
            .where(BookmakerEvent.bookmaker == "stake", BookmakerEvent.game == game)
        )
        return {
            event.source_id: (
                event.starts_at,
                event.stopped_at is not None,
                at.timestamp() if at else 0,
            )
            for event, at in rows
        }


def publish(
    engine: Engine,
    run_id: UUID,
    captures: list[Capture],
    closing: EventMetadata,
    *,
    guard_seconds: int,
) -> dict[str, int]:
    if not captures:
        raise ValueError("No complete source capture")
    finished_at = datetime.now(UTC)
    if not closing.eligible(finished_at, guard_seconds):
        raise ValueError("Event state no longer collectible at publication")
    phase = "live" if closing.status == "live" else "prematch"
    tabs = {capture.tab for capture in captures}
    if len(tabs) != len(captures):
        raise ValueError("Duplicate tab capture")
    for capture in captures:
        metadata = capture.metadata
        if (
            metadata.id != closing.id
            or metadata.url != closing.url
            or metadata.competition_key != closing.competition_key
            or [p.name for p in metadata.participants] != [p.name for p in closing.participants]
            or metadata.status != closing.status
            or not metadata.eligible(finished_at, guard_seconds)
            or metadata.observed_at > finished_at
            or not capture.markets
            or any(not market.expanded for market in capture.markets)
            or {tab.id for tab in capture.tabs if not tab.disabled} - tabs
        ):
            raise ValueError("Incomplete or inconsistent event traversal")
    starts_at = min(
        (m.starts_at for m in [closing, *(c.metadata for c in captures)] if m.starts_at),
        default=None,
    )
    started_at = min(c.metadata.observed_at for c in captures)
    snapshot_id = uuid5(run_id, str(closing.id))
    document = {
        "metadata": closing.model_dump(mode="json", exclude={"observed_at"}),
        "phase": phase,
        "tabs": [
            {"tab": capture.tab, "markets": [m.model_dump(mode="json") for m in capture.markets]}
            for capture in captures
        ],
    }
    sha = fingerprint(document)
    markets: dict[UUID, dict[str, object]] = {}
    selections: dict[UUID, dict[str, object]] = {}
    quotes: list[dict[str, object]] = []
    for capture in captures:
        seen_markets: set[UUID] = set()
        for market in capture.markets:
            key, basis, period, family = market_identity(market, tab=capture.tab)
            market_id = uuid5(closing.id, key)
            if market_id in seen_markets:
                raise ValueError("Ambiguous source market identity")
            seen_markets.add(market_id)
            markets[market_id] = {
                "id": market_id,
                "event_id": closing.id,
                "identity_key": key,
                "identity_basis": basis,
                "source_id": market.source_id,
                "label": market.label,
                "family": family,
                "scope": "period" if period is not None else "match",
                "period": period,
                "first_seen_at": started_at,
                "last_seen_at": capture.metadata.observed_at,
            }
            seen_selections: set[UUID] = set()
            for selection in market.selections:
                key, basis, line, raw, ordinal = selection_identity(market, selection)
                selection_id = uuid5(market_id, key)
                if selection_id in seen_selections:
                    raise ValueError("Ambiguous source selection identity")
                seen_selections.add(selection_id)
                odds = decimal(selection.odds_raw)
                if (
                    not selection.disabled
                    and selection.odds_raw is not None
                    and (odds is None or not 1 < odds < 1_000_000_000)
                ):
                    raise ValueError("Unrecognized decimal odds; snapshot not published")
                disabled = selection.disabled or odds is None
                selections[selection_id] = {
                    "id": selection_id,
                    "market_id": market_id,
                    "identity_key": key,
                    "identity_basis": basis,
                    "source_id": selection.source_id,
                    "label": selection.name,
                    "accessible_label": selection.accessible_name,
                    "column_label": selection.column,
                    "row_label": selection.row_label,
                    "line": line,
                    "line_raw": raw,
                    "ordinal": ordinal,
                    "first_seen_at": started_at,
                    "last_seen_at": capture.metadata.observed_at,
                }
                quotes.append(
                    {
                        "snapshot_id": snapshot_id,
                        "selection_id": selection_id,
                        "observed_at": capture.metadata.observed_at,
                        "tab": capture.tab,
                        "odds": None if disabled else odds,
                        "odds_raw": selection.odds_raw,
                        "disabled": disabled,
                    }
                )
    if not quotes:
        raise ValueError("No selections; retain the previous snapshot")
    with Session(engine) as db, db.begin():
        lock_identities(db)
        event = _upsert_event(db, closing)
        db.flush()
        if event.stopped_at is not None or not closing.eligible(datetime.now(UTC), guard_seconds):
            raise ValueError("Event stopped before commit")
        if db.get(BookmakerSnapshot, snapshot_id) is not None:
            reconcile_in_session(db, event_ids={closing.id})
            return {"markets": 0, "selections": 0, "quotes": 0, "snapshots": 0}
        db.execute(
            insert(BookmakerPayload)
            .values(sha256=sha, parser_version=PARSER_VERSION, document=document)
            .on_conflict_do_nothing()
        )
        db.add(
            BookmakerSnapshot(
                id=snapshot_id,
                event_id=closing.id,
                run_id=run_id,
                payload_sha256=sha,
                started_at=started_at,
                finished_at=finished_at,
                scheduled_start_at=starts_at,
                phase=phase,
                capture_times={c.tab: c.metadata.observed_at.isoformat() for c in captures},
            )
        )
        db.flush()
        for model, rows in [(BookmakerMarket, markets), (BookmakerSelection, selections)]:
            statement = insert(model).values(list(rows.values()))
            update = {
                key: getattr(statement.excluded, key)
                for key in next(iter(rows.values()))
                if key not in {"id", "first_seen_at"}
            }
            db.execute(statement.on_conflict_do_update(index_elements=["id"], set_=update))
        # Bounded batches avoid parameter-count limits as new esport offerings grow.
        for offset in range(0, len(quotes), 500):
            db.execute(insert(BookmakerQuote), quotes[offset : offset + 500])
        reconcile_in_session(db, event_ids={closing.id})
    return {
        "markets": len(markets),
        "selections": len(selections),
        "quotes": len(quotes),
        "openQuotes": sum(not quote["disabled"] for quote in quotes),
        "suspendedQuotes": sum(bool(quote["disabled"]) for quote in quotes),
        "snapshots": 1,
    }
