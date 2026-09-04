"""Erreurs métier structurées et sérialisables."""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType

type ErrorContextValue = str | int | bool | None


class ErrorCode(StrEnum):
    """Codes stables utilisables par les API, jobs et audits."""

    INVALID_INPUT = "INVALID_INPUT"
    INVALID_STATE = "INVALID_STATE"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


class BusinessError(Exception):
    """Erreur attendue avec code, contexte sûr et retryability explicite."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        context: Mapping[str, ErrorContextValue] | None = None,
        retryable: bool = False,
    ) -> None:
        if not message.strip():
            raise ValueError("Une erreur métier exige un message lisible")
        super().__init__(message)
        self.code = code
        self.message = message
        self.context: Mapping[str, ErrorContextValue] = MappingProxyType(dict(context or {}))
        self.retryable = retryable

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "context": dict(self.context),
            "retryable": self.retryable,
        }
