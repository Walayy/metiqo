"""The server releases its shared database pool exactly once on shutdown."""

import asyncio

import pytest

from metiquo.api.app import create_app
from metiquo.config import Settings


def test_api_lifespan_disposes_shared_auth_and_read_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": "real",
            "auth_mode": "owner",
            "database_url": "postgresql+psycopg://fixture@127.0.0.1:1/fixture",
            "odds_provider": "disabled",
        }
    )
    app = create_app(settings=settings)
    engine = app.state.real_admin_engine
    disposed = []
    monkeypatch.setattr(engine, "dispose", lambda: disposed.append(True))

    async def lifecycle() -> None:
        async with app.router.lifespan_context(app):
            assert disposed == []

    asyncio.run(lifecycle())
    assert disposed == [True]
