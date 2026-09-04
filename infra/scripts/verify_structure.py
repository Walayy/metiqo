from __future__ import annotations

from pathlib import Path


REQUIRED_DIRECTORIES = (
    "apps/web",
    "services/api",
    "services/worker",
    "packages/contracts",
    "packages/ui",
    "packages/config",
    "python/metiquo/data_sources",
    "python/metiquo/ingestion",
    "python/metiquo/canonical",
    "python/metiquo/features",
    "python/metiquo/markets",
    "python/metiquo/models",
    "python/metiquo/pricing",
    "python/metiquo/signals",
    "python/metiquo/paper",
    "python/metiquo/ops",
    "infra/compose",
    "infra/gateway",
    "infra/scripts",
    "tests/fixtures",
    "tests/integration",
    "tests/model",
    "tests/e2e",
    "docs",
)

REQUIRED_FILES = (
    ".editorconfig",
    ".gitattributes",
    ".gitignore",
    ".node-version",
    ".python-version",
    "README.md",
    "docs/progress.md",
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def missing_paths(root: Path) -> list[str]:
    missing_directories = [
        path for path in REQUIRED_DIRECTORIES if not (root / path).is_dir()
    ]
    missing_files = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    return [*missing_directories, *missing_files]


def main() -> int:
    missing = missing_paths(repository_root())
    if missing:
        for path in missing:
            print(f"MISSING {path}")
        return 1

    print("Metiquo repository structure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
