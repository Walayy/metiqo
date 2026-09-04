"""Repositories et frontières d'accès aux données."""

from metiquo.repositories.boundary import (
    DataAccessBoundary,
    DataModeViolation,
    ExternalDataSource,
    LogicalSchema,
)
from metiquo.repositories.factory import (
    ConcreteRepositoryFactory,
    MockRepositoryFactory,
    RealRepositoryFactory,
    RepositoryFactory,
    build_repository_factory,
)
from metiquo.repositories.mock import (
    MockDataHealthRepository,
    MockEventRepository,
    MockMappingRepository,
    MockModelRepository,
    MockOddsProvider,
    MockOperationsRepository,
    MockOpportunityRepository,
    MockPaperRepository,
    MockRepositoryBundle,
    build_mock_repository_bundle,
)

__all__ = [
    "ConcreteRepositoryFactory",
    "DataAccessBoundary",
    "DataModeViolation",
    "ExternalDataSource",
    "LogicalSchema",
    "MockDataHealthRepository",
    "MockEventRepository",
    "MockMappingRepository",
    "MockModelRepository",
    "MockOddsProvider",
    "MockOperationsRepository",
    "MockOpportunityRepository",
    "MockPaperRepository",
    "MockRepositoryBundle",
    "MockRepositoryFactory",
    "RealRepositoryFactory",
    "RepositoryFactory",
    "build_mock_repository_bundle",
    "build_repository_factory",
]
