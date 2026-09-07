"""Entrées manuelles fictives, soumises aux preuves actuelles et à la bankroll."""

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, and_, case, func, insert, select, text
from sqlalchemy.orm import Session

from metiquo.contracts import PaperBet
from metiquo.contracts.enums import PaperBetStatus, ValueGrade
from metiquo.db.core_models import Game
from metiquo.db.feature_models import FeatureSnapshot
from metiquo.db.ml_models import PrematchPrediction
from metiquo.db.odds_models import MarketMappingAttempt
from metiquo.db.paper_models import PaperBetRecord, PaperSettlementRecord
from metiquo.db.pricing_models import SignalRecord, ValueEvaluationRecord
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock, SystemClock
from metiquo.services.value_pipeline import PostgresValuePipeline, ValueEvaluationRequest


def decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def fingerprint(document: dict[str, object]) -> str:
    return sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def bankroll_lock_id(currency: str) -> int:
    return int.from_bytes(sha256(f"paper-bankroll:{currency}".encode()).digest()[:8], signed=True)


@dataclass(frozen=True, slots=True)
class PaperBankrollPolicy:
    version: str
    currency: str
    opening_balance: Decimal
    max_open_exposure: Decimal

    def __post_init__(self) -> None:
        if not self.version.strip() or len(self.version) > 128:
            raise ValueError("La bankroll exige une version explicite")
        if re.fullmatch(r"[A-Z]{3}", self.currency) is None:
            raise ValueError("La devise fictive doit être un code à trois lettres")
        for amount in (self.opening_balance, self.max_open_exposure):
            if not amount.is_finite() or amount <= 0:
                raise ValueError("La bankroll et sa limite doivent être positives et finies")


class PostgresPaperService:
    """Aucune exécution bookmaker ; le montant est toujours saisi explicitement."""

    def __init__(
        self,
        engine: Engine,
        *,
        bankroll: PaperBankrollPolicy,
        source_sla: timedelta,
        clock: Clock | None = None,
    ) -> None:
        self.engine = engine
        self.bankroll = bankroll
        self.clock = clock or SystemClock()
        self.value = PostgresValuePipeline(engine, source_sla=source_sla, clock=self.clock)

    def create(
        self,
        key: str,
        signal_id: UUID,
        stake_amount: Decimal,
        currency: str,
        *,
        actor: str,
    ) -> PaperBet:
        if not key.strip() or len(key) > 255 or not actor.strip() or len(actor) > 255:
            raise BusinessError(ErrorCode.INVALID_INPUT, "Clé et acteur explicites requis")
        if (
            not stake_amount.is_finite()
            or stake_amount <= 0
            or stake_amount >= Decimal("1000000000000")
            or stake_amount != stake_amount.quantize(Decimal("0.00000001"))
        ):
            raise BusinessError(
                ErrorCode.INVALID_INPUT, "Montant fictif positif, huit décimales maximum"
            )
        if currency != self.bankroll.currency:
            raise BusinessError(
                ErrorCode.INVALID_INPUT, "La devise doit correspondre à la bankroll fictive"
            )
        identity = fingerprint({"action": "paper.create", "key": key})
        request_hash = fingerprint(
            {
                "signalId": str(signal_id),
                "stakeAmount": decimal_text(stake_amount),
                "currency": currency,
                "actor": actor,
            }
        )
        now = self.clock.now().value
        # La devise identifie le compte, indépendamment de la version de sa politique.
        lock = bankroll_lock_id(currency)
        with self.engine.begin() as connection, Session(bind=connection) as session:
            connection.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": lock})
            previous = session.scalar(
                select(PaperBetRecord).where(PaperBetRecord.idempotency_fingerprint == identity)
            )
            if previous is not None:
                if previous.request_fingerprint != request_hash:
                    raise BusinessError(
                        ErrorCode.CONFLICT, "Cette clé décrit une autre décision paper"
                    )
                return entry_dto(previous)
            if session.scalar(
                select(PaperBetRecord.id).where(PaperBetRecord.signal_id == signal_id)
            ):
                raise BusinessError(ErrorCode.CONFLICT, "Ce signal possède déjà une décision paper")
            signal = session.get(SignalRecord, signal_id, with_for_update={"read": True})
            if signal is None:
                raise BusinessError(ErrorCode.NOT_FOUND, "Signal introuvable")
            evaluation = session.scalar(
                select(ValueEvaluationRecord)
                .where(
                    ValueEvaluationRecord.signal_id == signal_id,
                    ValueEvaluationRecord.grade == "VALUE",
                    ValueEvaluationRecord.computed_at <= now,
                )
                .order_by(ValueEvaluationRecord.computed_at.desc())
                .limit(1)
            )
            if signal.grade not in {"VALUE", "STRONG_VALUE"} or evaluation is None:
                raise BusinessError(
                    ErrorCode.INVALID_STATE, "Une décision value admise est requise"
                )
            prediction = session.get(PrematchPrediction, signal.prediction_id)
            mapping = session.get(MarketMappingAttempt, evaluation.market_mapping_attempt_id)
            assert (
                prediction is not None
                and mapping is not None
                and mapping.rules_reference is not None
            )
            game = session.get(Game, prediction.event_id, with_for_update={"read": True})
            feature = session.get(FeatureSnapshot, prediction.feature_snapshot_id)
            assert game is not None and feature is not None and game.start_at is not None
            if signal.selected_team_id is None:
                raise BusinessError(
                    ErrorCode.INVALID_STATE,
                    "Le signal doit prouver l'identité de l'équipe sélectionnée",
                )
            other_team = (
                prediction.team_b_id
                if signal.selected_team_id == prediction.team_a_id
                else prediction.team_a_id
            )
            canonical_a = (
                signal.selected_team_id if signal.selection_type == "TEAM_A" else other_team
            )
            canonical_b = (
                other_team if signal.selection_type == "TEAM_A" else signal.selected_team_id
            )
            available, exposure = self._available(session)
            if (
                stake_amount > available
                or stake_amount + exposure > self.bankroll.max_open_exposure
            ):
                raise BusinessError(
                    ErrorCode.INVALID_STATE,
                    "Bankroll fictive ou exposition disponible insuffisante",
                )
            admission = self.value.evaluate_in_transaction(
                connection,
                ValueEvaluationRequest(
                    signal.odds_snapshot_id,
                    signal.event_mapping_attempt_id,
                    evaluation.market_mapping_attempt_id,
                    signal.policy_version,
                    signal.prediction_id,
                ),
            )
            if admission.grade is not ValueGrade.VALUE:
                raise BusinessError(
                    ErrorCode.INVALID_STATE,
                    "Le signal n'est plus admissible à l'entrée paper",
                    context={"reasons": ",".join(reason.value for reason in admission.reasons)},
                )
            if (
                admission.signal is None
                or admission.signal.selected_team_id != signal.selected_team_id
            ):
                raise BusinessError(
                    ErrorCode.INVALID_STATE,
                    "L'identité de l'équipe a changé depuis le signal ; "
                    "une nouvelle décision est requise",
                )
            bet = PaperBetRecord(
                id=uuid5(NAMESPACE_URL, f"metiquo:paper:{identity}"),
                signal_id=signal.id,
                value_evaluation_id=evaluation.id,
                prediction_id=signal.prediction_id,
                odds_snapshot_id=signal.odds_snapshot_id,
                model_version_id=prediction.model_version_id,
                policy_version=signal.policy_version,
                settlement_rules_version=mapping.rules_reference,
                entry_odds=signal.offered_odds,
                stake_amount=stake_amount,
                currency=currency,
                placed_at=now,
                actor=actor,
                idempotency_fingerprint=identity,
                request_fingerprint=request_hash,
                decision_evidence={
                    "mode": "paper",
                    "creation": "manual",
                    "bankrollVersion": self.bankroll.version,
                    "bankrollOpening": decimal_text(self.bankroll.opening_balance),
                    "maxOpenExposure": decimal_text(self.bankroll.max_open_exposure),
                    "availableBefore": decimal_text(available),
                    "exposureBefore": decimal_text(exposure),
                    "entryEvaluationId": str(admission.evaluation_id),
                    "entryEvaluationFingerprint": admission.fingerprint,
                    "signalFingerprint": signal.signal_fingerprint,
                    "eventProof": {
                        "competitionId": str(game.competition_id)
                        if game.competition_id
                        else "unknown",
                        "gameId": str(game.id),
                        "bestOf": game.best_of,
                        "gameNumber": game.game_number,
                        "startAt": game.start_at.isoformat(),
                        "teamAId": str(canonical_a),
                        "teamBId": str(canonical_b),
                    },
                },
            )
            connection.execute(
                insert(PaperBetRecord).values(
                    **{
                        column.name: getattr(bet, column.name)
                        for column in PaperBetRecord.__table__.columns
                    }
                )
            )
            return entry_dto(bet)

    def _available(self, session: Session) -> tuple[Decimal, Decimal]:
        first = session.scalar(
            select(PaperBetRecord)
            .where(PaperBetRecord.currency == self.bankroll.currency)
            .order_by(PaperBetRecord.placed_at, PaperBetRecord.id)
            .limit(1)
        )
        if first is not None and first.decision_evidence.get("bankrollOpening") != decimal_text(
            self.bankroll.opening_balance
        ):
            raise BusinessError(
                ErrorCode.INVALID_STATE, "Le capital initial du ledger ne peut être réécrit"
            )
        ranked = select(
            PaperSettlementRecord.paper_bet_id,
            PaperSettlementRecord.status,
            PaperSettlementRecord.profit_loss,
            func.row_number()
            .over(
                partition_by=PaperSettlementRecord.paper_bet_id,
                order_by=PaperSettlementRecord.revision.desc(),
            )
            .label("rank"),
        ).subquery()
        totals = session.execute(
            select(
                func.coalesce(func.sum(ranked.c.profit_loss), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                ranked.c.status.is_(None) | (ranked.c.status == "pending_review"),
                                PaperBetRecord.stake_amount,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .select_from(PaperBetRecord)
            .outerjoin(ranked, and_(ranked.c.paper_bet_id == PaperBetRecord.id, ranked.c.rank == 1))
            .where(PaperBetRecord.currency == self.bankroll.currency)
        ).one()
        pnl, exposure = Decimal(totals[0]), Decimal(totals[1])
        return self.bankroll.opening_balance + pnl - exposure, exposure


def entry_dto(bet: PaperBetRecord) -> PaperBet:
    """Réponse initiale stable pour l'idempotence, même après un règlement ultérieur."""
    return PaperBet(
        paper_bet_id=bet.id,
        signal_id=bet.signal_id,
        prediction_id=bet.prediction_id,
        odds_snapshot_id=bet.odds_snapshot_id,
        entry_odds=bet.entry_odds,
        stake_amount=bet.stake_amount,
        currency=bet.currency,
        placed_at=bet.placed_at,
        status=PaperBetStatus.OPEN,
        settlement_rules_version=bet.settlement_rules_version,
    )
