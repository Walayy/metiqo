"""Protection ASGI avant parsing, authentification et mutations métier."""

import logging
from time import perf_counter
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from metiquo.auth.rate_limit import HttpRateLimiter
from metiquo.config import AuthMode, Settings
from metiquo.foundation.metrics import ApiMetrics

MAX_BODY_BYTES = 65536
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class HttpProtection:
    def __init__(
        self, app: ASGIApp, *, settings: Settings, limiter: HttpRateLimiter, metrics: ApiMetrics
    ) -> None:
        self.app, self.settings, self.limiter, self.metrics = app, settings, limiter, metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        trace = str(uuid4())
        headers = Headers(scope=scope)
        started = False
        request_started = perf_counter()

        async def secured_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                if not scope.get("state", {}).get("audit_entered", False):
                    self.metrics.observe(message["status"], perf_counter() - request_started)
                outgoing = MutableHeaders(scope=message)
                outgoing["X-Content-Type-Options"] = "nosniff"
                outgoing["X-Frame-Options"] = "DENY"
                outgoing["Referrer-Policy"] = "no-referrer"
                outgoing["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
                outgoing["Cache-Control"] = "no-store"
                outgoing["Content-Security-Policy"] = (
                    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
                )
                if "x-trace-id" not in outgoing:
                    outgoing["X-Trace-Id"] = trace
                if self.settings.app_public_origin.startswith("https://"):
                    outgoing["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        async def reject(status: int, code: str, *, retry_after: int = 0) -> None:
            response = JSONResponse(
                {
                    "type": "about:blank",
                    "title": "Requête refusée",
                    "status": status,
                    "detail": "La requête ne peut pas être traitée. Réessayez si nécessaire.",
                    "instance": scope["path"],
                    "code": code,
                },
                status_code=status,
                media_type="application/problem+json",
                headers={"Retry-After": str(retry_after)} if retry_after else None,
            )
            await response(scope, receive, secured_send)

        origin, fetch_site = headers.get("origin"), headers.get("sec-fetch-site")
        expected_origin = self.settings.app_public_origin.rstrip("/")
        if origin is not None and origin != expected_origin:
            await reject(403, "ORIGIN_REFUSED")
            return
        unsafe = scope["method"] in UNSAFE_METHODS
        if unsafe and (
            fetch_site in {"cross-site", "same-site"}
            or (
                (
                    self.settings.auth_mode is AuthMode.OWNER
                    or origin is not None
                    or fetch_site is not None
                )
                and (origin != expected_origin or headers.get("x-metiquo-csrf") != "1")
            )
        ):
            await reject(403, "CSRF_REFUSED")
            return
        try:
            if unsafe:
                length = headers.get("content-length")
                if length is not None and (
                    len(length) > 6 or not length.isdigit() or int(length) > MAX_BODY_BYTES
                ):
                    await reject(413, "INPUT_TOO_LARGE")
                    return
                body = bytearray()
                while True:
                    part = await receive()
                    if part["type"] == "http.disconnect":
                        return
                    chunk = part.get("body", b"")
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        await reject(413, "INPUT_TOO_LARGE")
                        return
                    body.extend(chunk)
                    if not part.get("more_body", False):
                        break
                sent = False

                async def replay_body() -> Message:
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {"type": "http.request", "body": bytes(body), "more_body": False}
                    return await receive()

                retry = await run_in_threadpool(
                    self.limiter.check,
                    "login" if scope["path"].rstrip("/") == "/api/v1/auth/login" else "mutation",
                )
                if retry:
                    await reject(429, "RATE_LIMITED", retry_after=retry)
                    return
                await self.app(scope, replay_body, secured_send)
            else:
                await self.app(scope, receive, secured_send)
        except SQLAlchemyError:
            if not started:
                await reject(503, "DEPENDENCY_UNAVAILABLE")
            else:
                raise
        except Exception:
            # Ne journaliser ni message d'exception ni corps : ils peuvent contenir des secrets.
            logging.getLogger("metiquo.api.security").error("http.unhandled_failure")
            if not started:
                await reject(500, "INTERNAL_ERROR")
            else:
                raise
