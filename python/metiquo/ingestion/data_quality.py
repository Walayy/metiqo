"""Règles métier stables de qualité des lignes Oracle's Elixir."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Literal

from metiquo.foundation.time import Clock, SystemClock
from metiquo.ingestion.source_errors import DataQualityFailed

type QualitySeverity = Literal["blocking", "capability-only", "warning"]
type QualityContextValue = str | int | float | bool | None

_PLAYER_POSITIONS = {"top", "jng", "mid", "bot", "sup"}
_VALID_SIDES = {"Blue", "Red"}
_NUMERIC_RANGES: Mapping[str, tuple[float, float]] = MappingProxyType(
    {
        "result": (0, 1),
        "kills": (0, 200),
        "deaths": (0, 200),
        "assists": (0, 500),
        "gamelength": (60, 7200),
        "goldat15": (0, 50000),
        "xpat15": (0, 50000),
    }
)


class QualityCode(StrEnum):
    MISSING_GAME_ID = "MISSING_GAME_ID"
    MISSING_PARTICIPANT_ID = "MISSING_PARTICIPANT_ID"
    DATE_INVALID = "DATE_INVALID"
    DATE_IMPLAUSIBLE = "DATE_IMPLAUSIBLE"
    NATURAL_KEY_DUPLICATE = "NATURAL_KEY_DUPLICATE"
    PARTICIPANT_TEAM_INCONSISTENT = "PARTICIPANT_TEAM_INCONSISTENT"
    TEAMS_NOT_DISTINCT = "TEAMS_NOT_DISTINCT"
    SIDE_INVALID = "SIDE_INVALID"
    NUMERIC_INVALID = "NUMERIC_INVALID"
    NUMERIC_OUT_OF_RANGE = "NUMERIC_OUT_OF_RANGE"
    RESULT_INCONSISTENT = "RESULT_INCONSISTENT"
    INCOMPLETE_GAME = "INCOMPLETE_GAME"
    REMAKE_DETECTED = "REMAKE_DETECTED"
    FORFEIT_DETECTED = "FORFEIT_DETECTED"
    TEAM_ROW_STRUCTURE = "TEAM_ROW_STRUCTURE"
    PLAYER_ROW_STRUCTURE = "PLAYER_ROW_STRUCTURE"
    MASS_DELETION_DETECTED = "MASS_DELETION_DETECTED"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: QualityCode
    severity: QualitySeverity
    message: str
    row_number: int | None = None
    natural_key: str | None = None
    capability: str | None = None
    context: Mapping[str, QualityContextValue] = MappingProxyType({})

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "severity": self.severity,
            "message": self.message,
            "rowNumber": self.row_number,
            "naturalKey": self.natural_key,
            "capability": self.capability,
            "context": dict(self.context),
        }


@dataclass(frozen=True, slots=True)
class PreviousQualitySummary:
    row_count: int
    natural_keys: frozenset[str]

    def __post_init__(self) -> None:
        if self.row_count < 0:
            raise ValueError("row_count précédent invalide")


@dataclass(frozen=True, slots=True)
class QualityReport:
    status: Literal["passed", "failed", "capability-only"]
    row_count: int
    game_count: int
    min_event_date: str | None
    max_event_date: str | None
    issues: tuple[QualityIssue, ...]
    disabled_capabilities: tuple[str, ...]
    natural_keys: frozenset[str]

    @property
    def blocking(self) -> bool:
        return self.status == "failed"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "rowCount": self.row_count,
            "gameCount": self.game_count,
            "minEventDate": self.min_event_date,
            "maxEventDate": self.max_event_date,
            "disabledCapabilities": list(self.disabled_capabilities),
            "issues": [issue.to_dict() for issue in self.issues],
        }


class DataQualityValidator:
    """Scanner toutes les lignes et comparer la volumétrie au snapshot précédent."""

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        mass_deletion_ratio: float = 0.8,
    ) -> None:
        if not 0 < mass_deletion_ratio <= 1:
            raise ValueError("mass_deletion_ratio doit être dans ]0, 1]")
        self._clock = clock or SystemClock()
        self._mass_deletion_ratio = mass_deletion_ratio

    def validate(
        self,
        rows: Sequence[Mapping[str, str]],
        *,
        previous: PreviousQualitySummary | None = None,
        approve_mass_deletion: bool = False,
    ) -> QualityReport:
        issues: list[QualityIssue] = []
        natural_keys: set[str] = set()
        games: dict[str, list[tuple[int, Mapping[str, str]]]] = defaultdict(list)
        parsed_dates: list[date] = []
        latest_plausible = self._clock.now().value.date() + timedelta(days=366)

        for row_number, row in enumerate(rows, start=2):
            game_id = row.get("gameid", "").strip()
            participant_id = row.get("participantid", "").strip()
            natural_key = f"{game_id}:{participant_id}" if game_id and participant_id else None
            if not game_id:
                issues.append(_row_issue(QualityCode.MISSING_GAME_ID, row_number, natural_key))
            if not participant_id:
                issues.append(
                    _row_issue(QualityCode.MISSING_PARTICIPANT_ID, row_number, natural_key)
                )
            if natural_key is not None:
                if natural_key in natural_keys:
                    issues.append(
                        _row_issue(
                            QualityCode.NATURAL_KEY_DUPLICATE,
                            row_number,
                            natural_key,
                        )
                    )
                natural_keys.add(natural_key)
            if game_id:
                games[game_id].append((row_number, row))

            parsed = _parse_date(row.get("date", ""))
            if parsed is None:
                issues.append(_row_issue(QualityCode.DATE_INVALID, row_number, natural_key))
            elif parsed < date(2014, 1, 1) or parsed > latest_plausible:
                issues.append(
                    _row_issue(
                        QualityCode.DATE_IMPLAUSIBLE,
                        row_number,
                        natural_key,
                        context={"date": parsed.isoformat()},
                    )
                )
            else:
                parsed_dates.append(parsed)

            side = row.get("side", "").strip()
            if side not in _VALID_SIDES:
                issues.append(
                    _row_issue(
                        QualityCode.SIDE_INVALID,
                        row_number,
                        natural_key,
                        context={"side": side},
                    )
                )
            issues.extend(_numeric_issues(row, row_number, natural_key))

            completeness = row.get("datacompleteness", "").strip().casefold()
            if completeness and completeness != "complete":
                issues.append(
                    _issue(
                        QualityCode.INCOMPLETE_GAME,
                        "capability-only",
                        "game source marquée incomplète",
                        row_number=row_number,
                        natural_key=natural_key,
                        capability="market.match_winner",
                    )
                )
            game_length = _float_or_none(row.get("gamelength"))
            if game_length is not None and game_length < 600:
                issues.append(
                    _issue(
                        QualityCode.REMAKE_DETECTED,
                        "warning",
                        "durée compatible avec un remake",
                        row_number=row_number,
                        natural_key=natural_key,
                    )
                )
            if row.get("forfeit", "").strip().casefold() in {"1", "true", "yes"}:
                issues.append(
                    _issue(
                        QualityCode.FORFEIT_DETECTED,
                        "warning",
                        "forfeit signalé par la source",
                        row_number=row_number,
                        natural_key=natural_key,
                    )
                )

        for game_id, game_rows in games.items():
            issues.extend(_game_issues(game_id, game_rows))

        if (
            previous is not None
            and previous.row_count > 0
            and len(rows) < previous.row_count * self._mass_deletion_ratio
            and not approve_mass_deletion
        ):
            removed = previous.natural_keys - natural_keys
            issues.append(
                _issue(
                    QualityCode.MASS_DELETION_DETECTED,
                    "blocking",
                    "suppression massive par rapport au snapshot précédent",
                    context={
                        "previousRowCount": previous.row_count,
                        "currentRowCount": len(rows),
                        "removedNaturalKeys": len(removed),
                        "minimumRatio": self._mass_deletion_ratio,
                    },
                )
            )

        disabled = tuple(
            sorted({issue.capability for issue in issues if issue.capability is not None})
        )
        if any(issue.severity == "blocking" for issue in issues):
            status: Literal["passed", "failed", "capability-only"] = "failed"
        elif any(issue.severity == "capability-only" for issue in issues):
            status = "capability-only"
        else:
            status = "passed"
        return QualityReport(
            status=status,
            row_count=len(rows),
            game_count=len(games),
            min_event_date=min(parsed_dates).isoformat() if parsed_dates else None,
            max_event_date=max(parsed_dates).isoformat() if parsed_dates else None,
            issues=tuple(issues),
            disabled_capabilities=disabled,
            natural_keys=frozenset(natural_keys),
        )

    @staticmethod
    def require_pass(report: QualityReport, *, transport: str, source_id: str) -> None:
        if not report.blocking:
            return
        blocking_codes = sorted(
            {issue.code.value for issue in report.issues if issue.severity == "blocking"}
        )
        raise DataQualityFailed(
            "validation métier Oracle's Elixir bloquante",
            transport=transport,
            source_id=source_id,
            retryable=False,
            context={
                "rule": "DATA_QUALITY_BLOCKING",
                "blockingCodes": ",".join(blocking_codes),
                "rowCount": report.row_count,
            },
        )


def _row_issue(
    code: QualityCode,
    row_number: int,
    natural_key: str | None,
    *,
    context: Mapping[str, QualityContextValue] | None = None,
) -> QualityIssue:
    messages = {
        QualityCode.MISSING_GAME_ID: "gameid vide",
        QualityCode.MISSING_PARTICIPANT_ID: "participantid vide",
        QualityCode.DATE_INVALID: "date absente ou non parsable",
        QualityCode.DATE_IMPLAUSIBLE: "date hors plage plausible",
        QualityCode.NATURAL_KEY_DUPLICATE: "clé naturelle dupliquée",
        QualityCode.SIDE_INVALID: "side invalide",
    }
    return _issue(
        code,
        "blocking",
        messages[code],
        row_number=row_number,
        natural_key=natural_key,
        context=context,
    )


def _numeric_issues(
    row: Mapping[str, str], row_number: int, natural_key: str | None
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for field, (minimum, maximum) in _NUMERIC_RANGES.items():
        raw = row.get(field)
        if raw is None or not raw.strip():
            continue
        value = _float_or_none(raw)
        if value is None:
            issues.append(
                _issue(
                    QualityCode.NUMERIC_INVALID,
                    "blocking",
                    "statistique numérique non parsable",
                    row_number=row_number,
                    natural_key=natural_key,
                    context={"field": field},
                )
            )
        elif not minimum <= value <= maximum:
            issues.append(
                _issue(
                    QualityCode.NUMERIC_OUT_OF_RANGE,
                    "blocking",
                    "statistique numérique hors plage plausible",
                    row_number=row_number,
                    natural_key=natural_key,
                    context={
                        "field": field,
                        "value": value,
                        "minimum": minimum,
                        "maximum": maximum,
                    },
                )
            )
    return issues


def _game_issues(game_id: str, rows: Sequence[tuple[int, Mapping[str, str]]]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    names_by_side: dict[str, set[str]] = defaultdict(set)
    for _, row in rows:
        side = row.get("side", "").strip()
        team_name = row.get("teamname", "").strip()
        if side in _VALID_SIDES and team_name:
            names_by_side[side].add(team_name)
    if any(len(names) > 1 for names in names_by_side.values()):
        issues.append(
            _issue(
                QualityCode.PARTICIPANT_TEAM_INCONSISTENT,
                "blocking",
                "participants rattachés à plusieurs équipes pour une même side",
                natural_key=game_id,
            )
        )
    if len(names_by_side) == 2:
        blue = next(iter(names_by_side["Blue"]), "")
        red = next(iter(names_by_side["Red"]), "")
        if blue and blue == red:
            issues.append(
                _issue(
                    QualityCode.TEAMS_NOT_DISTINCT,
                    "blocking",
                    "les équipes opposées sont identiques",
                    natural_key=game_id,
                )
            )

    team_rows = [row for _, row in rows if row.get("position", "").strip().casefold() == "team"]
    if len(team_rows) != 2 or {row.get("side", "").strip() for row in team_rows} != _VALID_SIDES:
        issues.append(
            _issue(
                QualityCode.TEAM_ROW_STRUCTURE,
                "capability-only",
                "la game ne contient pas exactement deux lignes équipe Blue/Red",
                natural_key=game_id,
                capability="market.match_winner",
            )
        )
    elif all(row.get("result", "").strip() for row in team_rows):
        results = [_float_or_none(row.get("result")) for row in team_rows]
        if None in results or sum(value for value in results if value is not None) != 1:
            issues.append(
                _issue(
                    QualityCode.RESULT_INCONSISTENT,
                    "blocking",
                    "une game complète doit avoir un gagnant et un perdant",
                    natural_key=game_id,
                )
            )

    player_rows = [
        row for _, row in rows if row.get("position", "").strip().casefold() in _PLAYER_POSITIONS
    ]
    if player_rows:
        valid_structure = all(
            {
                row.get("position", "").strip().casefold()
                for row in player_rows
                if row.get("side") == side
            }
            == _PLAYER_POSITIONS
            for side in _VALID_SIDES
        )
        if len(player_rows) != 10 or not valid_structure:
            issues.append(
                _issue(
                    QualityCode.PLAYER_ROW_STRUCTURE,
                    "capability-only",
                    "structure attendue des dix lignes joueur absente",
                    natural_key=game_id,
                    capability="feature.player_form",
                )
            )
    return issues


def _issue(
    code: QualityCode,
    severity: QualitySeverity,
    message: str,
    *,
    row_number: int | None = None,
    natural_key: str | None = None,
    capability: str | None = None,
    context: Mapping[str, QualityContextValue] | None = None,
) -> QualityIssue:
    return QualityIssue(
        code=code,
        severity=severity,
        message=message,
        row_number=row_number,
        natural_key=natural_key,
        capability=capability,
        context=MappingProxyType(dict(context or {})),
    )


def _parse_date(value: str) -> date | None:
    candidate = value.strip()[:10]
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def _float_or_none(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
