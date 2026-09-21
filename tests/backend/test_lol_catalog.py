import io
import json
from collections import Counter

import httpx
import pytest
from metiquo_core.config import Settings
from metiquo_worker.catalog_images import fetch_image, image_url, webp
from metiquo_worker.catalog_sync import discover_catalog, fingerprint, retain_known_identities
from metiquo_worker.sources.lol import ROOT_URL, Reference, league_registry, parse_page
from PIL import Image


def source_page(*items):
    return (
        '<script>(window[Symbol.for("ApolloSSRDataTransport")] ??= []).push('
        + json.dumps(items)
        + ")</script>"
    )


def source_league(identity="new-league", slug="new-division"):
    return {
        "__typename": "League",
        "id": identity,
        "slug": slug,
        "name": "New league",
        "region": "NEW_REGION",
        "image": "https://static.lolesports.com/league.png",
    }


def source_items():
    league = source_league()
    international = source_league("intl", "worlds")
    international["region"] = "INTERNATIONAL"
    return [
        {"__typename": "Query", "leagues": [league, international]},
        {
            "__typename": "Team",
            "id": "team-1",
            "name": "Primary team",
            "code": "PT",
            "slug": "primary",
            "homeLeague": {"id": "new-league"},
            "image": "https://static.lolesports.com/team.png",
        },
        {
            "__typename": "Season",
            "id": "season-2027",
            "sport": "lol",
            "name": "2027",
            "splits": [{"__typename": "Split", "id": "split-1", "name": "Winter"}],
        },
        {
            "__typename": "EventMatch",
            "id": "match-1",
            "league": {"id": "intl"},
            "startTime": "2026-12-01T12:00:00Z",
            "matchTeams": [
                {
                    "__typename": "MatchTeam",
                    "id": "match-1:team-1",
                    "name": "Old match label",
                    "code": "OLD",
                },
                {"__typename": "MatchTeam", "id": "match-1:0", "name": "TBD"},
            ],
        },
        {
            "__typename": "Tournament",
            "id": "tournament-1",
            "league": {"id": "new-league"},
            "season": {"id": "season-2027"},
            "startTime": "2026-11-01T12:00:00Z",
            "endTime": "2026-12-01T12:00:00Z",
            "teams": [{"id": "team-1"}],
        },
    ]


def source_document():
    reference = Reference()
    reference.add_page(parse_page(source_page(*source_items())), ROOT_URL)
    return reference.document("2026-09-15")


def test_discovery_uses_source_registry_and_rejects_partial_crawls(tmp_path):
    urls = []
    body = source_page(*source_items())

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, text=body)

    settings = Settings(database_url="postgresql://unused", artifact_dir=tmp_path)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reference, pages = discover_catalog(client, settings)
        assert set(urls) == {
            ROOT_URL,
            ROOT_URL + "/leagues/new-division",
            ROOT_URL + "/leagues/worlds",
        }
        assert len(reference.leagues) == 2 and len(pages) == 3
        settings.catalog_max_pages = 1
        with pytest.raises(ValueError, match="page limit"):
            discover_catalog(client, settings)


def test_season_and_participation_are_not_invented_or_confused_with_home():
    document = source_document()
    team = document["catalog"]["teams"][0]
    assert team["leagueId"] == "new-league" and team["name"] == "Primary team"
    assert len(document["catalog"]["teams"]) == 1
    affiliations = {a["kind"]: a for a in document["affiliations"]}
    assert affiliations["home"]["seasonId"] is None
    assert affiliations["match"]["seasonId"] is None
    assert affiliations["tournament"]["seasonId"] == "season-2027"
    assert affiliations["tournament"]["startsAt"].startswith("2026")
    split = next(e for e in document["entities"] if e["kind"] == "split")
    assert split["attributes"]["seasonId"] == "season-2027"


def test_invalid_or_changed_source_fails_explicitly():
    with pytest.raises(ValueError, match="transport"):
        parse_page("<html>maintenance</html>")
    with pytest.raises(ValueError, match="registry"):
        league_registry(parse_page(source_page({"__typename": "Query", "leagues": []})))
    payload = source_page({"name": "undefined", "value": None}).replace(
        '"value": null', '"value": undefined'
    )
    result = parse_page(payload)
    assert result[0]["name"] == "undefined" and result[0]["value"] is None


def test_fingerprint_ignores_check_date_but_detects_affiliation_changes():
    document = source_document()
    original = fingerprint(document)
    document["catalog"]["retrievedAt"] = "2026-09-16"
    assert fingerprint(document) == original
    document["affiliations"][0]["seasonId"] = "another-season"
    assert fingerprint(document) != original


def png(color="red"):
    output = io.BytesIO()
    Image.new("RGBA", (300, 150), color).save(output, format="PNG")
    return output.getvalue()


def test_logos_revalidate_cache_and_publish_new_immutable_paths(tmp_path):
    settings = Settings(database_url="postgresql://unused", artifact_dir=tmp_path)
    count = Counter()
    revision = ['"v1"']

    def handler(request):
        count["requests"] += 1
        if request.headers.get("if-none-match") == revision[0]:
            count["notModified"] += 1
            return httpx.Response(304)
        return httpx.Response(
            200,
            content=png("red" if revision[0] == '"v1"' else "blue"),
            headers={"etag": revision[0]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        url = "http://static.lolesports.com/logo.png"
        first = fetch_image(client, url, {}, settings)
        second = fetch_image(client, url, first, settings)
        assert first == second and count["requests"] == 1
        second = fetch_image(client, url, {**first, "checkedAt": 0}, settings)
        assert first["sha256"] == second["sha256"] and count["notModified"] == 1
        revision[0] = '"v2"'
        third = fetch_image(client, url, {**second, "checkedAt": 0}, settings)
        assert third["sha256"] != first["sha256"]
        assert (tmp_path / first["path"]).is_file()
        with Image.open(tmp_path / third["path"]) as result:
            assert result.size == (144, 72) and result.format == "WEBP"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/image.png",
        "https://static.lolesports.com.evil/image.png",
        "file:///etc/passwd",
        "https://user@static.lolesports.com/a.png",
    ],
)
def test_logo_destinations_are_limited_to_official_source(url):
    with pytest.raises(ValueError, match="official"):
        image_url(url)


def test_loltv_rendered_logo_host_is_approved() -> None:
    url = "https://cdn.loltv.gg/teams/example.png"
    assert image_url(url) == url


def test_catalog_retains_observed_source_identities_without_inventing_affiliation() -> None:
    document = source_document()
    retain_known_identities(
        document,
        [
            {
                "id": "loltv:tournament:42",
                "slug": "observed-cup",
                "name": "Observed Cup",
                "region": "INTERNATIONAL",
                "image": "",
                "sourceImage": "",
                "tier": "international",
                "sourceId": "42",
            }
        ],
        [
            {
                "id": "loltv:team:7",
                "name": "Observed Team",
                "code": "",
                "slug": "observed-team",
                "leagueId": "loltv:tournament:42",
                "image": "",
                "sourceImage": "",
                "sourceImages": {"loltv": ["https://cdn.loltv.gg/teams/team-7.png"]},
            }
        ],
    )

    catalog = document["catalog"]
    team = next(item for item in catalog["teams"] if item["id"] == "loltv:team:7")
    assert team["leagueId"] == "loltv:tournament:42"
    assert team["sourceImage"].endswith("/teams/team-7.png")
    assert document["coverage"]["retainedKnownTeams"] == 1


def test_html_or_oversized_logo_does_not_create_an_asset(tmp_path):
    settings = Settings(
        database_url="postgresql://unused", artifact_dir=tmp_path, catalog_max_image_bytes=1024
    )
    for content in (b"<html>maintenance</html>", b"x" * 1025):
        with httpx.Client(
            transport=httpx.MockTransport(lambda _, body=content: httpx.Response(200, content=body))
        ) as client:
            with pytest.raises((ValueError, OSError)):
                fetch_image(client, "https://static.lolesports.com/a.png", {}, settings)
    assert not list(tmp_path.rglob("*.webp"))


def test_decoded_image_size_is_bounded_before_loading_pixels():
    with pytest.raises(ValueError, match="dimensions"):
        webp(png(), max_pixels=100)
