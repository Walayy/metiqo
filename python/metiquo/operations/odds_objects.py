"""Références d'archives de cotes à conserver lors des sauvegardes et restaurations."""

from sqlalchemy import Connection, text


def odds_object_references(connection: Connection) -> tuple[tuple[str, str], ...]:
    references: set[tuple[str, str]] = set()
    for table, hash_column in (
        ("snapshots", "raw_payload_sha256"),
        ("stake_page_captures", "sha256"),
    ):
        if connection.scalar(text("SELECT to_regclass(:name)"), {"name": f"odds.{table}"}) is None:
            continue
        for row in connection.execute(
            text(
                f"SELECT DISTINCT raw_payload_reference, {hash_column} FROM odds.{table} "
                f"WHERE {hash_column} IS NOT NULL AND raw_payload_reference LIKE 'odds/%'"
            )
        ):
            references.add((row[0], row[1]))
    return tuple(sorted(references))
