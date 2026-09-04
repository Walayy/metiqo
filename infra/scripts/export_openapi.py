"""Exporter le contrat OpenAPI déterministe de l'API."""

import sys
from collections.abc import Sequence
from pathlib import Path

from metiquo.api.openapi import render_openapi, verify_openapi_content

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESTINATION = ROOT / "packages" / "contracts" / "openapi" / "v1.json"


def export_openapi(destination: Path = DEFAULT_DESTINATION) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_openapi(), encoding="utf-8", newline="\n")


def verify_openapi(destination: Path = DEFAULT_DESTINATION) -> None:
    """Échouer si le contrat versionné ne correspond pas au code courant."""

    if not destination.is_file():
        raise RuntimeError("Le contrat OpenAPI versionné est absent ; exécuter `make openapi`")
    verify_openapi_content(destination.read_text(encoding="utf-8"))


def main(arguments: Sequence[str]) -> int:
    """Exécuter l'export ou sa vérification sans ambiguïté."""

    if not arguments:
        export_openapi()
        return 0
    if list(arguments) == ["--check"]:
        try:
            verify_openapi()
        except RuntimeError as error:
            print(str(error), file=sys.stderr)
            return 1
        return 0
    print("Usage : export_openapi.py [--check]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
