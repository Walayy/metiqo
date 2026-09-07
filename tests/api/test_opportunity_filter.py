"""Une fiche événement filtre ses signaux avant la pagination globale."""

from uuid import uuid4

from tests.api.test_api import build_test_settings, get

from metiquo.api.app import create_app


def test_event_filter_is_applied_before_pagination_in_the_mock_contract() -> None:
    app = create_app(settings=build_test_settings())
    all_items = get(app, "/api/v1/opportunities?limit=100").json()["data"]
    event_id = all_items[-1]["event"]["eventId"]
    expected = [item for item in all_items if item["event"]["eventId"] == event_id]
    response = get(app, f"/api/v1/opportunities?eventId={event_id}&limit=1").json()
    assert response["data"] == expected[:1]
    assert response["page"]["total"] == len(expected)
    assert get(app, f"/api/v1/opportunities?eventId={uuid4()}").json()["data"] == []


def test_mock_job_filter_supports_the_worker_lifecycle_contract() -> None:
    app = create_app(settings=build_test_settings())
    for status in ("queued", "cancelled", "dead"):
        response = get(app, f"/api/v1/admin/jobs?status={status}")
        assert response.status_code == 200
        assert all(item["status"] == status for item in response.json()["data"])
