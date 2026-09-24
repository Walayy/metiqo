from metiquo_core.catalog_logos import fill_team_logos
from metiquo_core.contracts import TeamData


def team(identity: str, name: str, image: str = "", source_image: str = "") -> TeamData:
    return TeamData(
        id=identity,
        name=name,
        code="",
        slug=name.casefold().replace(" ", "-"),
        league_id="source-league",
        image=image,
        source_image=source_image,
    )


def test_logos_reuse_unique_riot_assets_for_exact_and_reviewed_names() -> None:
    solary = team("riot:solary", "Solary", "/api/v1/catalog/logos/solary.webp")
    challengers = team("riot:dkc", "DK Challengers", "/api/v1/catalog/logos/dkc.webp")
    observed = [
        team("loltv:solary", "Solary", source_image="https://cdn.loltv.gg/solary.png"),
        team("loltv:dkc", "Dplus Kia Challengers"),
    ]

    evidence = fill_team_logos([solary, challengers, *observed])

    assert [item.image for item in observed] == [solary.image, challengers.image]
    assert [item["logoTeamId"] for item in evidence] == [solary.id, challengers.id]
    assert observed[0].source_image == "https://cdn.loltv.gg/solary.png"
    assert observed[1].id == "loltv:dkc"


def test_logo_reuse_refuses_ambiguous_or_unverified_assets() -> None:
    observed = team("loltv:other", "Other Team")
    official = team(
        "loltv:academy",
        "MVK Esports Academy",
        source_image="https://static.lolesports.com/teams/mvk.png",
    )
    teams = [
        team("riot:1", "Other Team", "/api/v1/catalog/logos/one.webp"),
        team("riot:2", "Other Team", "/api/v1/catalog/logos/two.webp"),
        observed,
        official,
        team("loltv:unknown", "Unknown", source_image="https://cdn.loltv.gg/unknown.png"),
    ]

    evidence = fill_team_logos(teams)

    assert observed.image == ""
    assert official.image == official.source_image
    assert teams[-1].image == ""
    assert evidence == [
        {
            "teamId": official.id,
            "sourceImage": official.source_image,
            "image": official.image,
        }
    ]
