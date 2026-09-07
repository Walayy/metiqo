"""Créneaux UTC configurables, sans rattrapage en rafale."""

from datetime import UTC, datetime, timedelta

from metiquo.worker.scheduler import SchedulePolicy, planned_jobs


def test_scheduler_selects_current_closed_and_modified_years_once_per_slot() -> None:
    now = datetime(2026, 9, 8, 7, 5, tzinfo=UTC)
    policy = SchedulePolicy(current_year=2026)
    initial = planned_jobs(policy, now, {2024: False, 2025: True, 2026: False})
    assert {item.job_type for item in initial} == {
        "oe.catalog",
        "oe.audit",
        "oe.sync",
        "oe.deep",
        "paper.settle",
        "paper.report",
    }
    current = next(item for item in initial if item.job_type == "oe.sync")
    assert current.scheduled_at == now.replace(hour=6, minute=0)
    assert current.scope == "oe:oracles_elixir:2026"
    same = planned_jobs(policy, now + timedelta(minutes=1), {2024: False, 2025: True, 2026: False})
    assert {item.key for item in initial} == {item.key for item in same}
    next_month = planned_jobs(policy, now.replace(month=10), {2024: False, 2025: True, 2026: False})
    assert next(item.key for item in initial if item.job_type == "oe.audit") != next(
        item.key for item in next_month if item.job_type == "oe.audit"
    )
    custom = planned_jobs(
        SchedulePolicy(current_year=2026, current_seconds=3600), now, {2026: False}
    )
    assert next(item.scheduled_at.hour for item in custom if item.job_type == "oe.sync") == 7
