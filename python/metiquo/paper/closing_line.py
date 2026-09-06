"""Proxy de clôture calculé exclusivement sur les observations connues pré-start."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from uuid import UUID

from sqlalchemy import DateTime, Engine, cast, select, true
from sqlalchemy.orm import Session, aliased

from metiquo.db.odds_models import OddsSnapshotRecord
from metiquo.db.paper_models import PaperBetRecord
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.time import Clock, SystemClock
from metiquo.paper.creation import decimal_text, fingerprint

CLOSING_METHOD_VERSION = "observed-price-ratio-v1"


@dataclass(frozen=True, slots=True)
class ClosingLineProxy:
    paper_bet_id: UUID
    entry_odds: Decimal
    closing_odds_snapshot_id: UUID | None
    closing_odds: Decimal | None
    captured_at: datetime | None
    event_starts_at: datetime | None
    clv: Decimal | None
    reason: str
    max_age_seconds: int
    quote_fingerprint: str | None
    is_proxy: bool = True
    method_version: str = CLOSING_METHOD_VERSION

    @property
    def available(self) -> bool:
        return self.clv is not None

    @property
    def evidence_fingerprint(self) -> str:
        return fingerprint(
            {
                "paperBetId": str(self.paper_bet_id),
                "entryOdds": decimal_text(self.entry_odds),
                "closingOddsSnapshotId": str(self.closing_odds_snapshot_id)
                if self.closing_odds_snapshot_id
                else None,
                "quoteFingerprint": self.quote_fingerprint,
                "clv": decimal_text(self.clv) if self.clv is not None else None,
                "reason": self.reason,
                "maxAgeSeconds": self.max_age_seconds,
                "eventStartsAt": self.event_starts_at.isoformat() if self.event_starts_at else None,
                "methodVersion": self.method_version,
            }
        )


class PostgresClosingLineRepository:
    """Projection déterministe de faits immuables, avec requête groupée sans N+1."""

    def __init__(
        self, engine: Engine, *, max_age_seconds: int = 90, clock: Clock | None = None
    ) -> None:
        if max_age_seconds <= 0:
            raise ValueError("L'âge maximal de clôture doit être positif")
        self.engine, self.max_age_seconds = engine, max_age_seconds
        self.clock = clock or SystemClock()

    def get(self, paper_bet_id: UUID) -> ClosingLineProxy:
        results = self.get_many((paper_bet_id,))
        if not results:
            raise BusinessError(ErrorCode.NOT_FOUND, "Décision paper introuvable")
        return results[0]

    def get_many(self, paper_bet_ids: Sequence[UUID]) -> tuple[ClosingLineProxy, ...]:
        if not paper_bet_ids:
            return ()
        entry = aliased(OddsSnapshotRecord, name="entry_quote")
        quote = aliased(OddsSnapshotRecord, name="closing_quote")
        starts = cast(
            PaperBetRecord.decision_evidence["eventProof"]["startAt"].as_string(),
            DateTime(timezone=True),
        )
        latest = (
            select(quote)
            .where(
                quote.market_id == entry.market_id,
                quote.selection_id == entry.selection_id,
                quote.line.is_not_distinct_from(entry.line),
                quote.timestamp_reliable.is_(True),
                quote.informational_only.is_(False),
                quote.captured_at < starts,
                quote.recorded_at < starts,
                quote.event_status == "scheduled",
                quote.market_status == "open",
                quote.provider_status == "operational",
            )
            .order_by(quote.captured_at.desc(), quote.recorded_at.desc(), quote.id)
            .limit(1)
            .correlate(PaperBetRecord, entry)
            .lateral()
        )
        closing = aliased(OddsSnapshotRecord, latest)
        query = (
            select(PaperBetRecord, closing, starts)
            .join(entry, entry.id == PaperBetRecord.odds_snapshot_id)
            .outerjoin(latest, true())
            .where(PaperBetRecord.id.in_(paper_bet_ids))
            .order_by(PaperBetRecord.id)
        )
        now = self.clock.now().value
        results: list[ClosingLineProxy] = []
        with Session(self.engine) as session:
            for bet, observed, start in session.execute(query).all():
                value: Decimal | None = None
                if start is None:
                    reason = "ENTRY_EVENT_PROOF_MISSING"
                elif now < start:
                    reason = "EVENT_NOT_STARTED"
                elif observed is None or observed.captured_at is None:
                    reason = "CLOSING_UNAVAILABLE"
                elif (start - observed.captured_at).total_seconds() > self.max_age_seconds:
                    reason = "CLOSING_TOO_OLD"
                else:
                    reason = "AVAILABLE_PROXY"
                    with localcontext() as ctx:
                        ctx.prec = 60
                        value = (bet.entry_odds / observed.decimal_odds - 1).quantize(
                            Decimal("0.000000000001")
                        )
                results.append(
                    ClosingLineProxy(
                        bet.id,
                        bet.entry_odds,
                        observed.id if observed else None,
                        observed.decimal_odds if observed else None,
                        observed.captured_at if observed else None,
                        start,
                        value,
                        reason,
                        self.max_age_seconds,
                        observed.observation_fingerprint if observed else None,
                    )
                )
        return tuple(results)
