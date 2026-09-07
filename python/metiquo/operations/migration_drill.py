"""Rehearse migrations only on a newly restored, verified database and object copy."""

from dataclasses import asdict, dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, text

from metiquo.config import Settings
from metiquo.operations.backup_tools import BackupError, PostgresTools
from metiquo.operations.restore import RestoreRequest, RestoreService


@dataclass(frozen=True, slots=True)
class MigrationDrillResult:
    database: str
    from_revision: str
    to_revision: str
    preserved_snapshots: int
    preserved_models: int

    def document(self) -> dict[str, object]:
        return asdict(self)


class MigrationDrill:
    def __init__(
        self, engine: Engine, settings: Settings, *, tools: PostgresTools | None = None
    ) -> None:
        self.restore = RestoreService(engine, settings, tools=tools)
        self.engine = engine

    def run(self, request: RestoreRequest) -> MigrationDrillResult:
        # RestoreService requires APP_ENV=test and refuses existing/overlapping targets.
        restored = self.restore.run(request)
        target = create_engine(self.engine.url.set(database=restored.database))
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parents[1] / "db/migrations"))
        config.attributes["database_url"] = target.url.render_as_string(hide_password=False)
        expected = ScriptDirectory.from_config(config).get_current_head()
        if expected is None:
            raise BackupError("MIGRATION_HEAD_MISSING")
        try:
            before = self._inventory(target)
            command.upgrade(config, "head")
            after = self._inventory(target)
            with target.connect() as connection:
                revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            if revision != expected or after != before:
                raise BackupError("MIGRATION_COPY_VERIFICATION_FAILED")
            # Deliberately keep the copy for inspection; never apply to the source.
            return MigrationDrillResult(
                restored.database,
                restored.migration_revision,
                expected,
                len(after[0]),
                len(after[1]),
            )
        except BackupError:
            raise
        except Exception as error:
            raise BackupError("MIGRATION_COPY_UPGRADE_FAILED") from error
        finally:
            target.dispose()

    @staticmethod
    def _inventory(engine: Engine) -> tuple[tuple[tuple[object, ...], ...], ...]:
        with engine.connect() as connection:
            return tuple(
                tuple(tuple(row) for row in connection.execute(text(query)))
                for query in (
                    "SELECT id, sha256, object_key, byte_size FROM raw.snapshots ORDER BY id",
                    "SELECT id, artifact_hash, artifact_object_key, artifact_size_bytes "
                    "FROM ml.model_versions ORDER BY id",
                )
            )
