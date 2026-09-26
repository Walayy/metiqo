"""Settle public winner selections from verified, durable match evidence only.

No bookmaker account, stake, or placed bet is represented here. A result can be
retracted after an identity or source correction; every transition is journaled.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from metiquo_core.bookmaker_markets import supported_winner_market
from metiquo_core.matches import completed_series_summary
from metiquo_core.models import (
    BookmakerEvent,
    BookmakerMarket,
    BookmakerMatchLink,
    BookmakerMatchResolution,
    BookmakerQuote,
    BookmakerSelection,
    BookmakerSelectionResult,
    BookmakerSelectionResultDecision,
    EsportMatch,
    MatchSnapshot,
    MatchSourceLink,
    Team,
)
from sqlalchemy import Engine, exists, select
from sqlalchemy.orm import Session

from metiquo_worker.fixture_identity import team_key
from metiquo_worker.reconciliation import lock_identities
from metiquo_worker.stake_types import fingerprint

DELAY = timedelta(minutes=30)


@dataclass(frozen=True)
class SeriesProof:
    source: str
    snapshot_id: UUID
    snapshot_sha256: str
    observed_at: datetime
    match_winner: str
    maps: dict[int, str]
    played_maps: int
    signature: str


def market_kind(market: BookmakerMarket) -> tuple[str, int | None] | None:
    return supported_winner_market(market.label, market.scope, market.period)


def _score(value: object) -> tuple[int, int] | None:
    if not isinstance(value, dict):
        return None
    home, away = value.get("home"), value.get("away")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (home, away)):
        return None
    assert isinstance(home, int) and isinstance(away, int)
    return home, away


def _validated(
    snapshot: MatchSnapshot, match: EsportMatch
) -> tuple[str, dict[int, str], int, str] | None:
    if snapshot.status != "finished" or snapshot.payload.get("status") != "finished":
        return None
    if snapshot.payload.get("format") != match.format or match.format not in {"BO1", "BO3", "BO5"}:
        return None
    target = {"BO1": 1, "BO3": 2, "BO5": 3}[match.format]
    score = _score(snapshot.payload.get("seriesScore"))
    raw_maps = snapshot.payload.get("maps")
    if not isinstance(raw_maps, list):
        return None
    maps: dict[int, str] = {}
    for item in raw_maps:
        if not isinstance(item, dict):
            return None
        number, status, winner = item.get("number"), item.get("status"), item.get("winnerId")
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 5:
            return None
        if number in maps:
            return None
        if status == "finished":
            if winner not in {match.home_id, match.away_id}:
                return None
            maps[number] = winner
        elif winner is not None:
            return None
    completed = completed_series_summary(raw_maps, match.home_id, match.away_id, match.format)
    if snapshot.source == "oracles-elixir":
        if completed is None or score != completed[1:]:
            return None
    elif snapshot.source == "loltv":
        if score is None and completed is None:
            return None
        if completed is not None and score is not None and score != completed[1:]:
            return None
        if score is None:
            score = completed[1:] if completed is not None else None
        if score is None or max(score) != target or min(score) >= target:
            return None
        if any(number > sum(score) for number in maps):
            return None
        map_score = (
            sum(w == match.home_id for w in maps.values()),
            sum(w == match.away_id for w in maps.values()),
        )
        if map_score[0] > score[0] or map_score[1] > score[1]:
            return None
    else:
        return None
    assert score is not None
    winner = match.home_id if score[0] > score[1] else match.away_id
    signature = fingerprint([match.format, score, sorted(maps.items())])
    return winner, maps, sum(score), signature


def source_proof(
    snapshots: list[MatchSnapshot], match: EsportMatch, source: str
) -> SeriesProof | None:
    source_rows = [row for row in snapshots if row.source == source]
    if not source_rows:
        return None
    source_rows.sort(key=lambda row: (row.observed_at, str(row.id)))
    latest = _validated(source_rows[-1], match)
    if latest is None:
        return None
    anchor = source_rows[-1]
    for row in reversed(source_rows[:-1]):
        prior = _validated(row, match)
        if prior is None or prior[3] != latest[3]:
            break
        anchor = row
    return SeriesProof(source, anchor.id, anchor.sha256, anchor.observed_at, *latest)


def _picked_team(
    selection: BookmakerSelection,
    mapping: list[dict[str, object]],
    names: dict[str, set[str]],
) -> str | None:
    if selection.line is not None or selection.ordinal is not None:
        return None
    labels = [selection.label, selection.accessible_label]
    hits: set[str] = set()
    for label in labels:
        if not isinstance(label, str):
            continue
        key = team_key(label)
        if not key or key in {"yes", "no", "oui", "non", "draw", "tie"}:
            continue
        for item in mapping:
            team_id = item.get("teamId")
            if isinstance(team_id, str) and key in names.get(team_id, set()):
                hits.add(team_id)
    return next(iter(hits)) if len(hits) == 1 else None


def _mapping(
    link: BookmakerMatchLink, event: BookmakerEvent, match: EsportMatch, db: Session
) -> tuple[list[dict[str, object]], dict[str, set[str]]] | None:
    raw = link.evidence.get("participants")
    if (
        not isinstance(raw, list)
        or len(raw) != 2
        or not all(isinstance(item, dict) for item in raw)
    ):
        return None
    mapping = raw
    if {item.get("teamId") for item in mapping} != {match.home_id, match.away_id}:
        return None
    participants = event.participants
    if not isinstance(participants, list) or len(participants) != 2:
        return None
    names: dict[str, set[str]] = {}
    for item in mapping:
        position, team_id, mapped_name = item.get("position"), item.get("teamId"), item.get("name")
        matched = next(
            (p for p in participants if isinstance(p, dict) and p.get("position") == position), None
        )
        if (
            not isinstance(team_id, str)
            or not isinstance(mapped_name, str)
            or not isinstance(matched, dict)
            or matched.get("name") != mapped_name
        ):
            return None
        team = db.get(Team, team_id)
        if team is None:
            return None
        aliases = team.data.get("aliases")
        candidates = [mapped_name, team.data.get("name")]
        if isinstance(aliases, list):
            candidates.extend(aliases)
        names[team_id] = {team_key(name) for name in candidates if isinstance(name, str)}
    return mapping, names


def _source_choice(
    loltv: SeriesProof | None, oracle: SeriesProof | None, kind: str, number: int | None
) -> tuple[SeriesProof | None, str | None]:
    if loltv and oracle:
        if loltv.match_winner != oracle.match_winner or any(
            number in oracle.maps and oracle.maps[number] != winner
            for number, winner in loltv.maps.items()
        ):
            return None, "source-conflict"
    for proof in (loltv, oracle):
        if proof is None:
            continue
        if (
            kind == "match_winner"
            or number in proof.maps
            or (number is not None and number > proof.played_maps)
        ):
            return proof, None
    return None, "missing-final-result"


def settle_selections(engine: Engine, *, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    counts = {"examined": 0, "changed": 0, "pending": 0, "won": 0, "lost": 0, "void": 0}
    with Session(engine) as db, db.begin():
        lock_identities(db)
        # Only selections ever quoted as open can describe a possible historical bet.
        rows = db.execute(
            select(BookmakerMarket, BookmakerSelection)
            .join(BookmakerSelection, BookmakerSelection.market_id == BookmakerMarket.id)
            .where(
                exists().where(
                    BookmakerQuote.selection_id == BookmakerSelection.id,
                    BookmakerQuote.odds.is_not(None),
                )
            )
            .order_by(BookmakerMarket.event_id, BookmakerMarket.id, BookmakerSelection.id)
        ).all()
        by_market: dict[UUID, list[BookmakerSelection]] = {}
        markets: dict[UUID, BookmakerMarket] = {}
        for market, selection in rows:
            if market_kind(market) is not None:
                markets[market.id] = market
                by_market.setdefault(market.id, []).append(selection)
        cache: dict[
            UUID,
            tuple[
                BookmakerEvent | None,
                EsportMatch | None,
                BookmakerMatchLink | None,
                SeriesProof | None,
                SeriesProof | None,
                tuple[list[dict[str, object]], dict[str, set[str]]] | None,
            ],
        ] = {}
        for market_id, selections in by_market.items():
            market = markets[market_id]
            kind, number = market_kind(market) or ("", None)
            if market.event_id not in cache:
                event = db.get(BookmakerEvent, market.event_id)
                link = db.get(BookmakerMatchLink, market.event_id)
                resolution = db.get(BookmakerMatchResolution, market.event_id)
                if resolution is None or resolution.status != "linked":
                    link = None
                match = db.get(EsportMatch, link.match_id) if link else None
                if match is not None:
                    source_ids = {
                        source.provider: source.source_id
                        for source in db.scalars(
                            select(MatchSourceLink).where(MatchSourceLink.match_id == match.id)
                        )
                        if source.provider in {"loltv", "oracles-elixir"}
                    }
                    snapshots = list(
                        db.scalars(
                            select(MatchSnapshot)
                            .where(MatchSnapshot.match_id == match.id)
                            .order_by(MatchSnapshot.observed_at, MatchSnapshot.id)
                        )
                    )
                    snapshots = [
                        row for row in snapshots if source_ids.get(row.source) == row.source_id
                    ]
                    loltv = source_proof(snapshots, match, "loltv")
                    oracle = source_proof(snapshots, match, "oracles-elixir")
                    if loltv is None and oracle is not None:
                        latest_loltv = next(
                            (row for row in reversed(snapshots) if row.source == "loltv"), None
                        )
                        latest_oracle = next(
                            (row for row in reversed(snapshots) if row.source == "oracles-elixir"),
                            None,
                        )
                        if (
                            latest_loltv is not None
                            and latest_oracle is not None
                            and (
                                latest_loltv.status == "walkover"
                                or latest_loltv.observed_at >= latest_oracle.observed_at
                            )
                        ):
                            # A newer unresolved LoLTV state can signal a correction.
                            oracle = None
                    mapping = (
                        _mapping(link, event, match, db)
                        if event is not None and link is not None
                        else None
                    )
                else:
                    loltv = oracle = mapping = None
                cache[market.event_id] = event, match, link, loltv, oracle, mapping
            event, match, link, loltv, oracle, mapped = cache[market.event_id]
            picks = {
                selection.id: _picked_team(selection, *mapped) if mapped else None
                for selection in selections
            }
            valid_market = (
                len(selections) == 2
                and match is not None
                and len({team for team in picks.values() if team is not None}) == 2
                and set(picks.values()) == {match.home_id, match.away_id}
            )
            proof, reason = (
                _source_choice(loltv, oracle, kind, number)
                if valid_market
                else (None, "unverified-market-or-identity")
            )
            for selection in selections:
                counts["examined"] += 1
                picked = picks[selection.id] if valid_market else None
                status = "pending"
                if proof is not None and now >= proof.observed_at + DELAY:
                    if kind == "map_winner" and number is not None and number > proof.played_maps:
                        status = "void"
                    else:
                        winner = (
                            proof.match_winner
                            if kind == "match_winner"
                            else proof.maps.get(number)
                            if number is not None
                            else None
                        )
                        if winner is not None:
                            status = "won" if picked == winner else "lost"
                elif proof is not None:
                    reason = "correction-window"
                evidence: dict[str, object] = {
                    "version": "selection-result-v1",
                    "eventId": str(market.event_id),
                    "selectionId": str(selection.id),
                    "marketKind": kind,
                    "mapNumber": number,
                    "matchId": str(match.id) if match else None,
                    "pickedTeamId": picked,
                    "status": status,
                }
                if proof is not None:
                    evidence.update(
                        {
                            "source": proof.source,
                            "snapshotId": str(proof.snapshot_id),
                            "snapshotSha256": proof.snapshot_sha256,
                            "finishedObservedAt": proof.observed_at.isoformat(),
                            "eligibleAt": (proof.observed_at + DELAY).isoformat(),
                            "winnerTeamId": (
                                proof.match_winner
                                if kind == "match_winner"
                                else proof.maps.get(number)
                                if number is not None
                                else None
                            ),
                            "playedMaps": proof.played_maps,
                            "resultSignature": proof.signature,
                        }
                    )
                if status == "pending":
                    evidence["reason"] = reason
                digest = fingerprint(evidence)
                current = db.get(BookmakerSelectionResult, selection.id)
                counts[status] += 1
                if current is not None and current.evidence_sha256 == digest:
                    continue
                if current is None:
                    current = BookmakerSelectionResult(
                        selection_id=selection.id, event_id=market.event_id
                    )
                    db.add(current)
                current.status = status
                current.market_kind = kind
                current.map_number = number
                current.picked_team_id = picked
                current.source = proof.source if proof else None
                current.source_snapshot_id = proof.snapshot_id if proof else None
                current.evidence_sha256 = digest
                current.evidence = evidence
                current.decided_at = now
                db.add(
                    BookmakerSelectionResultDecision(
                        selection_id=selection.id,
                        decided_at=now,
                        status=status,
                        evidence_sha256=digest,
                        evidence=evidence,
                    )
                )
                counts["changed"] += 1
    return counts
