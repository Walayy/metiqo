from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from metiquo_core.models import (
    AdminAudit,
    AppUser,
    AuthSession,
    IngestionRun,
    ScriptRun,
    ScriptSchedule,
    WorkerLogEntry,
    WorkerStatus,
)
from metiquo_core.scheduling import SCRIPTS, WORKER_SERVICES, upcoming, worker_for_script
from metiquo_core.source_issues import historical_loltv_issues, safe_source_issues
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, delete, func, insert, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from metiquo_api.auth import IDLE_TTL, authenticated_user
from metiquo_api.auth_config import AuthSettings


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "admin"]
    disabled: bool


class CronRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cron: str = Field(min_length=9, max_length=100)
    timezone: Literal["Europe/Paris", "UTC"]


class ScheduleUpdate(CronRequest):
    enabled: bool
    revision: int = Field(ge=1)


def dates_for(body: CronRequest) -> list[datetime]:
    try:
        return upcoming(body.cron.strip(), body.timezone, datetime.now(UTC))
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


def run_data(run: ScriptRun, ingestion: IngestionRun | None = None) -> dict[str, object]:
    details = ingestion.details if ingestion and ingestion.source in {"stake", "loltv"} else {}
    summary = {
        key: details[key]
        for key in (
            "eventsScanned",
            "eventsCollected",
            "liveEvents",
            "eventsStopped",
            "eventsFailed",
            "markets",
            "selections",
            "quotes",
            "openQuotes",
            "suspendedQuotes",
            "snapshots",
            "published",
            "created",
            "knownEvents",
            "pendingDetails",
            "unavailableFeeds",
        )
        if isinstance(details.get(key), int)
    }
    return {
        "id": run.id,
        "scriptId": run.script_id,
        "trigger": run.trigger,
        "status": run.status,
        "requestedAt": run.requested_at,
        "startedAt": run.started_at,
        "finishedAt": run.finished_at,
        "error": run.error,
        "availableAt": run.available_at,
        "summary": summary or None,
        "complete": details.get("complete") if isinstance(details.get("complete"), bool) else None,
        "eventErrors": details.get("eventErrors", []),
        "interruption": details.get("interruption"),
        "deferredReason": details.get("deferredReason"),
        "statusCorrection": details.get("statusCorrection"),
        "sourceIssues": (
            safe_source_issues(details.get("sourceIssues"))
            if "sourceIssues" in details
            else historical_loltv_issues(details.get("errors"))
        )
        if ingestion and ingestion.source == "loltv"
        else [],
    }


def create_admin_router(engine: Engine, settings: AuthSettings) -> APIRouter:
    def context(request: Request) -> Iterator[Session]:
        with Session(engine) as session:
            # User administration is serialized, including the actor's current role check.
            if request.method != "GET":
                if (
                    request.headers.get("origin") not in settings.auth_origins
                    or request.headers.get("x-metiquo-auth") != "1"
                ):
                    raise HTTPException(403, "Origine de la demande refusée.")
                session.execute(text("SELECT pg_advisory_xact_lock(62883201)"))
            user = authenticated_user(request, session, settings)
            if user.role != "admin":
                raise HTTPException(403, "Cet espace est réservé aux administrateurs.")
            request.state.admin_id = user.id
            yield session
            session.commit()

    router = APIRouter(prefix="/api/v1/admin", tags=["Administration"])

    def audit(
        db: Session,
        request: Request,
        action: str,
        target: str,
        details: dict[str, object] | None = None,
    ) -> None:
        db.add(
            AdminAudit(
                actor_id=request.state.admin_id, action=action, target=target, details=details or {}
            )
        )

    @router.get("/users")
    def users(
        db: Annotated[Session, Depends(context, scope="function")],
        q: str = Query(default="", max_length=254),
        page: int = Query(default=1, ge=1),
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        condition: ColumnElement[bool] = AppUser.email.is_not(None)
        if q.strip():
            condition = condition & AppUser.email.icontains(q.strip(), autoescape=True)
        total = db.scalar(select(func.count()).select_from(AppUser).where(condition)) or 0
        rows = db.scalars(
            select(AppUser)
            .where(condition)
            .order_by(AppUser.created_at.desc(), AppUser.id)
            .offset((page - 1) * 20)
            .limit(20)
        ).all()
        sessions = {
            user_id: count
            for user_id, count in db.execute(
                select(AuthSession.user_id, func.count())
                .where(
                    AuthSession.user_id.in_([row.id for row in rows]),
                    AuthSession.expires_at > now,
                    AuthSession.last_seen_at > now - IDLE_TTL,
                )
                .group_by(AuthSession.user_id)
            ).all()
        }
        return {
            "total": total,
            "page": page,
            "pageSize": 20,
            "items": [
                {
                    "id": row.id,
                    "email": row.email,
                    "role": row.role,
                    "disabled": row.disabled,
                    "verified": row.verified_at is not None,
                    "createdAt": row.created_at,
                    "sessions": sessions.get(row.id, 0),
                }
                for row in rows
            ],
        }

    @router.patch("/users/{user_id}")
    def update_user(
        user_id: UUID,
        body: UserUpdate,
        request: Request,
        db: Annotated[Session, Depends(context, scope="function")],
    ) -> dict[str, bool]:
        user = db.get(AppUser, user_id, with_for_update=True)
        if user is None:
            raise HTTPException(404, "Utilisateur introuvable.")
        if user.id == request.state.admin_id and (body.disabled or body.role != "admin"):
            raise HTTPException(
                409, "Vous ne pouvez pas retirer votre propre accès administrateur."
            )
        if user.role == "admin" and not user.disabled and (body.disabled or body.role != "admin"):
            count = (
                db.scalar(
                    select(func.count())
                    .select_from(AppUser)
                    .where(AppUser.role == "admin", AppUser.disabled.is_(False))
                )
                or 0
            )
            if count <= 1:
                raise HTTPException(409, "Conservez au moins un administrateur actif.")
        changed = user.role != body.role or user.disabled != body.disabled
        before = {"role": user.role, "disabled": user.disabled}
        user.role, user.disabled = body.role, body.disabled
        if changed:
            db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
            audit(
                db,
                request,
                "user.updated",
                str(user_id),
                {"before": before, "after": body.model_dump()},
            )
        return {"ok": True}

    @router.post("/users/{user_id}/revoke-sessions")
    def revoke(
        user_id: UUID, request: Request, db: Annotated[Session, Depends(context, scope="function")]
    ) -> dict[str, bool]:
        if db.get(AppUser, user_id) is None:
            raise HTTPException(404, "Utilisateur introuvable.")
        db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))
        audit(db, request, "user.sessions_revoked", str(user_id))
        return {"ok": True}

    @router.get("/scripts")
    def scripts(db: Annotated[Session, Depends(context, scope="function")]) -> dict[str, object]:
        now = datetime.now(UTC)
        workers = db.scalars(select(WorkerStatus)).all()
        active_scripts = {
            script
            for worker in workers
            if worker.seen_at > now - timedelta(seconds=90)
            for script in worker.scripts
        }
        online = bool(active_scripts)
        last_seen = max((worker.seen_at for worker in workers), default=None)
        worker_by_id = {worker.id: worker for worker in workers}
        running = db.scalars(select(ScriptRun).where(ScriptRun.status == "running")).all()
        services = [
            {
                "id": worker_id,
                "name": name,
                "online": bool(
                    worker_by_id.get(worker_id)
                    and worker_by_id[worker_id].seen_at > now - timedelta(seconds=90)
                ),
                "lastSeenAt": worker_by_id[worker_id].seen_at
                if worker_id in worker_by_id
                else None,
                "activeRuns": [
                    {
                        "id": run.id,
                        "scriptId": run.script_id,
                        "name": SCRIPTS[run.script_id].name,
                    }
                    for run in running
                    if run.script_id in SCRIPTS and worker_for_script(run.script_id) == worker_id
                ],
            }
            for worker_id, name in WORKER_SERVICES.items()
        ]
        rows = db.scalars(select(ScriptSchedule).order_by(ScriptSchedule.id)).all()
        items = []
        for row in rows:
            definition = SCRIPTS.get(row.id)
            if definition is None:
                continue
            runs = db.scalars(
                select(ScriptRun)
                .where(ScriptRun.script_id == row.id)
                .order_by(ScriptRun.requested_at.desc())
                .limit(8)
            ).all()
            active = db.scalar(
                select(ScriptRun).where(
                    ScriptRun.script_id == row.id, ScriptRun.status.in_(["queued", "running"])
                )
            )
            items.append(
                {
                    "id": row.id,
                    "workerId": worker_for_script(row.id),
                    "name": definition.name,
                    "description": definition.description,
                    "family": definition.family,
                    "command": definition.command,
                    "cron": row.cron,
                    "timezone": row.timezone,
                    "enabled": row.enabled,
                    "revision": row.revision,
                    "nextRunAt": row.next_run_at if row.enabled else None,
                    "upcoming": upcoming(row.cron, row.timezone, max(now, row.next_run_at))
                    if row.enabled
                    else [],
                    "available": row.id in active_scripts,
                    "activeRun": run_data(
                        active,
                        db.get(IngestionRun, active.ingestion_run_id)
                        if active.ingestion_run_id
                        else None,
                    )
                    if active
                    else None,
                    "runs": [
                        run_data(
                            run,
                            db.get(IngestionRun, run.ingestion_run_id)
                            if run.ingestion_run_id
                            else None,
                        )
                        for run in runs
                    ],
                }
            )
        return {
            "items": items,
            "worker": {"online": online, "lastSeenAt": last_seen},
            "workers": services,
        }

    def log_data(entry: WorkerLogEntry) -> dict[str, object]:
        return {
            "id": entry.id,
            "workerId": entry.worker_id,
            "scriptId": entry.script_id,
            "runId": entry.run_id,
            "recordedAt": entry.recorded_at,
            "level": entry.level,
            "stage": entry.stage,
            "message": entry.message,
            "eventId": entry.event_id,
            "context": entry.context,
        }

    @router.get("/worker-logs")
    def worker_logs(
        db: Annotated[Session, Depends(context, scope="function")],
        worker_id: Annotated[int, Query(alias="workerId", ge=1, le=3)],
        run_id: Annotated[UUID | None, Query(alias="runId")] = None,
        before: Annotated[int | None, Query(ge=1)] = None,
        after: Annotated[int | None, Query(ge=0)] = None,
        level: Literal["all", "warning", "error"] = "all",
        q: str = Query(default="", max_length=80),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> dict[str, object]:
        if before is not None and after is not None:
            raise HTTPException(422, "Choisissez un seul sens de pagination.")
        selected = db.get(ScriptRun, run_id) if run_id else None
        if run_id and (
            selected is None
            or selected.script_id not in SCRIPTS
            or worker_for_script(selected.script_id) != worker_id
        ):
            raise HTTPException(404, "Exécution introuvable pour ce worker.")
        condition: ColumnElement[bool] = (WorkerLogEntry.worker_id == worker_id) & (
            WorkerLogEntry.recorded_at >= datetime.now(UTC) - timedelta(days=14)
        )
        if run_id:
            condition = condition & (WorkerLogEntry.run_id == run_id)
        incident_rows = db.scalars(
            select(WorkerLogEntry)
            .where(condition, WorkerLogEntry.level.in_(["warning", "error"]))
            .order_by(WorkerLogEntry.id.desc())
            .limit(4)
        ).all()
        filtered = condition
        if level != "all":
            filtered = filtered & (WorkerLogEntry.level == level)
        term = q.strip()
        if term:
            filtered = filtered & (
                WorkerLogEntry.message.icontains(term, autoescape=True)
                | WorkerLogEntry.stage.icontains(term, autoescape=True)
                | WorkerLogEntry.event_id.icontains(term, autoescape=True)
                | WorkerLogEntry.script_id.icontains(term, autoescape=True)
            )
        if before is not None:
            filtered = filtered & (WorkerLogEntry.id < before)
        if after is not None:
            filtered = filtered & (WorkerLogEntry.id > after)
        ascending = after is not None
        rows = db.scalars(
            select(WorkerLogEntry)
            .where(filtered)
            .order_by(WorkerLogEntry.id.asc() if ascending else WorkerLogEntry.id.desc())
            .limit(limit + 1)
        ).all()
        has_more = len(rows) > limit
        page = list(rows[:limit])
        if not ascending:
            page.reverse()
        script_ids = [key for key in SCRIPTS if worker_for_script(key) == worker_id]
        recent = list(
            db.scalars(
                select(ScriptRun)
                .where(ScriptRun.script_id.in_(script_ids))
                .order_by(ScriptRun.requested_at.desc(), ScriptRun.id.desc())
                .limit(12)
            ).all()
        )
        if selected and all(run.id != selected.id for run in recent):
            recent.append(selected)
        return {
            "items": [log_data(entry) for entry in page],
            "incidents": [log_data(entry) for entry in incident_rows],
            "hasMore": has_more,
            "recentRuns": [
                {
                    "id": run.id,
                    "scriptId": run.script_id,
                    "name": SCRIPTS[run.script_id].name,
                    "status": run.status,
                    "requestedAt": run.requested_at,
                }
                for run in recent
            ],
            "run": run_data(
                selected,
                db.get(IngestionRun, selected.ingestion_run_id)
                if selected and selected.ingestion_run_id
                else None,
            )
            if selected
            else None,
        }

    @router.post("/scripts/preview")
    def preview(
        body: CronRequest, db: Annotated[Session, Depends(context, scope="function")]
    ) -> dict[str, object]:
        return {"upcoming": dates_for(body)}

    @router.patch("/scripts/{script_id}")
    def update_script(
        script_id: str,
        body: ScheduleUpdate,
        request: Request,
        db: Annotated[Session, Depends(context, scope="function")],
    ) -> dict[str, bool]:
        dates = dates_for(body)
        row = db.get(ScriptSchedule, script_id, with_for_update=True)
        if row is None or script_id not in SCRIPTS:
            raise HTTPException(404, "Script introuvable.")
        if row.revision != body.revision:
            raise HTTPException(
                409, "Cette planification a changé. Fermez puis rouvrez le formulaire."
            )
        before = {"cron": row.cron, "timezone": row.timezone, "enabled": row.enabled}
        row.cron, row.timezone, row.enabled = body.cron.strip(), body.timezone, body.enabled
        row.next_run_at = dates[0]
        row.revision += 1
        audit(
            db,
            request,
            "script.updated",
            script_id,
            {"before": before, "after": body.model_dump(exclude={"revision"})},
        )
        return {"ok": True}

    @router.post("/scripts/{script_id}/run", status_code=202)
    def run(
        script_id: str, request: Request, db: Annotated[Session, Depends(context, scope="function")]
    ) -> dict[str, object]:
        row = db.get(ScriptSchedule, script_id, with_for_update=True)
        if row is None or script_id not in SCRIPTS:
            raise HTTPException(404, "Script introuvable.")
        now = datetime.now(UTC)
        workers = db.scalars(
            select(WorkerStatus).where(WorkerStatus.seen_at > now - timedelta(seconds=90))
        ).all()
        if not any(script_id in worker.scripts for worker in workers):
            raise HTTPException(
                409, "Le worker de ce script est indisponible. Réessayez après son retour."
            )
        if (
            db.scalar(
                select(ScriptRun.id).where(
                    ScriptRun.script_id == script_id, ScriptRun.status.in_(["queued", "running"])
                )
            )
            is not None
        ):
            raise HTTPException(409, "Ce script est déjà en attente ou en cours.")
        run_id = uuid4()
        db.execute(
            insert(ScriptRun).values(
                id=run_id,
                script_id=script_id,
                trigger="manual",
                status="queued",
                requested_at=now,
                available_at=now,
            )
        )
        item = db.get(ScriptRun, run_id)
        assert item is not None
        audit(db, request, "script.requested", script_id, {"runId": str(item.id)})
        return run_data(item)

    return router
