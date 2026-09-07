"""Règlements OE automatiques, révisions auditées et reprises bornées."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from time import sleep
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Connection, Engine, insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from metiquo.contracts import PaperBet
from metiquo.contracts.enums import (
    FreshnessStatus,
)
from metiquo.contracts.enums import (
    PaperBetStatus as Status,
)
from metiquo.contracts.enums import (
    SelectionType as Selection,
)
from metiquo.db.core_models import CanonicalEntityRevision, Game, GameTeamStat, Series
from metiquo.db.ml_models import PrematchPrediction
from metiquo.db.odds_models import MarketRulesRecord
from metiquo.db.paper_models import PaperBetRecord, PaperSettlementRecord
from metiquo.db.pricing_models import SignalRecord
from metiquo.db.raw_models import Snapshot, SourceCatalog
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock, FixedClock, SystemClock, UtcInstant
from metiquo.ingestion.freshness import (
    FreshnessPolicy,
    FreshnessService,
    PostgresFreshnessRepository,
)
from metiquo.paper.creation import bankroll_lock_id, entry_dto, fingerprint
from metiquo.paper.game_settlement import GameResult, GameWinnerSettlementEngine
from metiquo.paper.series_settlement import SeriesResult, SeriesWinnerSettlementEngine
from metiquo.paper.settlement_rules import ResultProvenance, SettlementOutcome, SettlementRules


@dataclass(frozen=True, slots=True)
class SettlementJobReport:
    processed: int
    settled: int
    pending: int
    failed: tuple[UUID, ...]


class PostgresPaperSettlementService:
    def __init__(
        self,
        engine: Engine,
        *,
        source_sla: timedelta,
        settlement_delay: timedelta,
        clock: Clock | None = None,
    ) -> None:
        if source_sla <= timedelta(0) or settlement_delay < timedelta(0):
            raise ValueError("SLA positif et délai non négatif requis")
        self.engine, self.source_sla, self.settlement_delay = engine, source_sla, settlement_delay
        self.clock = clock or SystemClock()
        self.sleep: Callable[[float], None] = sleep

    def settle(
        self,
        paper_bet_id: UUID,
        *,
        key: str | None = None,
        actor: str = "oe-settlement-job",
        correction_reason: str | None = None,
        request_reason: str | None = None,
    ) -> PaperBet:
        if (
            not actor.strip()
            or len(actor) > 255
            or (key is not None and (not key.strip() or len(key) > 255))
        ):
            raise BusinessError(ErrorCode.INVALID_INPUT, "Acteur et clé de règlement invalides")
        if correction_reason is not None and (
            not correction_reason.strip() or len(correction_reason) > 400
        ):
            raise BusinessError(ErrorCode.INVALID_INPUT, "Une correction exige un motif explicite")
        if request_reason is not None and (not request_reason.strip() or len(request_reason) > 400):
            raise BusinessError(ErrorCode.INVALID_INPUT, "Motif de vérification invalide")
        now = self.clock.now().value
        request_hash = fingerprint(
            {
                "paperBetId": str(paper_bet_id),
                "actor": actor,
                "correctionReason": correction_reason,
                **({"requestReason": request_reason} if request_reason is not None else {}),
            }
        )
        identity = fingerprint({"action": "paper.settle", "key": key}) if key is not None else None
        with self.engine.begin() as connection, Session(bind=connection) as session:
            currency = session.scalar(
                select(PaperBetRecord.currency).where(PaperBetRecord.id == paper_bet_id)
            )
            if currency is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Décision paper introuvable")
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": bankroll_lock_id(currency)}
            )
            bet = session.get(PaperBetRecord, paper_bet_id, with_for_update=True)
            if bet is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Décision paper introuvable")
            if identity is not None:
                replay = session.scalar(
                    select(PaperSettlementRecord).where(
                        PaperSettlementRecord.idempotency_fingerprint == identity
                    )
                )
                if replay is not None:
                    if replay.request_fingerprint != request_hash:
                        raise BusinessError(
                            ErrorCode.CONFLICT, "Cette clé correspond à un autre règlement"
                        )
                    return settled_dto(bet, replay)
            previous = session.scalar(
                select(PaperSettlementRecord)
                .where(PaperSettlementRecord.paper_bet_id == bet.id)
                .order_by(PaperSettlementRecord.revision.desc())
                .limit(1)
            )
            if (
                previous is not None
                and previous.status != "pending_review"
                and correction_reason is None
            ):
                return settled_dto(bet, previous)
            if now < bet.placed_at:
                raise BusinessError(
                    ErrorCode.INVALID_STATE, "Le règlement ne peut précéder l'entrée"
                )
            outcome, source_id = self._result(connection, session, bet, now)
            if (
                previous is not None
                and previous.evidence.get("outcomeFingerprint") == outcome.fingerprint
                and correction_reason is None
            ):
                return settled_dto(bet, previous)
            identity = identity or fingerprint(
                {
                    "action": "paper.settle",
                    "bet": str(bet.id),
                    "outcome": outcome.fingerprint,
                    "request": request_hash,
                }
            )
            profit = None
            if outcome.status is not Status.PENDING_REVIEW:
                profit = (
                    bet.stake_amount * (bet.entry_odds - 1)
                    if outcome.status is Status.WON
                    else -bet.stake_amount
                    if outcome.status is Status.LOST
                    else Decimal(0)
                ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
            row = PaperSettlementRecord(
                id=uuid5(NAMESPACE_URL, f"metiquo:settlement:{identity}"),
                paper_bet_id=bet.id,
                revision=previous.revision + 1 if previous else 1,
                supersedes_id=previous.id if previous else None,
                status=outcome.status.value,
                profit_loss=profit,
                result_snapshot_id=source_id,
                settlement_rules_version=bet.settlement_rules_version,
                occurred_at=now,
                actor=actor,
                reason=correction_reason or outcome.reason,
                evidence={
                    **dict(outcome.evidence),
                    "outcomeReason": outcome.reason,
                    "outcomeFingerprint": outcome.fingerprint,
                    "correctionReason": correction_reason,
                    "requestReason": request_reason,
                    "settlementDelaySeconds": int(self.settlement_delay.total_seconds()),
                },
                idempotency_fingerprint=identity,
                request_fingerprint=request_hash,
            )
            connection.execute(
                insert(PaperSettlementRecord).values(
                    **{
                        column.name: getattr(row, column.name)
                        for column in PaperSettlementRecord.__table__.columns
                    }
                )
            )
            return settled_dto(bet, row)

    def _result(
        self,
        connection: Connection,
        session: Session,
        bet: PaperBetRecord,
        now: datetime,
    ) -> tuple[SettlementOutcome, UUID | None]:
        evidence: dict[str, object] = {"entrySignalId": str(bet.signal_id)}
        source_id: UUID | None = None

        def pending(reason: str) -> tuple[SettlementOutcome, UUID | None]:
            return SettlementOutcome(Status.PENDING_REVIEW, reason, evidence), source_id

        proof = bet.decision_evidence.get("eventProof")
        if not isinstance(proof, dict):
            return pending("ENTRY_EVENT_PROOF_MISSING")
        evidence["eventProof"] = proof
        signal = session.get(SignalRecord, bet.signal_id)
        prediction = session.get(PrematchPrediction, bet.prediction_id)
        assert signal is not None and prediction is not None
        game = session.get(Game, prediction.event_id, with_for_update={"read": True})
        rules_row = session.scalar(
            select(MarketRulesRecord).where(
                MarketRulesRecord.reference == bet.settlement_rules_version
            )
        )
        if game is None or rules_row is None:
            return pending("RESULT_OR_RULES_MISSING")
        rules = SettlementRules(
            rules_row.reference,
            rules_row.fingerprint,
            rules_row.period,
            frozenset(Selection(item) for item in rules_row.selection_types),
            rules_row.remake_policy,
            rules_row.forfeit_policy,
            rules_row.cancelled_policy,
            rules_row.active,
        )
        source_id = game.source_snapshot_id
        source = session.get(Snapshot, source_id, with_for_update={"read": True})
        assert source is not None
        catalog = session.get(
            SourceCatalog, source.source_catalog_id, with_for_update={"read": True}
        )
        if catalog is None or catalog.provider != "oracles_elixir":
            return pending("RESULT_SOURCE_UNKNOWN")
        source_state = FreshnessService(
            repository=PostgresFreshnessRepository(connection),
            sla=self.source_sla,
            clock=FixedClock(UtcInstant(now)),
        ).evaluate(catalog.id, policy=FreshnessPolicy())
        evidence["source"] = {
            "snapshotId": str(source_id),
            "currentSnapshotId": str(source_state.snapshot_id),
            "status": source_state.status.value,
        }
        if source_state.status is not FreshnessStatus.FRESH:
            return pending("SOURCE_STALE")
        if game.start_at is None or game.start_at.isoformat() != proof.get("startAt"):
            return pending("EVENT_TIME_CHANGED")
        if game.best_of != proof.get("bestOf") or game.game_number != proof.get("gameNumber"):
            return pending("SERIES_FORMAT_CHANGED")
        if game.game_length_seconds is None:
            return pending("RESULT_END_UNKNOWN")
        end = game.start_at + timedelta(seconds=game.game_length_seconds)
        teams = session.scalars(
            select(GameTeamStat).where(GameTeamStat.game_id == game.id).with_for_update(read=True)
        ).all()
        by_team = {str(team.team_id): team for team in teams}
        a, b = by_team.get(str(proof.get("teamAId"))), by_team.get(str(proof.get("teamBId")))
        if a is None or b is None or len(teams) != 2:
            return pending("RESULT_TEAMS_AMBIGUOUS")
        if any(team.source_snapshot_id != source_id for team in teams):
            return pending("RESULT_SOURCE_MIXED")
        processed = max(game.processed_at, a.processed_at, b.processed_at)
        revisions = session.scalars(
            select(CanonicalEntityRevision)
            .where(
                CanonicalEntityRevision.entity_type == "game",
                CanonicalEntityRevision.entity_id == game.id,
            )
            .order_by(CanonicalEntityRevision.revision.desc())
            .limit(1)
        ).all()
        evidence["canonicalRevisionIds"] = [str(item.id) for item in revisions]
        hashes = {
            "game": game.source_row_hash,
            "teamA": a.source_row_hash,
            "teamB": b.source_row_hash,
            "revision": game.source_row_revision,
        }
        evidence["resultHashes"] = hashes
        if source.validated_at is None or source.validated_at < end or processed < end:
            return pending("RESULT_NOT_KNOWN_AFTER_EVENT")
        if now < max(end, processed) + self.settlement_delay:
            return pending("SETTLEMENT_DELAY_PENDING")
        provenance = ResultProvenance(
            source_id, source.status, source.validated_at, processed, fingerprint(hashes)
        )
        selection = Selection(signal.selection_type)
        result = GameResult(
            provenance,
            game.game_number,
            game.best_of,
            game.complete,
            a.result,
            b.result,
            game.remake,
            game.forfeit,
        )
        if rules.period != "SERIES":
            outcome = GameWinnerSettlementEngine().settle(
                selection, result, rules, evaluated_at=now
            )
        elif game.best_of == 1:
            winner = (
                Selection.TEAM_A
                if a.result is True and b.result is False
                else Selection.TEAM_B
                if b.result is True and a.result is False
                else None
            )
            outcome = SeriesWinnerSettlementEngine().settle(
                selection,
                SeriesResult(
                    provenance,
                    1,
                    1,
                    False,
                    int(a.result) if a.result is not None else None,
                    int(b.result) if b.result is not None else None,
                    winner,
                    game.complete,
                    remake=game.remake,
                    forfeit=game.forfeit,
                ),
                rules,
                evaluated_at=now,
            )
        else:
            outcome = self._series(session, game, proof, provenance, selection, rules, now)
        return SettlementOutcome(
            outcome.status, outcome.reason, evidence | dict(outcome.evidence)
        ), source_id

    @staticmethod
    def _series(
        session: Session,
        game: Game,
        proof: dict[str, object],
        source: ResultProvenance,
        selection: Selection,
        rules: SettlementRules,
        now: datetime,
    ) -> SettlementOutcome:
        series = (
            session.get(Series, game.series_id, with_for_update={"read": True})
            if game.series_id
            else None
        )
        if (
            series is None
            or game.series_resolution_status != "resolved"
            or series.source_snapshot_id != source.snapshot_id
        ):
            return SettlementOutcome(
                Status.PENDING_REVIEW, "SERIES_RESULT_UNRESOLVED", source.document()
            )
        a_first = str(series.team_one_id) == proof.get("teamAId")
        if {str(series.team_one_id), str(series.team_two_id)} != {
            proof.get("teamAId"),
            proof.get("teamBId"),
        }:
            return SettlementOutcome(
                Status.PENDING_REVIEW, "SERIES_TEAMS_AMBIGUOUS", source.document()
            )
        winner = (
            Selection.DRAW
            if series.result_status == "draw"
            else Selection.TEAM_A
            if str(series.winner_team_id) == proof.get("teamAId")
            else Selection.TEAM_B
            if str(series.winner_team_id) == proof.get("teamBId")
            else None
        )
        return SeriesWinnerSettlementEngine().settle(
            selection,
            SeriesResult(
                source,
                game.best_of,
                series.best_of,
                series.allows_draw,
                series.score_one if a_first else series.score_two,
                series.score_two if a_first else series.score_one,
                winner,
                series.quality_status == "complete" and series.processed_at <= now,
            ),
            rules,
            evaluated_at=now,
        )

    def run_pending(self, *, limit: int = 100, max_attempts: int = 3) -> SettlementJobReport:
        if not 1 <= limit <= 1000 or not 1 <= max_attempts <= 5:
            raise ValueError("Limite 1..1000 et tentatives 1..5 requises")
        with self.engine.connect() as connection:
            ids = tuple(
                connection.scalars(
                    text("""
                SELECT b.id FROM signals.paper_bets b
                LEFT JOIN LATERAL (SELECT status FROM signals.settlements
                  WHERE paper_bet_id = b.id ORDER BY revision DESC LIMIT 1) s ON true
                WHERE s.status IS NULL OR s.status = 'pending_review'
                ORDER BY b.placed_at, b.id LIMIT :limit
            """),
                    {"limit": limit},
                )
            )
        settled, pending = 0, 0
        failed: list[UUID] = []
        for identity in ids:
            for attempt in range(max_attempts):
                try:
                    result = self.settle(identity)
                    if result.status is Status.PENDING_REVIEW:
                        pending += 1
                    else:
                        settled += 1
                    break
                except DBAPIError as error:
                    state = getattr(error.orig, "sqlstate", "")
                    transient = error.connection_invalidated or state in {
                        "40001",
                        "40P01",
                        "08006",
                        "08003",
                    }
                    if not transient or attempt + 1 == max_attempts:
                        failed.append(identity)
                        break
                    self.sleep(min(0.1 * 2**attempt, 2.0))
                except BusinessError:
                    failed.append(identity)
                    break
        return SettlementJobReport(len(ids), settled, pending, tuple(failed))


def settled_dto(bet: PaperBetRecord, settlement: PaperSettlementRecord) -> PaperBet:
    terminal = settlement.status != "pending_review"
    return PaperBet.model_validate(
        entry_dto(bet).model_dump()
        | {
            "status": Status(settlement.status),
            "settled_at": settlement.occurred_at if terminal else None,
            "profit_loss": settlement.profit_loss,
            "settlement_reason": settlement.reason,
        }
    )
