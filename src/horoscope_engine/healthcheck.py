from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

from .interpretation.renderer import (
    DAILY_FACTOR_ORDER,
    MONTHLY_FACTOR_ORDER,
    WEEKLY_FACTOR_ORDER,
    YEARLY_FACTOR_ORDER,
)
from .models import Period


PERIOD_FACTOR_ORDERS: Dict[Period, Sequence[str]] = {
    Period.DAILY: DAILY_FACTOR_ORDER,
    Period.WEEKLY: WEEKLY_FACTOR_ORDER,
    Period.MONTHLY: MONTHLY_FACTOR_ORDER,
    Period.YEARLY: YEARLY_FACTOR_ORDER,
}

SCHEMA_FILE_BY_PERIOD: Dict[Period, str] = {
    Period.DAILY: "kaggle_content_schema_daily_V2.json",
    Period.WEEKLY: "kaggle_content_schema_weekly_V2.json",
    Period.MONTHLY: "kaggle_content_schema_monthly_V2.json",
    Period.YEARLY: "kaggle_content_schema_yearly_V2.json",
}


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


def _collect_factor_types(period_dir: Path) -> Set[str]:
    factor_types: Set[str] = set()
    for sign_dir in period_dir.iterdir():
        if not sign_dir.is_dir():
            continue
        for section_dir in sign_dir.iterdir():
            if not section_dir.is_dir():
                continue
            for factor_dir in section_dir.iterdir():
                if factor_dir.is_dir():
                    factor_types.add(factor_dir.name)
    return factor_types


def run_content_coverage_healthcheck(
    *,
    content_root: Path,
    schema_root: Path,
    periods: Optional[Iterable[Period]] = None,
) -> List[str]:
    issues: List[str] = []
    selected_periods = (
        list(periods) if periods is not None else list(PERIOD_FACTOR_ORDERS.keys())
    )

    for period in selected_periods:
        period_dir = content_root / period.value
        if not period_dir.exists():
            issues.append(f"{period.value}: missing content root directory")
            continue

        expected = set(PERIOD_FACTOR_ORDERS[period])
        available = _collect_factor_types(period_dir)
        missing_in_content = sorted(expected - available)
        if missing_in_content:
            issues.append(
                f"{period.value}: missing factor directories in content packs: {', '.join(missing_in_content)}"
            )

        schema_file = schema_root / SCHEMA_FILE_BY_PERIOD[period]
        if not schema_file.exists():
            issues.append(f"{period.value}: missing schema file {schema_file.name}")
            continue

        try:
            schema_payload = json.loads(schema_file.read_text())
        except (OSError, json.JSONDecodeError):
            issues.append(
                f"{period.value}: schema file {schema_file.name} is unreadable"
            )
            continue

        pattern_text = _extract_factor_regex(schema_payload)
        if not pattern_text:
            issues.append(
                f"{period.value}: factor regex not found in schema {schema_file.name}"
            )
            continue

        try:
            pattern = re.compile(pattern_text)
        except re.error:
            issues.append(
                f"{period.value}: invalid factor regex in schema {schema_file.name}"
            )
            continue

        schema_misses = sorted(
            [factor for factor in expected if not pattern.fullmatch(factor)]
        )
        if schema_misses:
            issues.append(
                f"{period.value}: schema regex does not accept factors: {', '.join(schema_misses)}"
            )

    return issues
