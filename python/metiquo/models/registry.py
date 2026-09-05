"""Registre des versions de modèles et artefacts adressés par contenu."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, RowMapping, Table, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from metiquo.db.ml_models import CalibratorArtifact as CalibratorArtifactRow
from metiquo.db.ml_models import ModelVersion as ModelVersionRow
from metiquo.db.ml_models import TrainingDataset
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime
from metiquo.ingestion.object_store import ObjectCollisionError, ObjectStore
from metiquo.models.evaluation import EvaluationReport
from metiquo.models.uncertainty import UncertaintyArtifact

MODEL_GAME = "lol"
MODEL_MARKET = "game_winner"
CANDIDATE = "candidate"
CHAMPION = "champion"
RETIRED = "retired"
BLOCKED = "blocked"
MODEL_STATUSES = frozenset({CANDIDATE, CHAMPION, RETIRED, BLOCKED})
_COMMIT = re.compile(r"^[0-9a-f]{7,64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ModelArtifactChecksumError(RuntimeError):
    """Le contenu chargé ne correspond pas à la référence du registre."""


class ChampionAlreadyExistsError(RuntimeError):
    """Un champion existe déjà sur le même jeu, marché et segment."""


@dataclass(frozen=True, slots=True)
class ModelRegistration:
    algorithm: str
    hyperparameters: Mapping[str, object]
    segment: str = "global"
    artifact_format: str = "application/octet-stream"
    status: str = CANDIDATE
    registered_by: str = "system"
    reason: str = "validated candidate registration"
    code_commit: str = ""
    game: str = MODEL_GAME
    market: str = MODEL_MARKET

    def __post_init__(self) -> None:
        object.__setattr__(self, "hyperparameters", MappingProxyType(dict(self.hyperparameters)))
        if self.game != MODEL_GAME or self.market != MODEL_MARKET:
            raise ValueError("seul lol/game_winner est pris en charge")
        if self.status not in MODEL_STATUSES:
            raise ValueError("statut de modèle inconnu")
        if any(
            not value.strip()
            for value in (
                self.algorithm,
                self.segment,
                self.artifact_format,
                self.registered_by,
                self.reason,
            )
        ):
            raise ValueError("les métadonnées textuelles du modèle sont requises")
        if _COMMIT.fullmatch(self.code_commit) is None:
            raise ValueError("code_commit doit être un hash git hexadécimal")


@dataclass(frozen=True, slots=True)
class ModelArtifactReference:
    year: int
    object_key: str
    sha256: str
    size_bytes: int
    artifact_format: str

    def __post_init__(self) -> None:
        if self.year < 2014 or _SHA256.fullmatch(self.sha256) is None:
            raise ValueError("référence d'artefact invalide")
        if self.size_bytes < 1 or not self.object_key.strip() or not self.artifact_format.strip():
            raise ValueError("métadonnées d'artefact invalides")
        expected_key = f"year={self.year}/sha256={self.sha256}/source.bin"
        if self.object_key != expected_key:
            raise ValueError("la clé d'artefact ne correspond pas à son adresse")


class ModelArtifactStore:
    """Adapter l'ObjectStore immuable aux binaires de modèles."""

    def __init__(self, store: ObjectStore) -> None:
        self._store = store

    def put(
        self,
        payload: bytes,
        *,
        year: int,
        artifact_format: str,
        code_commit: str,
    ) -> ModelArtifactReference:
        if not payload:
            raise ValueError("un artefact modèle ne peut pas être vide")
        if not artifact_format.strip() or _COMMIT.fullmatch(code_commit) is None:
            raise ValueError("format ou commit d'artefact invalide")
        expected_hash = hashlib.sha256(payload).hexdigest()
        stored = self._store.put_source(
            year=year,
            chunks=(payload,),
            source_kind="bin",
            manifest={
                "artifactFormat": artifact_format,
                "codeCommit": code_commit,
                "kind": "model_artifact",
                "sha256": expected_hash,
                "sizeBytes": len(payload),
            },
        )
        if stored.sha256 != expected_hash:
            raise ModelArtifactChecksumError("le hash retourné par l'ObjectStore est incorrect")
        return ModelArtifactReference(
            year=year,
            object_key=stored.object_key,
            sha256=stored.sha256,
            size_bytes=len(payload),
            artifact_format=artifact_format,
        )

    def load(self, reference: ModelArtifactReference) -> bytes:
        try:
            with self._store.open_source(year=reference.year, sha256=reference.sha256) as stream:
                payload = stream.read()
        except ObjectCollisionError as error:
            raise ModelArtifactChecksumError(
                "le checksum physique de l'artefact est invalide"
            ) from error
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != reference.sha256 or len(payload) != reference.size_bytes:
            raise ModelArtifactChecksumError(
                "le checksum ou la taille de l'artefact chargé ne correspond pas au registre"
            )
        return payload


@dataclass(frozen=True, slots=True)
class ModelVersion:
    model_version_id: UUID
    game: str
    market: str
    segment: str
    algorithm: str
    hyperparameters: Mapping[str, object]
    feature_set_version: str
    dataset_id: UUID
    dataset_hash: str
    training_cutoff_min: datetime
    training_cutoff_max: datetime
    evaluation_report: Mapping[str, object]
    evaluation_report_fingerprint: str
    calibrator_artifact_id: UUID
    uncertainty_artifact_id: UUID
    uncertainty_fingerprint: str
    artifact: ModelArtifactReference
    code_commit: str
    status: str
    registered_by: str
    registered_at: datetime
    registration_reason: str
    status_changed_by: str
    status_changed_at: datetime
    status_reason: str
    registration_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "hyperparameters", MappingProxyType(dict(self.hyperparameters)))
        object.__setattr__(
            self, "evaluation_report", MappingProxyType(dict(self.evaluation_report))
        )
        object.__setattr__(
            self, "training_cutoff_min", normalize_utc_datetime(self.training_cutoff_min)
        )
        object.__setattr__(
            self, "training_cutoff_max", normalize_utc_datetime(self.training_cutoff_max)
        )
        object.__setattr__(self, "registered_at", normalize_utc_datetime(self.registered_at))
        object.__setattr__(
            self, "status_changed_at", normalize_utc_datetime(self.status_changed_at)
        )


class ModelRegistry:
    """Enregistrer et charger les versions sans faire confiance au disque."""

    def __init__(
        self,
        *,
        engine: Engine,
        artifacts: ModelArtifactStore,
        clock: Clock | None = None,
    ) -> None:
        self._engine = engine
        self._artifacts = artifacts
        self._clock = clock or SystemClock()

    def register(
        self,
        registration: ModelRegistration,
        *,
        evaluation: EvaluationReport,
        uncertainty: UncertaintyArtifact,
        artifact_payload: bytes,
    ) -> ModelVersion:
        datasets = cast(Table, TrainingDataset.__table__)
        calibrators = cast(Table, CalibratorArtifactRow.__table__)
        with self._engine.connect() as connection:
            dataset = (
                connection.execute(
                    select(
                        datasets.c.id,
                        datasets.c.dataset_hash,
                        datasets.c.feature_set_version,
                        datasets.c.cutoff_min,
                        datasets.c.cutoff_max,
                    ).where(datasets.c.id == evaluation.dataset_id)
                )
                .mappings()
                .one_or_none()
            )
            calibrator = (
                connection.execute(
                    select(
                        calibrators.c.dataset_id,
                        calibrators.c.artifact_fingerprint,
                    ).where(calibrators.c.id == evaluation.calibrator_artifact_id)
                )
                .mappings()
                .one_or_none()
            )
        if dataset is None or calibrator is None:
            raise ValueError("dataset ou calibrateur du modèle introuvable")
        if calibrator["dataset_id"] != evaluation.dataset_id:
            raise ValueError("le calibrateur n'appartient pas au dataset évalué")
        if (
            evaluation.uncertainty_artifact_id != uncertainty.artifact_id
            or uncertainty.calibrator_artifact_id != evaluation.calibrator_artifact_id
            or calibrator["artifact_fingerprint"] != uncertainty.calibrator.artifact_fingerprint
        ):
            raise ValueError("le rapport et l'incertitude ne correspondent pas")
        if _SHA256.fullmatch(uncertainty.artifact_fingerprint) is None:
            raise ValueError("fingerprint d'incertitude invalide")
        registered_at = self._clock.now().value
        artifact = self._artifacts.put(
            artifact_payload,
            year=registered_at.year,
            artifact_format=registration.artifact_format,
            code_commit=registration.code_commit,
        )
        content = _registration_document(
            registration,
            dataset=dataset,
            evaluation=evaluation,
            uncertainty=uncertainty,
            artifact=artifact,
        )
        fingerprint = _content_hash(content)
        model_version_id = uuid5(NAMESPACE_URL, f"metiquo:model-version:{fingerprint}")
        models = cast(Table, ModelVersionRow.__table__)
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    insert(models)
                    .values(
                        id=model_version_id,
                        game=registration.game,
                        market=registration.market,
                        segment=registration.segment,
                        algorithm=registration.algorithm,
                        hyperparameters=dict(registration.hyperparameters),
                        feature_set_version=cast(str, dataset["feature_set_version"]),
                        dataset_id=cast(UUID, dataset["id"]),
                        dataset_hash=cast(str, dataset["dataset_hash"]),
                        training_cutoff_min=cast(datetime, dataset["cutoff_min"]),
                        training_cutoff_max=cast(datetime, dataset["cutoff_max"]),
                        evaluation_report=evaluation.document(),
                        evaluation_report_fingerprint=evaluation.report_fingerprint,
                        calibrator_artifact_id=evaluation.calibrator_artifact_id,
                        uncertainty_artifact_id=uncertainty.artifact_id,
                        uncertainty_fingerprint=uncertainty.artifact_fingerprint,
                        artifact_object_year=artifact.year,
                        artifact_object_key=artifact.object_key,
                        artifact_hash=artifact.sha256,
                        artifact_size_bytes=artifact.size_bytes,
                        artifact_format=artifact.artifact_format,
                        code_commit=registration.code_commit,
                        status=registration.status,
                        registered_by=registration.registered_by,
                        registered_at=registered_at,
                        registration_reason=registration.reason,
                        status_changed_by=registration.registered_by,
                        status_changed_at=registered_at,
                        status_reason=registration.reason,
                        registration_fingerprint=fingerprint,
                    )
                    .on_conflict_do_nothing(index_elements=[models.c.registration_fingerprint])
                )
        except IntegrityError as error:
            if "uq_ml_model_versions_champion_scope" in str(error):
                raise ChampionAlreadyExistsError(
                    "un champion existe déjà pour ce jeu, marché et segment"
                ) from error
            raise
        stored = self.get_by_fingerprint(fingerprint)
        if stored is None:
            raise RuntimeError("la version de modèle n'a pas été enregistrée")
        return stored

    def get(self, model_version_id: UUID) -> ModelVersion | None:
        models = cast(Table, ModelVersionRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(select(models).where(models.c.id == model_version_id))
                .mappings()
                .one_or_none()
            )
        return _stored_model(row) if row is not None else None

    def get_by_fingerprint(self, fingerprint: str) -> ModelVersion | None:
        models = cast(Table, ModelVersionRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(models).where(models.c.registration_fingerprint == fingerprint)
                )
                .mappings()
                .one_or_none()
            )
        return _stored_model(row) if row is not None else None

    def current_champion(
        self,
        *,
        game: str = MODEL_GAME,
        market: str = MODEL_MARKET,
        segment: str = "global",
    ) -> ModelVersion | None:
        models = cast(Table, ModelVersionRow.__table__)
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    select(models).where(
                        models.c.game == game,
                        models.c.market == market,
                        models.c.segment == segment,
                        models.c.status == CHAMPION,
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _stored_model(row) if row is not None else None

    def load_artifact(self, version: ModelVersion) -> bytes:
        return self._artifacts.load(version.artifact)


def _registration_document(
    registration: ModelRegistration,
    *,
    dataset: RowMapping,
    evaluation: EvaluationReport,
    uncertainty: UncertaintyArtifact,
    artifact: ModelArtifactReference,
) -> dict[str, object]:
    return {
        "algorithm": registration.algorithm,
        "artifact": {
            "format": artifact.artifact_format,
            "object_key": artifact.object_key,
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "year": artifact.year,
        },
        "calibrator_artifact_id": str(evaluation.calibrator_artifact_id),
        "code_commit": registration.code_commit,
        "dataset_hash": cast(str, dataset["dataset_hash"]),
        "dataset_id": str(cast(UUID, dataset["id"])),
        "evaluation_report_fingerprint": evaluation.report_fingerprint,
        "feature_set_version": cast(str, dataset["feature_set_version"]),
        "game": registration.game,
        "hyperparameters": dict(registration.hyperparameters),
        "initial_status": registration.status,
        "market": registration.market,
        "reason": registration.reason,
        "registered_by": registration.registered_by,
        "segment": registration.segment,
        "training_cutoff_max": cast(datetime, dataset["cutoff_max"]).isoformat(),
        "training_cutoff_min": cast(datetime, dataset["cutoff_min"]).isoformat(),
        "uncertainty_artifact_id": str(uncertainty.artifact_id),
        "uncertainty_fingerprint": uncertainty.artifact_fingerprint,
    }


def _stored_model(row: RowMapping) -> ModelVersion:
    return ModelVersion(
        model_version_id=cast(UUID, row["id"]),
        game=cast(str, row["game"]),
        market=cast(str, row["market"]),
        segment=cast(str, row["segment"]),
        algorithm=cast(str, row["algorithm"]),
        hyperparameters=cast(Mapping[str, object], row["hyperparameters"]),
        feature_set_version=cast(str, row["feature_set_version"]),
        dataset_id=cast(UUID, row["dataset_id"]),
        dataset_hash=cast(str, row["dataset_hash"]),
        training_cutoff_min=cast(datetime, row["training_cutoff_min"]),
        training_cutoff_max=cast(datetime, row["training_cutoff_max"]),
        evaluation_report=cast(Mapping[str, object], row["evaluation_report"]),
        evaluation_report_fingerprint=cast(str, row["evaluation_report_fingerprint"]),
        calibrator_artifact_id=cast(UUID, row["calibrator_artifact_id"]),
        uncertainty_artifact_id=cast(UUID, row["uncertainty_artifact_id"]),
        uncertainty_fingerprint=cast(str, row["uncertainty_fingerprint"]),
        artifact=ModelArtifactReference(
            year=cast(int, row["artifact_object_year"]),
            object_key=cast(str, row["artifact_object_key"]),
            sha256=cast(str, row["artifact_hash"]),
            size_bytes=cast(int, row["artifact_size_bytes"]),
            artifact_format=cast(str, row["artifact_format"]),
        ),
        code_commit=cast(str, row["code_commit"]),
        status=cast(str, row["status"]),
        registered_by=cast(str, row["registered_by"]),
        registered_at=cast(datetime, row["registered_at"]),
        registration_reason=cast(str, row["registration_reason"]),
        status_changed_by=cast(str, row["status_changed_by"]),
        status_changed_at=cast(datetime, row["status_changed_at"]),
        status_reason=cast(str, row["status_reason"]),
        registration_fingerprint=cast(str, row["registration_fingerprint"]),
    )


def _content_hash(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()
