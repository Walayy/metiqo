"""Contrats HTTP des mutations mock contrôlées."""

import asyncio
from datetime import UTC, datetime

from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient, Response

from metiquo.api.app import create_app
from metiquo.api.readiness import ReadinessCheck
from metiquo.config import Settings
from metiquo.foundation.time import FixedClock, UtcInstant

REFERENCE_TIME = datetime(2026, 9, 4, 12, tzinfo=UTC)


class ReadyProbe:
    def check(self) -> ReadinessCheck:
        return ReadinessCheck(available=True)


def build_app() -> FastAPI:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "mock",
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "mock",
            "mock_seed": "metiquo-mutations-test",
        }
    )
    return create_app(
        settings=settings,
        readiness_probe=ReadyProbe(),
        clock=FixedClock(UtcInstant(REFERENCE_TIME)),
    )


def request(
    app: FastAPI,
    method: str,
    path: str,
    *,
    key: str | None = None,
    payload: dict[str, object] | None = None,
) -> Response:
    async def send_request() -> Response:
        transport = ASGITransport(app=app)
        headers = {"Idempotency-Key": key} if key is not None else {}
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, headers=headers, json=payload)

    return asyncio.run(send_request())


def get(app: FastAPI, path: str) -> Response:
    return request(app, "GET", path)


def post(
    app: FastAPI,
    path: str,
    key: str | None,
    payload: dict[str, object] | None = None,
) -> Response:
    return request(app, "POST", path, key=key, payload=payload)


def test_sync_is_idempotent_and_requires_a_key() -> None:
    app = build_app()
    path = "/api/v1/admin/oracles-elixir/sync"

    missing = post(app, path, None)
    first = post(app, path, "sync-key-0001")
    second = post(app, path, "sync-key-0001")

    assert missing.status_code == 422
    assert first.status_code == 200
    assert second.json() == first.json()
    assert first.json()["data"]["rowCount"] == 12
    audit = get(app, "/api/v1/admin/audit-log").json()
    assert audit["page"]["total"] == 1
    assert audit["data"][0]["action"] == "mock.sync"


def test_model_train_promote_and_retire_return_realistic_states() -> None:
    app = build_app()

    train = post(
        app,
        "/api/v1/admin/models/train",
        "train-key-0001",
        {"gameTitle": "lol", "marketType": "MATCH_WINNER"},
    )
    assert train.status_code == 200
    candidate_id = train.json()["data"]["modelVersionId"]
    assert train.json()["data"]["status"] == "candidate"

    promoted = post(
        app,
        f"/api/v1/admin/models/{candidate_id}/promote",
        "promote-key-01",
        {"reason": "Validation mock réussie"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["data"]["status"] == "champion"
    assert promoted.json()["data"]["promotedAt"] == "2026-09-04T12:00:00Z"

    existing_id = get(app, "/api/v1/models?limit=1").json()["data"][0]["modelVersionId"]
    retired = post(
        app,
        f"/api/v1/admin/models/{existing_id}/retire",
        "retire-key-001",
        {"reason": "Remplacé par le candidat mock"},
    )
    assert retired.status_code == 200
    assert retired.json()["data"]["status"] == "retired"


def test_paper_bet_creation_and_settlement_are_idempotent() -> None:
    app = build_app()
    signal_id = get(app, "/api/v1/opportunities?grade=STRONG_VALUE").json()["data"][0]["signalId"]
    path = "/api/v1/paper-bets"
    payload: dict[str, object] = {
        "signalId": signal_id,
        "stakeAmount": "10.00",
        "currency": "EUR",
    }

    created = post(app, path, "paper-create-01", payload)
    duplicate = post(app, path, "paper-create-01", payload)
    assert created.status_code == 200
    assert duplicate.json() == created.json()
    assert created.json()["data"]["status"] == "open"

    conflict = post(
        app,
        path,
        "paper-create-01",
        {**payload, "stakeAmount": "20.00"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "CONFLICT"

    paper_bet_id = created.json()["data"]["paperBetId"]
    settled = post(
        app,
        "/api/v1/admin/paper-bets/settle",
        "paper-settle-01",
        {
            "paperBetId": paper_bet_id,
            "status": "won",
            "profitLoss": "35.00",
            "reason": "Résultat mock confirmé",
        },
    )
    assert settled.status_code == 200
    assert settled.json()["data"]["status"] == "won"
    assert settled.json()["data"]["profitLoss"] == "35.00"


def test_mapping_alias_and_all_actions_are_audited_once() -> None:
    app = build_app()
    mapping_id = get(app, "/api/v1/admin/mappings/pending").json()["data"][0]["mappingReviewId"]
    event_id = get(app, "/api/v1/events?limit=1").json()["data"][0]["eventId"]

    approved = post(
        app,
        f"/api/v1/admin/mappings/{mapping_id}/approve",
        "mapping-key-001",
        {"reviewer": "mock-admin", "reason": "Participants confirmés"},
    )
    alias = post(
        app,
        "/api/v1/admin/aliases",
        "alias-key-0001",
        {"provider": "mock-provider", "alias": "Aurore", "canonicalId": event_id},
    )

    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "approved"
    assert alias.status_code == 200
    assert alias.json()["data"]["dataMode"] == "mock"
    audit = get(app, "/api/v1/admin/audit-log")
    assert audit.status_code == 200
    assert [item["action"] for item in audit.json()["data"]] == [
        "mapping.approved",
        "alias.create",
    ]
    assert all(len(item["idempotencyFingerprint"]) == 64 for item in audit.json()["data"])


def test_non_publishable_opportunity_cannot_create_paper_bet() -> None:
    app = build_app()
    signal_id = get(app, "/api/v1/opportunities?grade=BLOCKED&limit=1").json()["data"][0][
        "signalId"
    ]

    response = post(
        app,
        "/api/v1/paper-bets",
        "blocked-paper-1",
        {"signalId": signal_id, "stakeAmount": "10.00", "currency": "EUR"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"
    assert get(app, "/api/v1/admin/audit-log").json()["page"]["total"] == 0
