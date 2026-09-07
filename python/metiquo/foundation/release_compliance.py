"""Vérification des preuves approuvées manuellement avant ouverture du produit."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

type ReleaseAudience = Literal["personal", "public", "commercial"]
type GateStatus = Literal["NO-GO", "GO"]
type Reviewer = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ManualReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_by: Reviewer = Field(alias="approvedBy")
    reviewed_at: datetime = Field(alias="reviewedAt")
    expires_at: datetime = Field(alias="expiresAt")
    scope: list[Literal["public", "commercial"]] = Field(min_length=1)
    proof: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def verify_release(
    audience: ReleaseAudience,
    gates: dict[str, GateStatus],
    evidence_file: Path | None,
    *,
    now: datetime | None = None,
) -> None:
    """Une empreinte vérifie l'intégrité, jamais la validité juridique du document."""
    if set(gates) != {"OE-COMMERCIAL", "RIOT-PRODUCT"}:
        raise ValueError("Publication refusée : portes absentes, état NO-GO")
    if audience != "personal" and any(status != "GO" for status in gates.values()):
        raise ValueError("Publication refusée : portes de conformité NO-GO")
    granted = {gate for gate, status in gates.items() if status == "GO"}
    if not granted:
        return
    try:
        if evidence_file is None or evidence_file.stat().st_size > 64 * 1024:
            raise ValueError("preuve absente ou manifeste trop grand")
        reviews = TypeAdapter(dict[str, ManualReview]).validate_json(evidence_file.read_bytes())
        if set(reviews) != set(gates):
            raise ValueError("preuve incomplète")
        instant = now or datetime.now(UTC)
        directory = evidence_file.resolve().parent
        for gate in granted:
            review = reviews[gate]
            if (
                review.reviewed_at.tzinfo is None
                or review.expires_at.tzinfo is None
                or not review.reviewed_at <= instant < review.expires_at
                or (audience != "personal" and audience not in review.scope)
            ):
                raise ValueError("preuve périmée ou hors périmètre")
            proof = (directory / review.proof).resolve()
            if not proof.is_relative_to(directory) or not proof.is_file():
                raise ValueError("preuve inaccessible")
            if not 0 < proof.stat().st_size <= 10 * 1024 * 1024:
                raise ValueError("preuve vide ou trop grande")
            if hashlib.sha256(proof.read_bytes()).hexdigest() != review.sha256:
                raise ValueError("preuve altérée")
    except (OSError, ValueError) as error:
        raise ValueError("Publication refusée : preuve manuelle absente ou invalide") from error
