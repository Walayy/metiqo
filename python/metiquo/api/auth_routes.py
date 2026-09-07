"""Sessions Owner et émission de cookies privés avec attributs explicites."""

from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response

from metiquo.auth.service import AuthError, OwnerAuthService, OwnerPrincipal, SessionGrant
from metiquo.config import Settings
from metiquo.contracts.auth import AuthStatus, OwnerIdentity, OwnerLoginRequest
from metiquo.foundation.time import Clock


def secure_cookie(settings: Settings) -> bool:
    return urlsplit(settings.app_public_origin).scheme == "https"


def owner_cookie_name(settings: Settings) -> str:
    return "__Host-metiquo_owner" if secure_cookie(settings) else "metiquo_owner"


def set_owner_cookie(
    response: Response, grant: SessionGrant, settings: Settings, clock: Clock
) -> None:
    response.set_cookie(
        owner_cookie_name(settings),
        grant.token,
        max_age=max(0, int((grant.expires_at - clock.now().value).total_seconds())),
        expires=grant.expires_at,
        path="/",
        secure=secure_cookie(settings),
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def auth_status(settings: Settings, principal: OwnerPrincipal | None) -> AuthStatus:
    return AuthStatus(
        mode=settings.auth_mode.value,
        authenticated=principal is not None,
        owner=OwnerIdentity(id=principal.owner_id, username=principal.username)
        if principal
        else None,
    )


def build_auth_router(
    service: OwnerAuthService | None, settings: Settings, clock: Clock
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

    @router.get("/session", response_model=AuthStatus)
    def current_session(request: Request, response: Response) -> AuthStatus:
        response.headers["Cache-Control"] = "no-store"
        principal = getattr(request.state, "owner", None)
        return auth_status(settings, principal)

    @router.post("/login", response_model=AuthStatus)
    def login(payload: OwnerLoginRequest, request: Request, response: Response) -> AuthStatus:
        if service is None:
            raise AuthError("AUTH_DISABLED", 409)
        grant = service.login(
            payload.username,
            payload.password.get_secret_value(),
            previous_token=request.cookies.get(owner_cookie_name(settings)),
        )
        set_owner_cookie(response, grant, settings, clock)
        return auth_status(settings, grant.principal)

    @router.post("/logout", status_code=204)
    def logout(request: Request) -> Response:
        if service is not None:
            service.logout(request.cookies.get(owner_cookie_name(settings), ""))
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(
            owner_cookie_name(settings),
            path="/",
            secure=secure_cookie(settings),
            httponly=True,
            samesite="lax",
        )
        return response

    return router
