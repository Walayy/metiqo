"""Installer uniquement les binaires officiels épinglés et vérifiés avant extraction."""

import argparse
import hashlib
import json
import platform
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def install_tool(name: str) -> Path:
    if name not in {"gitleaks", "trivy"}:
        raise ValueError("Outil de sécurité inconnu")
    system = platform.system().lower()
    if system not in {"windows", "linux"} or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Cette installation vérifiée prend en charge Windows/Linux x64")
    configuration = json.loads((ROOT / "config/security-tools.json").read_text(encoding="utf-8"))[
        name
    ]
    source = configuration[system]
    directory = ROOT / "data/tools" / f"{name}-{configuration['version']}"
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / source["asset"]
    if not archive.exists():
        url = (
            f"https://github.com/{configuration['repository']}/releases/download/"
            f"v{configuration['version']}/{source['asset']}"
        )
        temporary = directory / (source["asset"] + ".part")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as stream:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 256 * 1024 * 1024:
                    raise RuntimeError("Archive trop volumineuse")
                stream.write(chunk)
        temporary.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != source["sha256"]:
        raise RuntimeError("Empreinte de l'archive incorrecte ; exécution refusée")
    executable = name + (".exe" if system == "windows" else "")
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            payload = bundle.read(executable)
    else:
        with tarfile.open(archive) as bundle:
            member = bundle.getmember(executable)
            if not member.isfile():
                raise RuntimeError("Le binaire attendu doit être un fichier régulier")
            reader = bundle.extractfile(member)
            if reader is None:
                raise RuntimeError("Binaire absent de l'archive")
            payload = reader.read()
    target = directory / executable
    if not target.exists() or target.read_bytes() != payload:
        target.write_bytes(payload)
    target.chmod(0o755)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", choices=("all", "gitleaks", "trivy"), default="all")
    args = parser.parse_args()
    names = ("gitleaks", "trivy") if args.tool == "all" else (args.tool,)
    print(json.dumps({name: str(install_tool(name)) for name in names}))


if __name__ == "__main__":
    main()
