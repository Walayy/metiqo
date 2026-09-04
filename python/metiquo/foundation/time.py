"""Instants UTC et horloges injectables."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


def normalize_utc_datetime(value: datetime) -> datetime:
    """Refuser un instant naïf et normaliser un instant conscient en UTC."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Un datetime interne doit être conscient de son fuseau")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True, order=True)
class UtcInstant:
    """Valeur immuable garantissant un datetime conscient normalisé en UTC."""

    value: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", normalize_utc_datetime(self.value))

    @classmethod
    def parse(cls, value: str) -> "UtcInstant":
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as error:
            raise ValueError("Instant ISO 8601 invalide") from error
        return cls(parsed)

    def isoformat(self) -> str:
        return self.value.isoformat().replace("+00:00", "Z")

    def __repr__(self) -> str:
        return f"UtcInstant({self.isoformat()!r})"


class Clock(Protocol):
    """Source injectable de l'instant courant."""

    def now(self) -> UtcInstant: ...


class SystemClock:
    """Horloge de production utilisant le temps système en UTC."""

    def now(self) -> UtcInstant:
        return UtcInstant(datetime.now(UTC))


class FixedClock:
    """Horloge déterministe destinée aux tests et aux rejeux."""

    def __init__(self, instant: UtcInstant) -> None:
        self._instant = instant

    def now(self) -> UtcInstant:
        return self._instant
