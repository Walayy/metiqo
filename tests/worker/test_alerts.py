"""Règles locales de supervision, sans signaler les anciennes anomalies comme actives."""

from metiquo.worker.alerts import AlertFacts, alert_conditions


def test_alert_rules_cover_stale_missing_and_thresholds() -> None:
    assert alert_conditions(AlertFacts("fresh", "fresh", 0, 0, "fresh"), mapping_limit=10) == ()
    facts = AlertFacts("stale", "stale", 10, 2, "failed")
    alerts = alert_conditions(facts, mapping_limit=10)
    assert {item.code for item in alerts} == {
        "SOURCE_UNHEALTHY",
        "MODEL_UNHEALTHY",
        "MAPPING_BACKLOG",
        "DQ_BLOCKING",
        "BACKUP_UNHEALTHY",
    }
    assert next(item.details for item in alerts if item.code == "DQ_BLOCKING") == {"count": 2}
    missing = alert_conditions(
        AlertFacts("failed", "missing", 9, 0, "not_configured"), mapping_limit=10
    )
    assert {item.code for item in missing} == {
        "SOURCE_UNHEALTHY",
        "MODEL_UNHEALTHY",
        "BACKUP_UNHEALTHY",
    }
