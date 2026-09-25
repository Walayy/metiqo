"""Public source contracts and stable DOM identities, shared by browser and storage."""

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

PARSER_VERSION = "stake-dom-v2"
IDENTITY_VERSION = "stake-dom-v1"


def identity_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def fingerprint(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def event_id(game: str, source_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"stake:{game}:{source_id}")


def decimal(raw: str | None) -> Decimal | None:
    if not raw or not re.fullmatch(r"[+-]?\d+(?:[.,]\d+)?", raw):
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None


class SourceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Participant(SourceModel):
    name: str
    position: int
    source_id: str | None = None
    image_url: str | None = None


class EventMetadata(SourceModel):
    game: str
    source_id: str
    url: str
    competition_key: str
    competition_name: str | None = None
    category_name: str | None = None
    participants: list[Participant] = Field(default_factory=list)
    starts_at: AwareDatetime | None = None
    status: Literal["scheduled", "live", "closed", "unknown"] = "unknown"
    observed_at: AwareDatetime
    raw: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def id(self) -> UUID:
        return event_id(self.game, self.source_id)

    def eligible(self, now: datetime, guard_seconds: int = 0) -> bool:
        if len(self.participants) != 2 or not all(p.name.strip() for p in self.participants):
            return False
        if identity_text(self.participants[0].name) == identity_text(self.participants[1].name):
            return False
        if self.status == "live":
            # A published live marker is sufficient even when the planned start is unknown.
            return True
        return (
            self.status == "scheduled"
            and self.starts_at is not None
            and self.starts_at > now + timedelta(seconds=guard_seconds)
        )


class SelectionReading(SourceModel):
    name: str
    accessible_name: str | None = None
    column: str | None = None
    row_label: str | None = None
    source_id: str | None = None
    odds_raw: str | None = None
    disabled: bool
    attributes: dict[str, str] = Field(default_factory=dict)


class MarketReading(SourceModel):
    label: str
    source_id: str | None = None
    expanded: bool
    selections: list[SelectionReading]
    controls: list[str]
    attributes: dict[str, str] = Field(default_factory=dict)


class Tab(SourceModel):
    id: str
    label: str
    disabled: bool


class Capture(SourceModel):
    metadata: EventMetadata
    tab: str
    tabs: list[Tab]
    markets: list[MarketReading]


class Listing(SourceModel):
    url: str
    observed_at: AwareDatetime
    ready: bool
    fixtures: list[EventMetadata]
    links: list[str]
    more: str | None


def validate_event_url(url: str, game: str) -> str:
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.netloc != "stake.bet"
        or parts.query
        or parts.fragment
        or not re.fullmatch(rf"/fr/sports/{re.escape(game)}/[^/]+/[^/]+/\d+-[^/]+", parts.path)
    ):
        raise ValueError("Invalid discovered Stake event URL")
    return url


def market_identity(
    market: MarketReading, *, tab: str | None = None
) -> tuple[str, str, int | None, str | None]:
    label = identity_text(market.label)
    period_match = re.match(
        r"(?:map|carte|game|manche)\s+(\d+)\b|vainqueur de la carte\s+(\d+)\b",
        label,
    )
    period = int(period_match[1] or period_match[2]) if period_match else None
    # Family is descriptive only. Unknown families retain their complete source label.
    family = re.sub(r"^(?:map|carte|game|manche)\s+\d+\s*[-–]?\s*", "", label)
    if market.source_id:
        return fingerprint(["source-id", market.source_id]), "source-id", period, family
    if tab == "tab-players" and re.search(r"\bduel\b", label):
        # Stake repeats the same duel heading for different player pairs and
        # provides no market/outcome IDs. The visible pair, unlike DOM order or
        # odds, distinguishes those sourced markets across observations.
        if len(market.selections) != 2:
            raise ValueError("Player duel lacks stable participant identity")
        pair = sorted(identity_text(selection.name) for selection in market.selections)
        if not pair[0] or pair[0] == pair[1]:
            raise ValueError("Player duel lacks stable participant identity")
        basis = "stake-dom-v2-player-pair"
        return fingerprint([basis, label, pair]), basis, period, family
    return fingerprint([IDENTITY_VERSION, label]), IDENTITY_VERSION, period, family


def selection_identity(
    market: MarketReading, selection: SelectionReading
) -> tuple[str, str, Decimal | None, str | None, int | None]:
    label = identity_text(market.label)
    numeric = decimal(selection.name)
    line = (
        numeric
        if re.search(r"handicap|nombre|total|durée|duration|premier.*atteindre|first.*to", label)
        else None
    )
    ordinal = (
        int(selection.name)
        if re.search(r"[º°].*meurtre|nth.*kill", market.label, re.IGNORECASE)
        and selection.name.isdigit()
        else None
    )
    basis = (
        "source-id"
        if selection.source_id
        else "stake-dom-v2-row"
        if selection.row_label
        else IDENTITY_VERSION
    )
    # Row headings survive suspension even when a button loses its accessible name.
    if selection.source_id:
        parts = [
            basis,
            selection.source_id,
            str(line) if line is not None else None,
            ordinal,
            identity_text(selection.name) if numeric is not None and line is None else None,
        ]
    elif selection.row_label:
        parts = [
            basis,
            identity_text(selection.row_label),
            identity_text(selection.name),
            str(line) if line is not None else None,
            ordinal,
        ]
    else:
        parts = [
            basis,
            identity_text(selection.name),
            identity_text(selection.accessible_name or ""),
            identity_text(selection.column or ""),
            str(line) if line is not None else None,
            ordinal,
        ]
    key = fingerprint(parts)
    return key, basis, line, selection.name if line is not None else None, ordinal
