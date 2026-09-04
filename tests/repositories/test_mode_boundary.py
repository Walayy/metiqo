"""Tests unitaires de la frontière mock/réel."""

import pytest

from metiquo.config import Settings
from metiquo.contracts.enums import DataMode
from metiquo.repositories import (
    DataAccessBoundary,
    DataModeViolation,
    ExternalDataSource,
    LogicalSchema,
    MockRepositoryFactory,
    RealRepositoryFactory,
    build_repository_factory,
)


def build_settings(mode: DataMode) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "app_data_mode": mode.value,
            "database_url": "postgresql+psycopg://metiquo@postgres:5432/metiquo",
            "odds_provider": "mock" if mode is DataMode.MOCK else "disabled",
        }
    )


def test_mock_and_real_resolve_distinct_physical_schemas() -> None:
    mock = DataAccessBoundary(DataMode.MOCK)
    real = DataAccessBoundary(DataMode.REAL)

    assert set(mock.schema_translate_map().values()) == {"mock"}
    assert real.schema_translate_map() == {schema.value: schema.value for schema in LogicalSchema}
    assert mock.physical_schema(LogicalSchema.CORE) == "mock"
    assert real.physical_schema(LogicalSchema.CORE) == "core"


@pytest.mark.parametrize("context_mode", list(DataMode))
def test_context_rejects_payload_from_other_mode(context_mode: DataMode) -> None:
    other_mode = DataMode.REAL if context_mode is DataMode.MOCK else DataMode.MOCK
    boundary = DataAccessBoundary(context_mode)

    with pytest.raises(DataModeViolation, match="refuse les données"):
        boundary.require_payload_mode(other_mode)

    boundary.require_payload_mode(context_mode)


def test_mock_blocks_external_source_before_transport_is_called() -> None:
    calls: list[ExternalDataSource] = []
    boundary = DataAccessBoundary(DataMode.MOCK)

    def guarded_request(source: ExternalDataSource) -> None:
        boundary.require_external_access(source)
        calls.append(source)

    for source in ExternalDataSource:
        with pytest.raises(DataModeViolation, match="interdit tout accès externe"):
            guarded_request(source)

    assert calls == []


def test_real_boundary_allows_external_sources() -> None:
    boundary = DataAccessBoundary(DataMode.REAL)

    for source in ExternalDataSource:
        boundary.require_external_access(source)


def test_factory_selection_is_typed_and_mode_bound() -> None:
    mock_settings = build_settings(DataMode.MOCK)
    real_settings = build_settings(DataMode.REAL)
    mock = build_repository_factory(mock_settings)
    real = build_repository_factory(real_settings)

    try:
        assert isinstance(mock, MockRepositoryFactory)
        assert isinstance(real, RealRepositoryFactory)
        assert mock.data_mode is DataMode.MOCK
        assert real.data_mode is DataMode.REAL

        with pytest.raises(DataModeViolation, match="APP_DATA_MODE=mock"):
            MockRepositoryFactory.from_settings(real_settings)
        with pytest.raises(DataModeViolation, match="APP_DATA_MODE=real"):
            RealRepositoryFactory.from_settings(mock_settings)
        with pytest.raises(DataModeViolation, match="frontière incompatible"):
            MockRepositoryFactory(boundary=real.boundary, engine=mock.engine)
        with pytest.raises(DataModeViolation, match="moteur incompatible"):
            MockRepositoryFactory(boundary=mock.boundary, engine=real.engine)
    finally:
        mock.engine.dispose()
        real.engine.dispose()
