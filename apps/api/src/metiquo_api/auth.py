import hashlib
import hmac
import logging
import math
import secrets
import smtplib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from metiquo_core.models import AppUser, AuthChallenge, AuthRateLimit, AuthSession
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from metiquo_api.auth_config import AuthSettings
from metiquo_api.mail import send_login_code

logger = logging.getLogger(__name__)
CODE_TTL = 600
RESEND_DELAY = 60
SESSION_TTL = timedelta(days=30)
IDLE_TTL = timedelta(days=7)
MAX_ATTEMPTS = 5


class EmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def normalized_email(cls, value: str) -> str:
        try:
            # Application identities are case-insensitive; no provider-specific alias rewriting.
            return validate_email(
                value.strip(), check_deliverability=False, allow_smtputf8=False
            ).normalized.lower()
        except EmailNotValidError as error:
            raise ValueError("Adresse email invalide") from error


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    challenge_id: UUID = Field(alias="challengeId")
    code: str = Field(pattern=r"^[0-9]{6}$")


class ChallengeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    challenge_id: UUID = Field(alias="challengeId")
    expires_at: datetime = Field(alias="expiresAt")
    resend_at: datetime = Field(alias="resendAt")


class UserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: UUID
    email: str
    role: Literal["user", "admin"]
    created_at: datetime = Field(alias="createdAt")


class SessionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user: UserResponse | None
    expires_at: datetime | None = Field(default=None, alias="expiresAt")


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def digest(settings: AuthSettings, value: str) -> str:
    return hmac.new(
        settings.auth_secret.get_secret_value().encode(), value.encode(), "sha256"
    ).hexdigest()


def authenticated_user(request: Request, session: Session, settings: AuthSettings) -> AppUser:
    now = datetime.now(UTC)
    token = request.cookies.get(settings.session_cookie, "")
    auth_session = session.get(AuthSession, fingerprint(token))
    if (
        auth_session is None
        or auth_session.expires_at <= now
        or auth_session.last_seen_at + IDLE_TTL <= now
    ):
        raise HTTPException(401, "Connectez-vous pour accéder à cet espace.")
    user = session.get(AppUser, auth_session.user_id)
    if user is None or user.verified_at is None:
        raise HTTPException(401, "Cette session n’est plus valide.")
    if user.disabled:
        raise HTTPException(423, "Ce compte est suspendu. Contactez un administrateur.")
    if now - auth_session.last_seen_at >= timedelta(minutes=5):
        auth_session.last_seen_at = now
        session.flush()
    return user


def enforce_limits(
    session: Session, settings: AuthSettings, limits: list[tuple[str, int, int]], now: datetime
) -> None:
    retry_after = 0
    # Sorted acquisition makes concurrent callers lock rows in a consistent order.
    for scope, maximum, seconds in sorted(limits):
        key = digest(settings, scope)
        session.execute(
            insert(AuthRateLimit)
            .values(key=key, count=0, expires_at=now + timedelta(seconds=seconds))
            .on_conflict_do_nothing(index_elements=[AuthRateLimit.key])
        )
        bucket = session.scalars(
            select(AuthRateLimit).where(AuthRateLimit.key == key).with_for_update()
        ).one()
        if bucket.expires_at <= now:
            bucket.count = 0
            bucket.expires_at = now + timedelta(seconds=seconds)
        if bucket.count >= maximum:
            retry_after = max(retry_after, math.ceil((bucket.expires_at - now).total_seconds()))
        else:
            bucket.count += 1
    # Persist failed requests too, independently of SMTP or verification rollback.
    session.commit()
    if retry_after:
        raise HTTPException(
            429,
            "Trop de demandes. Patientez avant de réessayer.",
            headers={"Retry-After": str(retry_after)},
        )


def create_auth_router(engine: Engine, settings: AuthSettings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

    def get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    def same_origin(request: Request) -> None:
        if (
            request.headers.get("origin") not in settings.auth_origins
            or request.headers.get("x-metiquo-auth") != "1"
        ):
            raise HTTPException(403, "Origine de la demande refusée.")

    def client_ip(request: Request) -> str:
        # Only enabled behind the private Compose API network. Nginx overwrites this header.
        if settings.auth_trust_proxy:
            return request.headers.get("x-real-ip", "unknown")
        return request.client.host if request.client else "unknown"

    def set_cookie(response: Response, name: str, token: str, max_age: int) -> None:
        response.set_cookie(
            name,
            token,
            max_age=max_age,
            path="/",
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite="lax",
        )

    def clear_cookie(response: Response, name: str) -> None:
        response.delete_cookie(
            name, path="/", httponly=True, secure=settings.auth_cookie_secure, samesite="lax"
        )

    def session_response(user: AppUser, auth_session: AuthSession) -> SessionResponse:
        return SessionResponse(
            user=UserResponse.model_validate(
                {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role,
                    "createdAt": user.created_at,
                }
            ),
            expires_at=min(auth_session.expires_at, auth_session.last_seen_at + IDLE_TTL),
        )

    @router.post(
        "/request-code", response_model=ChallengeResponse, dependencies=[Depends(same_origin)]
    )
    def request_code(
        body: EmailRequest,
        request: Request,
        response: Response,
        session: Annotated[Session, Depends(get_session)],
    ) -> ChallengeResponse:
        now = datetime.now(UTC)
        # Only expired authentication records are pruned; source data is never touched.
        session.execute(delete(AuthChallenge).where(AuthChallenge.expires_at <= now))
        session.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
        session.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at <= now))
        session.commit()
        enforce_limits(
            session,
            settings,
            [
                (f"email-minute:{body.email}", 1, RESEND_DELAY),
                (f"email-hour:{body.email}", 5, 3600),
                (f"send-ip:{client_ip(request)}", 30, 3600),
                ("send-global", 100, 60),
            ],
            now,
        )
        # Serialize all challenge replacement for an address, including first registration.
        lock_key = int(digest(settings, f"email-lock:{body.email}")[:15], 16)
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        challenge_id, binding = uuid4(), secrets.token_urlsafe(32)
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires = now + timedelta(seconds=CODE_TTL)
        session.execute(delete(AuthChallenge).where(AuthChallenge.email == body.email))
        session.add(
            AuthChallenge(
                id=challenge_id,
                email=body.email,
                code_hash=digest(settings, f"code:{challenge_id}:{code}"),
                binding_hash=fingerprint(binding),
                expires_at=expires,
                attempts=0,
            )
        )
        session.flush()
        try:
            send_login_code(settings, body.email, code)
        except (OSError, smtplib.SMTPException):
            session.rollback()
            logger.warning("Authentication email delivery failed")
            raise HTTPException(
                503, "L’envoi de l’email est indisponible. Réessayez dans une minute."
            ) from None
        session.commit()
        set_cookie(response, settings.challenge_cookie, binding, CODE_TTL)
        return ChallengeResponse(
            challenge_id=challenge_id,
            expires_at=expires,
            resend_at=now + timedelta(seconds=RESEND_DELAY),
        )

    @router.post(
        "/verify-code", response_model=SessionResponse, dependencies=[Depends(same_origin)]
    )
    def verify_code(
        body: VerifyRequest,
        request: Request,
        response: Response,
        session: Annotated[Session, Depends(get_session)],
    ) -> SessionResponse:
        now = datetime.now(UTC)
        enforce_limits(session, settings, [(f"verify-ip:{client_ip(request)}", 60, 600)], now)
        challenge = session.scalars(
            select(AuthChallenge).where(AuthChallenge.id == body.challenge_id).with_for_update()
        ).one_or_none()
        binding = request.cookies.get(settings.challenge_cookie, "")
        if (
            challenge is None
            or challenge.expires_at <= now
            or challenge.attempts >= MAX_ATTEMPTS
            or not hmac.compare_digest(challenge.binding_hash, fingerprint(binding))
        ):
            raise HTTPException(
                400, "Code invalide ou expiré. Demandez un nouveau code si nécessaire."
            )
        challenge.attempts += 1
        if not hmac.compare_digest(
            challenge.code_hash, digest(settings, f"code:{challenge.id}:{body.code}")
        ):
            session.commit()
            raise HTTPException(
                400, "Code invalide ou expiré. Demandez un nouveau code si nécessaire."
            )
        user = session.scalars(
            select(AppUser).where(AppUser.email == challenge.email).with_for_update()
        ).one_or_none()
        if user is None:
            user = AppUser(
                auth_issuer="metiquo:email",
                auth_subject=challenge.email,
                email=challenge.email,
                verified_at=now,
            )
            session.add(user)
            session.flush()
        elif user.disabled:
            session.delete(challenge)
            session.commit()
            raise HTTPException(423, "Ce compte est suspendu. Contactez un administrateur.")
        elif user.verified_at is None:
            user.verified_at = now
        token = secrets.token_urlsafe(32)
        session.execute(
            delete(AuthSession).where(
                AuthSession.token_hash
                == fingerprint(request.cookies.get(settings.session_cookie, ""))
            )
        )
        auth_session = AuthSession(
            token_hash=fingerprint(token),
            user_id=user.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_TTL,
        )
        session.add(auth_session)
        session.delete(challenge)
        result = session_response(user, auth_session)
        session.commit()
        set_cookie(response, settings.session_cookie, token, int(SESSION_TTL.total_seconds()))
        clear_cookie(response, settings.challenge_cookie)
        return result

    @router.get("/session", response_model=SessionResponse)
    def current_session(
        request: Request, response: Response, session: Annotated[Session, Depends(get_session)]
    ) -> SessionResponse:
        token = request.cookies.get(settings.session_cookie)
        if not token:
            return SessionResponse(user=None)
        now = datetime.now(UTC)
        auth_session = session.get(AuthSession, fingerprint(token), with_for_update=True)
        if (
            auth_session is None
            or auth_session.expires_at <= now
            or auth_session.last_seen_at + IDLE_TTL <= now
        ):
            if auth_session:
                session.delete(auth_session)
                session.commit()
            clear_cookie(response, settings.session_cookie)
            return SessionResponse(user=None)
        user = session.get(AppUser, auth_session.user_id)
        if user is None or user.verified_at is None:
            clear_cookie(response, settings.session_cookie)
            return SessionResponse(user=None)
        if user.disabled:
            raise HTTPException(423, "Ce compte est suspendu. Contactez un administrateur.")
        if now - auth_session.last_seen_at >= timedelta(minutes=5):
            auth_session.last_seen_at = now
            session.commit()
        return session_response(user, auth_session)

    @router.post("/logout", status_code=204, dependencies=[Depends(same_origin)])
    def logout(
        request: Request, response: Response, session: Annotated[Session, Depends(get_session)]
    ) -> None:
        session.execute(
            delete(AuthSession).where(
                AuthSession.token_hash
                == fingerprint(request.cookies.get(settings.session_cookie, ""))
            )
        )
        session.commit()
        clear_cookie(response, settings.session_cookie)
        clear_cookie(response, settings.challenge_cookie)

    return router
