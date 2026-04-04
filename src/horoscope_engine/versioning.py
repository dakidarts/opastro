from __future__ import annotations

import configparser
from importlib import metadata as importlib_metadata
from pathlib import Path


def _version_from_setup_cfg(path: Path) -> str | None:
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except Exception:
        return None
    version = parser.get("metadata", "version", fallback="").strip()
    return version or None


def resolve_version(package_name: str = "opastro") -> str:
    # Prefer local repo version when running from source (avoids stale installed metadata).
    repo_setup_cfg = Path(__file__).resolve().parents[2] / "setup.cfg"
    if repo_setup_cfg.exists():
        local_version = _version_from_setup_cfg(repo_setup_cfg)
        if local_version:
            return local_version
    try:
        return importlib_metadata.version(package_name)
    except importlib_metadata.PackageNotFoundError:
        return "dev"
