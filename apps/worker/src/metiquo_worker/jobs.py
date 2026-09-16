"""Shared locks and durable run state for the two collectors."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

from metiquo_core.models import IngestionRun
from sqlalchemy import Engine, func, text, update
from sqlalchemy.orm import Session


class CollectionBusy(Exception):
    pass


@contextmanager
def source_lock(engine: Engine, lock_id: int) -> Iterator[None]:
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": lock_id})
        connection.commit()
        if not acquired:
            raise CollectionBusy("Another collection owns this source lock")
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": lock_id})
            connection.commit()


def start_run(engine: Engine, source: str, scope: str) -> UUID:
    run_id = uuid4()
    with Session(engine) as session, session.begin():
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.source == source, IngestionRun.status == "running")
            .values(status="interrupted", finished_at=func.now(), error="Worker interrupted")
        )
        session.add(IngestionRun(id=run_id, source=source, scope=scope))
    return run_id


def fail_run(engine: Engine, run_id: UUID, stage: str, error: Exception) -> str:
    message = f"{stage}: {type(error).__name__}"
    with Session(engine) as session, session.begin():
        session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(status="failed", finished_at=func.now(), error=message)
        )
    return message
