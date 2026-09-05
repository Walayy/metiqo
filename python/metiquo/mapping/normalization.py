"""Normalisation fermée des seules variations typographiques de noms."""

import unicodedata
from typing import Final

NORMALIZATION_VERSION: Final = "entity-name-typography-v1"


def normalize_entity_name(value: str) -> str:
    """Normaliser casse, espaces et ponctuation sans modifier les mots du nom."""

    compatible = unicodedata.normalize("NFKC", value).casefold()
    characters: list[str] = []
    for character in compatible:
        if character.isspace() or unicodedata.category(character).startswith("P"):
            characters.append(" ")
            continue
        if unicodedata.category(character).startswith("C"):
            raise ValueError("un nom d'entité ne peut pas contenir de caractère de contrôle")
        characters.append(character)
    normalized = " ".join("".join(characters).split())
    if not normalized:
        raise ValueError("un nom d'entité doit contenir au moins un caractère significatif")
    return unicodedata.normalize("NFKC", normalized)


def typographically_equal(left: str, right: str) -> bool:
    """Comparer uniquement les formes normalisées exactes, sans score de similarité."""

    return normalize_entity_name(left) == normalize_entity_name(right)
