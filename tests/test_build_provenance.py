"""La provenance d'une image ne peut désigner un checkout modifié."""

import subprocess
from pathlib import Path

import pytest
from infra.scripts.build_images import code_revision

from tests.test_config import build_settings


def test_build_revision_requires_a_clean_commit_and_checks_untracked_files(tmp_path: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    assert code_revision(tmp_path) is None
    git("init", "--quiet")
    git("config", "user.email", "fixture@example.invalid")
    git("config", "user.name", "Build fixture")
    source = tmp_path / "source.py"
    source.write_text("VERSION = 1\n")
    git("add", "source.py")
    git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture")
    revision = git("rev-parse", "HEAD")
    assert code_revision(tmp_path) == revision
    source.write_text("VERSION = 2\n")
    assert code_revision(tmp_path) is None
    source.write_text("VERSION = 1\n")
    (tmp_path / "new.py").write_text("NEW = True\n")
    assert code_revision(tmp_path) is None


@pytest.mark.parametrize("value", [None, "", "a" * 40, "b" * 64])
def test_runtime_revision_allows_unlabelled_development_and_full_hashes(value: str | None) -> None:
    assert build_settings(app_code_commit=value).app_code_commit == (value or None)


@pytest.mark.parametrize("value", ["abcdef1", "a" * 39, "A" * 40, "main", " " * 40])
def test_runtime_revision_rejects_ambiguous_identifiers(value: str) -> None:
    with pytest.raises(ValueError):
        build_settings(app_code_commit=value)
