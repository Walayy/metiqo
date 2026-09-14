"""Validation stricte des seules valeurs visibles sur les pages Stake françaises."""

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from metiquo.contracts.enums import EventStatus, GameTitle
from metiquo.contracts.odds_provider import ProviderEvent
from metiquo.contracts.stake_scraping import ScrapedMarket, ScrapedOutcome

STAKE_ORIGIN = "https://stake.bet"
STAKE_LIST_URL = STAKE_ORIGIN + "/fr/sports/league-of-legends/all"
PROVIDER_CODE = "stake-public"
PARSER_VERSION = "stake-dom-fr-v2"
DISPLAY_TIMEZONE = "Europe/Paris"
_PATH = re.compile(r"/fr/sports/league-of-legends(?:/[a-z0-9-]+){1,3}/?\Z")
_PRICE = re.compile(r"\d{1,5}(?:[,.]\d{1,8})?\Z")


class StakeScrapeError(RuntimeError):
    """Erreur stable : les détails réseau et tokens de challenge restent privés."""

    def __init__(self, code: str, detail: str, *, blocked: bool = False) -> None:
        super().__init__(detail)
        self.code, self.blocked = code, blocked


def public_url(value: str, *, event_only: bool = False) -> str:
    parsed = urlsplit(value if not value.startswith("/") else STAKE_ORIGIN + value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "stake.bet"
        or parsed.query
        or parsed.fragment
        or not _PATH.fullmatch(parsed.path)
        or (
            event_only
            and (
                not re.search(r"/\d+-[a-z0-9-]+/?$", parsed.path)
                or len(parsed.path.strip("/").split("/")) != 6
            )
        )
    ):
        raise ValueError("Seules les pages publiques LoL de stake.bet/fr sont acceptées")
    return STAKE_ORIGIN + parsed.path.rstrip("/")


def decimal_price(text: str) -> Decimal | None:
    text = text.strip()
    if not text:
        return None
    if not _PRICE.fullmatch(text):
        raise StakeScrapeError("ODDS_FORMAT_CHANGED", "Format de cote décimale non reconnu")
    price = Decimal(text.replace(",", "."))
    if price <= 1:
        raise StakeScrapeError("ODDS_INVALID", "Cote hors plage : observation refusée")
    return price


def parse_event(
    dom: dict[str, Any], captured_at: datetime, *, display_timezone: str = DISPLAY_TIMEZONE
) -> ProviderEvent:
    url = public_url(dom["url"], event_only=True)
    match = re.fullmatch(r"(\d{2}:\d{2}) (\d{2}/\d{2}/\d{4})", dom["displayedStart"])
    if match is None:
        raise StakeScrapeError("START_TIME_MISSING", "Date complète du match absente ou ambiguë")
    local = datetime.strptime(match[0], "%H:%M %d/%m/%Y")
    zone = ZoneInfo(display_timezone)
    first, second = local.replace(tzinfo=zone, fold=0), local.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise StakeScrapeError(
            "START_TIME_AMBIGUOUS", "Heure locale ambiguë au changement de fuseau"
        )
    starts_at = first.astimezone(UTC)
    if len(dom["participants"]) != 2 or not dom["competition"]:
        raise StakeScrapeError("EVENT_IDENTITY_MISSING", "Équipes ou compétition absentes du DOM")
    participants = tuple(dom["participants"])
    # Le même match peut afficher un nom court en en-tête et un nom complet sur
    # son marché vainqueur. Une équipe identique ancre la correspondance des deux
    # sélections ; aucune similarité textuelle ni alias global n'est utilisé.
    winner = next(
        (m for m in dom["markets"] if m["label"] == "Vainqueur du match - Two options"), None
    )
    if winner is not None and len(winner["outcomes"]) == 2:
        labels = tuple(o["label"] or o["displayedLabel"] for o in winner["outcomes"])
        if (
            len(set(labels)) == 2
            and all(label and label.casefold() not in {"suspended", "suspendu"} for label in labels)
            and set(labels) != set(participants)
        ):
            shared = set(labels) & set(participants)
            if len(shared) != 1:
                raise StakeScrapeError(
                    "EVENT_IDENTITY_CONFLICT", "Équipes du marché et de l'en-tête incompatibles"
                )
            full_name = next(label for label in labels if label not in shared)
            participants = tuple(p if p in shared else full_name for p in participants)
    # Sans date lisible, aucune estimation du début d'un match live n'est autorisée.
    if starts_at <= captured_at:
        raise StakeScrapeError(
            "EVENT_ALREADY_STARTED", "Match déjà commencé : statut live non vérifié"
        )
    status = EventStatus.SCHEDULED
    return ProviderEvent(
        provider_event_id=url.rsplit("/", 1)[1].split("-", 1)[0],
        game_title=GameTitle.LEAGUE_OF_LEGENDS,
        competition=dom["competition"],
        participants=participants,
        starts_at=starts_at,
        best_of=None,
        status=status,
        collected_at=captured_at,
        source_reference=url,
    )


def parse_markets(dom: dict[str, Any], tab: str, at: datetime) -> tuple[ScrapedMarket, ...]:
    values = []
    for raw in dom["markets"]:
        outcomes = []
        for item in raw["outcomes"]:
            price = decimal_price(item["oddsText"])
            suspended = item["disabled"] or "suspend" in item["text"].casefold()
            label = item["label"] or item["displayedLabel"] or item["text"]
            outcomes.append(
                ScrapedOutcome(
                    label=label,
                    displayed_label=item["displayedLabel"],
                    odds_text=item["oddsText"],
                    decimal_odds=price,
                    status="suspended" if suspended else "open" if price else "unavailable",
                )
            )
        values.append(
            ScrapedMarket(
                label=raw["label"],
                tab=tab,
                captured_at=at,
                expanded=raw["expanded"],
                raw_text=raw["rawText"],
                outcomes=tuple(outcomes),
            )
        )
    if not values:
        raise StakeScrapeError("MARKETS_MISSING", "Aucun marché identifiable dans cet onglet")
    if len({m.label for m in values}) != len(values):
        raise StakeScrapeError(
            "MARKET_IDENTITY_AMBIGUOUS", "Libellé de marché dupliqué dans un onglet"
        )
    return tuple(values)
