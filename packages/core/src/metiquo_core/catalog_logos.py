"""Reuse verified team emblems without conflating source team identities."""

from metiquo_core.contracts import TeamData

# Visual name equivalents observed in the public LoLTV team records and the
# Riot LoL Esports catalog. They are scoped to logo display, never match linkage.
# See docs/data-sources.md for the source and coverage limits.
_RIOT_LOGO_NAME: dict[str, str] = {
    "kt rolster challengers": "kt Challengers",
    "dplus kia challengers": "DK Challengers",
    "gamespace mediterranean college esports": "Gamespace M.C.",
    "magaza esports": "MAGAZA",
    "team heretics academy": "Heretics Academy",
    "red canids": "RED Kalunga",
    "cloud9": "Cloud9 Kia",
    "team liquid": "Team Liquid Alienware",
    "1tap dino": "Saigon 1TAP DINO",
    "sn cybercore esports": "TP.HCM SN CyberCore Esports",
    "9gaming": "Saigon 9Gaming Esports",
}


def fill_team_logos(teams: list[TeamData]) -> list[dict[str, str]]:
    """Fill missing LoLTV emblems only from one unambiguous sourced image."""
    riot_by_name: dict[str, list[TeamData]] = {}
    for team in teams:
        if not team.id.startswith("loltv:") and team.image.startswith("/api/v1/catalog/logos/"):
            riot_by_name.setdefault(team.name.casefold(), []).append(team)

    evidence: list[dict[str, str]] = []
    for team in teams:
        if team.image or not team.id.startswith("loltv:"):
            continue
        name = _RIOT_LOGO_NAME.get(team.name.casefold(), team.name).casefold()
        candidates = riot_by_name.get(name, [])
        if len(candidates) == 1:
            donor = candidates[0]
            team.image = donor.image
            evidence.append({"teamId": team.id, "logoTeamId": donor.id, "image": donor.image})
        elif team.source_image.startswith("https://static.lolesports.com/teams/"):
            # A verified official URL is usable until the next catalog sync
            # downloads and stores its WebP in the local artifact cache.
            team.image = team.source_image
            evidence.append(
                {"teamId": team.id, "sourceImage": team.source_image, "image": team.image}
            )
    return evidence
