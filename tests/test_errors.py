"""Tests des erreurs métier structurées."""

from types import MappingProxyType

from metiquo.foundation.errors import BusinessError, ErrorCode


def test_business_error_has_stable_serializable_shape() -> None:
    error = BusinessError(
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        "La source est temporairement indisponible",
        context={"provider": "oracles_elixir", "attempt": 2},
        retryable=True,
    )

    assert error.to_dict() == {
        "code": "DEPENDENCY_UNAVAILABLE",
        "message": "La source est temporairement indisponible",
        "context": {"provider": "oracles_elixir", "attempt": 2},
        "retryable": True,
    }
    assert isinstance(error.context, MappingProxyType)
