"""Identify near-identical Riot artwork already rendered by the source browser."""

import base64
import hashlib
import io
import json
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from metiquo_worker.artifacts import store_bytes


class PortraitReference:
    def __init__(self, path: Path | None = None):
        path = path or Path(__file__).with_name("data") / "champion-portraits.json"
        raw = path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.entries: list[tuple[str, Image.Image]] = []
        self.labels: dict[str, str] = {}
        for entry in json.loads(raw)["portraits"]:
            self.labels[self.key(entry["id"])] = entry["name"]
            self.labels[self.key(entry["name"])] = entry["name"]
            self.entries.append(
                (
                    entry["name"],
                    Image.frombytes(
                        "RGB", (32, 32), base64.b64decode(entry["rgb32"], validate=True)
                    ),
                )
            )

    @staticmethod
    def key(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    def label(self, value: object) -> str | None:
        return self.labels.get(self.key(value)) if isinstance(value, str) else None

    def identify(self, raw: bytes) -> str | None:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width > 1024 or image.height > 1024 or min(image.size) < 24:
                return None
            candidate = image.convert("RGB").resize((32, 32), Image.Resampling.BICUBIC)
        scores = sorted(
            (sum(ImageStat.Stat(ImageChops.difference(candidate, reference)).mean) / 3, name)
            for name, reference in self.entries
        )
        # Only near-identical artwork. Do not select the "closest" champion
        # when a skin, changed portrait, placeholder or ambiguous image appears.
        if len(scores) < 2 or scores[0][0] > 3 or scores[1][0] - scores[0][0] < 12:
            return None
        return scores[0][1]


def record_portrait(raw: bytes, reference: PortraitReference, root: Path) -> dict[str, object]:
    digest, path = store_bytes(root, "sofascore-portraits", raw, "bin")
    return {
        "name": reference.identify(raw),
        "sourceSha256": digest,
        "sourcePath": path,
        "referenceSha256": reference.sha256,
        "method": "rendered-portrait-match",
    }
