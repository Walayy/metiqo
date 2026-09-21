"""Build an offline portrait reference from the already downloaded Riot assets."""

import base64
import hashlib
import json
from pathlib import Path

from PIL import Image

root = Path(__file__).resolve().parents[1]
public = root / "apps/web/public"
manifest = root / "apps/web/src/domain/data/champions.json"
destination = root / "apps/worker/src/metiquo_worker/data/champion-portraits.json"
entries = []
for item in json.loads(manifest.read_text(encoding="utf-8")):
    path = (public / item["image"].lstrip("/")).resolve()
    if not path.is_relative_to(public.resolve()):
        raise ValueError("Portrait path escapes public assets")
    with Image.open(path) as image:
        pixels = image.convert("RGB").resize((32, 32), Image.Resampling.BICUBIC).tobytes()
    entries.append(
        {
            "id": item["id"],
            "name": item["name"],
            "source": item["source"],
            "version": item["version"],
            "retrievedAt": item["retrievedAt"],
            "sourceSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rgb32": base64.b64encode(pixels).decode("ascii"),
        }
    )
destination.parent.mkdir(parents=True, exist_ok=True)
temporary = destination.with_suffix(".json.tmp")
temporary.write_text(
    json.dumps({"schema": 1, "portraits": entries}, ensure_ascii=False) + "\n", encoding="utf-8"
)
temporary.replace(destination)
print(f"Built {len(entries)} offline champion references; no network requests.")
