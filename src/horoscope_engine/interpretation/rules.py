from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class RuleSet:
    sign_tone: Dict[str, str]
    section_weights: Dict[str, Dict[str, float]]
    planet_keywords: Dict[str, List[str]]
    aspect_keywords: Dict[str, str]


def load_rules(path: Path) -> RuleSet:
    payload = json.loads(path.read_text())
    return RuleSet(
        sign_tone=payload["sign_tone"],
        section_weights=payload["section_weights"],
        planet_keywords=payload["planet_keywords"],
        aspect_keywords=payload["aspect_keywords"],
    )
