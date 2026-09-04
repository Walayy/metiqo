"""Schémas logiques PostgreSQL actifs au MVP."""

from typing import Final

LOGICAL_SCHEMAS: Final[tuple[str, ...]] = (
    "raw",
    "core",
    "odds",
    "features",
    "ml",
    "signals",
    "ops",
)

MOCK_SCHEMA: Final = "mock"
ALL_SCHEMAS: Final[tuple[str, ...]] = (*LOGICAL_SCHEMAS, MOCK_SCHEMA)
