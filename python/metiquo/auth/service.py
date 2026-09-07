"""Créer, vérifier et faire tourner des sessions opaques sans persister leur valeur."""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from metiquo.config import Settings
from metiquo.db.auth_models import OwnerAccountRecord, OwnerSessionRecord
from metiquo.db.ops_models import AuditEventRecord
from metiquo.foundation.audit import current_audit_context
from metiquo.foundation.locks import resource_lock_key
from metiquo.foundation.time import Clock, SystemClock

_HASHER = PasswordHasher()


class AuthError(RuntimeError):
    def __init__(self, code: str, status: int = 401) -> None:
        super().__init__(code)
        self.code, self.status = code, status


@dataclass(frozen=True, slots=True)
class OwnerPrincipal:
    owner_id: UUID
    username: str
    session_id: UUID


@dataclass(frozen=True, slots=True)
class SessionGrant:
    principal: OwnerPrincipal
    token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthResolution:
    principal: OwnerPrincipal
    replacement: SessionGrant | None = None


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _HASHER.hash(secrets.token_urlsafe(32))


def _password_hash(password: str) -> str:
    if len(password) < 15 or len(password.encode()) > 1024:
        raise AuthError("AUTH_PASSWORD_POLICY", 400)
    return _HASHER.hash(password)


def _token_hash(token: str) -> str | None:
    if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        return None
    return hashlib.sha256(token.encode()).hexdigest()


class OwnerAuthService:
    def __init__(self, engine: Engine, settings: Settings, *, clock: Clock | None = None) -> None:
        self.engine, self.settings, self.clock = engine, settings, clock or SystemClock()
        _dummy_hash()

    @staticmethod
    def _owner(session: Session) -> OwnerAccountRecord | None:
        session.execute(text("SET LOCAL lock_timeout = '5s'"))
        session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": resource_lock_key("auth:owner")}
        )
        return session.scalar(select(OwnerAccountRecord).with_for_update())

    def _event(
        self, session: Session, action: str, target: str, *, actor: str | None = None
    ) -> None:
        context = current_audit_context()
        session.add(
            AuditEventRecord(
                id=uuid4(),
                actor=actor or (context.actor if context else "owner-service"),
                action=action,
                target_type="ops.owner_accounts",
                target_id=target,
                before_refs={},
                after_refs={},
                trace_id=context.trace_id if context else uuid4(),
                occurred_at=self.clock.now().value,
            )
        )

    @staticmethod
    def _bind_owner(session: Session, owner: OwnerAccountRecord) -> None:
        session.execute(
            text("SELECT set_config('metiquo.audit_actor', :actor, true)"),
            {"actor": f"owner:{owner.id}"},
        )

    def bootstrap(self, username: str, password: str) -> UUID:
        username = username.strip().casefold()
        if re.fullmatch(r"[a-z0-9_.-]{3,64}", username) is None:
            raise AuthError("AUTH_USERNAME_POLICY", 400)
        password_hash = _password_hash(password)
        now = self.clock.now().value
        with Session(self.engine) as session, session.begin():
            if self._owner(session) is not None:
                raise AuthError("AUTH_OWNER_EXISTS", 409)
            owner = OwnerAccountRecord(
                id=uuid4(),
                singleton=True,
                username=username,
                password_hash=password_hash,
                revision=1,
                created_at=now,
                updated_at=now,
            )
            session.add(owner)
            self._event(session, "auth.owner_bootstrapped", str(owner.id))
            return owner.id

    def _new_session(
        self, session: Session, owner: OwnerAccountRecord, *, expires_at: datetime | None = None
    ) -> SessionGrant:
        now = self.clock.now().value
        token = secrets.token_urlsafe(32)
        row = OwnerSessionRecord(
            id=uuid4(),
            owner_id=owner.id,
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            status="active",
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at
            or now + timedelta(seconds=self.settings.auth_session_absolute_seconds),
            rotate_at=now + timedelta(seconds=self.settings.auth_session_rotation_seconds),
        )
        session.add(row)
        session.flush()
        return SessionGrant(OwnerPrincipal(owner.id, owner.username, row.id), token, row.expires_at)

    def _revoke(self, row: OwnerSessionRecord, reason: str) -> None:
        if row.status == "active":
            row.status, row.revoked_at, row.reason_code = "revoked", self.clock.now().value, reason

    @staticmethod
    def _find(session: Session, token: str) -> OwnerSessionRecord | None:
        digest = _token_hash(token)
        return (
            session.scalar(
                select(OwnerSessionRecord).where(OwnerSessionRecord.token_hash == digest)
            )
            if digest
            else None
        )

    def login(
        self, username: str, password: str, *, previous_token: str | None = None
    ) -> SessionGrant:
        grant = None
        with Session(self.engine) as session, session.begin():
            owner = self._owner(session)
            known = owner is not None and owner.username == username.strip().casefold()
            digest = owner.password_hash if owner is not None and known else _dummy_hash()
            verified = False
            try:
                if len(password.encode()) <= 1024:
                    verified = _HASHER.verify(digest, password)
            except (VerificationError, InvalidHashError):
                pass
            if not known or not verified or owner is None:
                self._event(
                    session,
                    "auth.login_failed",
                    str(owner.id) if owner else "unconfigured",
                    actor="anonymous",
                )
            else:
                self._bind_owner(session, owner)
                if _HASHER.check_needs_rehash(owner.password_hash):
                    owner.password_hash, owner.updated_at = (
                        _HASHER.hash(password),
                        self.clock.now().value,
                    )
                    owner.revision += 1
                if previous_token:
                    previous = self._find(session, previous_token)
                    if previous is not None and previous.owner_id == owner.id:
                        self._revoke(previous, "login_replaced")
                grant = self._new_session(session, owner)
                self._event(
                    session, "auth.login_succeeded", str(owner.id), actor=f"owner:{owner.id}"
                )
        if grant is None:
            raise AuthError("AUTH_INVALID_CREDENTIALS")
        return grant

    def _effective_session(
        self, session: Session, token: str, owner: OwnerAccountRecord
    ) -> OwnerSessionRecord | None:
        row = self._find(session, token)
        now = self.clock.now().value
        if row is None or row.owner_id != owner.id:
            return None
        if row.status == "revoked":
            if (
                row.reason_code != "rotated"
                or row.grace_until is None
                or now >= row.grace_until
                or row.replacement_id is None
            ):
                return None
            row = session.get(OwnerSessionRecord, row.replacement_id)
            if row is None or row.owner_id != owner.id or row.status != "active":
                return None
        if now < row.created_at or now < row.last_seen_at:
            return None
        if (
            now >= row.expires_at
            or (now - row.last_seen_at).total_seconds() >= self.settings.auth_session_idle_seconds
        ):
            self._revoke(row, "expired")
            return None
        return row

    def authenticate(self, token: str) -> AuthResolution | None:
        if _token_hash(token) is None:
            return None
        with Session(self.engine) as session, session.begin():
            owner = self._owner(session)
            if owner is None:
                return None
            self._bind_owner(session, owner)
            row = self._effective_session(session, token, owner)
            if row is None:
                return None
            now = self.clock.now().value
            if now >= row.rotate_at:
                grant = self._new_session(session, owner, expires_at=row.expires_at)
                self._revoke(row, "rotated")
                row.replacement_id = grant.principal.session_id
                row.grace_until = now + timedelta(seconds=self.settings.auth_session_grace_seconds)
                self._event(
                    session, "auth.session_rotated", str(owner.id), actor=f"owner:{owner.id}"
                )
                return AuthResolution(grant.principal, grant)
            row.last_seen_at = now
            return AuthResolution(OwnerPrincipal(owner.id, owner.username, row.id))

    def logout(self, token: str) -> None:
        if _token_hash(token) is None:
            return
        with Session(self.engine) as session, session.begin():
            owner = self._owner(session)
            if owner is None:
                return
            self._bind_owner(session, owner)
            row = self._effective_session(session, token, owner)
            if row is not None:
                self._revoke(row, "logout")
                self._event(session, "auth.logout", str(owner.id), actor=f"owner:{owner.id}")

    def reset_password(self, username: str, password: str) -> UUID:
        password_hash = _password_hash(password)
        with Session(self.engine) as session, session.begin():
            owner = self._owner(session)
            if owner is None or owner.username != username.strip().casefold():
                raise AuthError("AUTH_OWNER_NOT_FOUND", 404)
            owner.password_hash, owner.updated_at = password_hash, self.clock.now().value
            owner.revision += 1
            for row in session.scalars(
                select(OwnerSessionRecord).where(
                    OwnerSessionRecord.status == "active", OwnerSessionRecord.owner_id == owner.id
                )
            ):
                self._revoke(row, "credentials_reset")
            self._event(session, "auth.password_reset", str(owner.id))
            return owner.id
