"""Résolution explicite des identités fournisseurs vers le canonique."""

from metiquo.mapping.normalization import (
    NORMALIZATION_VERSION,
    normalize_entity_name,
    typographically_equal,
)

__all__ = [
    "NORMALIZATION_VERSION",
    "normalize_entity_name",
    "typographically_equal",
]
