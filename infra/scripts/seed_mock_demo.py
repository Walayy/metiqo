"""Valider et décrire la graine déterministe de la démo mock."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from typing import cast

from metiquo.foundation.time import UtcInstant
from metiquo.mock.demo import DEFAULT_REFERENCE_TIME, build_demo_manifest


def _parse_reference_time(value: str) -> datetime:
    return UtcInstant.parse(value).value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        default=os.environ.get("MOCK_SEED", "metiquo-demo-v1"),
        help="Graine stable de la démo (défaut : MOCK_SEED ou metiquo-demo-v1)",
    )
    parser.add_argument(
        "--reference-time",
        default=UtcInstant(DEFAULT_REFERENCE_TIME).isoformat(),
        type=_parse_reference_time,
        help="Instant UTC déterministe utilisé pour le manifeste",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Valider le catalogue et afficher un résumé compact",
    )
    return parser


def main() -> int:
    """Point d'entrée CLI sans effet externe."""

    arguments = _parser().parse_args()
    seed = cast(str, arguments.seed)
    reference_time = cast(datetime, arguments.reference_time)
    check = cast(bool, arguments.check)
    manifest = build_demo_manifest(seed, reference_time)
    if check:
        print(
            "Graine mock valide : "
            f"{manifest['scenarioCount']} scénarios, SHA-256 {manifest['catalogSha256']}"
        )
    else:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
