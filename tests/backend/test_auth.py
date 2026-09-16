import smtplib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from metiquo_api.auth import EmailRequest, VerifyRequest, digest, fingerprint
from metiquo_api.auth_config import AuthSettings
from metiquo_api.main import create_app
from metiquo_core.models import AppUser, AuthChallenge, AuthRateLimit, AuthSession
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

ORIGIN = "http://127.0.0.1:8080"
HEADERS = {"Origin": ORIGIN, "X-Metiquo-Auth": "1"}
KEY = "only-for-tests-32-character-secret-key"


def test_auth_contracts_and_email_normalization():
    assert EmailRequest(email="  Test@Example.COM ").email == "test@example.com"
    assert EmailRequest(email="user+tag@example.com").email == "user+tag@example.com"
    for email in ("broken", "name@example.com\r\nBcc:other@example.com"):
        with pytest.raises(ValidationError):
            EmailRequest(email=email)
    for code in ("12345", "1234567", "１２３４５６", "abcdef", 123456):
        with pytest.raises(ValidationError):
            VerifyRequest(challengeId=uuid4(), code=code)
    with pytest.raises(ValidationError):
        EmailRequest(email="test@example.com", role="admin")


def test_auth_configuration_fails_closed():
    with pytest.raises(ValidationError):
        AuthSettings(auth_secret="short")
    with pytest.raises(ValidationError):
        AuthSettings(auth_secret=KEY, auth_cookie_secure=False, auth_origins=["http://metiquo.fr"])
    with pytest.raises(ValidationError):
        AuthSettings(auth_secret=KEY, smtp_username="user", smtp_password="secret")
    with pytest.raises(ValidationError):
        AuthSettings(auth_secret=KEY, auth_origins=["*"])
    config = AuthSettings(auth_secret=KEY)
    assert config.auth_cookie_secure
    assert config.session_cookie.startswith("__Host-")
    assert digest(config, "code:one:123456") != digest(config, "code:two:123456")


@pytest.fixture
def auth(database, monkeypatch):
    engine, settings = database
    config = AuthSettings(auth_secret=KEY, auth_cookie_secure=False, auth_origins=[ORIGIN])
    sent = []
    monkeypatch.setattr(
        "metiquo_api.auth.send_login_code", lambda _, email, code: sent.append((email, code))
    )
    app = create_app(settings, config)
    with TestClient(app, base_url=ORIGIN, headers=HEADERS) as client:
        yield client, engine, config, sent, app


def request_code(client, email="person@example.com"):
    response = client.post("/api/v1/auth/request-code", json={"email": email})
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()["challengeId"]


def verify(client, challenge, code):
    return client.post("/api/v1/auth/verify-code", json={"challengeId": challenge, "code": code})


@pytest.mark.integration
def test_registration_session_persistence_and_logout(auth):
    client, engine, config, sent, app = auth
    assert client.get("/api/v1/auth/session").json()["user"] is None
    challenge = request_code(client, "Person@Example.com")
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AppUser)) == 0
        stored = db.get(AuthChallenge, UUID(challenge))
        assert len(stored.code_hash) == 64 and stored.code_hash != sent[-1][1]
        assert stored.binding_hash != client.cookies[config.challenge_cookie]
    wrong = "000000" if sent[-1][1] != "000000" else "111111"
    assert verify(client, challenge, wrong).status_code == 400
    response = verify(client, challenge, sent[-1][1])
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "person@example.com"
    assert response.json()["user"]["role"] == "user"
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
    token = client.cookies[config.session_cookie]
    with Session(engine) as db:
        assert db.get(AuthSession, fingerprint(token)) is not None
        assert db.get(AuthSession, token) is None
    assert token not in response.text and sent[-1][1] not in response.text
    assert verify(client, challenge, sent[-1][1]).status_code == 400
    with TestClient(app, base_url=ORIGIN) as new_tab:
        new_tab.cookies.set(config.session_cookie, token)
        assert (
            new_tab.get("/api/v1/auth/session").json()["user"]["id"]
            == response.json()["user"]["id"]
        )
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.set(config.session_cookie, token)
    assert client.get("/api/v1/auth/session").json()["user"] is None
    assert client.post("/api/v1/auth/logout").status_code == 204


@pytest.mark.integration
def test_admin_is_provisioned_and_repeat_login_preserves_identity(auth):
    client, engine, config, sent, _ = auth
    with Session(engine) as db, db.begin():
        db.add(
            AppUser(
                auth_issuer="metiquo:email",
                auth_subject="admin@metiquo.fr",
                email="admin@metiquo.fr",
                role="admin",
            )
        )
    first = verify(client, request_code(client, "Admin@Metiquo.fr"), sent[-1][1]).json()
    old_token = client.cookies[config.session_cookie]
    with Session(engine) as db, db.begin():
        db.execute(delete(AuthRateLimit))
    second = verify(client, request_code(client, "admin@metiquo.fr"), sent[-1][1]).json()
    assert first["user"]["id"] == second["user"]["id"]
    assert second["user"]["role"] == "admin"
    assert client.cookies[config.session_cookie] != old_token
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AppUser)) == 1
        assert db.get(AuthSession, fingerprint(old_token)) is None


@pytest.mark.integration
def test_code_bound_to_requesting_browser_and_five_attempt_limit(auth):
    client, engine, config, sent, app = auth
    challenge = request_code(client)
    correct = sent[-1][1]
    with TestClient(app, base_url=ORIGIN, headers=HEADERS) as other:
        assert verify(other, challenge, correct).status_code == 400
    wrong = "000000" if correct != "000000" else "111111"
    for _ in range(5):
        assert verify(client, challenge, wrong).status_code == 400
    assert verify(client, challenge, correct).status_code == 400
    with Session(engine) as db:
        assert db.get(AuthChallenge, UUID(challenge)).attempts == 5
        assert db.scalar(select(func.count()).select_from(AppUser)) == 0


@pytest.mark.integration
def test_resend_replaces_old_code_and_limits_survive_new_clients(auth):
    client, engine, _, sent, app = auth
    old = request_code(client)
    old_code = sent[-1][1]
    with TestClient(app, base_url=ORIGIN, headers=HEADERS) as other:
        response = other.post("/api/v1/auth/request-code", json={"email": "PERSON@example.com"})
        assert response.status_code == 429 and int(response.headers["Retry-After"]) > 0
    with Session(engine) as db, db.begin():
        db.execute(
            update(AuthRateLimit).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    new = request_code(client)
    assert old != new and len(sent) == 2
    assert verify(client, old, old_code).status_code == 400
    assert verify(client, new, sent[-1][1]).status_code == 200


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["code", "idle", "absolute"])
def test_expiration_is_enforced_on_server(auth, kind):
    client, engine, config, sent, _ = auth
    challenge = request_code(client)
    past = datetime.now(UTC) - timedelta(days=31)
    if kind == "code":
        with Session(engine) as db, db.begin():
            db.get(AuthChallenge, UUID(challenge)).expires_at = past
        assert verify(client, challenge, sent[-1][1]).status_code == 400
    else:
        assert verify(client, challenge, sent[-1][1]).status_code == 200
        with Session(engine) as db, db.begin():
            stored = db.get(AuthSession, fingerprint(client.cookies[config.session_cookie]))
            if kind == "idle":
                stored.last_seen_at = past
            else:
                stored.expires_at = past
        assert client.get("/api/v1/auth/session").json()["user"] is None


@pytest.mark.integration
def test_smtp_failure_does_not_create_user_or_valid_challenge(auth, monkeypatch):
    client, engine, _, _, _ = auth

    def fail(*_):
        raise smtplib.SMTPException("private SMTP diagnostic")

    monkeypatch.setattr("metiquo_api.auth.send_login_code", fail)
    response = client.post("/api/v1/auth/request-code", json={"email": "person@example.com"})
    assert response.status_code == 503 and "private SMTP" not in response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AppUser)) == 0
        assert db.scalar(select(func.count()).select_from(AuthChallenge)) == 0
        assert db.scalar(select(func.count()).select_from(AuthRateLimit)) > 0


@pytest.mark.integration
def test_csrf_input_validation_and_no_secrets_in_errors(auth):
    client, _, _, sent, _ = auth
    for path in ("request-code", "verify-code", "logout"):
        response = client.post(
            f"/api/v1/auth/{path}", json={}, headers={"Origin": "https://evil.example"}
        )
        assert response.status_code == 403
        assert response.headers["Cache-Control"] == "no-store"
    response = client.post(
        "/api/v1/auth/request-code", json={"email": "admin@metiquo.fr", "role": "admin"}
    )
    assert response.status_code == 422 and "admin@metiquo.fr" not in response.text
    assert not sent
    response = verify(client, str(uuid4()), "1234567")
    assert response.status_code == 422 and "1234567" not in response.text


@pytest.mark.integration
def test_concurrent_verification_issues_only_one_session(auth):
    client, engine, config, sent, app = auth
    challenge = request_code(client)
    binding = client.cookies[config.challenge_cookie]

    def attempt(_):
        with TestClient(app, base_url=ORIGIN, headers=HEADERS) as other:
            other.cookies.set(config.challenge_cookie, binding)
            return verify(other, challenge, sent[-1][1]).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [200, 400]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1


@pytest.mark.integration
def test_migration_admin_seed_and_database_role_boundaries(database):
    engine, _ = database
    command.downgrade(Config("alembic.ini"), "0001")
    command.upgrade(Config("alembic.ini"), "head")
    with Session(engine) as db:
        admin = db.scalars(select(AppUser).where(AppUser.email == "admin@metiquo.fr")).one()
        assert admin.role == "admin" and admin.verified_at is None
        for email, role in (("metiquo@admin.fr", "admin"), ("metiquo@user.fr", "user")):
            account = db.scalars(select(AppUser).where(AppUser.email == email)).one()
            assert account.role == role and account.verified_at is None
    # A second downgrade/upgrade preserves the provisioned identity.
    command.downgrade(Config("alembic.ini"), "0001")
    command.upgrade(Config("alembic.ini"), "head")
    command.check(Config("alembic.ini"))
    with engine.connect() as conn:
        if not conn.scalar(
            text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname='metiquo_api')")
        ):
            pytest.skip("Docker SQL roles not installed")
    for role, statement in (
        ("metiquo_api", "DELETE FROM app_users WHERE false"),
        ("metiquo_api", "UPDATE teams SET data = '{}' WHERE false"),
        ("metiquo_worker", "SELECT * FROM auth_sessions"),
        ("metiquo_worker", "SELECT * FROM app_users"),
    ):
        with pytest.raises(ProgrammingError), engine.begin() as conn:
            conn.execute(text(f"SET LOCAL ROLE {role}"))
            conn.execute(text(statement))


@pytest.mark.integration
def test_requested_roles_preserve_accounts_and_revoke_only_changed_sessions(database):
    engine, _ = database
    command.downgrade(Config("alembic.ini"), "0004")
    now = datetime.now(UTC)
    emails = ("metiquo@admin.fr", "metiquo@user.fr", "unchanged@example.com")
    ids = [uuid4() for _ in emails]
    with Session(engine) as db:
        for index, email in enumerate(emails):
            db.add(
                AppUser(
                    id=ids[index],
                    auth_issuer="metiquo:email",
                    auth_subject=email,
                    email=email,
                    role="admin" if index == 1 else "user",
                    verified_at=now,
                    disabled=index == 1,
                )
            )
        db.flush()
        for index, user_id in enumerate(ids):
            db.add(
                AuthSession(
                    token_hash=str(index) * 64,
                    user_id=user_id,
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(days=1),
                )
            )
        db.commit()
    command.upgrade(Config("alembic.ini"), "head")
    with Session(engine) as db:
        for index, user_id in enumerate(ids):
            account = db.get(AppUser, user_id)
            assert account is not None and account.email == emails[index]
            assert account.role == ("admin" if index == 0 else "user")
            assert account.verified_at == now and account.disabled == (index == 1)
        assert list(db.scalars(select(AuthSession.user_id))) == [ids[2]]


@pytest.mark.integration
def test_https_cookie_flags_and_missing_csrf_header(auth):
    _, _, _, sent, app = auth
    # Build a separate app configured for the public HTTPS origin.
    from metiquo_core.config import Settings

    secure_config = AuthSettings(auth_secret=KEY, auth_origins=["https://metiquo.example"])
    with TestClient(
        create_app(Settings(), secure_config),
        base_url="https://metiquo.example",
        headers={"Origin": "https://metiquo.example", "X-Metiquo-Auth": "1"},
    ) as client:
        challenge = request_code(client)
        assert "__Host-metiquo_challenge" in client.cookies
        response = verify(client, challenge, sent[-1][1])
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "Domain=" not in cookie
        assert "__Host-metiquo_session" in client.cookies
        client.headers.pop("X-Metiquo-Auth")
        assert client.post("/api/v1/auth/logout").status_code == 403
        assert client.get("/api/v1/auth/session").json()["user"] is not None


@pytest.mark.integration
def test_hourly_email_limit_and_smtp_failure_preserves_previous_code(auth, monkeypatch):
    client, engine, config, sent, _ = auth
    challenge = request_code(client)
    code = sent[-1][1]
    minute_key = digest(config, "email-minute:person@example.com")
    # Expire only the short cooldown; the hourly counter remains active.
    with Session(engine) as db, db.begin():
        db.execute(delete(AuthRateLimit).where(AuthRateLimit.key == minute_key))

    def fail(*_):
        raise OSError("SMTP is unavailable")

    monkeypatch.setattr("metiquo_api.auth.send_login_code", fail)
    assert (
        client.post("/api/v1/auth/request-code", json={"email": "person@example.com"}).status_code
        == 503
    )
    assert verify(client, challenge, code).status_code == 200
    with Session(engine) as db, db.begin():
        db.execute(delete(AuthRateLimit).where(AuthRateLimit.key == minute_key))
        db.execute(
            update(AuthRateLimit)
            .where(AuthRateLimit.key == digest(config, "email-hour:person@example.com"))
            .values(count=5)
        )
    response = client.post("/api/v1/auth/request-code", json={"email": "person@example.com"})
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 60
