import argparse
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from metiquo_core.catalog import CATALOG_LOCK_ID, import_catalog
from metiquo_core.config import Settings
from metiquo_core.contracts import Catalog
from metiquo_core.db import create_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Metiquo administration (no public write API)")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser("catalog-import", help="Import a sourced catalog JSON explicitly")
    catalog.add_argument("path", type=Path)
    args = parser.parse_args()
    data = Catalog.model_validate_json(args.path.read_bytes())
    engine = create_db(Settings())
    try:
        with Session(engine) as session, session.begin():
            if not session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:id)"), {"id": CATALOG_LOCK_ID}
            ):
                raise SystemExit("Catalog busy: another import or collection is running")
            import_catalog(session, data)
        print(f"Imported {len(data.leagues)} leagues and {len(data.teams)} teams")
    finally:
        engine.dispose()
