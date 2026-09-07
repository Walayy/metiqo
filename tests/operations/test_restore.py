"""Une restauration de test ne doit jamais remplacer une cible existante."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from metiquo.config import AppEnvironment
from metiquo.contracts.enums import DataMode
from metiquo.operations.backup_tools import BackupError
from metiquo.operations.restore import RestoreRequest, RestoreService
from tests.api.test_api import build_test_settings


def test_restore_rejects_production_mock_and_existing_targets_before_sql(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")
    base = build_test_settings().model_copy(
        update={
            "app_data_mode": DataMode.REAL,
            "app_env": AppEnvironment.TEST,
            "object_store_root": tmp_path / "source",
            "backup_root": tmp_path / "backups",
        }
    )
    request = RestoreRequest(uuid4(), "a" * 64, "metiquo_restore_test", tmp_path / "restored")
    for settings, code in (
        (base.model_copy(update={"app_data_mode": DataMode.MOCK}), "RESTORE_REAL_MODE_REQUIRED"),
        (
            base.model_copy(update={"app_env": AppEnvironment.PRODUCTION}),
            "RESTORE_TEST_ENV_REQUIRED",
        ),
    ):
        with pytest.raises(BackupError, match=code):
            RestoreService(engine, settings).run(request)
    with pytest.raises(BackupError, match="RESTORE_TARGET_NAME_INVALID"):
        RestoreService(engine, base).run(
            RestoreRequest(uuid4(), "a" * 64, "metiquo", tmp_path / "restored")
        )
    request.target_root.mkdir()
    (request.target_root / "keep.txt").write_text("existing user data")
    with pytest.raises(BackupError, match="RESTORE_TARGET_EXISTS"):
        RestoreService(engine, base).run(request)
    assert (request.target_root / "keep.txt").read_text() == "existing user data"
    engine.dispose()
