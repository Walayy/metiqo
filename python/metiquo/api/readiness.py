"""Sonde de disponibilité PostgreSQL et Alembic."""

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

DATABASE_UNREACHABLE: Final = "DATABASE_UNREACHABLE"
MIGRATIONS_NOT_AT_HEAD: Final = "MIGRATIONS_NOT_AT_HEAD"


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """Résultat interne d'une sonde, sans dépendance au contrat HTTP."""

    available: bool
    reason_code: str | None = None


class ReadinessProbe(Protocol):
    """Frontière injectable de la vérification de disponibilité."""

    def check(self) -> ReadinessCheck: ...


class DatabaseReadinessProbe:
    """Vérifier la connexion et l'alignement avec toutes les têtes Alembic."""

    def __init__(self, database_url: str, *, alembic_config: Path = Path("alembic.ini")) -> None:
        self._database_url = database_url
        self._alembic_config = alembic_config

    def check(self) -> ReadinessCheck:
        engine = create_engine(
            self._database_url,
            poolclass=NullPool,
            connect_args={"connect_timeout": 2, "options": "-c timezone=UTC"},
        )
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                current_heads = frozenset(
                    MigrationContext.configure(connection).get_current_heads()
                )
            expected_heads = frozenset(
                ScriptDirectory.from_config(Config(self._alembic_config)).get_heads()
            )
        except (CommandError, OSError, SQLAlchemyError):
            return ReadinessCheck(available=False, reason_code=DATABASE_UNREACHABLE)
        finally:
            engine.dispose()

        if current_heads != expected_heads:
            return ReadinessCheck(available=False, reason_code=MIGRATIONS_NOT_AT_HEAD)
        return ReadinessCheck(available=True)
