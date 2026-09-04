"""Primitives de validation communes aux contrats publics."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Un instant de contrat doit inclure un fuseau horaire")
    return value.astimezone(UTC)


class ContractModel(BaseModel):
    """Base stricte, immuable et indépendante de la persistance."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        strict=True,
    )


UtcDateTime = Annotated[datetime, AfterValidator(_normalize_utc)]
NonEmptyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
VersionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
ProbabilityValue = Annotated[
    Decimal,
    Field(ge=Decimal(0), le=Decimal(1), allow_inf_nan=False),
]
NonNegativeDecimal = Annotated[
    Decimal,
    Field(ge=Decimal(0), allow_inf_nan=False),
]
PositiveDecimal = Annotated[
    Decimal,
    Field(gt=Decimal(0), allow_inf_nan=False),
]
FiniteDecimal = Annotated[
    Decimal,
    Field(allow_inf_nan=False),
]
SignedUnitValue = Annotated[
    Decimal,
    Field(ge=Decimal(-1), le=Decimal(1), allow_inf_nan=False),
]
ExpectedValueDecimal = Annotated[
    Decimal,
    Field(ge=Decimal(-1), allow_inf_nan=False),
]
DecimalOddsValue = Annotated[
    Decimal,
    Field(ge=Decimal(1), allow_inf_nan=False),
]
