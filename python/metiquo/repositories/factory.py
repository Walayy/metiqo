"""Factories de repositories physiquement liées à un seul mode."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from metiquo.config import Settings
from metiquo.contracts.enums import DataMode
from metiquo.repositories.boundary import DataAccessBoundary, DataModeViolation


class RepositoryFactory(Protocol):
    """Surface commune consommée par les futurs services métier."""

    @property
    def data_mode(self) -> DataMode: ...

    @property
    def boundary(self) -> DataAccessBoundary: ...

    @property
    def engine(self) -> Engine: ...


def _mode_engine(settings: Settings, boundary: DataAccessBoundary) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        connect_args={"options": "-c timezone=UTC"},
        execution_options={"schema_translate_map": boundary.schema_translate_map()},
    )


def _validate_binding(
    boundary: DataAccessBoundary,
    engine: Engine,
    expected_mode: DataMode,
) -> None:
    if boundary.data_mode is not expected_mode:
        raise DataModeViolation(
            f"La factory {expected_mode.value} a reçu une frontière incompatible"
        )
    translation = engine.get_execution_options().get("schema_translate_map")
    if translation != boundary.schema_translate_map():
        raise DataModeViolation(f"La factory {expected_mode.value} a reçu un moteur incompatible")


@dataclass(frozen=True, slots=True)
class MockRepositoryFactory:
    """Factory dont toutes les tables logiques pointent vers `mock`."""

    boundary: DataAccessBoundary
    engine: Engine

    def __post_init__(self) -> None:
        _validate_binding(self.boundary, self.engine, DataMode.MOCK)

    @property
    def data_mode(self) -> DataMode:
        return DataMode.MOCK

    @classmethod
    def from_settings(cls, settings: Settings) -> "MockRepositoryFactory":
        if settings.app_data_mode is not DataMode.MOCK:
            raise DataModeViolation("MockRepositoryFactory exige APP_DATA_MODE=mock")
        boundary = DataAccessBoundary(DataMode.MOCK)
        return cls(boundary=boundary, engine=_mode_engine(settings, boundary))


@dataclass(frozen=True, slots=True)
class RealRepositoryFactory:
    """Factory conservant les sept namespaces métier réels."""

    boundary: DataAccessBoundary
    engine: Engine

    def __post_init__(self) -> None:
        _validate_binding(self.boundary, self.engine, DataMode.REAL)

    @property
    def data_mode(self) -> DataMode:
        return DataMode.REAL

    @classmethod
    def from_settings(cls, settings: Settings) -> "RealRepositoryFactory":
        if settings.app_data_mode is not DataMode.REAL:
            raise DataModeViolation("RealRepositoryFactory exige APP_DATA_MODE=real")
        boundary = DataAccessBoundary(DataMode.REAL)
        return cls(boundary=boundary, engine=_mode_engine(settings, boundary))


type ConcreteRepositoryFactory = MockRepositoryFactory | RealRepositoryFactory


def build_repository_factory(settings: Settings) -> ConcreteRepositoryFactory:
    """Construire exactement une factory après validation de configuration."""

    if settings.app_data_mode is DataMode.MOCK:
        return MockRepositoryFactory.from_settings(settings)
    return RealRepositoryFactory.from_settings(settings)
