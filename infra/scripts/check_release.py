"""Prévol manuel obligatoire ; n'effectue aucun déploiement."""

import argparse
import json

from metiquo.config import load_settings
from metiquo.foundation.release_compliance import verify_release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audience", choices=("personal", "public", "commercial"), required=True)
    args = parser.parse_args()
    settings = load_settings()
    try:
        verify_release(args.audience, settings.release_gates, settings.release_evidence_file)
    except ValueError as error:
        print(json.dumps({"allowed": False, "audience": args.audience, "reason": str(error)}))
        return 1
    print(json.dumps({"allowed": True, "audience": args.audience, "gates": settings.release_gates}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
