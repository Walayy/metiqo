"""Read-only source status, versioned reference and immutable local logos."""

import re
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from metiquo_core.config import Settings
from metiquo_core.models import CatalogMetadata, CatalogVersion, IngestionRun
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session


def create_catalog_router(engine: Engine, settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/sources/lol-esports")
    def status() -> dict[str, object]:
        with Session(engine) as session:
            metadata = session.get(CatalogMetadata, 1)
            runs = session.scalars(
                select(IngestionRun)
                .where(IngestionRun.source == "lol-esports")
                .order_by(IngestionRun.started_at.desc())
                .limit(20)
            ).all()
            return {
                "source": "lol-esports",
                "activeVersionId": metadata.active_version_id if metadata else None,
                "checkedAt": metadata.checked_at if metadata else None,
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

    @router.get("/api/v1/sources/lol-esports/reference")
    def reference(versionId: UUID | None = None) -> dict[str, object]:
        with Session(engine) as session:
            if versionId:
                version = session.get(CatalogVersion, versionId)
            else:
                version = session.scalar(
                    select(CatalogVersion)
                    .join(CatalogMetadata, CatalogMetadata.active_version_id == CatalogVersion.id)
                    .where(CatalogMetadata.id == 1)
                )
            if version is None:
                raise HTTPException(404 if versionId else 503, "No collected LoL catalog version")
            return {
                "versionId": version.id,
                "sha256": version.sha256,
                "retrievedAt": version.retrieved_at,
                "document": version.document,
            }

    @router.get("/api/v1/catalog/logos/{digest}.webp")
    def logo(digest: str, request: Request) -> Response:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise HTTPException(404, "Unknown logo")
        path = settings.artifact_dir / "catalog" / "logos" / digest[:2] / f"{digest}.webp"
        if not path.is_file():
            raise HTTPException(404, "Unknown logo")
        headers = {
            "ETag": f'"{digest}"',
            "Cache-Control": "public, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        }
        if request.headers.get("if-none-match") == headers["ETag"]:
            return Response(status_code=304, headers=headers)
        return FileResponse(path, media_type="image/webp", headers=headers)

    return router
