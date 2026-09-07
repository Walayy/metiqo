"""Compte personnel, empreintes privées et rotation concurrente sur PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from metiquo.auth.service import AuthError, OwnerAuthService
from metiquo.config import AuthMode
from metiquo.foundation.time import FixedClock, UtcInstant
from tests.integration.test_job_queue import NOW
from tests.integration.test_migrations import alembic_config
from tests.integration.test_postgres_canonical_api import _settings

FIXTURE_PASSWORD = "fixture-only-owner-passphrase"


@pytest.mark.integration
def test_owner_credentials_sessions_rotation_and_password_reset(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "real").model_copy(update={"auth_mode": AuthMode.OWNER})
    clock = FixedClock(UtcInstant(NOW))
    service = OwnerAuthService(engine, settings, clock=clock)
    owner_id = service.bootstrap("Owner", FIXTURE_PASSWORD)
    with pytest.raises(AuthError, match="AUTH_OWNER_EXISTS"):
        service.bootstrap("another", FIXTURE_PASSWORD)
    for username, password in (("owner", "wrong-fixture-password"), ("unknown", FIXTURE_PASSWORD)):
        with pytest.raises(AuthError, match="AUTH_INVALID_CREDENTIALS"):
            service.login(username, password)
    first = service.login("owner", FIXTURE_PASSWORD)
    assert first.principal.owner_id == owner_id
    assert service.authenticate(first.token) is not None
    with engine.connect() as connection:
        stored_password = connection.scalar(text("SELECT password_hash FROM ops.owner_accounts"))
        stored_session = connection.scalar(text("SELECT token_hash FROM ops.owner_sessions"))
        assert stored_password.startswith("$argon2id$")
        assert FIXTURE_PASSWORD not in stored_password
        assert first.token != stored_session and len(stored_session) == 64
        assert first.token not in str(
            connection.execute(text("SELECT * FROM ops.audit_events")).all()
        )

    rotated_service = OwnerAuthService(
        engine,
        settings,
        clock=FixedClock(
            UtcInstant(NOW + timedelta(seconds=settings.auth_session_rotation_seconds + 1))
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = tuple(pool.map(rotated_service.authenticate, (first.token, first.token)))
    assert all(result is not None for result in concurrent)
    assert sum(result.replacement is not None for result in concurrent if result) == 1
    rotated = next(result for result in concurrent if result and result.replacement)
    assert rotated is not None and rotated.replacement is not None
    new_token = rotated.replacement.token
    assert new_token != first.token
    # Une requête simultanée au renouvellement peut finir sans invalider le nouveau cookie.
    parallel = rotated_service.authenticate(first.token)
    assert parallel is not None and parallel.replacement is None
    later = OwnerAuthService(
        engine,
        settings,
        clock=FixedClock(
            UtcInstant(
                NOW
                + timedelta(
                    seconds=settings.auth_session_rotation_seconds
                    + settings.auth_session_grace_seconds
                    + 2
                )
            )
        ),
    )
    assert later.authenticate(first.token) is None
    assert later.authenticate(new_token) is not None
    later.reset_password("owner", "replacement-fixture-passphrase")
    assert later.authenticate(new_token) is None
    with pytest.raises(AuthError, match="AUTH_INVALID_CREDENTIALS"):
        later.login("owner", FIXTURE_PASSWORD)
    final = later.login("owner", "replacement-fixture-passphrase")
    later.logout(final.token)
    assert later.authenticate(final.token) is None
    for statement in (
        "DELETE FROM ops.owner_accounts",
        "TRUNCATE ops.owner_sessions",
        "UPDATE ops.owner_sessions SET status='active', revoked_at=NULL WHERE status='revoked'",
        "UPDATE ops.owner_accounts SET password_hash='tampered'",
    ):
        with pytest.raises(DBAPIError), engine.begin() as connection:
            connection.execute(text(statement))
    engine.dispose()


@pytest.mark.integration
def test_session_expiration_and_fixation_are_bounded(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "real").model_copy(update={"auth_mode": AuthMode.OWNER})
    service = OwnerAuthService(engine, settings, clock=FixedClock(UtcInstant(NOW)))
    service.bootstrap("owner", FIXTURE_PASSWORD)
    first = service.login("owner", FIXTURE_PASSWORD)
    second = service.login("owner", FIXTURE_PASSWORD, previous_token=first.token)
    assert first.token != second.token
    assert service.authenticate(first.token) is None
    expired = OwnerAuthService(
        engine,
        settings,
        clock=FixedClock(
            UtcInstant(NOW + timedelta(seconds=settings.auth_session_idle_seconds + 1))
        ),
    )
    assert expired.authenticate(second.token) is None
    assert service.authenticate("untrusted cookie") is None
    engine.dispose()


@pytest.mark.integration
def test_absolute_expiration_survives_activity_and_rotation(postgresql_url: str) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    engine = create_engine(postgresql_url)
    settings = _settings(postgresql_url, "real").model_copy(
        update={
            "auth_mode": AuthMode.OWNER,
            "auth_session_idle_seconds": 180,
            "auth_session_rotation_seconds": 60,
            "auth_session_absolute_seconds": 300,
        }
    )
    service = OwnerAuthService(engine, settings, clock=FixedClock(UtcInstant(NOW)))
    service.bootstrap("owner", FIXTURE_PASSWORD)
    grant = service.login("owner", FIXTURE_PASSWORD)
    for seconds in (70, 140, 210, 280):
        active = OwnerAuthService(
            engine, settings, clock=FixedClock(UtcInstant(NOW + timedelta(seconds=seconds)))
        ).authenticate(grant.token)
        assert active is not None and active.replacement is not None
        assert active.replacement.expires_at == NOW + timedelta(seconds=300)
        grant = active.replacement
    expired = OwnerAuthService(
        engine, settings, clock=FixedClock(UtcInstant(NOW + timedelta(seconds=300)))
    )
    assert expired.authenticate(grant.token) is None
    engine.dispose()
