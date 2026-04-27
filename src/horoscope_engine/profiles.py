from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_PROFILE_NAME = "default"


def _default_config_dir() -> Path:
    override = os.getenv("OPASTRO_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "opastro"


class ProfileStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or (_default_config_dir() / "profiles.json")

    def _empty_payload(self) -> Dict[str, Any]:
        return {"active_profile": None, "profiles": {}}

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty_payload()
        try:
            payload = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return self._empty_payload()
        if not isinstance(payload, dict):
            return self._empty_payload()
        profiles = payload.get("profiles")
        if not isinstance(profiles, dict):
            profiles = {}
        active_profile = payload.get("active_profile")
        if active_profile is not None and not isinstance(active_profile, str):
            active_profile = None
        return {"active_profile": active_profile, "profiles": profiles}

    def _save(self, payload: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def list_profiles(self) -> List[str]:
        payload = self._load()
        return sorted(payload["profiles"].keys())

    def active_profile_name(self) -> Optional[str]:
        payload = self._load()
        active = payload.get("active_profile")
        if isinstance(active, str) and active in payload["profiles"]:
            return active
        return None

    def get_profile(self, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        payload = self._load()
        target = name or payload.get("active_profile")
        if not isinstance(target, str):
            return None
        profile = payload["profiles"].get(target)
        if not isinstance(profile, dict):
            return None
        return dict(profile)

    def save_profile(
        self, name: str, profile: Dict[str, Any], *, set_active: bool = False
    ) -> None:
        payload = self._load()
        payload["profiles"][name] = profile
        if set_active or payload.get("active_profile") is None:
            payload["active_profile"] = name
        self._save(payload)

    def use_profile(self, name: str) -> bool:
        payload = self._load()
        if name not in payload["profiles"]:
            return False
        payload["active_profile"] = name
        self._save(payload)
        return True
