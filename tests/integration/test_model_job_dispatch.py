"""Le point d'entrée de production déclenche un entraînement observable en file."""

from pathlib import Path
from uuid import UUID

import pytest
from alembic import command

from metiquo.api.app import create_app
from metiquo.worker.handlers import default_handlers
from metiquo.worker.queue import PostgresJobQueue
from metiquo.worker.runner import PostgresJobRunner
from tests.integration.test_migrations import alembic_config
from tests.integration.test_model_training_workflow import _seed_training_dataset
from tests.integration.test_real_admin_api import ReadyProbe, _settings
from tests.integration.test_real_model_api import _request

FIXTURE_COMMIT = "a" * 40


@pytest.mark.integration
def test_default_real_training_endpoint_queues_one_idempotent_job_without_running_ml(
    postgresql_url: str,
    tmp_path: Path,
) -> None:
    command.upgrade(alembic_config(postgresql_url), "head")
    settings = _settings(postgresql_url, "real").model_copy(
        update={
            "object_store_root": tmp_path,
            "app_code_commit": FIXTURE_COMMIT,
        }
    )
    app = create_app(settings=settings, readiness_probe=ReadyProbe())
    engine = app.state.real_admin_engine
    try:
        responses = [
            _request(
                app,
                "POST",
                "/api/v1/admin/models/train",
                headers={"Idempotency-Key": "qa005-model-dispatch", "X-Metiquo-CSRF": "1"},
                json={"gameTitle": "lol", "marketType": "MATCH_WINNER"},
            )
            for _ in range(2)
        ]
        assert all(response.status_code == 202 for response in responses)
        first, second = [response.json()["data"] for response in responses]
        assert first["jobId"] == second["jobId"]
        assert first["status"] == "queued"
        job = PostgresJobQueue(engine).get(UUID(first["jobId"]))
        assert job is not None and job.job_type == "model.train"
        assert job.payload == {
            "gameTitle": "lol",
            "marketType": "MATCH_WINNER",
            "codeCommit": FIXTURE_COMMIT,
        }
        assert "model.train" in default_handlers(engine, settings)
        detail = _request(app, "GET", f"/api/v1/admin/jobs/{job.job_id}")
        assert detail.status_code == 200
        assert detail.json()["data"]["jobId"] == first["jobId"]
        runner = PostgresJobRunner(
            PostgresJobQueue(engine), default_handlers(engine, settings), owner="qa005-empty"
        )
        assert runner.run_once()
        failed = _request(app, "GET", f"/api/v1/admin/jobs/{job.job_id}").json()["data"]
        assert failed["status"] == "failed"
        assert failed["errorCode"] == "INVALID_STATE"
        assert failed["modelVersionId"] is None
    finally:
        engine.dispose()


@pytest.mark.integration
@pytest.mark.parametrize("cancel_before_publication", [False, True])
def test_production_worker_trains_persisted_data_and_honours_cancellation_before_publication(
    postgresql_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cancel_before_publication: bool,
) -> None:
    from metiquo.models import training

    command.upgrade(alembic_config(postgresql_url), "head")
    settings = _settings(postgresql_url, "real").model_copy(
        update={"object_store_root": tmp_path, "app_code_commit": FIXTURE_COMMIT}
    )
    app = create_app(settings=settings, readiness_probe=ReadyProbe())
    engine = app.state.real_admin_engine
    try:
        dataset_id = _seed_training_dataset(engine)
        accepted = _request(
            app,
            "POST",
            "/api/v1/admin/models/train",
            headers={"Idempotency-Key": "qa005-production-training", "X-Metiquo-CSRF": "1"},
            json={"gameTitle": "lol", "marketType": "MATCH_WINNER"},
        )
        assert accepted.status_code == 202
        job_id = UUID(accepted.json()["data"]["jobId"])
        queue = PostgresJobQueue(engine)
        runner = PostgresJobRunner(queue, default_handlers(engine, settings), owner="qa005-model")
        if cancel_before_publication:
            original = training.build_reproducible_artifact

            def cancel_after_artifact(*args: object, **kwargs: object) -> object:
                artifact = original(*args, **kwargs)  # type: ignore[arg-type]
                runner.request_stop()
                return artifact

            monkeypatch.setattr(training, "build_reproducible_artifact", cancel_after_artifact)
        assert runner.run_once()
        job = queue.get(job_id)
        assert job is not None
        detail = _request(app, "GET", f"/api/v1/admin/jobs/{job_id}").json()["data"]
        models = _request(app, "GET", "/api/v1/models").json()["data"]
        assert not any(model["status"] == "champion" for model in models)
        if cancel_before_publication:
            assert job.status == "cancelled"
            assert detail["modelVersionId"] is None
            assert models == []
        else:
            assert job.status == "succeeded", job.error_code
            assert job.result["datasetId"] == str(dataset_id)
            assert job.result["codeCommit"] == FIXTURE_COMMIT
            assert detail["modelVersionId"] == job.result["modelVersionId"]
            assert len(models) == 1
            assert models[0]["codeCommit"] == FIXTURE_COMMIT
            assert models[0]["status"] in {"candidate", "blocked"}
            assert not runner.run_once()
    finally:
        engine.dispose()
