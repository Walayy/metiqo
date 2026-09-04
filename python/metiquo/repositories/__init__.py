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

__all__ = [
    "ConcreteRepositoryFactory",
    "DataAccessBoundary",
    "DataModeViolation",
    "ExternalDataSource",
    "LogicalSchema",
    "MockRepositoryFactory",
    "RealRepositoryFactory",
    "RepositoryFactory",
    "build_repository_factory",
]
