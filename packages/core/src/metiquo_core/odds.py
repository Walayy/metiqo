from datetime import UTC
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from metiquo_core.contracts import Quote
from metiquo_core.models import EsportMatch, Market, OddsObservation


def record_quote(session: Session, market_id: UUID, quote: Quote) -> None:
    """Future adapter boundary. The caller owns the transaction; duplicate delivery is safe."""
    market = session.scalar(select(Market).where(Market.id == market_id).with_for_update())
    if market is None:
        raise ValueError("Unknown market; resolve identities and register the match first")
    match = session.get(EsportMatch, market.match_id)
    if match is None or market.pick_id not in (match.home_id, match.away_id):
        raise ValueError("Selection does not belong to this match")
    recorded_at = quote.recorded_at.astimezone(UTC)
    if recorded_at < match.registered_at:
        raise ValueError("Observation predates match registration")
    odds = Decimal(str(quote.odds)).quantize(Decimal("0.000001"))
    previous = session.get(OddsObservation, (market_id, recorded_at))
    if previous:
        if previous.odds != odds:
            raise ValueError("Conflicting observations at the same timestamp")
        return
    session.add(OddsObservation(market_id=market_id, recorded_at=recorded_at, odds=odds))
