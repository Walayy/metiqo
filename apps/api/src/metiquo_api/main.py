import logging
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time, timedelta
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from metiquo_core.catalog import other_game_identities
from metiquo_core.config import Settings
from metiquo_core.contracts import Catalog, LeagueData, Opportunities, Opportunity, TeamData
from metiquo_core.db import create_db
from metiquo_core.matches import (
    completed_series_summary,
    merge_completed_map,
    unique_bans,
)
from metiquo_core.models import (
    CatalogMetadata,
    CatalogVersion,
    CollectorState,
    Dataset,
    DatasetVersion,
    EsportMatch,
    IngestionRun,
    League,
    Market,
    MatchSnapshot,
    MatchSourceLink,
    OddsObservation,
    OracleRow,
    ProbabilityEstimate,
    Team,
)
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from metiquo_api.admin import create_admin_router
from metiquo_api.auth import create_auth_router
from metiquo_api.auth_config import AuthSettings
from metiquo_api.catalog import create_catalog_router

logger = logging.getLogger(__name__)
MATCH_FORMATS = {"BO1", "BO3", "BO5"}
PARIS = ZoneInfo("Europe/Paris")
_LEAGUE_CONTRACT_FIELDS = frozenset(
    field.serialization_alias or field.alias or name
    for name, field in LeagueData.model_fields.items()
)
_TEAM_CONTRACT_FIELDS = frozenset(
    field.serialization_alias or field.alias or name
    for name, field in TeamData.model_fields.items()
)


def _catalog_record(
    data: Mapping[str, object], contract_fields: frozenset[str]
) -> dict[str, object]:
    """Project stored source metadata onto the stable public catalog contract."""
    return {key: value for key, value in data.items() if key in contract_fields}


def _snapshot_format(snapshot: MatchSnapshot, match: EsportMatch) -> str | None:
    """Return a safe format without rejecting valid partial live-map details."""
    value = snapshot.payload.get("format")
    format_name = value if isinstance(value, str) else match.format
    if format_name not in MATCH_FORMATS:
        return None
    maps = snapshot.payload.get("maps")
    if not isinstance(maps, list):
        return None
    if snapshot.source == "oracles-elixir":
        if snapshot.payload.get("completionBasis") != "sourced-format":
            return None
        summary = completed_series_summary(maps, match.home_id, match.away_id, match.format)
        if summary is None or summary[0] != format_name:
            return None
    return format_name


def _is_complete_oracle_snapshot(snapshot: MatchSnapshot, match: EsportMatch) -> bool:
    if snapshot.source != "oracles-elixir" or snapshot.status != "finished":
        return False
    format_name = _snapshot_format(snapshot, match)
    maps = snapshot.payload.get("maps")
    return format_name is not None and isinstance(maps, list) and bool(maps)


def _snapshot_score(snapshot: MatchSnapshot | None, match: EsportMatch) -> object:
    if snapshot is None:
        return None
    if snapshot.source == "oracles-elixir":
        summary = completed_series_summary(
            snapshot.payload.get("maps"), match.home_id, match.away_id, match.format
        )
        return {"home": summary[1], "away": summary[2]} if summary else None
    return snapshot.payload.get("currentScore")


def _match_maps(
    history: list[MatchSnapshot], match: EsportMatch, status: str, snapshot: MatchSnapshot | None
) -> list[dict[str, object]]:
    """Keep independently captured maps without mixing impossible live states."""
    if status in {"scheduled", "cancelled", "postponed"} or snapshot is None:
        return []
    by_number: dict[int, dict[str, object]] = {}
    format_name = _snapshot_format(snapshot, match)
    if format_name is None and snapshot.source != "loltv":
        return []
    for observation in history:
        maps = observation.payload.get("maps")
        if not isinstance(maps, list):
            continue
        for item in maps:
            if not isinstance(item, dict):
                continue
            number = item.get("number")
            if not isinstance(number, int) or not 1 <= number <= (
                int(format_name[2:]) if format_name else 5
            ):
                continue
            sides = item.get("sides")
            if not isinstance(sides, list) or len(sides) != 2:
                continue
            if {side.get("teamId") for side in sides if isinstance(side, dict)} != {
                match.home_id,
                match.away_id,
            }:
                continue
            if item.get("status") == "live":
                current_score = _snapshot_score(snapshot, match)
                if (
                    status != "live"
                    or _snapshot_score(observation, match) != current_score
                    or not isinstance(current_score, dict)
                    or number != current_score.get("home", 0) + current_score.get("away", 0) + 1
                ):
                    continue
            normalized: dict[str, object] = {
                **item,
                "bans": unique_bans(item.get("bans")),
                "sides": sides,
                "updatedAt": item.get("sourceObservedAt") or observation.observed_at.isoformat(),
            }
            previous = by_number.get(number, {})
            if (
                normalized.get("status") == previous.get("status") == "live"
                and normalized.get("sourceGameId")
                and normalized.get("sourceGameId") == previous.get("sourceGameId")
                and all(not side.get("players") for side in sides)
            ):
                # A metadata refresh cannot erase or re-date the last live frame.
                continue
            by_number[number] = merge_completed_map(previous, normalized)
    maps_out = [by_number[number] for number in sorted(by_number)]
    score = _snapshot_score(snapshot, match)
    if isinstance(score, dict) and any(
        sum(item.get("winnerId") == team_id for item in maps_out) > score.get(label, 0)
        for label, team_id in (("home", match.home_id), ("away", match.away_id))
    ):
        return []
    return maps_out


def create_app(
    settings: Settings | None = None, auth_settings: AuthSettings | None = None
) -> FastAPI:
    config = settings or Settings()
    engine = create_db(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    app = FastAPI(
        title="Metiquo API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.include_router(create_auth_router(engine, auth_settings or AuthSettings()))
    app.include_router(create_admin_router(engine, auth_settings or AuthSettings()))
    app.include_router(create_catalog_router(engine, config))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> Response:
        if request.url.path.startswith(("/api/v1/auth/", "/api/v1/admin/")):
            return JSONResponse(
                status_code=422, content={"detail": "Données de la demande invalides."}
            )
        return await request_validation_exception_handler(request, error)

    @app.middleware("http")
    async def private_auth_responses(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(("/api/v1/auth/", "/api/v1/admin/")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    def get_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, error: SQLAlchemyError) -> JSONResponse:
        logger.error("Database request failed: %s", type(error).__name__)
        return JSONResponse(
            status_code=503,
            content={"detail": "Le service est momentanément indisponible."},
            headers={"Retry-After": "30", "Cache-Control": "no-store"},
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, error: Exception) -> JSONResponse:
        # No SQL parameters, cookies, credentials or request bodies in client responses/logs.
        logger.error("Unhandled request failure: %s", type(error).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Une erreur du serveur empêche de terminer la demande."},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/health/live", include_in_schema=False)
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def ready(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
        session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        session.execute(select(Dataset.id).limit(1))
        return {"status": "ready"}

    @app.get("/api/v1/catalog", response_model=Catalog)
    def catalog(session: Annotated[Session, Depends(get_session)]) -> Catalog:
        excluded_leagues, excluded_teams = other_game_identities(session)
        snapshot = session.scalar(
            select(CatalogVersion)
            .join(CatalogMetadata, CatalogMetadata.active_version_id == CatalogVersion.id)
            .where(CatalogMetadata.id == 1)
        )
        if snapshot is not None:
            catalog_document = snapshot.document.get("catalog")
            if not isinstance(catalog_document, dict):
                raise HTTPException(status_code=503, detail="Catalogue actif invalide")
            document: dict[str, object] = dict(catalog_document)
            league_items = document.get("leagues")
            league_items = league_items if isinstance(league_items, list) else []
            team_items = document.get("teams")
            team_items = team_items if isinstance(team_items, list) else []
            known_leagues = {
                str(item["id"]): _catalog_record(item, _LEAGUE_CONTRACT_FIELDS)
                for item in league_items
                if isinstance(item, dict) and "id" in item
            }
            known_teams = {
                str(item["id"]): _catalog_record(item, _TEAM_CONTRACT_FIELDS)
                for item in team_items
                if isinstance(item, dict) and "id" in item
            }
            # LoLTV can expose a cross-region tournament before the next
            # Riot catalog publication. Keep the Riot version immutable, but
            # expose newly sourced LoLTV identities in the same read
            # contract so a valid match is never hidden or reclassified.
            for league in session.scalars(select(League).order_by(League.id)):
                known_leagues.setdefault(
                    league.id, _catalog_record(league.data, _LEAGUE_CONTRACT_FIELDS)
                )
            for team in session.scalars(select(Team).order_by(Team.id)):
                known_teams.setdefault(team.id, _catalog_record(team.data, _TEAM_CONTRACT_FIELDS))
            document["leagues"] = [
                item for key, item in known_leagues.items() if key not in excluded_leagues
            ]
            document["teams"] = [
                item
                for key, item in known_teams.items()
                if key not in excluded_teams and item.get("leagueId") not in excluded_leagues
            ]
            return Catalog.model_validate(document)
        metadata = session.get(CatalogMetadata, 1)
        if metadata is None:
            raise HTTPException(
                503, "No sourced catalog imported; run metiquo-admin catalog-import"
            )
        return Catalog.model_validate(
            {
                "retrievedAt": metadata.retrieved_at,
                "source": metadata.source,
                "leagues": [
                    _catalog_record(league.data, _LEAGUE_CONTRACT_FIELDS)
                    for league in session.scalars(select(League).order_by(League.id))
                    if league.id not in excluded_leagues
                ],
                "teams": [
                    _catalog_record(team.data, _TEAM_CONTRACT_FIELDS)
                    for team in session.scalars(select(Team).order_by(Team.id))
                    if team.id not in excluded_teams and team.league_id not in excluded_leagues
                ],
            }
        )

    @app.get("/api/v1/opportunities", response_model=Opportunities)
    def opportunities(session: Annotated[Session, Depends(get_session)]) -> Opportunities:
        now = datetime.now(UTC)
        latest = (
            select(func.max(ProbabilityEstimate.estimated_at))
            .where(
                ProbabilityEstimate.market_id == Market.id, ProbabilityEstimate.estimated_at <= now
            )
            .correlate(Market)
            .scalar_subquery()
        )
        rows = session.execute(
            select(Market, EsportMatch, ProbabilityEstimate)
            .join(EsportMatch, EsportMatch.id == Market.match_id)
            .join(ProbabilityEstimate, ProbabilityEstimate.market_id == Market.id)
            .where(
                Market.active.is_(True),
                EsportMatch.starts_at > now,
                ProbabilityEstimate.estimated_at == latest,
                ProbabilityEstimate.valid_until > now,
            )
            .order_by(EsportMatch.starts_at, Market.id)
        ).all()
        histories: dict[UUID, list[dict[str, object]]] = {}
        if rows:
            quotes = session.scalars(
                select(OddsObservation)
                .where(
                    OddsObservation.market_id.in_([market.id for market, _, _ in rows]),
                    OddsObservation.recorded_at <= now,
                )
                .order_by(OddsObservation.recorded_at)
            )
            for quote in quotes:
                histories.setdefault(quote.market_id, []).append(
                    {"recordedAt": quote.recorded_at, "odds": float(quote.odds)}
                )
        items = []
        for market, match, estimate in rows:
            history = histories.get(market.id, [])
            if not history:
                continue
            last_recorded = history[-1]["recordedAt"]
            if not isinstance(last_recorded, datetime) or last_recorded < now - timedelta(
                seconds=config.odds_max_age_seconds
            ):
                continue
            items.append(
                Opportunity.model_validate(
                    {
                        "id": str(market.id),
                        "leagueId": match.league_id,
                        "homeId": match.home_id,
                        "awayId": match.away_id,
                        "pickId": market.pick_id,
                        "startsAt": match.starts_at,
                        "format": match.format,
                        "market": market.kind,
                        "probability": float(estimate.probability),
                        "bookmaker": market.bookmaker,
                        "history": history,
                    }
                )
            )
        return Opportunities(generated_at=now, reference_date=now, items=items)

    @app.get("/api/v1/matches")
    def matches(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
        now = datetime.now(UTC)
        paris_today = now.astimezone(PARIS).date()
        window_start = datetime.combine(
            paris_today - timedelta(days=7), time.min, PARIS
        ).astimezone(UTC)
        window_end = datetime.combine(paris_today + timedelta(days=7), time.max, PARIS).astimezone(
            UTC
        )
        rows = session.scalars(
            select(EsportMatch)
            .where(
                EsportMatch.starts_at >= window_start,
                EsportMatch.starts_at <= window_end,
            )
            .order_by(EsportMatch.starts_at, EsportMatch.id)
        ).all()
        snapshots: dict[UUID, list[MatchSnapshot]] = {}
        last_seen: dict[tuple[UUID, str], datetime] = {}
        if rows:
            for item in session.scalars(
                select(MatchSnapshot)
                .where(MatchSnapshot.match_id.in_([match.id for match in rows]))
                .order_by(MatchSnapshot.observed_at, MatchSnapshot.id)
            ).all():
                snapshots.setdefault(item.match_id, []).append(item)
            for link in session.scalars(
                select(MatchSourceLink).where(
                    MatchSourceLink.match_id.in_([match.id for match in rows])
                )
            ).all():
                key = (link.match_id, link.provider)
                previous = last_seen.get(key)
                if previous is None or link.last_seen_at > previous:
                    last_seen[key] = link.last_seen_at

        def snapshot_value(snapshot: MatchSnapshot | None, key: str) -> object:
            if snapshot is None:
                return None
            return snapshot.payload.get(key)

        items: list[dict[str, object]] = []
        for match in rows:
            history = snapshots.get(match.id, [])
            if match.source == "sofascore" and not any(item.source == "loltv" for item in history):
                continue
            # Retired observations are evidence only; active details use LoLTV and Oracle.
            history = [item for item in history if item.source != "sofascore"]
            usable_history = [
                item
                for item in history
                if _snapshot_format(item, match) is not None or item.source == "loltv"
            ]
            oracle_snapshot = next(
                (
                    item
                    for item in reversed(usable_history)
                    if _is_complete_oracle_snapshot(item, match)
                ),
                None,
            )
            # A complete Oracle series is the historical truth, even when a
            # newer live snapshot was captured before the worker stopped.
            snapshot = oracle_snapshot or (usable_history[-1] if usable_history else None)
            detail_snapshot = oracle_snapshot or next(
                (
                    item
                    for item in reversed(usable_history)
                    if isinstance(item.payload.get("maps"), list) and item.payload["maps"]
                ),
                None,
            )
            selected_format = _snapshot_format(snapshot, match) if snapshot is not None else None
            status = snapshot.status if snapshot else "scheduled"
            if status not in {"scheduled", "live", "finished", "cancelled", "postponed"}:
                status = "scheduled"
            items.append(
                {
                    "id": str(match.id),
                    "leagueId": match.league_id,
                    "homeId": match.home_id,
                    "awayId": match.away_id,
                    "startsAt": match.starts_at,
                    # A deduplicated snapshot records the last *changed* payload,
                    # while the source link records every observation. Display the
                    # latter without fabricating a new snapshot for an unchanged score.
                    "updatedAt": last_seen.get(
                        (match.id, snapshot.source if snapshot else match.source),
                        snapshot.observed_at if snapshot else match.registered_at,
                    ),
                    "format": selected_format or match.format,
                    "status": status,
                    "patch": snapshot_value(snapshot, "patch")
                    or snapshot_value(detail_snapshot, "patch"),
                    "stage": snapshot_value(snapshot, "stage")
                    or snapshot_value(detail_snapshot, "stage"),
                    "currentScore": _snapshot_score(snapshot, match)
                    if status != "scheduled"
                    else None,
                    "seriesScore": _snapshot_score(snapshot, match)
                    if status != "scheduled"
                    else None,
                    "maps": _match_maps(
                        [
                            *[item for item in usable_history if item.source != "oracles-elixir"],
                            oracle_snapshot,
                        ]
                        if oracle_snapshot
                        else usable_history,
                        match,
                        status,
                        snapshot,
                    ),
                }
            )
        return {"generatedAt": now, "items": items}

    @app.get("/api/v1/sources/loltv")
    def loltv_status(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
        state = session.get(CollectorState, "loltv")
        control = state.data if state else {}
        runs = session.scalars(
            select(IngestionRun)
            .where(IngestionRun.source == "loltv")
            .order_by(IngestionRun.started_at.desc())
            .limit(20)
        ).all()
        return {
            "source": "loltv",
            "collection": {
                key: control.get(key)
                for key in (
                    "blockedUntil",
                    "lastBlockAt",
                    "lastBlockStatus",
                    "lastBlockReason",
                    "consecutiveBlocks",
                    "lastRequestAt",
                )
            },
            "runs": [
                {
                    "id": run.id,
                    "status": run.status,
                    "scope": run.scope,
                    "startedAt": run.started_at,
                    "finishedAt": run.finished_at,
                    "error": run.error,
                    "details": run.details,
                }
                for run in runs
            ],
        }

    @app.get("/api/v1/performance")
    def performance() -> dict[str, object]:
        # No source currently links pre-match decisions to verified settlements.
        return {"generatedAt": datetime.now(UTC), "items": []}

    @app.get("/api/v1/sources/oracles-elixir")
    def source_status(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
        runs = session.scalars(
            select(IngestionRun)
            .where(IngestionRun.source == "oracles-elixir")
            .order_by(IngestionRun.started_at.desc())
            .limit(20)
        ).all()
        return {
            "source": "oracles-elixir",
            "runs": [
                {
                    "id": run.id,
                    "status": run.status,
                    "scope": run.scope,
                    "startedAt": run.started_at,
                    "finishedAt": run.finished_at,
                    "error": run.error,
                    "details": run.details,
                }
                for run in runs
            ],
        }

    @app.get("/api/v1/sources/oracles-elixir/datasets")
    def datasets(session: Annotated[Session, Depends(get_session)]) -> dict[str, object]:
        rows = session.execute(
            select(Dataset, DatasetVersion)
            .join(DatasetVersion, Dataset.active_version_id == DatasetVersion.id)
            .where(Dataset.source == "oracles-elixir")
            .order_by(Dataset.file_year)
        )
        return {
            "items": [
                {
                    "year": dataset.file_year,
                    "filename": dataset.filename,
                    "sourceFileId": dataset.source_file_id,
                    "versionId": version.id,
                    "sha256": version.sha256,
                    "rowCount": version.row_count,
                    "byteCount": version.byte_count,
                    "columns": version.columns,
                    "retrievedAt": version.retrieved_at,
                    "checkedAt": dataset.checked_at,
                }
                for dataset, version in rows
            ]
        }

    def get_version(session: Session, year: int, version_id: UUID | None) -> DatasetVersion:
        dataset = session.get(Dataset, f"oracles-elixir:{year}")
        if dataset is None:
            raise HTTPException(404, "Unknown dataset year")
        selected = version_id or dataset.active_version_id
        version = session.get(DatasetVersion, selected) if selected else None
        if version is None or version.dataset_id != dataset.id:
            raise HTTPException(404, "Unknown dataset version")
        return version

    @app.get("/api/v1/sources/oracles-elixir/datasets/{year}/rows")
    def source_rows(
        year: int,
        session: Annotated[Session, Depends(get_session)],
        version_id: Annotated[UUID | None, Query(alias="versionId")] = None,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 100,
        game_id: Annotated[str | None, Query(alias="gameId", max_length=200)] = None,
    ) -> dict[str, object]:
        if after and version_id is None:
            raise HTTPException(422, "Pin versionId when continuing pagination")
        version = get_version(session, year, version_id)
        statement = (
            select(OracleRow)
            .where(OracleRow.version_id == version.id, OracleRow.row_number > after)
            .order_by(OracleRow.row_number)
            .limit(limit + 1)
        )
        if game_id is not None:
            statement = statement.where(OracleRow.game_id == game_id)
        rows = session.scalars(statement).all()
        page = rows[:limit]
        return {
            "versionId": version.id,
            "sha256": version.sha256,
            "nextAfter": page[-1].row_number if len(rows) > limit else None,
            "items": [{"rowNumber": row.row_number, "data": row.payload} for row in page],
        }

    @app.get("/api/v1/sources/oracles-elixir/datasets/{year}/file")
    def source_file(
        year: int,
        session: Annotated[Session, Depends(get_session)],
        version_id: Annotated[UUID | None, Query(alias="versionId")] = None,
    ) -> FileResponse:
        version = get_version(session, year, version_id)
        root = config.artifact_dir.resolve()
        path = (root / version.artifact_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(503, "Stored CSV unavailable; restore the artifact volume")
        return FileResponse(
            path,
            media_type="text/csv",
            filename=f"oracle-{year}.csv",
            headers={"ETag": f'"{version.sha256}"', "Cache-Control": "no-cache"},
        )

    return app
