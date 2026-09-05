"""Les alias Make OE restent reliés à la CLI publique."""

from pathlib import Path

from metiquo.cli.main import build_parser

ROOT = Path(__file__).resolve().parents[1]


def test_makefile_exposes_every_oe_alias() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    commands = {
        "oe-catalog:": "oe catalog refresh",
        "oe-backfill:": "oe backfill --from-year $(FROM) --to-year $(TO)",
        "oe-sync:": "oe sync --year $(YEAR)",
        "oe-sync-current:": "oe sync",
        "oe-validate:": "oe verify --snapshot $(SNAPSHOT)",
        "oe-diff:": "oe diff --left $(LEFT) --right $(RIGHT)",
        "oe-rebuild-canonical:": "oe rebuild-canonical --from $(FROM)",
        "features-rebuild:": "oe features-rebuild --from $(FROM)",
    }
    for target, command in commands.items():
        assert target in makefile
        assert command in makefile
    assert "est réservée et sera implémentée" not in makefile


def test_features_rebuild_cli_requires_a_date_and_accepts_commit() -> None:
    arguments = build_parser().parse_args(
        [
            "features-rebuild",
            "--from",
            "2026-01-01",
            "--code-commit",
            "abcdef1",
            "--json",
        ]
    )

    assert arguments.command == "features-rebuild"
    assert arguments.from_date.isoformat() == "2026-01-01"
    assert arguments.code_commit == "abcdef1"
    assert arguments.json is True
