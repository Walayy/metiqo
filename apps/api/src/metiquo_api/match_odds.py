"""Read the two supported Stake winner outcomes for linked match fixtures."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from uuid import UUID

from metiquo_core.bookmaker_markets import supported_winner_market
from metiquo_core.models import (
    BookmakerEvent,
    BookmakerMarket,
    BookmakerMatchLink,
    BookmakerMatchResolution,
    BookmakerQuote,
    BookmakerSelection,
    BookmakerSelectionResult,
    BookmakerSnapshot,
    EsportMatch,
    Market,
    ProbabilityEstimate,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def match_odds(
    db: Session,
    matches: Sequence[EsportMatch],
    *,
    statuses: Mapping[UUID, str],
    now: datetime,
    max_age_seconds: int,
) -> dict[UUID, list[dict[str, object]]]:
    """Return only uniquely linked, explicitly mapped two-outcome winner markets."""
    if not matches:
        return {}

    by_match = {match.id: match for match in matches}
    link_rows = db.execute(
        select(BookmakerMatchLink.match_id, BookmakerMatchLink.event_id, BookmakerEvent.status)
        .join(
            BookmakerMatchResolution,
            BookmakerMatchResolution.event_id == BookmakerMatchLink.event_id,
        )
        .join(BookmakerEvent, BookmakerEvent.id == BookmakerMatchLink.event_id)
        .where(
            BookmakerMatchLink.match_id.in_(by_match),
            BookmakerMatchResolution.status == "linked",
            BookmakerMatchResolution.last_match_id == BookmakerMatchLink.match_id,
            BookmakerEvent.bookmaker == "stake",
            BookmakerEvent.game == "league-of-legends",
        )
    ).all()
    events_by_match: dict[UUID, list[UUID]] = defaultdict(list)
    bookmaker_status: dict[UUID, str] = {}
    for match_id, event_id, event_status in link_rows:
        events_by_match[match_id].append(event_id)
        bookmaker_status[match_id] = event_status
    # Multiple active Stake events for the same fixture are ambiguous for display.
    match_by_event = {
        event_ids[0]: match_id
        for match_id, event_ids in events_by_match.items()
        if len(event_ids) == 1
    }
    if not match_by_event:
        return {}

    market_rows = db.execute(
        select(BookmakerMarket, BookmakerSelection, BookmakerSelectionResult)
        .join(BookmakerSelection, BookmakerSelection.market_id == BookmakerMarket.id)
        .join(
            BookmakerSelectionResult,
            BookmakerSelectionResult.selection_id == BookmakerSelection.id,
        )
        .where(
            BookmakerMarket.event_id.in_(match_by_event),
            BookmakerSelectionResult.event_id == BookmakerMarket.event_id,
            BookmakerSelectionResult.picked_team_id.is_not(None),
        )
    ).all()

    candidates: dict[
        tuple[UUID, str, int | None], dict[UUID, list[tuple[BookmakerSelection, str, str]]]
    ] = defaultdict(lambda: defaultdict(list))
    for market, selection, result in market_rows:
        parsed = supported_winner_market(market.label, market.scope, market.period)
        if (
            parsed is None
            or parsed != (result.market_kind, result.map_number)
            or result.picked_team_id is None
        ):
            continue
        match_id = match_by_event[market.event_id]
        match = by_match[match_id]
        if result.picked_team_id not in {match.home_id, match.away_id}:
            continue
        key = (match_id, parsed[0], parsed[1])
        candidates[key][market.id].append((selection, result.picked_team_id, result.status))

    unique_markets: dict[
        tuple[UUID, str, int | None], list[tuple[BookmakerSelection, str, str]]
    ] = {}
    for key, market_groups in candidates.items():
        # Refuse partial, duplicate, or ambiguously mapped markets.
        valid_groups = [
            selections
            for selections in market_groups.values()
            if len(selections) == 2
            and {team_id for _, team_id, _ in selections}
            == {by_match[key[0]].home_id, by_match[key[0]].away_id}
            and len({selection.id for selection, _, _ in selections}) == 2
        ]
        if len(market_groups) == 1 and len(valid_groups) == 1:
            unique_markets[key] = valid_groups[0]
    if not unique_markets:
        return {}

    event_ids = set(match_by_event)
    ranked_snapshots = (
        select(
            BookmakerSnapshot.id.label("snapshot_id"),
            BookmakerSnapshot.event_id.label("event_id"),
            BookmakerSnapshot.phase.label("phase"),
            func.row_number()
            .over(
                partition_by=(BookmakerSnapshot.event_id, BookmakerSnapshot.phase),
                order_by=(BookmakerSnapshot.finished_at.desc(), BookmakerSnapshot.id.desc()),
            )
            .label("row_number"),
        )
        .where(
            BookmakerSnapshot.event_id.in_(event_ids),
            BookmakerSnapshot.finished_at <= now,
        )
        .subquery()
    )
    latest_snapshot_ids = set(
        db.scalars(
            select(ranked_snapshots.c.snapshot_id).where(ranked_snapshots.c.row_number == 1)
        ).all()
    )
    selection_ids = {
        selection.id for selections in unique_markets.values() for selection, _, _ in selections
    }
    quote_rows = db.execute(
        select(BookmakerQuote, BookmakerSnapshot.phase)
        .join(BookmakerSnapshot, BookmakerSnapshot.id == BookmakerQuote.snapshot_id)
        .where(
            BookmakerQuote.selection_id.in_(selection_ids),
            BookmakerQuote.snapshot_id.in_(latest_snapshot_ids),
            BookmakerQuote.observed_at <= now,
        )
        .order_by(BookmakerQuote.observed_at.desc())
    ).all()
    latest_quotes: dict[tuple[UUID, str], BookmakerQuote] = {}
    for quote, phase in quote_rows:
        latest_quotes.setdefault((quote.selection_id, phase), quote)

    probability_by_pick = _probabilities(db, list(by_match.values()), now)
    output: dict[UUID, list[dict[str, object]]] = defaultdict(list)
    fresh_after = now - timedelta(seconds=max_age_seconds)
    for (match_id, kind, map_number), selections in unique_markets.items():
        for phase in ("prematch", "live"):
            status = statuses.get(match_id)
            if phase == "live" and status == "scheduled":
                continue
            expected_status = "scheduled" if phase == "prematch" else "live"
            historical = status != expected_status or bookmaker_status[match_id] != expected_status
            quote_rows_for_market: list[tuple[BookmakerSelection, str, str, BookmakerQuote]] = []
            for selection, team_id, result_status in selections:
                current_quote = latest_quotes.get((selection.id, phase))
                if current_quote is None:
                    quote_rows_for_market = []
                    break
                quote_rows_for_market.append((selection, team_id, result_status, current_quote))
            if len(quote_rows_for_market) != 2:
                continue

            core_kind = "winner" if kind == "match_winner" else "map1" if map_number == 1 else None
            picks: list[dict[str, object]] = []
            for _selection, team_id, result_status, quote in sorted(
                quote_rows_for_market,
                key=lambda item: 0 if item[1] == by_match[match_id].home_id else 1,
            ):
                suspended = quote.disabled or quote.odds is None
                fresh = quote.observed_at >= fresh_after
                probability = (
                    probability_by_pick.get((match_id, core_kind, team_id))
                    # Existing estimates describe pre-match markets only. A live
                    # price must never inherit a probability from before the match.
                    if core_kind is not None
                    and fresh
                    and not suspended
                    and phase == "prematch"
                    and not historical
                    else None
                )
                picks.append(
                    {
                        "teamId": team_id,
                        "odds": float(quote.odds)
                        if not suspended and quote.odds is not None
                        else None,
                        "suspended": suspended,
                        "observedAt": quote.observed_at,
                        "probability": probability,
                        "result": result_status,
                    }
                )
            output[match_id].append(
                {
                    "kind": kind,
                    "phase": phase,
                    "historical": historical,
                    "mapNumber": map_number,
                    "observedAt": max(
                        quote.observed_at for _, _, _, quote in quote_rows_for_market
                    ),
                    "selections": picks,
                }
            )
    for rows in output.values():
        rows.sort(
            key=lambda item: (item["kind"], item["mapNumber"] or 0, item["phase"] != "prematch")
        )
    return dict(output)


def _probabilities(
    db: Session, matches: list[EsportMatch], now: datetime
) -> dict[tuple[UUID, str, str], float]:
    if not matches:
        return {}
    match_ids = [match.id for match in matches]
    ranked_estimates = (
        select(
            ProbabilityEstimate.market_id.label("market_id"),
            ProbabilityEstimate.probability.label("probability"),
            func.row_number()
            .over(
                partition_by=ProbabilityEstimate.market_id,
                order_by=ProbabilityEstimate.estimated_at.desc(),
            )
            .label("row_number"),
        )
        .where(
            ProbabilityEstimate.estimated_at <= now,
            ProbabilityEstimate.valid_until > now,
        )
        .subquery()
    )
    rows = db.execute(
        select(Market.match_id, Market.kind, Market.pick_id, ranked_estimates.c.probability)
        .join(ranked_estimates, ranked_estimates.c.market_id == Market.id)
        .where(
            Market.match_id.in_(match_ids),
            Market.bookmaker == "stake",
            Market.active.is_(True),
            ranked_estimates.c.row_number == 1,
        )
    ).all()
    grouped: dict[tuple[UUID, str, str], list[float]] = defaultdict(list)
    for match_id, kind, pick_id, probability in rows:
        grouped[(match_id, kind, pick_id)].append(float(probability))
    # Duplicate active estimates for a selection are not resolved by guessing.
    return {key: values[0] for key, values in grouped.items() if len(values) == 1}
