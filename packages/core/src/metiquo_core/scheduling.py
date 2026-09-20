"""Allowlisted collectors and shared, timezone-aware cron calculation."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, CroniterBadDateError, croniter


@dataclass(frozen=True)
class ScriptDefinition:
    name: str
    description: str
    source: str
    command: str
    cron: str


SCRIPTS = {
    "lol-catalog": ScriptDefinition(
        "Catalogue League of Legends",
        "Actualise les ligues, les équipes et leurs logos.",
        "lol-catalog",
        "sync-lol-catalog",
        "0 4 * * *",
    ),
    "oracle-latest": ScriptDefinition(
        "Oracle’s Elixir · saison récente",
        "Récupère les données de la dernière année disponible.",
        "oracles-elixir",
        "sync-oracles-elixir --latest",
        "0 */6 * * *",
    ),
    "oracle-full": ScriptDefinition(
        "Oracle’s Elixir · historique complet",
        "Vérifie et actualise toutes les années disponibles.",
        "oracles-elixir",
        "sync-oracles-elixir",
        "0 3 * * 0",
    ),
    "sofascore-matches": ScriptDefinition(
        "SofaScore · matchs LoL",
        "Scrape les rencontres de J−7 à J+7, avec un relevé fréquent des directs.",
        "sofascore",
        "sync-sofascore-matches",
        "*/1 * * * *",
    ),
}


def upcoming(cron: str, timezone: str, after: datetime, count: int = 3) -> list[datetime]:
    # Standard numeric five-field crons only: no seconds, macros or random extensions.
    if len(cron.split()) != 5 or not re.fullmatch(r"[0-9*/ ,\-]+", cron):
        raise ValueError("Utilisez un cron à cinq champs : minute, heure, jour, mois, semaine.")
    if timezone not in {"Europe/Paris", "UTC"}:
        raise ValueError("Choisissez le fuseau Europe/Paris ou UTC.")
    try:
        iterator = croniter(cron, after.astimezone(ZoneInfo(timezone)), max_years_between_matches=5)
        dates = [iterator.get_next(datetime).astimezone(UTC) for _ in range(count)]
    except (CroniterBadCronError, CroniterBadDateError, ZoneInfoNotFoundError) as error:
        raise ValueError(
            "Cron invalide ou sans exécution dans les cinq prochaines années."
        ) from error
    return dates
