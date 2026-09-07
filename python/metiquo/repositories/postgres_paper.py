"""Lecture paginée du ledger et des proxies de clôture, sans calcul financier lourd."""

from uuid import UUID

from sqlalchemy import Engine, func, select, true
from sqlalchemy.orm import Session, aliased

from metiquo.contracts import PaperBet
from metiquo.contracts.enums import PaperBetStatus
from metiquo.db.paper_models import PaperBetRecord, PaperSettlementRecord
from metiquo.foundation.time import Clock
from metiquo.paper.closing_line import PostgresClosingLineRepository
from metiquo.paper.creation import entry_dto
from metiquo.paper.settlement_job import settled_dto


class PostgresPaperRepository:
    def __init__(self, engine: Engine, clock: Clock, *, closing_max_age_seconds: int = 90) -> None:
        self.engine, self.clock = engine, clock
        self.closing_max_age_seconds = closing_max_age_seconds

    def page(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        status: PaperBetStatus | None = None,
        paper_bet_id: UUID | None = None,
    ) -> tuple[tuple[PaperBet, ...], int]:
        now = self.clock.now().value
        with self.engine.connect() as connection, Session(bind=connection) as session:
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
            settlement = aliased(PaperSettlementRecord, latest)
            query = (
                select(PaperBetRecord, settlement)
                .outerjoin(latest, true())
                .where(PaperBetRecord.placed_at <= now)
            )
            if status is not None:
                query = query.where(func.coalesce(settlement.status, "open") == status.value)
            if paper_bet_id is not None:
                query = query.where(PaperBetRecord.id == paper_bet_id)
            total = int(session.scalar(select(func.count()).select_from(query.subquery())) or 0)
            rows = session.execute(
                query.order_by(PaperBetRecord.placed_at.desc(), PaperBetRecord.id)
                .offset(offset)
                .limit(limit)
            ).all()
            proxies = {
                p.paper_bet_id: p
                for p in PostgresClosingLineRepository(
                    connection,
                    max_age_seconds=self.closing_max_age_seconds,
                    clock=self.clock,
                ).get_many(tuple(row[0].id for row in rows))
            }
            result = []
            for bet, revision in rows:
                dto = settled_dto(bet, revision) if revision is not None else entry_dto(bet)
                proxy = proxies[bet.id]
                result.append(
                    dto.model_copy(
                        update={
                            "closing_odds_snapshot_id": proxy.closing_odds_snapshot_id
                            if proxy.available
                            else None,
                            "clv": proxy.clv,
                            "clv_is_proxy": True,
                        }
                    )
                )
            return tuple(result), total

    def get(self, paper_bet_id: UUID) -> PaperBet | None:
        rows, _ = self.page(paper_bet_id=paper_bet_id, limit=1)
        return rows[0] if rows else None
