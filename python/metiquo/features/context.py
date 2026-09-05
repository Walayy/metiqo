"""Contexte compétition et calendrier avec provenance OE obligatoire."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from metiquo.features.registry import FeatureDefinitionSpec, FeatureValue
from metiquo.features.temporal import AsOfGameBatch, FeatureCutoff, HistoricalGame
from metiquo.foundation.time import normalize_utc_datetime

type ContextScalar = str | int | bool | UUID
type ContextSource = Literal["canonical_oe", "unknown"]

_QUANTUM = Decimal("0.000001")
_CODE_VERSION = "competition-context-v1"


@dataclass(frozen=True, slots=True)
class ContextField:
    """Valeur OE prouvée ou absence explicite, sans troisième voie."""

    value: ContextScalar | None = None
    source: ContextSource = "unknown"
    source_revision_id: UUID | None = None
    known_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.source == "unknown":
            if (
                self.value is not None
                or self.source_revision_id is not None
                or self.known_at is not None
            ):
                raise ValueError("un champ unknown ne peut transporter ni valeur ni provenance")
            return
        if self.source != "canonical_oe":
            raise ValueError("seule la provenance canonical_oe est autorisée")
        if self.value is None or self.source_revision_id is None or self.known_at is None:
            raise ValueError(
                "un champ canonical_oe exige valeur, révision et instant de connaissance"
            )
        object.__setattr__(self, "known_at", normalize_utc_datetime(self.known_at))

    @classmethod
    def oe(
        cls,
        value: ContextScalar,
        *,
        source_revision_id: UUID,
        known_at: datetime,
    ) -> ContextField:
        return cls(value, "canonical_oe", source_revision_id, known_at)

    @property
    def provenance(self) -> str:
        if self.source == "unknown":
            return "unknown"
        return f"canonical_oe:{self.source_revision_id}"


@dataclass(frozen=True, slots=True)
class TargetCompetitionContext:
    competition: ContextField = field(default_factory=ContextField)
    league: ContextField = field(default_factory=ContextField)
    region: ContextField = field(default_factory=ContextField)
    tournament: ContextField = field(default_factory=ContextField)
    stage: ContextField = field(default_factory=ContextField)
    playoffs: ContextField = field(default_factory=ContextField)
    international: ContextField = field(default_factory=ContextField)
    best_of: ContextField = field(default_factory=ContextField)
    patch: ContextField = field(default_factory=ContextField)

    def fields(self) -> Mapping[str, ContextField]:
        return MappingProxyType(
            {
                "best_of": self.best_of,
                "competition": self.competition,
                "international": self.international,
                "league": self.league,
                "patch": self.patch,
                "playoffs": self.playoffs,
                "region": self.region,
                "stage": self.stage,
                "tournament": self.tournament,
            }
        )


@dataclass(frozen=True, slots=True)
class CompetitionContextParameters:
    density_days: int = 14
    version: str = "competition-context-v1"

    def __post_init__(self) -> None:
        if self.density_days <= 0:
            raise ValueError("la fenêtre de densité doit être positive")
        if not self.version.strip():
            raise ValueError("version contexte requise")

    def document(self) -> dict[str, object]:
        return {
            "density_days": self.density_days,
            "external_news": "forbidden",
            "provenance_policy": "canonical_oe_or_unknown",
        }


@dataclass(frozen=True, slots=True)
class TeamScheduleContext:
    team_id: UUID
    rest_days: Decimal | None
    density_window_days: int
    density_games: int
    format_experience_games: int | None


@dataclass(frozen=True, slots=True)
class CompetitionContextFeatureResult:
    parameters_version: str
    cutoff_at: datetime
    max_input_time: datetime | None
    competition: str | None
    league: str | None
    region: str | None
    tournament: str | None
    stage: str | None
    phase: str | None
    best_of: int | None
    patch: str | None
    team_a: TeamScheduleContext
    team_b: TeamScheduleContext
    provenance: Mapping[str, str]

    @property
    def values(self) -> Mapping[str, FeatureValue]:
        values: dict[str, FeatureValue] = {
            "context.best_of": self.best_of,
            "context.best_of_known": self.best_of is not None,
            "context.competition": self.competition,
            "context.competition_known": self.competition is not None,
            "context.league": self.league,
            "context.league_known": self.league is not None,
            "context.patch": self.patch,
            "context.patch_known": self.patch is not None,
            "context.phase": self.phase,
            "context.phase_known": self.phase is not None,
            "context.region": self.region,
            "context.region_known": self.region is not None,
            "context.stage": self.stage,
            "context.stage_known": self.stage is not None,
            "context.tournament": self.tournament,
            "context.tournament_known": self.tournament is not None,
        }
        _write_team_values(values, "team_a", self.team_a)
        _write_team_values(values, "team_b", self.team_b)
        return MappingProxyType(values)


def competition_context_feature_definitions(
    parameters: CompetitionContextParameters | None = None,
) -> tuple[FeatureDefinitionSpec, ...]:
    resolved = parameters or CompetitionContextParameters()
    optional_names = {
        "context.best_of",
        "context.competition",
        "context.league",
        "context.patch",
        "context.phase",
        "context.region",
        "context.stage",
        "context.tournament",
        "context.team_a.format_experience_games",
        "context.team_a.rest_days",
        "context.team_b.format_experience_games",
        "context.team_b.rest_days",
    }
    names = [
        "context.best_of",
        "context.best_of_known",
        "context.competition",
        "context.competition_known",
        "context.league",
        "context.league_known",
        "context.patch",
        "context.patch_known",
        "context.phase",
        "context.phase_known",
        "context.region",
        "context.region_known",
        "context.stage",
        "context.stage_known",
        "context.tournament",
        "context.tournament_known",
    ]
    for team in ("team_a", "team_b"):
        names.extend(
            (
                f"context.{team}.rest_days",
                f"context.{team}.density_games_{resolved.density_days}d",
                f"context.{team}.format_experience_games",
            )
        )
    document = resolved.document()
    return tuple(
        FeatureDefinitionSpec(
            name=name,
            domain="competition_context",
            definition_version=resolved.version,
            parameters=document,
            availability="optional" if name in optional_names else "required",
            code_version=_CODE_VERSION,
        )
        for name in names
    )


class CompetitionContextFeatureCalculator:
    """Combiner contexte OE prouvé et calendrier historique strictement antérieur."""

    def __init__(self, parameters: CompetitionContextParameters | None = None) -> None:
        self._parameters = parameters or CompetitionContextParameters()

    def calculate(
        self,
        batch: AsOfGameBatch,
        *,
        team_a_id: UUID,
        team_b_id: UUID,
        target: TargetCompetitionContext,
    ) -> CompetitionContextFeatureResult:
        if team_a_id == team_b_id:
            raise ValueError("les deux équipes cibles doivent être distinctes")
        cutoff = FeatureCutoff(batch.audit.cutoff_at)
        fields = target.fields()
        audit = cutoff.audit(
            (game.event_time for game in batch.games),
            source_knowledge_times=(
                timestamp
                for timestamp in (
                    *(game.source_processed_at for game in batch.games),
                    *(field.known_at for field in fields.values() if field.known_at is not None),
                )
            ),
        )
        best_of = _optional_int(target.best_of)
        phase, phase_provenance = _phase(target)
        provenance = {
            "context.best_of": target.best_of.provenance,
            "context.competition": target.competition.provenance,
            "context.league": target.league.provenance,
            "context.patch": target.patch.provenance,
            "context.phase": phase_provenance,
            "context.region": target.region.provenance,
            "context.stage": target.stage.provenance,
            "context.tournament": target.tournament.provenance,
        }
        team_a = self._schedule(batch.games, team_a_id, cutoff, best_of)
        team_b = self._schedule(batch.games, team_b_id, cutoff, best_of)
        _schedule_provenance(provenance, "team_a", team_a, best_of)
        _schedule_provenance(provenance, "team_b", team_b, best_of)
        return CompetitionContextFeatureResult(
            parameters_version=self._parameters.version,
            cutoff_at=cutoff.at,
            max_input_time=audit.max_input_time,
            competition=_optional_text(target.competition),
            league=_optional_text(target.league),
            region=_optional_text(target.region),
            tournament=_optional_text(target.tournament),
            stage=_optional_text(target.stage),
            phase=phase,
            best_of=best_of,
            patch=_optional_text(target.patch),
            team_a=team_a,
            team_b=team_b,
            provenance=MappingProxyType(provenance),
        )

    def _schedule(
        self,
        games: Sequence[HistoricalGame],
        team_id: UUID,
        cutoff: FeatureCutoff,
        target_best_of: int | None,
    ) -> TeamScheduleContext:
        team_games = tuple(
            game
            for game in sorted(games, key=lambda item: (item.event_time, item.game_id))
            if _has_team(game, team_id)
        )
        latest = team_games[-1].event_time if team_games else None
        rest_days = (
            _quantize(Decimal(str((cutoff.at - latest).total_seconds())) / Decimal(86400))
            if latest is not None
            else None
        )
        lower_bound = cutoff.at - timedelta(days=self._parameters.density_days)
        density = sum(1 for game in team_games if game.event_time >= lower_bound)
        format_experience = (
            sum(1 for game in team_games if game.best_of == target_best_of)
            if target_best_of is not None
            else None
        )
        return TeamScheduleContext(
            team_id=team_id,
            rest_days=rest_days,
            density_window_days=self._parameters.density_days,
            density_games=density,
            format_experience_games=format_experience,
        )


def _phase(target: TargetCompetitionContext) -> tuple[str | None, str]:
    international = _optional_bool(target.international)
    if international is True:
        return "international", target.international.provenance
    playoffs = _optional_bool(target.playoffs)
    if playoffs is True:
        return "playoffs", target.playoffs.provenance
    if playoffs is False:
        return "regular", target.playoffs.provenance
    return None, "unknown"


def _has_team(game: HistoricalGame, team_id: UUID) -> bool:
    return any(stat.team_id == team_id for stat in game.team_stats) or any(
        player.team_id == team_id for player in game.player_stats
    )


def _optional_text(field: ContextField) -> str | None:
    if field.value is None:
        return None
    if isinstance(field.value, bool):
        raise ValueError("une valeur booléenne ne peut pas devenir une catégorie texte")
    return str(field.value)


def _optional_int(field: ContextField) -> int | None:
    if field.value is None:
        return None
    if isinstance(field.value, bool) or not isinstance(field.value, int) or field.value < 1:
        raise ValueError("best_of OE doit être un entier positif")
    return field.value


def _optional_bool(field: ContextField) -> bool | None:
    if field.value is None:
        return None
    if not isinstance(field.value, bool):
        raise ValueError("les indicateurs de phase OE doivent être booléens")
    return field.value


def _schedule_provenance(
    target: dict[str, str],
    label: str,
    schedule: TeamScheduleContext,
    target_best_of: int | None,
) -> None:
    derived = "derived:canonical_oe_history"
    target[f"context.{label}.rest_days"] = derived if schedule.rest_days is not None else "unknown"
    target[f"context.{label}.density_games_{schedule.density_window_days}d"] = derived
    target[f"context.{label}.format_experience_games"] = (
        derived if target_best_of is not None else "unknown"
    )


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


def _write_team_values(
    target: dict[str, FeatureValue],
    label: str,
    schedule: TeamScheduleContext,
) -> None:
    base = f"context.{label}"
    target[f"{base}.rest_days"] = schedule.rest_days
    target[f"{base}.density_games_{schedule.density_window_days}d"] = schedule.density_games
    target[f"{base}.format_experience_games"] = schedule.format_experience_games
