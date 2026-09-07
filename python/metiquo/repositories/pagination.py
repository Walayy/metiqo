"""Consistent bounded reads, including totals for empty pages beyond the end."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Connection, RowMapping, func, select
from sqlalchemy.sql import Select


@dataclass(frozen=True, slots=True)
class ReadPage[T]:
    items: tuple[T, ...]
    total: int


def page_rows(
    connection: Connection, statement: Select[tuple[Any, ...]], *, offset: int, limit: int
) -> ReadPage[RowMapping]:
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("Pagination hors limites")
    total = int(
        connection.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
        or 0
    )
    rows = tuple(connection.execute(statement.offset(offset).limit(limit)).mappings())
    return ReadPage(rows, total)
