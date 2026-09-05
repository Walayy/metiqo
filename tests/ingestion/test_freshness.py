"""Classification de fraîcheur et politiques stale/strictes."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from metiquo.contracts.enums import FreshnessStatus
from metiquo.foundation.time import FixedClock, UtcInstant
from metiquo.ingestion.freshness import (
    FreshDataRequired,
    FreshnessFacts,
    FreshnessPolicy,
    FreshnessService,
    PublishedSnapshot,
)

NOW = datetime(2026, 9, 6, 3, tzinfo=UTC)
CATALOG_ID = uuid4()
SNAPSHOT_ID = uuid4()


class FakeFreshnessRepository:
    def __init__(self, facts: FreshnessFacts) -> None:
        self.facts = facts

    def get_facts(self, source_catalog_id: UUID) -> FreshnessFacts:
        assert source_catalog_id == CATALOG_ID
        return self.facts


def _service(facts: FreshnessFacts) -> FreshnessService:
    return FreshnessService(
        repository=FakeFreshnessRepository(facts),
        sla=timedelta(hours=3),
        clock=FixedClock(UtcInstant(NOW)),
    )


def _current(*, age: timedelta = timedelta(hours=1)) -> PublishedSnapshot:
    return PublishedSnapshot(id=SNAPSHOT_ID, validated_at=NOW - age)


@pytest.mark.parametrize(
    ("facts", "expected_status", "expected_reason"),
    [
        (
            FreshnessFacts(catalog_status="active", current=_current()),
            FreshnessStatus.FRESH,
            "FRESHNESS_WITHIN_SLA",
        ),
        (
            FreshnessFacts(catalog_status="active", current=_current(age=timedelta(hours=4))),
            FreshnessStatus.STALE,
            "FRESHNESS_SLA_EXCEEDED",
        ),
        (
            FreshnessFacts(
                catalog_status="active",
                current=_current(),
                failed_at=NOW,
                failure_code="SOURCE_TIMEOUT",
            ),
            FreshnessStatus.DEGRADED,
            "SOURCE_TIMEOUT",
        ),
        (
            FreshnessFacts(
                catalog_status="active",
                current=_current(),
                quarantined_at=NOW,
            ),
            FreshnessStatus.QUARANTINED,
            "NEWER_CONTENT_QUARANTINED",
        ),
        (
            FreshnessFacts(
                catalog_status="active",
                current=None,
                failed_at=NOW,
                failure_code="SOURCE_NOT_FOUND",
            ),
            FreshnessStatus.FAILED,
            "SOURCE_NOT_FOUND",
        ),
    ],
)
def test_freshness_states_are_deterministic(
    facts: FreshnessFacts,
    expected_status: FreshnessStatus,
    expected_reason: str,
) -> None:
    decision = _service(facts).evaluate(CATALOG_ID, policy=FreshnessPolicy())

    assert decision.status is expected_status
    assert decision.reason_code == expected_reason
    assert decision.usable is (expected_status is FreshnessStatus.FRESH)


@pytest.mark.parametrize(
    "status_facts",
    [
        FreshnessFacts(catalog_status="active", current=_current(age=timedelta(hours=4))),
        FreshnessFacts(catalog_status="blocked", current=_current()),
        FreshnessFacts(catalog_status="active", current=_current(), quarantined_at=NOW),
    ],
)
def test_allow_stale_reuses_only_the_validated_current_snapshot(
    status_facts: FreshnessFacts,
) -> None:
    decision = _service(status_facts).evaluate(
        CATALOG_ID,
        policy=FreshnessPolicy(allow_stale=True),
    )

    assert decision.usable is True
    assert decision.snapshot_id == SNAPSHOT_ID
    assert status_facts.current is not None
    assert decision.as_of == status_facts.current.validated_at
    assert decision.status is not FreshnessStatus.FRESH


def test_allow_stale_never_invents_a_snapshot_when_none_was_validated() -> None:
    decision = _service(FreshnessFacts(catalog_status="active", current=None)).evaluate(
        CATALOG_ID,
        policy=FreshnessPolicy(allow_stale=True),
    )

    assert decision.status is FreshnessStatus.FAILED
    assert decision.usable is False
    assert decision.snapshot_id is None
    assert decision.as_of is None


def test_require_fresh_has_stable_nonzero_exit_code_and_diagnostic() -> None:
    service = _service(
        FreshnessFacts(catalog_status="active", current=_current(age=timedelta(hours=4)))
    )

    with pytest.raises(FreshDataRequired) as captured:
        service.evaluate(CATALOG_ID, policy=FreshnessPolicy(require_fresh=True))

    assert captured.value.exit_code == 3
    assert captured.value.decision.status is FreshnessStatus.STALE
    assert captured.value.decision.usable is False
    assert captured.value.decision.to_dict() == {
        "status": "stale",
        "usable": False,
        "asOf": "2026-09-05T23:00:00Z",
        "snapshotId": str(SNAPSHOT_ID),
        "ageSeconds": 14_400,
        "slaSeconds": 10_800,
        "reasonCode": "FRESHNESS_SLA_EXCEEDED",
    }


def test_conflicting_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="incompatibles"):
        FreshnessPolicy(allow_stale=True, require_fresh=True)
