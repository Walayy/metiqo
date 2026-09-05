"""Découverte défensive du catalogue officiel Oracle's Elixir."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from typing import Literal, cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

from sqlalchemy import Connection, Table, select, update
from sqlalchemy.dialects.postgresql import insert

from metiquo.db.raw_models import SourceCatalog
from metiquo.foundation.time import Clock, SystemClock, normalize_utc_datetime

OFFICIAL_LANDING_PAGE = "https://oracleselixir.com/tools/downloads"
PROVIDER = "oracles_elixir"
DATASET = "league_of_legends_match_data"
_DRIVE_HOST = "drive.google.com"
_YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
_FILE_PATH_PATTERN = re.compile(r"/(?:file/d|folders)/([A-Za-z0-9_-]+)(?:/|$)")

type DriveLinkKind = Literal["file", "folder"]
type CatalogOrigin = Literal["discovered", "validated-bootstrap"]
type DecisionStatus = Literal["confirmed", "new", "changed", "ambiguous", "missing"]
type AlertKind = Literal["duplicate", "unresolved"]
type PageLoader = Callable[[str, float, int], bytes]


class LandingPageUnavailable(RuntimeError):
    """La page officielle n'a pas pu être lue temporairement."""


class LandingPageInvalid(RuntimeError):
    """La réponse officielle ne peut pas être interprétée sans risque."""


@dataclass(frozen=True, slots=True)
class LandingPage:
    url: str
    payload: bytes
    fetched_at: datetime

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True, slots=True)
class DriveLink:
    drive_file_id: str
    url: str
    source_name: str
    kind: DriveLinkKind
    year: int | None
    mutable: bool | None = None


@dataclass(frozen=True, slots=True)
class CatalogDiscovery:
    landing_page: str
    payload_hash: str
    fetched_at: datetime
    links: tuple[DriveLink, ...]
    origin: CatalogOrigin = "discovered"

    @property
    def annual_links(self) -> Mapping[int, tuple[DriveLink, ...]]:
        years = sorted({link.year for link in self.links if link.year is not None})
        return {
            year: tuple(link for link in self.links if link.year == year)
            for year in years
            if year is not None
        }


@dataclass(frozen=True, slots=True)
class CatalogRecord:
    id: UUID
    season_year: int
    drive_file_id: str
    source_name: str
    landing_page: str


@dataclass(frozen=True, slots=True)
class CatalogDecision:
    year: int
    status: DecisionStatus
    candidates: tuple[DriveLink, ...]
    previous: CatalogRecord | None


@dataclass(frozen=True, slots=True)
class DiscoveryAlert:
    kind: AlertKind
    message: str
    year: int | None = None


@dataclass(frozen=True, slots=True)
class CatalogReconciliation:
    discovery: CatalogDiscovery
    decisions: tuple[CatalogDecision, ...]
    alerts: tuple[DiscoveryAlert, ...]


class LandingPageFetcher:
    """Fetcher borné qui ne connaît que la page officielle Oracle's Elixir."""

    def __init__(
        self,
        *,
        loader: PageLoader | None = None,
        clock: Clock | None = None,
        timeout_seconds: float = 10.0,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        if timeout_seconds <= 0 or max_bytes <= 0:
            raise ValueError("timeout_seconds et max_bytes doivent être positifs")
        self._loader = loader or _load_official_page
        self._clock = clock or SystemClock()
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes

    def fetch(self) -> LandingPage:
        try:
            payload = self._loader(OFFICIAL_LANDING_PAGE, self._timeout_seconds, self._max_bytes)
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise LandingPageUnavailable(
                "page de téléchargement Oracle's Elixir indisponible"
            ) from error
        if len(payload) > self._max_bytes:
            raise LandingPageInvalid("page de téléchargement Oracle's Elixir trop volumineuse")
        return LandingPage(
            url=OFFICIAL_LANDING_PAGE,
            payload=payload,
            fetched_at=self._clock.now().value,
        )


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a" or self._href is not None:
            return
        href = dict(attrs).get("href")
        if href is not None:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._href is None:
            return
        self.anchors.append((self._href, " ".join("".join(self._text).split())))
        self._href = None
        self._text = []


def discover_catalog(page: LandingPage) -> CatalogDiscovery:
    """Extraire seulement les références Google Drive de la page officielle."""

    try:
        html = page.payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LandingPageInvalid("page officielle non UTF-8") from error
    parser = _AnchorParser()
    parser.feed(html)
    links = tuple(
        link
        for href, label in parser.anchors
        if (link := _parse_drive_link(href, label)) is not None
    )
    return CatalogDiscovery(
        landing_page=page.url,
        payload_hash=page.payload_hash,
        fetched_at=normalize_utc_datetime(page.fetched_at),
        links=links,
    )


def reconcile_catalog(
    discovery: CatalogDiscovery,
    active_records: Mapping[int, CatalogRecord],
) -> CatalogReconciliation:
    """Comparer sans jamais remplacer silencieusement un actif divergent."""

    decisions: list[CatalogDecision] = []
    alerts: list[DiscoveryAlert] = []
    annual_links = discovery.annual_links

    for year, links in annual_links.items():
        distinct = tuple({link.drive_file_id: link for link in links}.values())
        previous = active_records.get(year)
        if len(links) != len(distinct):
            alerts.append(
                DiscoveryAlert("duplicate", f"l'année {year} contient un lien Drive dupliqué", year)
            )
        if len(distinct) > 1:
            decisions.append(CatalogDecision(year, "ambiguous", distinct, previous))
            continue
        candidate = distinct[0]
        if previous is None:
            status: DecisionStatus = "new"
        elif previous.drive_file_id == candidate.drive_file_id:
            status = "confirmed"
        else:
            status = "changed"
        decisions.append(CatalogDecision(year, status, (candidate,), previous))

    for year, previous in active_records.items():
        if year not in annual_links:
            decisions.append(CatalogDecision(year, "missing", (), previous))

    for link in discovery.links:
        if link.year is None:
            alerts.append(
                DiscoveryAlert(
                    "unresolved",
                    f"le lien Drive {link.drive_file_id} n'a pas d'année non ambiguë",
                )
            )

    return CatalogReconciliation(
        discovery=discovery,
        decisions=tuple(sorted(decisions, key=lambda decision: decision.year)),
        alerts=tuple(alerts),
    )


class SourceCatalogRepository:
    """Persistance PostgreSQL des observations et alertes de catalogue."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._table = cast(Table, SourceCatalog.__table__)

    def active_records(self) -> dict[int, CatalogRecord]:
        rows = self._connection.execute(
            select(self._table).where(
                self._table.c.provider == PROVIDER,
                self._table.c.dataset == DATASET,
                self._table.c.status == "active",
            )
        ).mappings()
        return {
            int(row["season_year"]): CatalogRecord(
                id=row["id"],
                season_year=int(row["season_year"]),
                drive_file_id=str(row["drive_file_id"]),
                source_name=str(row["source_name"]),
                landing_page=str(row["landing_page"]),
            )
            for row in rows
        }

    def apply(self, reconciliation: CatalogReconciliation) -> None:
        observed_at = reconciliation.discovery.fetched_at
        payload_hash = reconciliation.discovery.payload_hash
        for decision in reconciliation.decisions:
            if decision.status == "confirmed":
                assert decision.previous is not None
                self._connection.execute(
                    update(self._table)
                    .where(self._table.c.id == decision.previous.id)
                    .values(
                        last_confirmed_at=observed_at,
                        discovery_payload_hash=payload_hash,
                        updated_at=observed_at,
                    )
                )
            elif decision.status == "missing":
                assert decision.previous is not None
                self._connection.execute(
                    update(self._table)
                    .where(self._table.c.id == decision.previous.id)
                    .values(
                        status="missing",
                        discovery_payload_hash=payload_hash,
                        updated_at=observed_at,
                    )
                )
            else:
                persisted_status = {
                    "new": "active",
                    "changed": "changed",
                    "ambiguous": "ambiguous",
                }[decision.status]
                for candidate in decision.candidates:
                    mutable = (
                        candidate.mutable
                        if candidate.mutable is not None
                        else decision.year == observed_at.year
                    )
                    statement = insert(self._table).values(
                        id=uuid4(),
                        provider=PROVIDER,
                        dataset=DATASET,
                        season_year=decision.year,
                        landing_page=reconciliation.discovery.landing_page,
                        drive_file_id=candidate.drive_file_id,
                        source_name=candidate.source_name,
                        origin=reconciliation.discovery.origin,
                        status=persisted_status,
                        discovered_at=observed_at,
                        last_confirmed_at=observed_at,
                        discovery_payload_hash=payload_hash,
                        mutable=mutable,
                        created_at=observed_at,
                        updated_at=observed_at,
                    )
                    updates: dict[str, object] = {
                        "last_confirmed_at": observed_at,
                        "discovery_payload_hash": payload_hash,
                        "source_name": candidate.source_name,
                        "landing_page": reconciliation.discovery.landing_page,
                        "mutable": mutable,
                        "updated_at": observed_at,
                    }
                    is_active_candidate = (
                        decision.previous is not None
                        and candidate.drive_file_id == decision.previous.drive_file_id
                    )
                    if decision.status == "ambiguous" and is_active_candidate:
                        continue
                    if not is_active_candidate:
                        updates["status"] = persisted_status
                    self._connection.execute(
                        statement.on_conflict_do_update(
                            constraint="uq_source_catalog_source",
                            set_=updates,
                        )
                    )


def _parse_drive_link(href: str, label: str) -> DriveLink | None:
    parsed = urlparse(href)
    if parsed.scheme not in ("http", "https") or parsed.hostname != _DRIVE_HOST:
        return None
    path_match = _FILE_PATH_PATTERN.search(parsed.path)
    query_id = parse_qs(parsed.query).get("id", [None])[0]
    drive_file_id = path_match.group(1) if path_match is not None else query_id
    if drive_file_id is None or not re.fullmatch(r"[A-Za-z0-9_-]+", drive_file_id):
        return None
    kind: DriveLinkKind = "folder" if "/folders/" in parsed.path else "file"
    year_matches = {int(value) for value in _YEAR_PATTERN.findall(f"{label} {parsed.path}")}
    year = next(iter(year_matches)) if len(year_matches) == 1 else None
    return DriveLink(
        drive_file_id=drive_file_id,
        url=href,
        source_name=label or drive_file_id,
        kind=kind,
        year=year,
    )


def _load_official_page(url: str, timeout_seconds: float, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "Metiquo/0.1 source-catalog"})
    with urlopen(request, timeout=timeout_seconds) as response:
        final_url = urlparse(response.geturl())
        if final_url.hostname not in {"oracleselixir.com", "www.oracleselixir.com"}:
            raise LandingPageInvalid("redirection de la page officielle vers un autre domaine")
        return cast(bytes, response.read(max_bytes + 1))
