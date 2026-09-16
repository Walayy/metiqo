import csv
import hashlib
import io
import zipfile
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from metiquo_worker.archive import (
    SourceFile,
    csv_records,
    download_export,
    is_export_url,
    persist_artifact,
    validate_archive,
)
from metiquo_worker.sources.oracle import parse_inventory, select_files
from metiquo_worker.sources.stake import StakeSource

HEADER = ["gameid", "participantid", "teamid", "playerid", "date", "year", "league"]


def csv_bytes(rows=None):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(HEADER)
    writer.writerows(
        rows
        or [
            ["game-1", "1", "oe:team:1", "player1", "2026-09-15 09:47:51", "2027", "LIT"],
            ["game-1", "2", "oe:team:1", "player2", "2026-09-15 09:47:51", "2027", "LIT"],
        ]
    )
    return output.getvalue().encode("utf-8-sig")


def make_archive(root: Path, payload: bytes | None = None, year: int = 2026):
    root.mkdir(parents=True, exist_ok=True)
    source = SourceFile(str(year), f"{year}_LoL_esports_match_data_from_OraclesElixir.csv", year)
    archive = root / "export.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(source.name, payload if payload is not None else csv_bytes())
    return archive, source


def test_archive_preserves_raw_season_and_naive_date(tmp_path):
    archive, source = make_archive(tmp_path)
    validated = validate_archive(archive, [source], tmp_path, 100_000)[0]
    rows = list(csv_records(validated.path))
    assert validated.row_count == 2
    assert rows[0]["year"] == "2027" and validated.source.year == 2026
    assert rows[0]["date"] == "2026-09-15 09:47:51"
    root = tmp_path / "artifacts"
    stored = persist_artifact(validated, root)
    assert hashlib.sha256((root / stored).read_bytes()).hexdigest() == validated.sha256
    assert persist_artifact(validated, root) == stored
    (root / stored).write_text("corrupt")
    with pytest.raises(ValueError, match="corrupt"):
        persist_artifact(validated, root)


@pytest.mark.parametrize(
    "payload",
    [
        b"<html>Google Drive - Quota exceeded</html>",
        csv_bytes([["too", "few"]]),
        (",".join(HEADER) + "\n").encode(),
        (",".join(HEADER + ["gameid"]) + "\nx,1,t,p,d,2026,LIT,x\n").encode(),
    ],
)
def test_invalid_csv_is_never_published(tmp_path, payload):
    archive, source = make_archive(tmp_path, payload)
    with pytest.raises(ValueError):
        validate_archive(archive, [source], tmp_path, 100_000)


@pytest.mark.parametrize("extra", ["../escape.csv", "unexpected.csv", "duplicate"])
def test_zip_inventory_is_exact(tmp_path, extra):
    archive, source = make_archive(tmp_path)
    with zipfile.ZipFile(archive, "a") as output:
        if extra == "duplicate":
            with pytest.warns(UserWarning):
                output.writestr(source.name, csv_bytes())
        else:
            output.writestr(extra, "bad")
    with pytest.raises(ValueError, match="inventory"):
        validate_archive(archive, [source], tmp_path, 100_000)
    assert not (tmp_path.parent / "escape.csv").exists()


def test_truncated_or_crc_corrupt_zip_rejected(tmp_path):
    archive, source = make_archive(tmp_path)
    archive.write_bytes(archive.read_bytes().replace(b"game-1", b"game-X", 1))
    with pytest.raises(zipfile.BadZipFile):
        validate_archive(archive, [source], tmp_path, 100_000)


def test_expansion_limit(tmp_path):
    archive, source = make_archive(tmp_path)
    with pytest.raises(ValueError, match="size limit"):
        validate_archive(archive, [source], tmp_path, 1)


@pytest.mark.parametrize(
    "url",
    [
        "http://storage.googleapis.com/drive-bulk-export-anonymous/a",
        "https://storage.googleapis.com.attacker.test/drive-bulk-export-anonymous/a",
        "https://storage.googleapis.com/other/a",
        "https://user@storage.googleapis.com/drive-bulk-export-anonymous/a",
        "https://storage.googleapis.com:444/drive-bulk-export-anonymous/a",
    ],
)
def test_export_origin_is_restricted(url):
    assert not is_export_url(url)


def test_dynamic_inventory_and_companion_selection():
    html = "".join(
        f'<tr data-id="file-{year}" data-target="doc"><strong>'
        f"{year}_LoL_esports_match_data_from_OraclesElixir.csv</strong></tr>"
        for year in (2014, 2026, 2027)
    )
    inventory = parse_inventory(html)
    assert [file.year for file in select_files(inventory, {2027})] == [2014, 2027]
    assert select_files(inventory, None) == inventory
    with pytest.raises(ValueError, match="absent"):
        select_files(inventory, {2030})
    with pytest.raises(ValueError, match="ambiguous"):
        parse_inventory(html + html)


def test_stake_is_explicitly_unimplemented():
    with pytest.raises(NotImplementedError):
        StakeSource().collect()


@pytest.mark.parametrize(
    "headers,body,maximum,expected",
    [
        ({"content-type": "text/html"}, b"Quota exceeded", 100, "HTML"),
        ({"content-length": "1000"}, b"small", 100, "limit"),
        ({"content-length": "10"}, b"small", 100, "Truncated"),
        ({"x-goog-hash": "md5=invalid"}, b"small", 100, "checksum"),
        ({}, b"too large", 4, "limit"),
    ],
)
def test_http_200_is_not_enough_to_accept_a_download(
    tmp_path, monkeypatch, headers, body, maximum, expected
):
    url = "https://storage.googleapis.com/drive-bulk-export-anonymous/test"

    @contextmanager
    def stream(*_args, **_kwargs):
        response = httpx.Response(
            200, headers=headers, content=body, request=httpx.Request("GET", url)
        )
        try:
            yield response
        finally:
            response.close()

    monkeypatch.setattr(httpx, "stream", stream)
    with pytest.raises(ValueError, match=expected):
        download_export(url, tmp_path / "file.zip", maximum)
