from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .models import Period


TIP_KEY_BY_PERIOD = {
    Period.DAILY: "daily_tip",
    Period.WEEKLY: "weekly_tip",
    Period.MONTHLY: "monthly_tip",
    Period.YEARLY: "yearly_tip",
}


def stable_index(seed: str, size: int) -> int:
    if size <= 0:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


@dataclass(frozen=True)
class ContentSelection:
    factor_type: str
    factor_value: str
    variant_id: str
    content_blocks: dict
    tip_key: str
    source_file: str


class V2ContentRepository:
    def __init__(self, root: Path):
        self.root = root

    def has_period_data(self, period: Period) -> bool:
        period_dir = self._resolve_child_dir(self.root, period.value)
        return bool(period_dir and period_dir.exists())

    def select(
        self,
        period: Period,
        sign: str,
        section_candidates: Sequence[str],
        intensity: str,
        factor_candidates: Sequence[Tuple[str, str]],
        seed: str,
        allow_section_fallback: bool = True,
        allow_any_value_for_factor: bool = True,
    ) -> Optional[ContentSelection]:
        period_dir = self._resolve_child_dir(self.root, period.value)
        if not period_dir:
            return None
        sign_dir = self._resolve_child_dir(period_dir, sign)
        if not sign_dir:
            return None

        for section_name in section_candidates:
            section_dir = self._resolve_child_dir(sign_dir, section_name)
            if not section_dir:
                continue

            for factor_type, factor_value in factor_candidates:
                selection = self._select_specific(
                    section_dir=section_dir,
                    period=period,
                    intensity=intensity,
                    factor_type=factor_type,
                    factor_value=factor_value,
                    seed=seed,
                )
                if selection:
                    return selection
                if allow_any_value_for_factor:
                    selection = self._select_any_value_for_factor_type(
                        section_dir=section_dir,
                        period=period,
                        intensity=intensity,
                        factor_type=factor_type,
                        seed=seed,
                    )
                    if selection:
                        return selection

            if allow_section_fallback:
                fallback = self._select_fallback_any_factor(
                    section_dir=section_dir,
                    period=period,
                    intensity=intensity,
                    seed=seed,
                )
                if fallback:
                    return fallback

        return None

    def _select_any_value_for_factor_type(
        self,
        section_dir: Path,
        period: Period,
        intensity: str,
        factor_type: str,
        seed: str,
    ) -> Optional[ContentSelection]:
        factor_type_dir = self._resolve_child_dir(section_dir, factor_type)
        if not factor_type_dir:
            return None

        matches: List[Path] = []
        for factor_value_dir in factor_type_dir.iterdir():
            if not factor_value_dir.is_dir():
                continue
            intensity_dir = self._resolve_child_dir(factor_value_dir, intensity)
            if not intensity_dir:
                continue
            matches.extend(sorted(intensity_dir.glob("*.json")))
        if not matches:
            return None

        file_path = matches[stable_index(f"{seed}|{factor_type}|any_value", len(matches))]
        rel = file_path.relative_to(self.root).parts
        factor_value = rel[4] if len(rel) > 4 else "unknown"
        return self._selection_from_file(
            file_path=file_path,
            period=period,
            factor_type=factor_type,
            factor_value=factor_value,
            seed=seed,
        )

    def _select_specific(
        self,
        section_dir: Path,
        period: Period,
        intensity: str,
        factor_type: str,
        factor_value: str,
        seed: str,
    ) -> Optional[ContentSelection]:
        factor_type_dir = self._resolve_child_dir(section_dir, factor_type)
        if not factor_type_dir:
            return None
        factor_value_dir = self._resolve_child_dir(factor_type_dir, factor_value)
        if not factor_value_dir:
            return None
        intensity_dir = self._resolve_child_dir(factor_value_dir, intensity)
        if not intensity_dir:
            return None

        files = sorted(intensity_dir.glob("*.json"))
        if not files:
            return None
        file_path = files[stable_index(f"{seed}|{factor_type}|{factor_value}", len(files))]
        return self._selection_from_file(
            file_path=file_path,
            period=period,
            factor_type=factor_type,
            factor_value=factor_value,
            seed=seed,
        )

    def _select_fallback_any_factor(
        self,
        section_dir: Path,
        period: Period,
        intensity: str,
        seed: str,
    ) -> Optional[ContentSelection]:
        matches: List[Path] = []
        for factor_type_dir in section_dir.iterdir():
            if not factor_type_dir.is_dir():
                continue
            for factor_value_dir in factor_type_dir.iterdir():
                if not factor_value_dir.is_dir():
                    continue
                intensity_dir = self._resolve_child_dir(factor_value_dir, intensity)
                if not intensity_dir:
                    continue
                matches.extend(sorted(intensity_dir.glob("*.json")))

        if not matches:
            return None

        file_path = matches[stable_index(f"{seed}|fallback", len(matches))]
        rel = file_path.relative_to(self.root).parts
        # .../<period>/<sign>/<section>/<factor_type>/<factor_value>/<intensity>/<file>.json
        factor_type = rel[3] if len(rel) > 3 else "unknown"
        factor_value = rel[4] if len(rel) > 4 else "unknown"
        return self._selection_from_file(
            file_path=file_path,
            period=period,
            factor_type=factor_type,
            factor_value=factor_value,
            seed=seed,
        )

    def _selection_from_file(
        self,
        file_path: Path,
        period: Period,
        factor_type: str,
        factor_value: str,
        seed: str,
    ) -> Optional[ContentSelection]:
        try:
            payload = json.loads(file_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

        sections = payload.get("sections") or []
        if not sections:
            return None
        factor_blocks = sections[0].get("factor_blocks") or {}
        if not factor_blocks:
            return None

        normalized_factor_type = normalize_key(factor_type)
        normalized_factor_value = normalize_key(factor_value)

        for key, value in factor_blocks.items():
            if normalize_key(key) != normalized_factor_type:
                continue
            variant_list = self._variant_list_for_value(value, normalized_factor_value)
            if variant_list:
                chosen = variant_list[stable_index(f"{seed}|variant|{file_path.name}", len(variant_list))]
                return self._build_selection(
                    period=period,
                    factor_type=key,
                    factor_value=factor_value,
                    chosen=chosen,
                    file_path=file_path,
                )

        # Fallback to first factor/value if key normalization still fails.
        first_type = next(iter(factor_blocks.keys()))
        first_values = factor_blocks[first_type]
        first_value_key = next(iter(first_values.keys()))
        variant_list = first_values[first_value_key]
        if not variant_list:
            return None
        chosen = variant_list[stable_index(f"{seed}|variant|{file_path.name}", len(variant_list))]
        return self._build_selection(
            period=period,
            factor_type=first_type,
            factor_value=first_value_key,
            chosen=chosen,
            file_path=file_path,
        )

    def _build_selection(
        self,
        period: Period,
        factor_type: str,
        factor_value: str,
        chosen: dict,
        file_path: Path,
    ) -> Optional[ContentSelection]:
        content_blocks = chosen.get("content_blocks") or {}
        if not content_blocks:
            return None
        return ContentSelection(
            factor_type=factor_type,
            factor_value=factor_value,
            variant_id=str(chosen.get("variant_id", "unknown")),
            content_blocks=content_blocks,
            tip_key=TIP_KEY_BY_PERIOD[period],
            source_file=str(file_path),
        )

    def _variant_list_for_value(self, value_map: dict, normalized_factor_value: str) -> Optional[list]:
        for key, variants in value_map.items():
            if normalize_key(key) == normalized_factor_value:
                return variants
        return None

    def _resolve_child_dir(self, parent: Path, target: str) -> Optional[Path]:
        if not parent.exists():
            return None

        direct = parent / target
        if direct.is_dir():
            return direct

        lower = parent / target.lower()
        if lower.is_dir():
            return lower

        upper = parent / target.upper()
        if upper.is_dir():
            return upper

        normalized_target = normalize_key(target)
        for child in parent.iterdir():
            if child.is_dir() and normalize_key(child.name) == normalized_target:
                return child
        return None
