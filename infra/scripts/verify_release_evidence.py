"""Vérifier les preuves exécutées et le statut de tous les jobs obligatoires."""

import argparse
import json
import os
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


def verify_jobs(jobs: dict[str, Any]) -> None:
    if set(jobs) != {"quality", "runtime", "e2e"}:
        raise ValueError("Un job obligatoire manque au gate de release")
    if any(item.get("result") != "success" for item in jobs.values()):
        raise ValueError("Release refusée : un job obligatoire a échoué ou n'a pas été exécuté")


def verify_junit(path: Path) -> int:
    root = ElementTree.parse(path).getroot()
    cases = root.findall(".//testcase")
    if not cases or any(
        case.find(state) is not None for case in cases for state in ("skipped", "failure", "error")
    ):
        raise ValueError("Preuve de tests incomplète : test absent, sauté ou en échec")
    return len(cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("junit", "jobs"))
    parser.add_argument("path", type=Path, nargs="?")
    args = parser.parse_args()
    if args.kind == "jobs":
        verify_jobs(json.loads(os.environ["NEEDS_JSON"]))
        print("Tous les jobs obligatoires ont réussi.")
    else:
        if args.path is None:
            parser.error("Un rapport JUnit est requis")
        print(f"{verify_junit(args.path)} tests exécutés sans exclusion ni échec.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
