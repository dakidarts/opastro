from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

TIP_KEY_BY_PERIOD = {
    "daily": "daily_tip",
    "weekly": "weekly_tip",
    "monthly": "monthly_tip",
    "yearly": "yearly_tip",
}

VALID_PERIODS = set(TIP_KEY_BY_PERIOD.keys())

PERIOD_TEMPORAL_TOKEN_PATTERNS: Dict[str, re.Pattern[str]] = {
    "daily": re.compile(
        r"\b(today|today['’]s|this day|day ahead|the day ahead|day[- ]?long|daily)\b",
        flags=re.IGNORECASE,
    ),
    "weekly": re.compile(
        r"\b(this week|this week['’]s|the week|week ahead|the week ahead|week[- ]?long|weekly)\b",
        flags=re.IGNORECASE,
    ),
    "monthly": re.compile(
        r"\b(this month|this month['’]s|the month|month ahead|the month ahead|month[- ]?long|monthly)\b",
        flags=re.IGNORECASE,
    ),
    "yearly": re.compile(
        r"\b(this year|this year['’]s|the year|year ahead|the year ahead|year[- ]?long|yearly)\b",
        flags=re.IGNORECASE,
    ),
}


def _iter_content_strings(payload: object) -> Iterator[Tuple[str, str]]:
    if not isinstance(payload, dict):
        return
    sections = payload.get("sections")
    if not isinstance(sections, list):
        return
    for sec_idx, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        factor_blocks = section.get("factor_blocks")
        if not isinstance(factor_blocks, dict):
            continue
        for factor_type, factor_map in factor_blocks.items():
            if not isinstance(factor_map, dict):
                continue
            for factor_value, variants in factor_map.items():
                if not isinstance(variants, list):
                    continue
                for var_idx, variant in enumerate(variants):
                    if not isinstance(variant, dict):
                        continue
                    content_blocks = variant.get("content_blocks")
                    if not isinstance(content_blocks, dict):
                        continue
                    for block_key, lines in content_blocks.items():
                        if not isinstance(lines, list):
                            continue
                        for line_idx, line in enumerate(lines):
                            if isinstance(line, str):
                                location = (
                                    f"sections[{sec_idx}].factor_blocks.{factor_type}.{factor_value}."
                                    f"variants[{var_idx}].content_blocks.{block_key}[{line_idx}]"
                                )
                                yield location, line


def _period_json_files(
    content_root: Path, period: str, factor_type: Optional[str]
) -> Iterable[Path]:
    period_root = (
        content_root / period if (content_root / period).exists() else content_root
    )
    if factor_type:
        pattern = f"*/*/{factor_type}/*/*/*.json"
    else:
        pattern = "*/*/*/*/*/*.json"
    return sorted(period_root.glob(pattern))


def validate_period_temporal_tokens(
    *,
    period: str,
    content_root: Path,
    factor_type: Optional[str] = None,
    max_issues: int = 100,
) -> List[str]:
    period_key = str(period).strip().lower()
    if period_key not in VALID_PERIODS:
        return [f"invalid period '{period}'"]

    resolved_factor_type = factor_type
    if resolved_factor_type is None:
        resolved_factor_type = f"{period_key}_house_focus"

    issues: List[str] = []
    files = _period_json_files(
        content_root, period_key, factor_type=resolved_factor_type
    )
    if not files:
        scope = resolved_factor_type or f"all {period_key} factors"
        return [
            f"{period_key} temporal preflight: no files found for scope '{scope}' under {content_root}"
        ]

    disallowed = {
        label: pattern
        for label, pattern in PERIOD_TEMPORAL_TOKEN_PATTERNS.items()
        if label != period_key
    }

    for file_path in files:
        try:
            payload = json.loads(file_path.read_text())
        except (OSError, json.JSONDecodeError):
            issues.append(
                f"{period_key} temporal preflight: unreadable json file {file_path}"
            )
            if len(issues) >= max_issues:
                break
            continue

        rel_path = str(file_path)
        for location, text in _iter_content_strings(payload):
            for label, pattern in disallowed.items():
                match = pattern.search(text)
                if match:
                    token = match.group(0)
                    issues.append(
                        f"{period_key} temporal leakage [{label}] in {rel_path} @ {location}: '{token}'"
                    )
                    break
            if len(issues) >= max_issues:
                break
        if len(issues) >= max_issues:
            break

    return issues


def validate_daily_temporal_tokens(
    *,
    content_root: Path,
    factor_type: Optional[str] = "daily_house_focus",
    max_issues: int = 100,
) -> List[str]:
    return validate_period_temporal_tokens(
        period="daily",
        content_root=content_root,
        factor_type=factor_type,
        max_issues=max_issues,
    )


def _extract_factor_regex(payload: object) -> Optional[str]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and key.startswith("^") and key.endswith("$"):
                return key
            nested = _extract_factor_regex(value)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = _extract_factor_regex(item)
            if nested:
                return nested
    return None


def validate_generation_contract(
    *,
    period: str,
    schema_path: Path,
    factor_values: Sequence[str],
    tip_key: str,
) -> List[str]:
    issues: List[str] = []
    period_key = str(period).strip().lower()
    if period_key not in VALID_PERIODS:
        return [f"invalid period '{period}'"]

    schema_name = schema_path.name.lower()
    if period_key not in schema_name:
        issues.append(
            f"schema file name mismatch: expected period '{period_key}' in '{schema_path.name}'"
        )

    try:
        payload = json.loads(schema_path.read_text())
    except (OSError, json.JSONDecodeError):
        return [f"schema unreadable: {schema_path}"]

    factor_pattern_text = _extract_factor_regex(payload)
    if not factor_pattern_text:
        return [f"factor regex not found in schema: {schema_path.name}"]

    try:
        factor_pattern = re.compile(factor_pattern_text)
    except re.error:
        return [f"invalid factor regex in schema: {schema_path.name}"]

    for factor in factor_values:
        if not factor_pattern.fullmatch(factor):
            issues.append(
                f"schema regex missing factor '{factor}' for period '{period_key}'"
            )

    expected_tip_key = TIP_KEY_BY_PERIOD[period_key]
    if tip_key != expected_tip_key:
        issues.append(
            f"tip key mismatch: period '{period_key}' expects '{expected_tip_key}', got '{tip_key}'"
        )

    return issues
