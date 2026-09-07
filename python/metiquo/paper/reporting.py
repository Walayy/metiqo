"""Calcul hors requête web et lecture de rapports financiers append-only."""

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, func, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from metiquo.db.ml_models import PrematchPrediction
from metiquo.db.odds_models import MarketRulesRecord, OddsProviderRecord, OddsSnapshotRecord
from metiquo.db.paper_models import FinancialReportRecord, PaperBetRecord, PaperSettlementRecord
from metiquo.db.pricing_models import SignalRecord
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock, SystemClock
from metiquo.paper.closing_line import PostgresClosingLineRepository
from metiquo.paper.creation import entry_dto, fingerprint
from metiquo.paper.metrics import (
    FINANCIAL_METHOD_VERSION,
    FinancialMetricsEngine,
    FinancialObservation,
)
from metiquo.paper.reporting_audit import reporting_audit
from metiquo.paper.settlement_job import settled_dto


@dataclass(frozen=True, slots=True)
class StoredFinancialReport:
    report_id: UUID
    currency: str
    computed_at: datetime
    document: dict[str, object]
    input_evidence: dict[str, object]
    input_fingerprint: str
    report_fingerprint: str


class PostgresFinancialReportingService:
    def __init__(
        self, engine: Engine, *, closing_max_age_seconds: int = 90, clock: Clock | None = None
    ) -> None:
        if closing_max_age_seconds <= 0:
            raise ValueError("L'âge maximal du proxy de clôture doit être positif")
        self.engine, self.closing_max_age_seconds = engine, closing_max_age_seconds
        self.clock = clock or SystemClock()

    def build(self, *, currency: str) -> StoredFinancialReport:
        if re.fullmatch(r"[A-Z]{3}", currency) is None:
            raise ValueError("Devise invalide")
        now = self.clock.now().value
        with (
            self.engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection,
            connection.begin(),
            Session(bind=connection) as session,
        ):
            latest = (
                select(PaperSettlementRecord)
                .where(
                    PaperSettlementRecord.paper_bet_id == PaperBetRecord.id,
                    PaperSettlementRecord.occurred_at <= now,
                )
                .order_by(PaperSettlementRecord.revision.desc())
                .limit(1)
                .correlate(PaperBetRecord)
                .lateral()
            )
            settled = aliased(PaperSettlementRecord, latest)
            query = (
                select(
                    PaperBetRecord,
                    SignalRecord,
                    PrematchPrediction,
                    OddsSnapshotRecord,
                    OddsProviderRecord,
                    MarketRulesRecord,
                    settled,
                )
                .join(SignalRecord, SignalRecord.id == PaperBetRecord.signal_id)
                .join(PrematchPrediction, PrematchPrediction.id == PaperBetRecord.prediction_id)
                .join(OddsSnapshotRecord, OddsSnapshotRecord.id == PaperBetRecord.odds_snapshot_id)
                .join(OddsProviderRecord, OddsProviderRecord.id == OddsSnapshotRecord.provider_id)
                .join(
                    MarketRulesRecord,
                    MarketRulesRecord.reference == PaperBetRecord.settlement_rules_version,
                )
                .outerjoin(latest, true())
                .where(PaperBetRecord.currency == currency, PaperBetRecord.placed_at <= now)
                .order_by(PaperBetRecord.id)
            )
            rows = session.execute(query).all()
            proxies = {
                p.paper_bet_id: p
                for p in PostgresClosingLineRepository(
                    connection, max_age_seconds=self.closing_max_age_seconds, clock=self.clock
                ).get_many(tuple(row[0].id for row in rows))
            }
            observations: list[FinancialObservation] = []
            inputs: list[dict[str, object]] = []
            for bet, signal, prediction, quote, provider, rules, settlement in rows:
                if (
                    provider.provider_type not in {"manual_import", "licensed_feed"}
                    or not quote.timestamp_reliable
                    or quote.captured_at is None
                    or quote.informational_only
                    or quote.recorded_at > bet.placed_at
                    or quote.decimal_odds != bet.entry_odds
                ):
                    raise BusinessError(
                        ErrorCode.INVALID_STATE,
                        "Rapport interdit sans provenance de cotes observées vérifiable",
                    )
                dto = settled_dto(bet, settlement) if settlement is not None else entry_dto(bet)
                proof = bet.decision_evidence.get("eventProof")
                competition = (
                    str(proof.get("competitionId", "unknown"))
                    if isinstance(proof, dict)
                    else "unknown"
                )
                proxy = proxies[bet.id]
                if signal.expected_value is None:
                    raise BusinessError(
                        ErrorCode.INVALID_STATE, "L'EV annoncée du signal doit rester disponible"
                    )
                observations.append(
                    FinancialObservation(
                        dto,
                        prediction.event_id,
                        f"{rules.market_type}/{rules.period}",
                        competition,
                        str(bet.model_version_id),
                        signal.grade,
                        signal.expected_value,
                        proxy.clv,
                        quote.observation_fingerprint,
                    )
                )
                inputs.append(
                    {
                        "paperBetId": str(bet.id),
                        "signalId": str(signal.id),
                        "oddsSnapshotId": str(quote.id),
                        "quoteFingerprint": quote.observation_fingerprint,
                        "decisionFingerprint": bet.request_fingerprint,
                        "settlementId": str(settlement.id) if settlement else None,
                        "closingSnapshotId": str(proxy.closing_odds_snapshot_id)
                        if proxy.available
                        else None,
                        "closingFingerprint": proxy.evidence_fingerprint,
                    }
                )
            signals = int(
                session.scalar(
                    select(func.count())
                    .select_from(SignalRecord)
                    .where(SignalRecord.computed_at <= now)
                )
                or 0
            )
            audit = reporting_audit(session, now=now, currency=currency)
            evidence: dict[str, object] = {
                "entries": inputs,
                "signalCount": signals,
                "methodVersion": FINANCIAL_METHOD_VERSION,
                "currency": currency,
                "closingMaxAgeSeconds": self.closing_max_age_seconds,
                "auditFingerprint": fingerprint(audit),
            }
            input_hash = fingerprint(evidence)
            existing = session.scalar(
                select(FinancialReportRecord).where(
                    FinancialReportRecord.input_fingerprint == input_hash
                )
            )
            if existing is not None:
                return _stored(existing)
            document = (
                FinancialMetricsEngine()
                .calculate(observations, signals_count=signals, currency=currency)
                .document()
            )
            document["audit"] = audit
            report_hash = fingerprint({"inputs": evidence, "report": document})
            identity = uuid5(NAMESPACE_URL, f"metiquo:financial-report:{report_hash}")
            connection.execute(
                insert(FinancialReportRecord)
                .values(
                    id=identity,
                    currency=currency,
                    method_version=FINANCIAL_METHOD_VERSION,
                    computed_at=now,
                    document=document,
                    input_evidence=evidence,
                    input_fingerprint=input_hash,
                    report_fingerprint=report_hash,
                )
                .on_conflict_do_nothing(index_elements=["input_fingerprint"])
            )
            return StoredFinancialReport(
                identity, currency, now, document, evidence, input_hash, report_hash
            )

    def latest(self, *, currency: str) -> StoredFinancialReport | None:
        with Session(self.engine) as session:
            row = session.scalar(
                select(FinancialReportRecord)
                .where(
                    FinancialReportRecord.currency == currency,
                    FinancialReportRecord.computed_at <= self.clock.now().value,
                )
                .order_by(FinancialReportRecord.computed_at.desc(), FinancialReportRecord.id)
                .limit(1)
            )
            return _stored(row) if row is not None else None

    def get(self, report_id: UUID) -> StoredFinancialReport | None:
        with Session(self.engine) as session:
            row = session.get(FinancialReportRecord, report_id)
            return _stored(row) if row is not None else None


def _stored(row: FinancialReportRecord) -> StoredFinancialReport:
    if (
        fingerprint(row.input_evidence) != row.input_fingerprint
        or fingerprint({"inputs": row.input_evidence, "report": row.document})
        != row.report_fingerprint
    ):
        raise BusinessError(ErrorCode.INVALID_STATE, "Empreinte du rapport financier invalide")
    return StoredFinancialReport(
        row.id,
        row.currency,
        row.computed_at,
        row.document,
        row.input_evidence,
        row.input_fingerprint,
        row.report_fingerprint,
    )
