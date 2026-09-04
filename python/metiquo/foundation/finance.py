"""Valeurs financières exactes fondées exclusivement sur Decimal."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

type DecimalInput = Decimal | int | str


def _as_decimal(value: object, *, label: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise TypeError(f"{label} refuse les booléens et les float")
    if not isinstance(value, (Decimal, int, str)):
        raise TypeError(f"{label} exige Decimal, int ou str")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{label} doit être un nombre décimal valide") from error
    if not parsed.is_finite():
        raise ValueError(f"{label} doit être fini")
    return parsed


@dataclass(frozen=True, slots=True, order=True)
class Probability:
    """Probabilité fermée sur l'intervalle [0, 1]."""

    value: Decimal

    def __post_init__(self) -> None:
        parsed = _as_decimal(self.value, label="Probability")
        if not Decimal(0) <= parsed <= Decimal(1):
            raise ValueError("Probability doit être comprise entre 0 et 1")
        object.__setattr__(self, "value", parsed)

    @classmethod
    def parse(cls, value: object) -> "Probability":
        return cls(_as_decimal(value, label="Probability"))


@dataclass(frozen=True, slots=True, order=True)
class DecimalOdds:
    """Cote décimale finie supérieure ou égale à 1."""

    value: Decimal

    def __post_init__(self) -> None:
        parsed = _as_decimal(self.value, label="DecimalOdds")
        if parsed < Decimal(1):
            raise ValueError("DecimalOdds doit être supérieure ou égale à 1")
        object.__setattr__(self, "value", parsed)

    @classmethod
    def parse(cls, value: object) -> "DecimalOdds":
        return cls(_as_decimal(value, label="DecimalOdds"))


@dataclass(frozen=True, slots=True)
class Money:
    """Montant exact associé à une devise ISO alphabétique."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        amount = _as_decimal(self.amount, label="Money")
        currency = self.currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
            raise ValueError("Money exige un code devise ISO alphabétique de trois lettres")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency)

    @classmethod
    def parse(cls, amount: object, currency: str) -> "Money":
        return cls(_as_decimal(amount, label="Money"), currency)

    def __add__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def scaled_by(self, factor: DecimalInput) -> "Money":
        return Money(self.amount * _as_decimal(factor, label="Facteur monétaire"), self.currency)

    def _require_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError("Les opérations Money exigent la même devise")
