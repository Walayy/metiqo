"""Synchroniser l'extracteur DOM entre le navigateur autonome et l'extension."""

from pathlib import Path

from metiquo.providers.stake_dom import EXTRACT_DOM

HEADER = "// Generated from python/metiquo/providers/stake_dom.py; checked by tests.\n"


def extension_source() -> str:
    return HEADER + "globalThis.metiquoExtractStake = " + EXTRACT_DOM + ";\n"


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    (root / "browser/stake-reader/extract-dom.js").write_text(extension_source(), encoding="utf-8")
