"""Preuve PostgreSQL des versions et audits de seuils de value."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from metiquo.contracts.enums import MarketType
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.pricing import (
    PolicyRegistrationError,
    PostgresValuePolicyRepository,
    ValuePolicy,
    ValueThresholdOverride,
    ValueThresholds,
)
from tests.integration.test_migrations import alembic_config

_NOW = datetime(2026, 9, 7, 21, 30, tzinfo=UTC)
_TUNED_THROUGH = datetime(2026, 7, 31, 23, 59, tzinfo=UTC)
_FINAL_TEST_START = datetime(2026, 8, 1, tzinfo=UTC)
_COMPETITION_ID = UUID("22222222-2222-4222-8222-222222222222")


@pytest.mark.integration
def test_policy_versions_are_idempotent_chained_and_audited(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url, connect_args={"options": "-c timezone=UTC"})
    repository = PostgresValuePolicyRepository(engine, FixedClock(UtcInstant(_NOW)))
    initial = _policy("integration-value-policy-v1", Decimal("0.03"))
    revised = _policy("integration-value-policy-v2", Decimal("0.05"))

    first = repository.register(
        initial,
        actor="pricing-admin",
        reason="Initial thresholds selected before final test",
    )
    replay = repository.register(
        initial,
        actor="pricing-admin",
        reason="Idempotent replay",
    )
    second = repository.register(
        revised,
        actor="pricing-reviewer",
        reason="Raise edge using validation window only",
        previous_version=initial.version,
    )

    assert first == replay == repository.get(initial.version)
    assert second == repository.get(revised.version)
    assert second.resolve(
        MarketType.MATCH_WINNER,
        competition_id=_COMPETITION_ID,
        bucket="longshot",
    ).thresholds == ValueThresholds(
        min_edge=Decimal("0.09"),
        min_ev=Decimal("0.05"),
        min_conservative_ev=Decimal("0.00"),
        max_odds_age_seconds=45,
        min_mapping_confidence=Decimal("0.90"),
    )

    audits = repository.list_audits()
    matching_audits = tuple(
        audit for audit in audits if audit.policy_version.startswith("integration-value-policy-")
    )
    assert [audit.action for audit in matching_audits] == ["policy.created", "policy.revised"]
    assert matching_audits[1].previous_version == initial.version
    assert matching_audits[1].actor == "pricing-reviewer"
    assert matching_audits[1].changes["previousVersion"] == initial.version

    with pytest.raises(PolicyRegistrationError, match="previous_version"):
        repository.register(
            _policy("integration-value-policy-v3", Decimal("0.06")),
            actor="pricing-reviewer",
            reason="Missing chain must fail",
        )
    with pytest.raises(PolicyRegistrationError, match="redéfinie"):
        repository.register(
            _policy(initial.version, Decimal("0.04")),
            actor="pricing-reviewer",
            reason="Existing version cannot change",
            previous_version=revised.version,
        )

    with engine.begin() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(
            text("UPDATE signals.value_policies SET min_edge = 0.01 WHERE version = :version"),
            {"version": initial.version},
        )
    with engine.begin() as connection, pytest.raises(DBAPIError, match="append-only"):
        connection.execute(
            text(
                "DELETE FROM signals.value_policy_audits "
                "WHERE policy_id = (SELECT id FROM signals.value_policies WHERE version = :version)"
            ),
            {"version": revised.version},
        )
    engine.dispose()


def _policy(version: str, min_edge: Decimal) -> ValuePolicy:
    return ValuePolicy(
        version=version,
        thresholds=ValueThresholds(
            min_edge=min_edge,
            min_ev=Decimal("0.05"),
            min_conservative_ev=Decimal("0.00"),
            max_odds_age_seconds=90,
            min_mapping_confidence=Decimal("0.80"),
        ),
        tuned_through=_TUNED_THROUGH,
        final_test_starts_at=_FINAL_TEST_START,
        market_overrides={MarketType.MATCH_WINNER: ValueThresholdOverride(min_ev=Decimal("0.05"))},
        competition_overrides={
            _COMPETITION_ID: ValueThresholdOverride(min_mapping_confidence=Decimal("0.90"))
        },
        bucket_overrides={
            "longshot": ValueThresholdOverride(
                min_edge=Decimal("0.09"),
                max_odds_age_seconds=45,
            )
        },
    )
