"""Fabrique de l'application FastAPI."""

import logging
from importlib.metadata import version
from time import perf_counter
from typing import Final
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from metiquo.api.contract_schema import install_domain_contract_schemas
from metiquo.api.dto import (
    DependencyStatus,
    HealthResponse,
    ProblemDetails,
    ReadyResponse,
    SystemStatusResponse,
)
from metiquo.api.messages import (
    HTTP_ERROR_TITLE,
    INVALID_REQUEST_DETAIL,
    INVALID_REQUEST_TITLE,
    NOT_FOUND_TITLE,
)
from metiquo.api.mutation_routes import build_mutation_router
from metiquo.api.paper_routes import build_paper_metrics_router, build_real_paper_router
from metiquo.api.read_routes import build_read_router
from metiquo.api.readiness import DatabaseReadinessProbe, ReadinessCheck, ReadinessProbe
from metiquo.api.real_admin_routes import build_real_admin_router
from metiquo.api.real_historical_routes import build_real_historical_router
from metiquo.api.real_model_routes import build_real_model_router
from metiquo.canonical.capabilities import CapabilityRegistry
from metiquo.config import AuthMode, ConfigurationError, Settings, load_settings
from metiquo.contracts.enums import DataMode, FreshnessStatus
from metiquo.foundation.audit import audit_context
from metiquo.foundation.errors import BusinessError, ErrorCode
from metiquo.foundation.identifiers import TraceId
from metiquo.foundation.metrics import ApiMetrics
from metiquo.foundation.observability import bind_log_context, configure_json_logging
from metiquo.foundation.time import Clock, SystemClock
from metiquo.mock import build_mock_scenario_catalog
from metiquo.paper.reporting import PostgresFinancialReportingService
from metiquo.repositories.postgres_admin import PostgresAdminRepository
from metiquo.repositories.postgres_canonical import PostgresCanonicalRepository
from metiquo.repositories.postgres_mapping import PostgresMappingRepository
from metiquo.repositories.postgres_models import PostgresModelRepository
from metiquo.repositories.postgres_opportunities import PostgresOpportunityRepository
from metiquo.services import MockMutationService, ReadService, build_mock_read_service
from metiquo.services.operational_audit import record_runtime_configuration
from metiquo.services.operational_status import OperationalStatusService
from metiquo.services.real_admin import RealAdminMutationService
from metiquo.services.real_mapping import RealMappingMutationService

ERROR_STATUSES: Final[dict[ErrorCode, int]] = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.INVALID_STATE: 409,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
}


def _dependency_status(check: ReadinessCheck) -> DependencyStatus:
    return DependencyStatus(
        status="available" if check.available else "unavailable",
        reason_code=check.reason_code,
    )


def _problem_response(problem: ProblemDetails) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json", by_alias=True, exclude_none=True),
        media_type="application/problem+json",
    )


def _router(settings: Settings, readiness_probe: ReadinessProbe, clock: Clock) -> APIRouter:
    router = APIRouter(
        responses={
            404: {
                "model": ProblemDetails,
                "description": NOT_FOUND_TITLE,
                "content": {"application/problem+json": {}},
            },
            422: {
                "model": ProblemDetails,
                "description": INVALID_REQUEST_TITLE,
                "content": {"application/problem+json": {}},
            },
        }
    )

    @router.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse()

    @router.get(
        "/ready",
        response_model=ReadyResponse,
        responses={503: {"model": ReadyResponse}},
        tags=["system"],
    )
    def ready() -> ReadyResponse | JSONResponse:
        database = _dependency_status(readiness_probe.check())
        response = ReadyResponse(
            status="ready" if database.status == "available" else "not_ready",
            dependencies={"database": database},
        )
        if response.status == "not_ready":
            return JSONResponse(status_code=503, content=response.model_dump(by_alias=True))
        return response

    @router.get(
        "/api/v1/system/status",
        response_model=SystemStatusResponse,
        tags=["system"],
    )
    def system_status(request: Request) -> SystemStatusResponse:
        database = _dependency_status(readiness_probe.check())
        operations = None
        healthy = database.status == "available"
        if healthy and settings.app_data_mode is DataMode.REAL:
            operations = OperationalStatusService(
                request.app.state.real_admin_engine, settings, clock
            ).snapshot(request.app.state.api_metrics.snapshot())
            healthy = (
                operations.source.status is FreshnessStatus.FRESH
                and operations.model.status == "fresh"
                and operations.backups.status == "fresh"
            )
        return SystemStatusResponse(
            status="ready" if healthy else "degraded",
            api_version=version("metiquo"),
            data_mode=settings.app_data_mode,
            generated_at=clock.now().value,
            dependencies={"database": database},
            operations=operations,
        )

    return router


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probe: ReadinessProbe | None = None,
    clock: Clock | None = None,
    read_service: ReadService | None = None,
    mutation_service: MockMutationService | None = None,
    real_admin_repository: PostgresAdminRepository | None = None,
    real_mutation_service: RealAdminMutationService | None = None,
) -> FastAPI:
    """Construire l'API après validation de la configuration."""

    resolved_settings = settings or load_settings()
    resolved_settings.check_auth_boundary()
    if resolved_settings.auth_mode is AuthMode.OWNER:
        raise ConfigurationError(
            "AUTH_OWNER_UNAVAILABLE : les sessions Owner doivent être installées avant exposition"
        )
    if settings is None:
        configure_json_logging(
            secrets=tuple(
                value.get_secret_value()
                for value in (
                    resolved_settings.database_url,
                    resolved_settings.oe_google_drive_bearer,
                )
                if value is not None
            )
        )
    resolved_probe = readiness_probe or DatabaseReadinessProbe(
        resolved_settings.database_url.get_secret_value()
    )
    resolved_clock = clock or SystemClock()
    app = FastAPI(title="Metiquo API", version=version("metiquo"))
    app.state.api_metrics = ApiMetrics()
    app.include_router(_router(resolved_settings, resolved_probe, resolved_clock))
    if resolved_settings.app_data_mode is DataMode.MOCK:
        app.include_router(build_paper_metrics_router(None, resolved_clock))
        catalog = build_mock_scenario_catalog(resolved_settings.mock_seed, resolved_clock)
        resolved_service = read_service or build_mock_read_service(catalog)
        app.include_router(build_read_router(resolved_service, resolved_clock))
        resolved_mutation_service = mutation_service or MockMutationService(catalog, resolved_clock)
        app.include_router(build_mutation_router(resolved_mutation_service, resolved_clock))
    else:
        real_engine = (
            real_admin_repository.engine
            if real_admin_repository is not None
            else create_engine(
                resolved_settings.database_url.get_secret_value(),
                connect_args={"options": "-c timezone=UTC"},
                pool_pre_ping=True,
            )
        )
        resolved_repository = real_admin_repository or PostgresAdminRepository(
            real_engine,
            resolved_clock,
            resolved_settings.odds_max_age_seconds,
            resolved_settings.odds_provider_max_age_seconds,
            oe_freshness_sla_seconds=resolved_settings.oe_freshness_sla_seconds,
            oe_current_year=resolved_settings.oe_current_year,
        )
        resolved_model_repository = PostgresModelRepository(real_engine)
        resolved_mapping_repository = PostgresMappingRepository(real_engine, resolved_clock)
        resolved_mapping_mutations = RealMappingMutationService(
            real_engine,
            resolved_mapping_repository,
            resolved_clock,
        )
        resolved_real_mutations = real_mutation_service or RealAdminMutationService(
            real_engine,
            resolved_settings,
            resolved_repository,
            resolved_model_repository,
            clock=resolved_clock,
        )
        app.state.real_admin_engine = real_engine
        app.include_router(
            build_paper_metrics_router(
                PostgresFinancialReportingService(
                    real_engine,
                    clock=resolved_clock,
                    closing_max_age_seconds=resolved_settings.paper_closing_max_age_seconds,
                ),
                resolved_clock,
            )
        )
        app.include_router(build_real_paper_router(real_engine, resolved_settings, resolved_clock))
        app.include_router(
            build_real_historical_router(
                PostgresCanonicalRepository(real_engine, resolved_clock),
                PostgresOpportunityRepository(real_engine, resolved_clock),
                resolved_repository,
                resolved_clock,
            )
        )
        app.include_router(build_real_model_router(resolved_model_repository, resolved_clock))
        app.include_router(
            build_real_admin_router(
                resolved_repository,
                resolved_real_mutations,
                resolved_clock,
                CapabilityRegistry(engine=real_engine, clock=resolved_clock),
                resolved_model_repository,
                resolved_mapping_repository,
                resolved_mapping_mutations,
            )
        )

    @app.middleware("http")
    async def bind_request_audit(request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace = uuid4()
        with (
            audit_context(actor="api-local", trace_id=trace),
            bind_log_context(trace_id=TraceId(trace)),
        ):
            started, status_code = perf_counter(), 500
            try:
                if resolved_settings.app_data_mode is DataMode.REAL and request.method in {
                    "POST",
                    "PUT",
                    "PATCH",
                    "DELETE",
                }:
                    await run_in_threadpool(
                        record_runtime_configuration,
                        app.state.real_admin_engine,
                        resolved_settings,
                        service="api",
                        clock=resolved_clock,
                    )
                response = await call_next(request)
                status_code = response.status_code
                response.headers["X-Trace-Id"] = str(trace)
                return response
            finally:
                elapsed = perf_counter() - started
                app.state.api_metrics.observe(status_code, elapsed)
                logging.getLogger("metiquo.api").info(
                    "http.completed",
                    extra={
                        "duration_ms": round(elapsed * 1000, 3),
                        "status_code": status_code,
                        "method": request.method,
                        "route": getattr(request.scope.get("route"), "path", "<unmatched>"),
                    },
                )

    @app.exception_handler(BusinessError)
    async def business_error_handler(request: Request, error: BusinessError) -> JSONResponse:
        status_code = ERROR_STATUSES[error.code]
        return _problem_response(
            ProblemDetails(
                title=error.message,
                status=status_code,
                detail=error.message,
                instance=request.url.path,
                code=error.code.value,
                context=dict(error.context),
            )
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        del error
        return _problem_response(
            ProblemDetails(
                title=INVALID_REQUEST_TITLE,
                status=422,
                detail=INVALID_REQUEST_DETAIL,
                instance=request.url.path,
                code=ErrorCode.INVALID_INPUT.value,
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, error: StarletteHTTPException) -> JSONResponse:
        title = NOT_FOUND_TITLE if error.status_code == 404 else HTTP_ERROR_TITLE
        return _problem_response(
            ProblemDetails(
                title=title,
                status=error.status_code,
                detail=title,
                instance=request.url.path,
                code=f"HTTP_{error.status_code}",
            )
        )

    install_domain_contract_schemas(app)
    return app
