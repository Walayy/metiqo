"""Frontières de mode et de chemins avant toute lecture de données privées."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine

from metiquo.operations.backup import BackupService
from metiquo.operations.backup_repository import safe_child
from metiquo.operations.backup_tools import BackupError
from tests.api.test_api import build_test_settings


def test_mock_backup_is_rejected_before_accessing_postgresql() -> None:
    engine = create_engine("sqlite://")
    with pytest.raises(BackupError, match="BACKUP_REAL_MODE_REQUIRED"):
        BackupService(engine, build_test_settings()).run()
    engine.dispose()


def test_backup_paths_reject_parent_escape_and_root_deletion(tmp_path: Path) -> None:
    for path in (tmp_path, tmp_path / ".." / "private", tmp_path / "raw" / ".." / "secret"):
        with pytest.raises(BackupError):
            safe_child(tmp_path, path)
