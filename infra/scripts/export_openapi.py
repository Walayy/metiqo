"""Exporter le contrat OpenAPI déterministe de l'API."""

from pathlib import Path

from metiquo.api.openapi import render_openapi

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DESTINATION = ROOT / "packages" / "contracts" / "openapi" / "v1.json"


def export_openapi(destination: Path = DEFAULT_DESTINATION) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_openapi(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    export_openapi()
