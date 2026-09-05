"""Propriétés de la normalisation sûre des noms fournisseurs."""

import unicodedata

import pytest

from metiquo.mapping import NORMALIZATION_VERSION, normalize_entity_name, typographically_equal


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("  Gen.G  ", "gen g"),
        ("GEN—G", "gen g"),
        ("Karmine\u00a0Corp", "karmine corp"),
        ("Team__Liquid", "team liquid"),
        ("Bilibili\uff0fGaming", "bilibili gaming"),
    ),
)
def test_case_spaces_and_punctuation_follow_the_closed_rules(raw: str, expected: str) -> None:
    assert normalize_entity_name(raw) == expected
    assert normalize_entity_name(expected) == expected


def test_canonically_equivalent_accents_match_without_transliteration() -> None:
    composed = "Équipe Élite"
    decomposed = unicodedata.normalize("NFD", composed)

    assert typographically_equal(composed, decomposed)
    assert normalize_entity_name(composed) == "équipe élite"
    assert not typographically_equal(composed, "Equipe Elite")


@pytest.mark.parametrize(
    ("canonical", "related_but_distinct"),
    (
        ("Team Liquid", "Team Liquid Honda"),
        ("Dplus", "Dplus KIA"),
        ("Karmine Corp", "Karmine Corp Blue"),
        ("Gen.G", "Gen.G Academy"),
        ("Aurora", "Aurora 05"),
        ("T1", "T1A"),
    ),
)
def test_sponsors_academies_and_close_names_remain_distinct(
    canonical: str,
    related_but_distinct: str,
) -> None:
    assert normalize_entity_name(canonical) != normalize_entity_name(related_but_distinct)
    assert not typographically_equal(canonical, related_but_distinct)


@pytest.mark.parametrize("raw", ("", "  ", "...", "\u200b", "T1\u200bAcademy"))
def test_empty_or_invisible_control_names_are_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_entity_name(raw)


def test_rule_version_is_stable_and_explicit() -> None:
    assert NORMALIZATION_VERSION == "entity-name-typography-v1"
