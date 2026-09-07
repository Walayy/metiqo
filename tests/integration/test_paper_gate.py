"""Le gate P7 émet une preuve technique honnête depuis une base vide."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from metiquo.paper.creation import fingerprint


@pytest.mark.integration
def test_paper_gate_emits_an_auditable_fixture_report(postgresql_url: str, tmp_path: Path) -> None:
    output = tmp_path / "paper-example.json"
    result = subprocess.run(
        [
            sys.executable,
            "infra/scripts/demo_paper_gate.py",
            "--database-url",
            postgresql_url,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["ok"] is True and summary["database"] == "ephemeral"
    example = json.loads(output.read_text(encoding="utf-8"))
    assert example["fixture"] is True and example["financialPerformanceValidated"] is False
    assert fingerprint(example["inputEvidence"]) == example["inputFingerprint"]
    assert (
        fingerprint({"inputs": example["inputEvidence"], "report": example["document"]})
        == example["reportFingerprint"]
    )
    assert example["document"]["estimates"]["profit_loss"]["value"] == "-10"
    assert example["document"]["audit"]["oddsHistory"]
