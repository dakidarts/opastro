"""Best-effort update checks against the project's latest GitHub release."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .versioning import resolve_version

DEFAULT_REPOSITORY = "dakidarts/opastro"
DEFAULT_CACHE_TTL = timedelta(hours=24)
VERSION_PATTERN = re.compile(r"^[vV]?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?$")


@dataclass(frozen=True)
class UpdateCheckResult:
    current_version: str
    latest_version: Optional[str] = None
    latest_tag: Optional[str] = None
    release_url: Optional[str] = None
    checked_at: Optional[datetime] = None
    checked: bool = False
    from_cache: bool = False
    error: Optional[str] = None

    @property
    def update_available(self) -> bool:
        current = _version_key(self.current_version)
        latest = _version_key(self.latest_version or "")
        return bool(current and latest and latest > current)


def _version_key(value: str) -> tuple[int, int, int] | None:
    match = VERSION_PATTERN.match(value.strip())
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _repository() -> str:
    value = (os.getenv("OPASTRO_UPDATE_REPOSITORY") or DEFAULT_REPOSITORY).strip()
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        return value
    return DEFAULT_REPOSITORY


def _cache_path() -> Path:
    override = os.getenv("OPASTRO_UPDATE_CACHE")
    if override:
        return Path(override).expanduser()
    config_dir = os.getenv("OPASTRO_CONFIG_DIR")
    if config_dir:
        return Path(config_dir).expanduser() / "update-check.json"
    return Path.home() / ".cache" / "opastro" / "update-check.json"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _cached_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _cached_result(
    payload: dict[str, Any], current_version: str, *, error: str | None = None
) -> UpdateCheckResult | None:
    checked_at_raw = payload.get("checked_at")
    latest_version = payload.get("latest_version")
    if not isinstance(checked_at_raw, str) or not isinstance(latest_version, str):
        return None
    try:
        checked_at = _utc(datetime.fromisoformat(checked_at_raw))
    except ValueError:
        return None
    return UpdateCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        latest_tag=payload.get("latest_tag"),
        release_url=payload.get("release_url"),
        checked_at=checked_at,
        checked=True,
        from_cache=True,
        error=error,
    )


def _write_cache(path: Path, result: UpdateCheckResult) -> None:
    if not result.latest_version or not result.checked_at:
        return
    payload = {
        "checked_at": _utc(result.checked_at).isoformat(),
        "latest_version": result.latest_version,
        "latest_tag": result.latest_tag,
        "release_url": result.release_url,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        return


def _fetch_latest_release(repository: str, timeout: float) -> tuple[str, str | None]:
    url = f"https://api.github.com/repos/{repository}/releases/latest"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "opastro-update-checker",
        },
    )
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS URL
        payload = json.loads(response.read().decode("utf-8"))
    tag = payload.get("tag_name") if isinstance(payload, dict) else None
    if not isinstance(tag, str) or not _version_key(tag):
        raise ValueError("GitHub latest release did not contain a semantic tag")
    release_url = payload.get("html_url") if isinstance(payload, dict) else None
    return tag, release_url if isinstance(release_url, str) else None


def check_for_update(
    *,
    current_version: str | None = None,
    cache_path: Path | None = None,
    force: bool = False,
    now: datetime | None = None,
    timeout: float | None = None,
    cache_ttl: timedelta = DEFAULT_CACHE_TTL,
) -> UpdateCheckResult:
    """Return update information without allowing network failures to escape."""
    current = current_version or resolve_version("opastro")
    mode = (os.getenv("OPASTRO_UPDATE_CHECK") or "").strip().lower()
    if mode in {"0", "false", "off", "disabled", "no"}:
        return UpdateCheckResult(current_version=current)
    if mode in {"1", "true", "always", "force"}:
        force = True

    checked_at = _utc(now or datetime.now(timezone.utc))
    path = cache_path or _cache_path()
    cached = _cached_payload(path)
    cached_result = _cached_result(cached, current) if cached else None
    if (
        cached_result
        and cached_result.checked_at
        and not force
        and checked_at - cached_result.checked_at <= cache_ttl
    ):
        return cached_result

    try:
        timeout_seconds = timeout
        if timeout_seconds is None:
            timeout_seconds = float(os.getenv("OPASTRO_UPDATE_TIMEOUT", "1.2"))
        timeout_seconds = min(10.0, max(0.1, timeout_seconds))
        tag, release_url = _fetch_latest_release(_repository(), timeout_seconds)
        latest_version = tag.lstrip("vV")
        result = UpdateCheckResult(
            current_version=current,
            latest_version=latest_version,
            latest_tag=tag,
            release_url=release_url,
            checked_at=checked_at,
            checked=True,
        )
        _write_cache(path, result)
        return result
    except (HTTPError, URLError, OSError, ValueError, TimeoutError) as exc:
        if cached_result:
            return UpdateCheckResult(
                current_version=current,
                latest_version=cached_result.latest_version,
                latest_tag=cached_result.latest_tag,
                release_url=cached_result.release_url,
                checked_at=cached_result.checked_at,
                checked=True,
                from_cache=True,
                error=str(exc),
            )
        return UpdateCheckResult(
            current_version=current,
            checked=True,
            checked_at=checked_at,
            error=str(exc),
        )


def update_notice(result: UpdateCheckResult) -> str | None:
    if not result.update_available or not result.latest_version:
        return None
    target = f" ({result.release_url})" if result.release_url else ""
    return (
        f"Update available: opastro {result.current_version} -> "
        f"{result.latest_version}{target}. Run `pip install --upgrade opastro`."
    )
