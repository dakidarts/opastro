from __future__ import annotations

import logging
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Astro.com hosts the Swiss Ephemeris data files.
EPHE_BASE_URL = "https://www.astro.com/swisseph/ephe/"

# Files that can be fetched from the public Astro.com ephemeris directory.
DOWNLOADABLE_EPHE_FILES = {
    "seas_18.se1": "Asteroid / dwarf planet data (Eris, Chiron backup, etc.)",
}

# Swiss Ephemeris fixed-star calculations use this catalogue, but it is not
# available at the public Astro.com directory used by the downloader.
MANUAL_EPHE_FILES = {
    "sefstars.txt": "Fixed star catalogue (manual installation)",
}

# Keep one complete inventory for doctor output and backwards compatibility
# with callers that imported OPTIONAL_EPHE_FILES.
OPTIONAL_EPHE_FILES = {**DOWNLOADABLE_EPHE_FILES, **MANUAL_EPHE_FILES}


@dataclass(frozen=True)
class EphemerisDownloadReport:
    """Result of an optional ephemeris download attempt."""

    downloaded: list[Path]
    missing_downloadable: dict[str, str]


def _ensure_ssl_context() -> ssl.SSLContext:
    """Return an SSL context that works on macOS and older Python builds."""
    return ssl.create_default_context()


def download_ephemeris_file(
    filename: str,
    dest_dir: Path,
    base_url: str = EPHE_BASE_URL,
    overwrite: bool = False,
) -> Path:
    """Download a single Swiss Ephemeris file from Astro.com.

    Args:
        filename: e.g. ``"seas_18.se1"``
        dest_dir: Directory to write the file into.
        base_url: Source mirror (Astro.com by default).
        overwrite: Whether to replace an existing file.

    Returns:
        Path to the downloaded file.

    Raises:
        RuntimeError: If the download fails or the server returns an error.
    """
    dest_dir = Path(dest_dir).expanduser()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / filename

    if dest_path.exists() and not overwrite:
        logger.info("Ephemeris file already exists: %s", dest_path)
        return dest_path

    url = f"{base_url.rstrip('/')}/{filename}"
    logger.info("Downloading %s ...", url)

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "OpAstroEngine/1.0 (+https://github.com/dakidarts/opastro)"
                ),
            },
        )
        with urllib.request.urlopen(
            req, context=_ensure_ssl_context(), timeout=60
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Server returned {resp.status} for {url}")
            data = resp.read()
            dest_path.write_bytes(data)
    except Exception as exc:
        raise RuntimeError(f"Failed to download {filename}: {exc}") from exc

    logger.info("Saved %s (%d bytes)", dest_path, dest_path.stat().st_size)
    return dest_path


def ensure_minor_body_ephemeris(
    ephemeris_path: Optional[str] = None,
) -> list[Path]:
    """Download supported optional files and return downloaded paths."""
    return ensure_minor_body_ephemeris_report(ephemeris_path).downloaded


def ensure_minor_body_ephemeris_report(
    ephemeris_path: Optional[str] = None,
) -> EphemerisDownloadReport:
    """Download supported optional files and report any remaining gaps.

    Fixed-star data is intentionally excluded from the automatic download
    list because the configured public source does not host ``sefstars.txt``.
    """
    if ephemeris_path:
        dest = Path(ephemeris_path).expanduser()
    else:
        dest = Path.home() / ".cache" / "opastro" / "ephemeris"

    downloaded: list[Path] = []
    for filename, description in DOWNLOADABLE_EPHE_FILES.items():
        target = dest / filename
        if not target.exists():
            try:
                path = download_ephemeris_file(filename, dest)
                downloaded.append(path)
            except RuntimeError as exc:
                logger.warning(
                    "Could not download %s (%s): %s", filename, description, exc
                )
    missing_downloadable = {
        filename: description
        for filename, description in DOWNLOADABLE_EPHE_FILES.items()
        if not (dest / filename).exists()
    }
    return EphemerisDownloadReport(
        downloaded=downloaded,
        missing_downloadable=missing_downloadable,
    )


def missing_ephemeris_files(ephemeris_path: Optional[str] = None) -> dict[str, str]:
    """Return a mapping of missing optional file names to their descriptions."""
    if ephemeris_path:
        dest = Path(ephemeris_path).expanduser()
    else:
        dest = Path.home() / ".cache" / "opastro" / "ephemeris"

    missing: dict[str, str] = {}
    for filename, description in OPTIONAL_EPHE_FILES.items():
        if not (dest / filename).exists():
            missing[filename] = description
    return missing
