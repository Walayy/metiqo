"""Offline image evidence and preservation of incomplete source drafts."""

import copy
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from metiquo_core.matches import merge_completed_map, unique_bans
from metiquo_worker.portraits import PortraitReference
from metiquo_worker.sofascore_sync import _rendered_maps
from metiquo_worker.sources import sofascore
from PIL import Image
from test_live_regressions import event, identities

FIXTURES = Path(__file__).with_name("fixtures") / "sofascore-portraits"


def test_real_source_portraits_match_only_near_identical_local_artwork():
    reference = PortraitReference()
    for asset in json.loads((FIXTURES / "manifest.json").read_text())["assets"]:
        raw = (FIXTURES / asset["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == asset["sha256"]
        assert reference.identify(raw) == asset["name"]
    placeholder = io.BytesIO()
    Image.new("RGB", (120, 120), "gray").save(placeholder, format="PNG")
    assert reference.identify(placeholder.getvalue()) is None
    # A tie must remain unknown even for exact artwork.
    rumble = next(image for name, image in reference.entries if name == "Rumble")
    reference.entries.append(("Conflicting identity", rumble.copy()))
    assert reference.identify((FIXTURES / "1552.webp").read_bytes()) is None


def test_only_images_loaded_by_the_site_are_used_to_resolve_names(monkeypatch, tmp_path):
    monkeypatch.setattr(sofascore, "_PORTRAITS", {})
    monkeypatch.setattr(sofascore, "_PORTRAIT_ROOT", tmp_path)
    prefix = "https://img.sofascore.com/api/v1/character/"
    raw = (FIXTURES / "1552.webp").read_bytes()
    sofascore._observe_response(
        SimpleNamespace(
            url=prefix + "1552/image",
            status=200,
            headers={"content-type": "image/webp"},
            body=lambda: raw,
        )
    )
    capture = {
        "championImages": [prefix + "1552/image", prefix + "1596/image", ""],
        "championNames": ["Character image", "", "Kai'Sa"],
        "bans": [{"teamId": "home", "image": prefix + "1552/image", "label": ""}],
    }
    sofascore._resolve_portrait_labels(capture)
    assert capture["championNames"] == ["Rumble", None, "Kai'Sa"]
    assert capture["bans"][0]["champion"] == "Rumble"
    evidence = capture["portraitEvidence"][prefix + "1552/image"]
    assert evidence["sourceSha256"] == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / evidence["sourcePath"]).read_bytes() == raw
    assert len(evidence["referenceSha256"]) == 64


def test_ten_unlabelled_bans_survive_projection_and_later_identification():
    bans = [
        {"teamId": team, "champion": None, "championImage": f"portrait-{team}-{i}"}
        for team in ("home", "away")
        for i in range(5)
    ]
    assert unique_bans([*bans, bans[-1]]) == bans
    assert unique_bans([{"teamId": "home", "champion": None, "championImage": ""}]) == []
    game = {
        "number": 1,
        "status": "finished",
        "winner": "home",
        "winnerId": "home",
        "bans": bans,
        "sides": [{"position": side, "players": []} for side in ("home", "away")],
    }
    _, home, away = identities()
    projected = _rendered_maps(replace(event(), payload={"rendered": {"maps": [game]}}), home, away)
    assert projected[0]["bans"] == bans
    current = copy.deepcopy(game)
    current["bans"] = [{**bans[0], "champion": "Gnar"}]
    merged = merge_completed_map(game, current)
    assert len(merged["bans"]) == 10
    assert merged["bans"][0]["champion"] == "Gnar"
    assert game["bans"][0]["champion"] is None
    # A new contradictory draft cannot borrow unrelated older bans.
    current["bans"] = [{**bans[0], "champion": "Gnar", "championImage": "other"}]
    assert merge_completed_map(game, current)["bans"] == current["bans"]


def test_observed_dom_stats_picks_and_bans_survive_the_whole_projection(monkeypatch):
    reference = PortraitReference()
    records = json.loads((FIXTURES / "manifest.json").read_text())["assets"]
    monkeypatch.setattr(
        sofascore,
        "_PORTRAITS",
        {
            asset["url"]: {"name": reference.identify((FIXTURES / asset["file"]).read_bytes())}
            for asset in records
        },
    )
    capture = json.loads((FIXTURES / "rendered-map.json").read_text())
    sofascore._resolve_portrait_labels(capture)
    game = sofascore._rendered_map(capture, number=1, status="finished", source_id="17091782")
    _, home, away = identities()
    projected = _rendered_maps(
        replace(event(), payload={"rendered": {"maps": [game]}}), home, away
    )[0]
    assert projected["winnerId"] == "home"
    assert len(projected["bans"]) == 10
    assert projected["bans"][0]["champion"] == "Cassiopeia"
    assert projected["bans"][1]["champion"] is None
    assert projected["sides"][1]["players"][0]["champion"] == "Rumble"
    assert projected["sides"][0]["players"][2]["champion"] is None
    assert projected["sides"][0]["players"][0]["gold"] == 14400
    assert projected["sides"][0]["towers"] == 11
