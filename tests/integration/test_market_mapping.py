"""Persistance PostgreSQL des règles et marchés provider inconnus."""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import Engine, Table, create_engine, insert, select, text
from sqlalchemy.exc import DBAPIError

from metiquo.contracts.enums import MarketPeriod, MarketType, SelectionType
from metiquo.db.odds_models import (
    MarketMappingAttempt,
    MarketRulesRecord,
    OddsProviderRecord,
    ProviderOddsEvent,
)
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.mapping import (
    MarketMappingStatus,
    MarketRulesReference,
    PostgresMarketMappingService,
    RawProviderMarket,
    UnresolvedMarketMappingError,
)
from tests.integration.test_migrations import alembic_config

_NOW = datetime(2026, 9, 7, 19, 0, tzinfo=UTC)


@pytest.mark.integration
def test_market_rules_and_raw_unknown_attempts_are_append_only(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    provider_code, external_event_id = _seed_provider_event(engine)
    service = PostgresMarketMappingService(engine, FixedClock(UtcInstant(_NOW)))
    rules = _rules()

    rules_id = service.register_rules(rules)
    assert service.register_rules(rules) == rules_id
    mapped = service.map_market(provider_code, external_event_id, _raw())
    unknown = service.map_market(
        provider_code,
        external_event_id,
        _raw(
            provider_market_id="provider-total-kills",
            raw_label="Total kills",
            declared_type="TOTAL_KILLS",
        ),
    )

    attempts = cast(Table, MarketMappingAttempt.__table__)
    stored_rules = cast(Table, MarketRulesRecord.__table__)
    with engine.connect() as connection:
        rows = {
            row.provider_market_id: row for row in connection.execute(select(attempts)).mappings()
        }
        fingerprint = connection.execute(
            select(stored_rules.c.fingerprint).where(stored_rules.c.id == rules_id)
        ).scalar_one()

    assert mapped.status is MarketMappingStatus.MAPPED
    assert mapped.require_mapped().market_type is MarketType.MATCH_WINNER
    assert unknown.status is MarketMappingStatus.UNKNOWN
    with pytest.raises(UnresolvedMarketMappingError, match="aucune prédiction"):
        unknown.require_mapped()
    assert rows["provider-match-winner"]["rules_reference"] == rules.reference
    assert rows["provider-match-winner"]["canonical_period"] == "SERIES"
    assert rows["provider-total-kills"]["rules_reference"] is None
    assert rows["provider-total-kills"]["canonical_market_type"] is None
    assert rows["provider-total-kills"]["raw_label"] == "Total kills"
    assert rows["provider-total-kills"]["raw_descriptor"] == {
        "declaredType": "TOTAL_KILLS",
        "period": "SERIES",
        "line": None,
        "unit": "winner",
        "selectionTypes": ["TEAM_A", "TEAM_B"],
        "outcomeCount": 2,
        "settlementRulesReference": rules.reference,
        "remakePolicy": "void",
        "forfeitPolicy": "settle",
        "cancelledPolicy": "void",
    }
    assert len(fingerprint) == 64

    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as connection:
        connection.execute(
            text("UPDATE odds.market_mapping_attempts SET raw_label = 'rewritten' WHERE id = :id"),
            {"id": unknown.attempt_id},
        )
    with pytest.raises(ValueError, match="autre signature"):
        service.register_rules(
            MarketRulesReference(
                reference=rules.reference,
                market_type=rules.market_type,
                period=rules.period,
                line_required=rules.line_required,
                unit=rules.unit,
                selection_types=(SelectionType.TEAM_A, SelectionType.TEAM_B, SelectionType.DRAW),
                remake_policy=rules.remake_policy,
                forfeit_policy=rules.forfeit_policy,
                cancelled_policy=rules.cancelled_policy,
            )
        )
    engine.dispose()


def _rules() -> MarketRulesReference:
    return MarketRulesReference(
        reference="lol-match-winner-series-v1",
        market_type=MarketType.MATCH_WINNER,
        period=MarketPeriod.SERIES,
        line_required=False,
        unit="winner",
        selection_types=(SelectionType.TEAM_A, SelectionType.TEAM_B),
        remake_policy="void",
        forfeit_policy="settle",
        cancelled_policy="void",
    )


def _raw(**changes: object) -> RawProviderMarket:
    values: dict[str, object] = {
        "provider_market_id": "provider-match-winner",
        "raw_label": "Match winner",
        "declared_type": "MATCH_WINNER",
        "period": "SERIES",
        "line": None,
        "unit": "winner",
        "selection_types": ("TEAM_A", "TEAM_B"),
        "settlement_rules_reference": "lol-match-winner-series-v1",
        "remake_policy": "void",
        "forfeit_policy": "settle",
        "cancelled_policy": "void",
    }
    values.update(changes)
    return RawProviderMarket(**values)  # type: ignore[arg-type]


def _seed_provider_event(engine: Engine) -> tuple[str, str]:
    providers = cast(Table, OddsProviderRecord.__table__)
    events = cast(Table, ProviderOddsEvent.__table__)
    provider_id = uuid4()
    provider_code = f"market-map-{uuid4().hex[:8]}"
    external_event_id = "provider-event-map-005"
    with engine.begin() as connection:
        connection.execute(
            insert(providers).values(
                id=provider_id,
                code=provider_code,
                display_name="Market mapping fixture",
                provider_type="licensed_feed",
                enabled=True,
                created_at=_NOW,
            )
        )
        connection.execute(
            insert(events).values(
                id=uuid4(),
                provider_id=provider_id,
                provider_event_id=external_event_id,
                game_title="lol",
                competition_name="League fixture",
                participants=["Team A", "Team B"],
                starts_at=_NOW,
                best_of=3,
                status="scheduled",
                collected_at=_NOW,
                source_reference="fixture:map-005",
                created_at=_NOW,
            )
        )
    return provider_code, external_event_id
