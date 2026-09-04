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
