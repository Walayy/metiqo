"""Public Riot HTML: discover the league registry, never execute its scripts.

The route template is the public league filter already used by this project.
Season, tournament participation and home-league evidence remain distinct.
"""

import json
import re
from dataclasses import dataclass, field
from typing import cast

from bs4 import BeautifulSoup
from metiquo_core.contracts import Catalog
from pydantic import JsonValue

SOURCE = "lol-esports"
ROOT_URL = "https://lolesports.com/en-US"
SLUG = re.compile(r"^[a-zA-Z0-9_-]+$")
# Presentation taxonomy only: this never determines which leagues are discovered.
MAJOR_SLUGS = {"lck", "lpl", "lec", "lcs", "cblol-brazil", "lcp"}
CROSS_REGION_SLUGS = {"worlds", "msi", "first_stand", "ewc_lol", "americas_cup", "emea_masters"}
REFERENCE_FIELDS = (
    "id",
    "name",
    "slug",
    "code",
    "region",
    "regionSlug",
    "image",
    "sport",
    "startTime",
    "endTime",
    "seasonId",
    "divisionId",
    "parentId",
)


def objects(value: JsonValue) -> list[dict[str, JsonValue]]:
    """Iterative traversal also handles deeply nested transport responses."""
    result: list[dict[str, JsonValue]] = []
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            result.append(item)
            pending.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            pending.extend(reversed(item))
    return result


def text(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""


def obj(value: JsonValue) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def array(value: JsonValue) -> list[JsonValue]:
    return value if isinstance(value, list) else []


def parse_page(html: str) -> list[dict[str, JsonValue]]:
    parsed: list[dict[str, JsonValue]] = []
    for script in BeautifulSoup(html, "html.parser").find_all("script"):
        source = script.get_text().strip()
        if not source.startswith('(window[Symbol.for("ApolloSSRDataTransport")]'):
            continue
        start, end = source.find(".push("), source.rfind(")")
        if start < 0 or end <= start:
            raise ValueError("Unrecognized Riot transport wrapper")
        # Replace JS undefined only outside strings. Never eval JavaScript.
        payload = source[start + 6 : end]
        payload = re.sub(
            r'"(?:[^"\\]|\\.)*"|\bundefined\b',
            lambda match: "null" if match[0] == "undefined" else match[0],
            payload,
        )
        parsed.extend(objects(cast(JsonValue, json.loads(payload))))
    if not parsed:
        raise ValueError("Riot HTML contains no recognized data transport")
    return parsed


def league_registry(page: list[dict[str, JsonValue]]) -> dict[str, dict[str, JsonValue]]:
    result: dict[str, dict[str, JsonValue]] = {}
    for item in page:
        if item.get("__typename") != "Query" or not isinstance(item.get("leagues"), list):
            continue
        for value in array(item.get("leagues")):
            league = obj(value)
            slug = text(league.get("slug"))
            if slug == "tft_esports" or league.get("sport") not in (None, "lol"):
                continue
            identity = text(league.get("id"))
            if not identity or not SLUG.fullmatch(slug) or not text(league.get("name")):
                raise ValueError("Riot league registry contains an invalid identity")
            result[identity] = league
    if not result:
        raise ValueError("Riot league registry is missing or empty")
    slugs = [text(league.get("slug")) for league in result.values()]
    if len(slugs) != len(set(slugs)):
        raise ValueError("Ambiguous Riot league slugs")
    return result


@dataclass
class Reference:
    leagues: dict[str, dict[str, JsonValue]] = field(default_factory=dict)
    teams: dict[str, dict[str, JsonValue]] = field(default_factory=dict)
    entities: dict[str, dict[str, JsonValue]] = field(default_factory=dict)
    affiliations: dict[str, dict[str, JsonValue]] = field(default_factory=dict)

    def entity(self, kind: str, item: dict[str, JsonValue], url: str) -> None:
        identity = text(item.get("id"))
        if not identity or identity == "0":
            return
        key = f"{kind}:{identity}"
        record = self.entities.setdefault(
            key, {"kind": kind, "sourceId": identity, "attributes": {}, "sourceUrls": []}
        )
        attributes = obj(record["attributes"])
        attributes.update(
            {k: item[k] for k in REFERENCE_FIELDS if k in item and item[k] is not None}
        )
        for relationship in ("league", "season", "division", "homeLeague"):
            parent = obj(item.get(relationship))
            if text(parent.get("id")):
                attributes[f"{relationship}Id"] = parent["id"]
        sources = array(record["sourceUrls"])
        if url not in sources:
            sources.append(url)
            sources.sort(key=str)

    def affiliation(
        self, team_id: str, league_id: str, kind: str, evidence: dict[str, JsonValue], url: str
    ) -> None:
        if not team_id or team_id == "0" or league_id not in self.leagues:
            return
        evidence_id = text(evidence.get("id"))
        key = f"{kind}:{team_id}:{league_id}:{evidence_id}"
        season_id = text(obj(evidence.get("season")).get("id")) or text(evidence.get("seasonId"))
        entry = self.affiliations.setdefault(
            key,
            {
                "teamId": team_id,
                "leagueId": league_id,
                "kind": kind,
                "evidenceId": evidence_id,
                "seasonId": season_id or None,
                "startsAt": evidence.get("startTime"),
                "endsAt": evidence.get("endTime"),
                "sourceUrls": [],
            },
        )
        urls = array(entry["sourceUrls"])
        if url not in urls:
            urls.append(url)
            urls.sort(key=str)

    def add_page(self, page: list[dict[str, JsonValue]], url: str) -> None:
        registry = league_registry(page)
        self.leagues.update(registry)
        for item in registry.values():
            self.entity("league", item, url)
            region = text(item.get("region"))
            if region:
                self.entity("region", {"id": f"riot:region:{region}", "name": region}, url)
        for item in page:
            kind = text(item.get("__typename"))
            identity = text(item.get("id"))
            if kind == "Team" and identity and text(item.get("name")):
                previous = self.teams.setdefault(identity, {})
                previous.update({k: v for k, v in item.items() if v is not None})
                self.entity("team", item, url)
                self.affiliation(
                    identity,
                    text(obj(item.get("homeLeague")).get("id")),
                    "home",
                    {"id": identity},
                    url,
                )
            elif kind in ("Season", "Split", "Tournament", "Division"):
                if kind == "Season" and item.get("sport") not in (None, "lol"):
                    continue
                self.entity(kind.lower(), item, url)
                if kind == "Season":
                    for value in array(item.get("splits")):
                        self.entity("split", {**obj(value), "seasonId": identity}, url)
                if kind == "Tournament":
                    for value in array(item.get("teams")):
                        self.affiliation(
                            text(obj(value).get("id")),
                            text(obj(item.get("league")).get("id")),
                            "tournament",
                            item,
                            url,
                        )
            elif kind == "EventMatch":
                league_id = text(obj(item.get("league")).get("id"))
                for value in array(item.get("matchTeams")):
                    team = obj(value)
                    match_team_id = text(team.get("id"))
                    prefix, separator, team_id = match_team_id.partition(":")
                    if not separator or prefix != identity or not team_id or team_id == "0":
                        continue
                    if not text(team.get("name")):
                        raise ValueError("Identified Riot match participant has no name")
                    canonical = {**team, "id": team_id}
                    # A full Team/homeLeague object takes precedence over match labels.
                    previous = self.teams.setdefault(team_id, {})
                    for k, v in canonical.items():
                        if v is not None and k not in previous:
                            previous[k] = v
                    self.entity("match-team", canonical, url)
                    self.affiliation(team_id, league_id, "match", item, url)

    def document(self, retrieved_at: str) -> dict[str, object]:
        leagues: list[dict[str, object]] = []
        for identity, item in sorted(self.leagues.items()):
            slug = text(item.get("slug"))
            region = text(item.get("region"))
            leagues.append(
                {
                    "id": identity,
                    "name": text(item.get("name")),
                    "slug": slug,
                    "region": region,
                    "image": "",
                    "sourceImage": text(item.get("image")),
                    "tier": "international"
                    if region == "INTERNATIONAL" or slug in CROSS_REGION_SLUGS
                    else "major"
                    if slug in MAJOR_SLUGS
                    else "regional",
                }
            )
        teams: list[dict[str, object]] = []
        assignments: dict[str, str] = {}
        unassigned: list[str] = []
        for identity, item in sorted(self.teams.items()):
            home = text(obj(item.get("homeLeague")).get("id"))
            candidates = [a for a in self.affiliations.values() if a["teamId"] == identity]
            if home in self.leagues:
                league_id, basis = home, "home"
            elif candidates:
                # Compatibility grouping only. This NEVER creates a home affiliation.
                candidates.sort(
                    key=lambda a: (text(a.get("startsAt")), text(a["evidenceId"])),
                    reverse=True,
                )
                candidates.sort(
                    key=lambda a: (
                        text(self.leagues[text(a["leagueId"])].get("slug")) in CROSS_REGION_SLUGS
                    )
                )
                league_id, basis = text(candidates[0]["leagueId"]), "participation"
            else:
                unassigned.append(identity)
                continue
            assignments[identity] = basis
            teams.append(
                {
                    "id": identity,
                    "name": text(item.get("name")),
                    "code": text(item.get("code")),
                    "slug": text(item.get("slug")) or f"riot-{identity}",
                    "leagueId": league_id,
                    "image": "",
                    "sourceImage": text(item.get("image")),
                }
            )
        if not leagues or not teams:
            raise ValueError("Riot reference is empty")
        catalog = Catalog.model_validate(
            {"source": ROOT_URL, "retrievedAt": retrieved_at, "leagues": leagues, "teams": teams}
        )
        return {
            "schemaVersion": 1,
            "catalog": catalog.model_dump(mode="json", by_alias=True),
            "entities": [self.entities[k] for k in sorted(self.entities)],
            "affiliations": [self.affiliations[k] for k in sorted(self.affiliations)],
            "leagueAssignment": assignments,
            "coverage": {
                "exhaustive": False,
                "unassignedTeamIds": unassigned,
                "seasonLinks": "Only explicit source relationships; null when unknown",
                "teamGrouping": "homeLeague when sourced, otherwise observed participation",
            },
        }
