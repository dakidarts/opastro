from __future__ import annotations

import argparse
import curses
from contextlib import redirect_stdout
from datetime import date, datetime
import difflib
from html import escape as html_escape
import importlib
from io import StringIO
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap
from typing import Any, Optional

import uvicorn

from .config import ServiceConfig
from .models import (
    BirthData,
    BirthdayHoroscopeRequest,
    Coordinates,
    HoroscopeRequest,
    NatalBirthchartRequest,
    Period,
    PlanetHoroscopeRequest,
    PlanetName,
    Section,
    ZODIAC_SIGNS,
)
from .natal_artifacts import (
    build_house_overlay_map,
    build_natal_report_pdf,
    build_natal_wheel_png,
    build_natal_wheel_svg,
)
from .profiles import DEFAULT_PROFILE_NAME, ProfileStore
from .service import HoroscopeService
from .versioning import resolve_version

WELCOME_BANNER = r"""
   ____  ____   ___   _____ _______ ____   ____ 
  / __ \/ __ \ /   | / ___//_  __// __ \ / __ \
 / / / / /_/ // /| | \__ \  / /  / /_/ // / / /
/ /_/ / ____// ___ |___/ / / /  / _, _// /_/ / 
\____/_/    /_/  |_/____/ /_/  /_/ |_| \____/  
"""

UPSELL_TEXT = (
    "✨ Want deeper insights?\n"
    "→ Explore OpAstro CLI platform: https://opastro.com\n"
    "→ Unlock full readings: https://numerologyapi.com"
)

DEFAULT_WRAP_WIDTH = 96
MIN_PYTHON_VERSION = (3, 11)
OUTPUT_FORMATS = ("text", "json", "markdown", "html")
COMMAND_ALIASES = {
    "init": ["onboard"],
    "welcome": ["home"],
    "catalog": ["ls"],
    "doctor": ["diag"],
    "profile": ["profiles"],
    "horoscope": ["h"],
    "birthday": ["bday", "b"],
    "planet": ["p"],
    "natal": ["n"],
    "serve": ["api"],
    "explain": ["x"],
    "completion": ["comp", "completions"],
    "ui": ["tui"],
    "batch": ["gen"],
}

ACCENT_RGB = (61, 221, 119)  # #3ddd77
ACCENT_SOFT_RGB = (148, 244, 183)
ACCENT_FADE_RGB = (108, 230, 151)
ACCENT_DEEP_RGB = (46, 187, 101)
COLOR_ACCENT = f"38;2;{ACCENT_RGB[0]};{ACCENT_RGB[1]};{ACCENT_RGB[2]}"
COLOR_ACCENT_BOLD = f"1;{COLOR_ACCENT}"
COLOR_ACCENT_DIM = f"38;2;{ACCENT_FADE_RGB[0]};{ACCENT_FADE_RGB[1]};{ACCENT_FADE_RGB[2]}"
COLOR_ACCENT_SOFT = f"38;2;{ACCENT_SOFT_RGB[0]};{ACCENT_SOFT_RGB[1]};{ACCENT_SOFT_RGB[2]}"
COLOR_ACCENT_DEEP = f"38;2;{ACCENT_DEEP_RGB[0]};{ACCENT_DEEP_RGB[1]};{ACCENT_DEEP_RGB[2]}"


class OpastroArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return _render_themed_help(self)


def _app_version() -> str:
    return resolve_version("opastro")


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _parse_sections(raw: Optional[str]) -> Optional[list[str]]:
    if not raw:
        return None
    values = [value.strip() for value in raw.split(",") if value.strip()]
    return values or None


def _build_birth(args: argparse.Namespace) -> Optional[BirthData]:
    has_birth_extras = any(
        value is not None for value in (args.birth_time, args.lat, args.lon, args.timezone)
    )
    if not args.birth_date:
        if has_birth_extras:
            raise ValueError("Provide --birth-date when using --birth-time, --lat/--lon, or --timezone.")
        return None
    if (args.lat is None) != (args.lon is None):
        raise ValueError("Provide both --lat and --lon together.")

    coordinates = None
    if args.lat is not None and args.lon is not None:
        coordinates = Coordinates(latitude=args.lat, longitude=args.lon)

    return BirthData(
        date=_parse_date(args.birth_date),
        time=args.birth_time,
        coordinates=coordinates,
        timezone=args.timezone,
    )


def _build_base_parser() -> argparse.ArgumentParser:
    parser = OpastroArgumentParser(
        prog="opastro",
        description="Opastro CLI: deterministic horoscope engine with premium-grade terminal UX.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              opastro
              opastro init
              opastro profile list
              opastro horoscope --period daily --sign ARIES --target-date 2026-04-03
              opastro horoscope --period weekly --birth-date 1992-06-15 --birth-time 09:30 --lat 4.0511 --lon 9.7679 --timezone Africa/Douala
              opastro horoscope --period daily --sign ARIES --format markdown --export reports/aries.md
              opastro planet --period monthly --planet mercury --sign TAURUS
              opastro natal --birth-date 2004-06-14 --birth-time 09:30 --lat 4.0511 --lon 9.7679 --pdf reports/natal.pdf
              opastro serve --host 127.0.0.1 --port 8000 --reload
            """
        ).strip(),
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"opastro {_app_version()}",
        help="Show installed Opastro version and exit.",
    )
    subparsers = parser.add_subparsers(dest="command", parser_class=OpastroArgumentParser)

    init = subparsers.add_parser(
        "init",
        aliases=COMMAND_ALIASES["init"],
        help="Interactive setup for default profile and UX preferences.",
        description="Run guided onboarding to save a reusable default profile.",
    )
    init.add_argument(
        "--profile",
        default=DEFAULT_PROFILE_NAME,
        help=f"Profile name to create/update (default: {DEFAULT_PROFILE_NAME}).",
    )
    init.set_defaults(handler=_handle_init)

    welcome = subparsers.add_parser(
        "welcome",
        aliases=COMMAND_ALIASES["welcome"],
        help="Show the Opastro home screen and quick command guide.",
        description="Display the branded Opastro welcome UI and command overview.",
    )
    welcome.set_defaults(handler=_handle_welcome)

    catalog = subparsers.add_parser(
        "catalog",
        aliases=COMMAND_ALIASES["catalog"],
        help="List supported periods, sections, signs, and planets.",
        description="Print the command catalog for scripting and onboarding.",
    )
    catalog.set_defaults(handler=_handle_catalog)

    doctor = subparsers.add_parser(
        "doctor",
        aliases=COMMAND_ALIASES["doctor"],
        help="Run local environment diagnostics for Opastro.",
        description="Check Python runtime, executable path, and key engine readiness flags.",
    )
    doctor.add_argument("--fix", action="store_true", help="Attempt automatic fixes for detected dependency/runtime gaps.")
    doctor.add_argument("--dry-run", action="store_true", help="Show fix commands without executing them.")
    doctor.set_defaults(handler=_handle_doctor)

    profile = subparsers.add_parser(
        "profile",
        aliases=COMMAND_ALIASES["profile"],
        help="Manage saved CLI profiles (save/list/show/use).",
        description="Manage reusable defaults for sign/birth/preferences.",
    )
    profile.set_defaults(handler=_handle_profile_list)
    profile_sub = profile.add_subparsers(dest="profile_command", parser_class=OpastroArgumentParser)

    profile_list = profile_sub.add_parser(
        "list",
        help="List all saved profiles.",
        description="Show all profiles and highlight the active one.",
    )
    profile_list.set_defaults(handler=_handle_profile_list)

    profile_show = profile_sub.add_parser(
        "show",
        help="Show one profile (default: active).",
        description="Inspect stored profile fields.",
    )
    profile_show.add_argument("--name", help="Profile name. Defaults to active profile.")
    profile_show.set_defaults(handler=_handle_profile_show)

    profile_use = profile_sub.add_parser(
        "use",
        help="Set active profile.",
        description="Switch active profile used by report commands.",
    )
    profile_use.add_argument("name", help="Profile name to activate.")
    profile_use.set_defaults(handler=_handle_profile_use)

    profile_save = profile_sub.add_parser(
        "save",
        help="Create or update a profile.",
        description="Save profile defaults from explicit CLI flags.",
    )
    profile_save.add_argument("--name", required=True, help="Profile name to create/update.")
    profile_save.add_argument("--set-active", action="store_true", help="Set this profile as active after saving.")
    _add_profile_fields(profile_save)
    profile_save.set_defaults(handler=_handle_profile_save)

    horoscope = subparsers.add_parser(
        "horoscope",
        aliases=COMMAND_ALIASES["horoscope"],
        help="Generate a standard horoscope report.",
        description="Generate deterministic horoscope output for a sign or birth profile.",
    )
    _add_common_report_args(horoscope, require_period=True)
    horoscope.set_defaults(handler=_handle_horoscope)

    birthday = subparsers.add_parser(
        "birthday",
        aliases=COMMAND_ALIASES["birthday"],
        help="Generate a birthday-cycle report.",
        description="Generate a yearly birthday-cycle report with lite meanings.",
    )
    _add_common_report_args(birthday, require_period=False)
    birthday.set_defaults(handler=_handle_birthday)

    planet = subparsers.add_parser(
        "planet",
        aliases=COMMAND_ALIASES["planet"],
        help="Generate a planet-focused horoscope report.",
        description="Generate a report anchored on one selected planet across the chosen period.",
    )
    _add_common_report_args(planet, require_period=True)
    planet.add_argument(
        "--planet",
        required=True,
        choices=["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto", "chiron"],
        help="Planet to focus in the report.",
    )
    planet.set_defaults(handler=_handle_planet)

    natal = subparsers.add_parser(
        "natal",
        aliases=COMMAND_ALIASES["natal"],
        help="Generate natal birthchart insights + visual/download artifacts.",
        description="Generate natal report JSON/text and optionally export wheel SVG/PNG, house overlay map, and PDF.",
    )
    _add_natal_args(natal)
    natal.set_defaults(handler=_handle_natal)

    serve = subparsers.add_parser(
        "serve",
        aliases=COMMAND_ALIASES["serve"],
        help="Run the FastAPI service locally.",
        description="Run the Opastro API server for app and integration development.",
    )
    serve.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    serve.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000).")
    serve.add_argument("--reload", action="store_true", help="Enable dev reload mode.")
    serve.set_defaults(handler=_handle_serve)

    explain = subparsers.add_parser(
        "explain",
        aliases=COMMAND_ALIASES["explain"],
        help="Explain why each section line appeared (factor provenance).",
        description="Generate provenance-first output with factor and line rationale.",
    )
    explain.add_argument(
        "--kind",
        choices=["horoscope", "birthday", "planet"],
        default="horoscope",
        help="Report type to explain (default: horoscope).",
    )
    explain.add_argument("--period", choices=["daily", "weekly", "monthly", "yearly"], help="Report period.")
    explain.add_argument("--planet", choices=[p.value for p in PlanetName], help="Planet required for kind=planet.")
    _add_common_report_args(explain, require_period=False)
    explain.set_defaults(handler=_handle_explain)

    completion = subparsers.add_parser(
        "completion",
        aliases=COMMAND_ALIASES["completion"],
        help="Print shell completion script.",
        description="Generate shell completion for bash/zsh/fish.",
    )
    completion.add_argument("--shell", choices=["bash", "zsh", "fish"], required=True, help="Target shell.")
    completion.set_defaults(handler=_handle_completion)

    ui = subparsers.add_parser(
        "ui",
        aliases=COMMAND_ALIASES["ui"],
        help="Interactive TUI report browser with section drill-down.",
        description="Launch curses-based keyboard UI for report navigation.",
    )
    _add_common_report_args(ui, require_period=True)
    ui.add_argument("--no-interactive", action="store_true", help="Fallback to static text render (no curses).")
    ui.set_defaults(handler=_handle_ui)

    batch = subparsers.add_parser(
        "batch",
        aliases=COMMAND_ALIASES["batch"],
        help="Batch-generate reports for multiple signs and dates.",
        description="Run deterministic generation across many sign/date combinations.",
    )
    batch.add_argument("--kind", choices=["horoscope", "birthday", "planet"], default="horoscope")
    batch.add_argument("--period", required=True, choices=["daily", "weekly", "monthly", "yearly"])
    batch.add_argument("--planet", choices=[p.value for p in PlanetName], help="Required for kind=planet.")
    batch.add_argument("--signs", help="Comma-separated signs. Defaults to profile sign or all zodiac signs.")
    batch.add_argument("--target-date", help="Single ISO date YYYY-MM-DD.")
    batch.add_argument("--date-from", help="Range start ISO date YYYY-MM-DD.")
    batch.add_argument("--date-to", help="Range end ISO date YYYY-MM-DD.")
    batch.add_argument("--step-days", type=int, default=1, help="Step days for date ranges (default: 1).")
    batch.add_argument("--sections", help="Comma-separated sections.")
    batch.add_argument("--birth-date", help="Birth date in ISO format YYYY-MM-DD.")
    batch.add_argument("--birth-time", help="Birth time in HH:MM format.")
    batch.add_argument("--lat", type=float, help="Birth latitude.")
    batch.add_argument("--lon", type=float, help="Birth longitude.")
    batch.add_argument("--timezone", help="IANA timezone.")
    batch.add_argument("--zodiac-system", choices=["sidereal", "tropical"])
    batch.add_argument("--ayanamsa", choices=["lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"])
    batch.add_argument("--house-system", choices=["placidus", "whole_sign", "equal", "koch"])
    batch.add_argument("--node-type", choices=["true", "mean"])
    batch.add_argument("--tenant-id", help="Tenant identifier.")
    batch.add_argument("--format", dest="output_format", choices=OUTPUT_FORMATS, default="text")
    batch.add_argument("--export-dir", help="Directory for per-item exports.")
    batch.set_defaults(handler=_handle_batch)

    return parser


def _add_common_report_args(parser: argparse.ArgumentParser, *, require_period: bool) -> None:
    if require_period:
        parser.add_argument(
            "--period",
            required=True,
            choices=["daily", "weekly", "monthly", "yearly"],
            help="Report period.",
        )
    parser.add_argument("--sign", help="Zodiac sign (e.g. ARIES, TAURUS, GEMINI).")
    parser.add_argument("--target-date", help="ISO date used to anchor the report, format YYYY-MM-DD.")
    parser.add_argument(
        "--sections",
        help="Comma-separated sections. Example: general,career,money",
    )
    parser.add_argument("--birth-date", help="Birth date in ISO format YYYY-MM-DD.")
    parser.add_argument("--birth-time", help="Birth time in HH:MM format.")
    parser.add_argument("--lat", type=float, help="Birth latitude for personalized house calculations.")
    parser.add_argument("--lon", type=float, help="Birth longitude for personalized house calculations.")
    parser.add_argument("--timezone", help="IANA timezone, e.g. Africa/Douala.")
    parser.add_argument(
        "--zodiac-system",
        choices=["sidereal", "tropical"],
        help="Zodiac system override (default: tropical).",
    )
    parser.add_argument(
        "--ayanamsa",
        choices=["lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"],
        help="Ayanamsa override (sidereal mode).",
    )
    parser.add_argument(
        "--house-system",
        choices=["placidus", "whole_sign", "equal", "koch"],
        help="House system override.",
    )
    parser.add_argument(
        "--node-type",
        choices=["true", "mean"],
        help="Node type override.",
    )
    parser.add_argument(
        "--tenant-id",
        help="Optional tenant identifier for cache isolation and analytics.",
    )
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument(
        "--json",
        action="store_true",
        help="Output full raw JSON instead of the styled terminal report.",
    )
    output_mode.add_argument(
        "--format",
        dest="output_format",
        choices=OUTPUT_FORMATS,
        help="Output format override: text, json, markdown, html.",
    )
    parser.add_argument(
        "--export",
        help="Optional file path to save rendered output.",
    )


def _add_natal_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--birth-date", help="Birth date in ISO format YYYY-MM-DD.")
    parser.add_argument("--birth-time", help="Birth time in HH:MM format.")
    parser.add_argument("--lat", type=float, help="Birth latitude for house calculations.")
    parser.add_argument("--lon", type=float, help="Birth longitude for house calculations.")
    parser.add_argument("--timezone", help="IANA timezone, e.g. Africa/Douala.")
    parser.add_argument("--user-name", help="Display name for personalized natal chart branding.")
    parser.add_argument("--zodiac-system", choices=["sidereal", "tropical"])
    parser.add_argument("--ayanamsa", choices=["lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"])
    parser.add_argument("--house-system", choices=["placidus", "whole_sign", "equal", "koch"])
    parser.add_argument("--node-type", choices=["true", "mean"])
    parser.add_argument("--tenant-id", help="Tenant identifier.")
    parser.add_argument("--json", action="store_true", help="Output raw natal JSON.")
    parser.add_argument("--wheel-svg", help="Export wheel chart as SVG.")
    parser.add_argument("--wheel-png", help="Export wheel chart as PNG.")
    parser.add_argument("--house-map", help="Export house overlay map JSON.")
    parser.add_argument("--pdf", help="Export branded natal PDF report.")
    parser.add_argument("--brand-title", default="OPASTRO", help="Brand title for exported assets.")
    parser.add_argument("--brand-url", default="https://opastro.com", help="Brand URL for PDF footer.")
    parser.add_argument("--premium-url", default="https://numerologyapi.com", help="Premium URL callout in PDF.")
    parser.add_argument("--accent", default="#3ddd77", help="Hex accent color for visual exports.")
    parser.add_argument(
        "--wheel-theme",
        choices=["night", "day"],
        default="night",
        help="Wheel color theme for SVG/PNG/PDF exports.",
    )


def _add_profile_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user-name", help="Default display name for personalized natal charts.")
    parser.add_argument("--sign", help="Default zodiac sign, e.g. ARIES.")
    parser.add_argument("--birth-date", help="Default birth date in ISO format YYYY-MM-DD.")
    parser.add_argument("--birth-time", help="Default birth time in HH:MM format.")
    parser.add_argument("--lat", type=float, help="Default birth latitude.")
    parser.add_argument("--lon", type=float, help="Default birth longitude.")
    parser.add_argument("--timezone", help="Default timezone, e.g. Africa/Douala.")
    parser.add_argument("--sections", help="Default comma-separated sections.")
    parser.add_argument(
        "--zodiac-system",
        choices=["sidereal", "tropical"],
        help="Default zodiac system.",
    )
    parser.add_argument(
        "--ayanamsa",
        choices=["lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"],
        help="Default ayanamsa.",
    )
    parser.add_argument(
        "--house-system",
        choices=["placidus", "whole_sign", "equal", "koch"],
        help="Default house system.",
    )
    parser.add_argument(
        "--node-type",
        choices=["true", "mean"],
        help="Default node type.",
    )
    parser.add_argument("--tenant-id", help="Default tenant id.")
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=OUTPUT_FORMATS,
        help="Default output format for reports.",
    )


def _normalize_sign(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in ZODIAC_SIGNS:
        raise ValueError(f"Unsupported zodiac sign: {value}")
    return normalized


def _style(text: str, code: str, *, colorize: bool = True) -> str:
    if not colorize or not _should_colorize():
        return text
    return f"\033[{_adapt_color_code(code)}m{text}\033[0m"


def _should_colorize() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    mode = (os.getenv("OPASTRO_COLOR") or "").strip().lower()
    if mode in {"never", "0", "false", "off"}:
        return False
    if mode in {"always", "1", "true", "on"}:
        return True
    force_color = (os.getenv("CLICOLOR_FORCE") or os.getenv("FORCE_COLOR") or "").strip()
    if force_color and force_color not in {"0", "false", "False"}:
        return True
    term = (os.getenv("TERM") or "").strip().lower()
    if term == "dumb":
        return False
    return sys.stdout.isatty()


def _supports_truecolor() -> bool:
    if (os.getenv("OPASTRO_TRUECOLOR") or "").strip().lower() in {"1", "true", "on", "yes"}:
        return True
    if (os.getenv("OPASTRO_TRUECOLOR") or "").strip().lower() in {"0", "false", "off", "no"}:
        return False
    if (os.getenv("TERM_PROGRAM") or "").strip() == "Apple_Terminal":
        # Apple Terminal can render truecolor inconsistently depending on profile/theme.
        return False
    colorterm = (os.getenv("COLORTERM") or "").strip().lower()
    if "truecolor" in colorterm or "24bit" in colorterm:
        return True
    term = (os.getenv("TERM") or "").strip().lower()
    return "direct" in term


def _supports_256color() -> bool:
    term = (os.getenv("TERM") or "").strip().lower()
    return "256color" in term


def _rgb_to_ansi256(r: int, g: int, b: int) -> int:
    r = max(0, min(255, int(r)))
    g = max(0, min(255, int(g)))
    b = max(0, min(255, int(b)))
    if r == g == b:
        if r < 8:
            return 16
        if r > 248:
            return 231
        return 232 + int(round(((r - 8) / 247) * 24))
    r6 = int(round((r / 255) * 5))
    g6 = int(round((g / 255) * 5))
    b6 = int(round((b / 255) * 5))
    return 16 + (36 * r6) + (6 * g6) + b6


_TRUECOLOR_PATTERN = re.compile(r"(38|48);2;(\d{1,3});(\d{1,3});(\d{1,3})")


def _adapt_color_code(code: str) -> str:
    if _supports_truecolor():
        return code

    def _replace(match: re.Match[str]) -> str:
        channel = match.group(1)
        r, g, b = int(match.group(2)), int(match.group(3)), int(match.group(4))
        if _supports_256color():
            return f"{channel};5;{_rgb_to_ansi256(r, g, b)}"
        # 8-color fallback: force green family for brand consistency.
        return "32" if channel == "38" else "42"

    return _TRUECOLOR_PATTERN.sub(_replace, code)


def _style_rgb(text: str, rgb: tuple[int, int, int], *, bold: bool = False) -> str:
    code = f"38;2;{rgb[0]};{rgb[1]};{rgb[2]}"
    if bold:
        code = f"1;{code}"
    return _style(text, code)


def _gradient_lines(block: str, colors: list[tuple[int, int, int]], *, bold: bool = False) -> str:
    lines = block.splitlines()
    if not lines:
        return block
    if len(colors) == 1:
        return "\n".join(_style_rgb(line, colors[0], bold=bold) for line in lines)
    rendered: list[str] = []
    steps = max(1, len(lines) - 1)
    for idx, line in enumerate(lines):
        color_idx = int(round((idx / steps) * (len(colors) - 1)))
        color_idx = max(0, min(color_idx, len(colors) - 1))
        rendered.append(_style_rgb(line, colors[color_idx], bold=bold))
    return "\n".join(rendered)


def _term_width() -> int:
    return max(72, min(DEFAULT_WRAP_WIDTH, shutil.get_terminal_size((DEFAULT_WRAP_WIDTH, 20)).columns))


def _wrap(line: str, indent: str = "") -> str:
    return textwrap.fill(
        line,
        width=_term_width(),
        initial_indent=indent,
        subsequent_indent=indent,
    )


def _wrap_bullet(line: str, indent: str = "    - ") -> str:
    return textwrap.fill(
        line,
        width=_term_width(),
        initial_indent=indent,
        subsequent_indent=" " * len(indent),
    )


def _table_chars() -> dict[str, str]:
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    if "utf" not in encoding:
        return {
            "h": "-",
            "v": "|",
            "tl": "+",
            "tr": "+",
            "bl": "+",
            "br": "+",
            "tm": "+",
            "bm": "+",
            "mm": "+",
            "lm": "+",
            "rm": "+",
        }
    return {
        "h": "─",
        "v": "│",
        "tl": "┌",
        "tr": "┐",
        "bl": "└",
        "br": "┘",
        "tm": "┬",
        "bm": "┴",
        "mm": "┼",
        "lm": "├",
        "rm": "┤",
    }


def _cell_wrap(text: str, width: int) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return [""]
    chunks: list[str] = []
    for source_line in normalized.splitlines():
        pieces = textwrap.wrap(
            source_line,
            width=max(8, width),
            break_long_words=True,
            replace_whitespace=False,
        )
        chunks.extend(pieces if pieces else [""])
    return chunks or [""]


def _render_line_table(
    rows: list[tuple[str, str]],
    *,
    headers: tuple[str, str] = ("Item", "Description"),
    left_max_width: int = 34,
    left_min_width: int = 14,
    cell_padding: int = 1,
) -> str:
    if not rows:
        return ""

    chars = _table_chars()
    width = _term_width()
    pad = max(0, cell_padding)
    fixed_overhead = 3 + (pad * 4)
    left_seed = [headers[0], *[left for left, _ in rows]]
    left_width = min(max(left_min_width, max(len(value) for value in left_seed)), left_max_width)
    right_width = width - left_width - fixed_overhead
    if right_width < 24:
        left_width = max(10, width - (24 + fixed_overhead))
        right_width = max(16, width - left_width - fixed_overhead)

    top = (
        f"{chars['tl']}{chars['h'] * (left_width + pad * 2)}"
        f"{chars['tm']}{chars['h'] * (right_width + pad * 2)}{chars['tr']}"
    )
    mid = (
        f"{chars['lm']}{chars['h'] * (left_width + pad * 2)}"
        f"{chars['mm']}{chars['h'] * (right_width + pad * 2)}{chars['rm']}"
    )
    bottom = (
        f"{chars['bl']}{chars['h'] * (left_width + pad * 2)}"
        f"{chars['bm']}{chars['h'] * (right_width + pad * 2)}{chars['br']}"
    )

    lines: list[str] = [_style(top, COLOR_ACCENT_DIM)]

    def _emit_row(left: str, right: str, *, tone: Optional[str] = None) -> None:
        left_lines = _cell_wrap(left, left_width)
        right_lines = _cell_wrap(right, right_width)
        row_height = max(len(left_lines), len(right_lines))
        for idx in range(row_height):
            left_part = left_lines[idx] if idx < len(left_lines) else ""
            right_part = right_lines[idx] if idx < len(right_lines) else ""
            row_line = (
                f"{chars['v']}{' ' * pad}{left_part.ljust(left_width)}{' ' * pad}"
                f"{chars['v']}{' ' * pad}{right_part.ljust(right_width)}{' ' * pad}{chars['v']}"
            )
            lines.append(_style(row_line, tone) if tone else row_line)

    _emit_row(headers[0], headers[1], tone=COLOR_ACCENT_BOLD)
    lines.append(_style(mid, COLOR_ACCENT_DIM))
    for left, right in rows:
        _emit_row(left, right)
    lines.append(_style(bottom, COLOR_ACCENT_DIM))
    return "\n".join(lines)


def _formatter_action_strings(parser: argparse.ArgumentParser, action: argparse.Action) -> tuple[str, str]:
    formatter = parser._get_formatter()
    if action.option_strings:
        option_tokens = sorted(
            action.option_strings,
            key=lambda token: (0 if token.startswith("--") else 1, len(token), token),
        )
        if action.nargs == 0:
            invocation = ", ".join(option_tokens)
        else:
            metavar: str
            if action.metavar is not None:
                if isinstance(action.metavar, tuple):
                    metavar = " ".join(str(item) for item in action.metavar)
                else:
                    metavar = str(action.metavar)
            elif action.choices:
                metavar = "VALUE"
            else:
                metavar = action.dest.upper()
            primary = option_tokens[0]
            invocation = f"{primary} {metavar}"
    else:
        invocation = action.metavar if isinstance(action.metavar, str) else action.dest
        invocation = str(invocation)
    invocation = " ".join(invocation.split())
    if action.help in (None, argparse.SUPPRESS):
        description = ""
    else:
        description = " ".join(formatter._expand_help(action).split())

    if action.required and action.option_strings:
        description = f"{description} (required)".strip()

    if action.choices:
        choices = [str(choice) for choice in action.choices]
        if len(choices) > 5:
            preview = ", ".join(choices[:4]) + f", +{len(choices) - 4} more"
        else:
            preview = ", ".join(choices)
        choice_suffix = f"Choices: {preview}."
        description = f"{description} {choice_suffix}".strip()
    return invocation, description


def _collect_subcommand_rows(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for subaction in action._get_subactions():
            label = subaction.dest
            aliases = COMMAND_ALIASES.get(label)
            if aliases:
                label = f"{label} ({', '.join(aliases)})"
            description = subaction.help or ""
            rows.append((label, description))
    return rows


def _collect_option_rows(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for action in parser._actions:
        if action.help == argparse.SUPPRESS:
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        if action.option_strings:
            rows.append(_formatter_action_strings(parser, action))
    return rows


def _collect_argument_rows(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for action in parser._actions:
        if action.help == argparse.SUPPRESS:
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        if not action.option_strings:
            rows.append(_formatter_action_strings(parser, action))
    return rows


def _collect_example_rows(epilog: Optional[str]) -> list[tuple[str, str]]:
    if not epilog:
        return []
    rows: list[tuple[str, str]] = []
    for line in epilog.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if clean.lower().startswith("examples:"):
            continue
        rows.append(("Run", clean))
    return rows


def _usage_value(parser: argparse.ArgumentParser) -> str:
    usage = parser.format_usage().strip()
    if usage.lower().startswith("usage:"):
        return usage.split(":", 1)[1].strip()
    return usage


def _render_themed_help(parser: argparse.ArgumentParser) -> str:
    lines: list[str] = []
    table_width = _term_width()
    compact = table_width <= 84
    tight = table_width <= 74
    lines.append(_gradient_lines("OPASTRO HELP", [ACCENT_SOFT_RGB, ACCENT_RGB, ACCENT_DEEP_RGB], bold=True))
    lines.append(_style(f"{parser.prog}", COLOR_ACCENT_SOFT))

    if parser.description:
        lines.append(_wrap(parser.description))

    usage_rows = [("Syntax", _usage_value(parser))]
    lines.append("")
    lines.append(_style("Usage", COLOR_ACCENT_BOLD))
    lines.append(
        _render_line_table(
            usage_rows,
            headers=("Scope", "Command Pattern"),
            left_max_width=15 if compact else 18,
            left_min_width=10,
            cell_padding=0 if tight else 1,
        )
    )

    command_rows = _collect_subcommand_rows(parser)
    if command_rows:
        lines.append("")
        lines.append(_style("Commands", COLOR_ACCENT_BOLD))
        lines.append(
            _render_line_table(
                command_rows,
                headers=("Command", "Purpose"),
                left_max_width=18 if compact else 24,
                left_min_width=11,
                cell_padding=0 if tight else 1,
            )
        )

    argument_rows = _collect_argument_rows(parser)
    if argument_rows:
        lines.append("")
        lines.append(_style("Arguments", COLOR_ACCENT_BOLD))
        lines.append(
            _render_line_table(
                argument_rows,
                headers=("Argument", "Description"),
                left_max_width=20 if compact else 28,
                left_min_width=10,
                cell_padding=0 if compact else 1,
            )
        )

    option_rows = _collect_option_rows(parser)
    if option_rows:
        lines.append("")
        lines.append(_style("Options", COLOR_ACCENT_BOLD))
        lines.append(
            _render_line_table(
                option_rows,
                headers=("Option", "Description"),
                left_max_width=30 if tight else (34 if compact else 40),
                left_min_width=12,
                cell_padding=0 if compact else 1,
            )
        )

    example_rows = _collect_example_rows(parser.epilog)
    if example_rows:
        lines.append("")
        lines.append(_style("Examples", COLOR_ACCENT_BOLD))
        lines.append(
            _render_line_table(
                example_rows,
                headers=("Try", "Command"),
                left_max_width=10 if compact else 14,
                left_min_width=5,
                cell_padding=0 if tight else 1,
            )
        )

    lines.append("")
    lines.append(_gradient_lines(UPSELL_TEXT, [ACCENT_SOFT_RGB, ACCENT_RGB], bold=True))
    return "\n".join(lines).rstrip() + "\n"


def _print_heading(label: str) -> None:
    print(_style(label, COLOR_ACCENT_BOLD))


def _print_divider(char: str = "─") -> None:
    print(_style(char * _term_width(), COLOR_ACCENT_DIM))


def _render_pretty_report(payload) -> int:
    _print_heading("OPASTRO REPORT")
    _print_divider()
    meta = (
        f"Type: {payload.report_type.value} | Sign: {payload.sign} | "
        f"Period: {payload.period.value} | Window: {payload.start.date()} → {payload.end.date()}"
    )
    print(_wrap(meta))
    if payload.data.factor_values:
        factor_preview = ", ".join(
            f"{key}={value}" for key, value in list(payload.data.factor_values.items())[:6]
        )
        print(_wrap(f"Top factor drivers: {factor_preview}"))
    _print_divider()

    for insight in payload.sections:
        section_label = insight.section.value.replace("_", " ").title()
        print(_style(f"{section_label} ({insight.intensity})", COLOR_ACCENT_BOLD))
        print(_wrap(insight.summary, indent="  "))

        if insight.highlights:
            print(_style("  Highlights", COLOR_ACCENT_SOFT))
            for item in insight.highlights[:3]:
                print(_wrap_bullet(item))
        if insight.cautions:
            print(_style("  Cautions", COLOR_ACCENT_SOFT))
            for item in insight.cautions[:2]:
                print(_wrap_bullet(item))
        if insight.actions:
            print(_style("  Actions", COLOR_ACCENT_SOFT))
            for item in insight.actions[:2]:
                print(_wrap_bullet(item))
        _print_divider("·")

    print(_style(UPSELL_TEXT, COLOR_ACCENT_BOLD))
    return 0


def _render_text_snapshot(payload) -> str:
    buffer = StringIO()
    with redirect_stdout(buffer):
        _render_pretty_report(payload)
    return buffer.getvalue()


def _render_markdown(payload) -> str:
    lines: list[str] = []
    lines.append("# OPASTRO REPORT")
    lines.append("")
    lines.append(
        f"- **Type:** `{payload.report_type.value}`  "
        f"- **Sign:** `{payload.sign}`  "
        f"- **Period:** `{payload.period.value}`  "
        f"- **Window:** `{payload.start.date()}` to `{payload.end.date()}`"
    )
    if payload.data.factor_values:
        preview = ", ".join(f"`{key}={value}`" for key, value in list(payload.data.factor_values.items())[:6])
        lines.append(f"- **Top factors:** {preview}")
    lines.append("")

    for insight in payload.sections:
        section_label = insight.section.value.replace("_", " ").title()
        lines.append(f"## {section_label} ({insight.intensity})")
        lines.append("")
        lines.append(insight.summary)
        lines.append("")
        if insight.highlights:
            lines.append("### Highlights")
            lines.extend(f"- {item}" for item in insight.highlights[:3])
            lines.append("")
        if insight.cautions:
            lines.append("### Cautions")
            lines.extend(f"- {item}" for item in insight.cautions[:2])
            lines.append("")
        if insight.actions:
            lines.append("### Actions")
            lines.extend(f"- {item}" for item in insight.actions[:2])
            lines.append("")

    lines.append("---")
    lines.append(UPSELL_TEXT.replace("\n", "  \n"))
    lines.append("")
    return "\n".join(lines)


def _render_html(payload) -> str:
    section_blocks: list[str] = []
    for insight in payload.sections:
        section_label = html_escape(insight.section.value.replace("_", " ").title())
        summary = html_escape(insight.summary)
        highlights = "".join(f"<li>{html_escape(item)}</li>" for item in insight.highlights[:3])
        cautions = "".join(f"<li>{html_escape(item)}</li>" for item in insight.cautions[:2])
        actions = "".join(f"<li>{html_escape(item)}</li>" for item in insight.actions[:2])
        section_blocks.append(
            f"""
            <section class="card">
              <h2>{section_label} <span class="pill">{html_escape(insight.intensity)}</span></h2>
              <p>{summary}</p>
              {"<h3>Highlights</h3><ul>" + highlights + "</ul>" if highlights else ""}
              {"<h3>Cautions</h3><ul>" + cautions + "</ul>" if cautions else ""}
              {"<h3>Actions</h3><ul>" + actions + "</ul>" if actions else ""}
            </section>
            """
        )

    factor_preview = ""
    if payload.data.factor_values:
        factor_preview = ", ".join(
            html_escape(f"{key}={value}") for key, value in list(payload.data.factor_values.items())[:6]
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Opastro Report</title>
  <style>
    :root {{
      --bg: #f6f7fb;
      --card: #ffffff;
      --ink: #0f172a;
      --muted: #475569;
      --accent: #0f766e;
    }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at 10% 0%, #dff6ff, var(--bg) 35%);
      color: var(--ink);
      line-height: 1.5;
    }}
    main {{
      max-width: 920px;
      margin: 0 auto;
      padding: 32px 16px 48px;
    }}
    .card {{
      background: var(--card);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 14px;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }}
    .meta {{
      color: var(--muted);
      margin-bottom: 10px;
    }}
    h1 {{
      margin: 0 0 10px;
      color: var(--accent);
    }}
    h2 {{
      margin: 0 0 8px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .pill {{
      font-size: 12px;
      color: var(--accent);
      background: #e7fffb;
      padding: 3px 8px;
      border-radius: 999px;
    }}
    h3 {{
      margin-bottom: 6px;
      color: var(--muted);
    }}
    footer {{
      margin-top: 24px;
      color: var(--muted);
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>OPASTRO REPORT</h1>
    <div class="card meta">
      <div><strong>Type:</strong> {html_escape(payload.report_type.value)}</div>
      <div><strong>Sign:</strong> {html_escape(payload.sign)}</div>
      <div><strong>Period:</strong> {html_escape(payload.period.value)}</div>
      <div><strong>Window:</strong> {html_escape(str(payload.start.date()))} to {html_escape(str(payload.end.date()))}</div>
      {"<div><strong>Top factors:</strong> " + factor_preview + "</div>" if factor_preview else ""}
    </div>
    {''.join(section_blocks)}
    <footer>{html_escape(UPSELL_TEXT).replace(chr(10), '<br/>')}</footer>
  </main>
</body>
</html>
"""


def _resolve_output_format(args: argparse.Namespace) -> str:
    if getattr(args, "json", False):
        return "json"
    explicit = getattr(args, "output_format", None)
    if explicit:
        return explicit
    return "text"


def _render_output(payload, *, output_format: str, export_path: Optional[str] = None) -> int:
    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported format: {output_format}")

    rendered: str
    if output_format == "text":
        _render_pretty_report(payload)
        rendered = _render_text_snapshot(payload) if export_path else ""
    elif output_format == "json":
        rendered = payload.model_dump_json(indent=2)
        print(rendered)
    elif output_format == "markdown":
        rendered = _render_markdown(payload)
        print(rendered)
    else:
        rendered = _render_html(payload)
        print(rendered)

    if export_path:
        target = Path(export_path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered)
        print(f"saved output to {target}", file=sys.stderr)
    return 0


def _report_to_string(payload, output_format: str) -> str:
    if output_format == "json":
        return payload.model_dump_json(indent=2)
    if output_format == "markdown":
        return _render_markdown(payload)
    if output_format == "html":
        return _render_html(payload)
    return _render_text_snapshot(payload)


def _save_export(content: str, export_path: str) -> Path:
    target = Path(export_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


def _build_natal_request(args: argparse.Namespace) -> NatalBirthchartRequest:
    birth = _build_birth(args)
    if birth is None:
        raise ValueError("--birth-date is required for natal reports.")
    return NatalBirthchartRequest(
        birth=birth,
        user_name=getattr(args, "user_name", None),
        zodiac_system=args.zodiac_system,
        ayanamsa=args.ayanamsa,
        house_system=args.house_system,
        node_type=args.node_type,
        tenant_id=args.tenant_id,
    )


def _render_natal_text(report) -> str:
    lines: list[str] = []
    lines.append("OPASTRO NATAL REPORT")
    lines.append("".ljust(min(96, _term_width()), "─"))
    lines.append(
        f"Sign: {report.sign} | Birth: {report.birth.date.isoformat()} | "
        f"Rising: {report.snapshot.rising_sign or 'N/A'} | Houses: {report.snapshot.house_system or 'N/A'}"
    )
    lines.append(f"Positions: {len(report.snapshot.positions)} | Aspects: {len(report.snapshot.aspects)}")
    premium = report.premium_insights
    if premium:
        signature = premium.dominant_signature
        lines.append(
            "Dominant signature: "
            f"{signature.dominant_element}/{signature.dominant_modality} "
            f"(top: {', '.join(signature.top_planets[:3]) or 'N/A'})"
        )
        lines.append(
            f"Aspect patterns: {len(premium.aspect_patterns)} | "
            f"House vectors: {len(premium.life_area_vectors)} | "
            f"Timing windows: {len(premium.timing_overlay.activations) if premium.timing_overlay else 0}"
        )
        if premium.relationship_module:
            lines.append(f"Relationship score: {premium.relationship_module.score:.1f}")
        if premium.career_module:
            lines.append(f"Career score: {premium.career_module.score:.1f}")
    lines.append("")
    lines.append(UPSELL_TEXT)
    return "\n".join(lines)


def _export_natal_assets(report, args: argparse.Namespace) -> list[Path]:
    exports: list[Path] = []

    if args.wheel_svg:
        svg = build_natal_wheel_svg(
            report,
            accent_color=args.accent,
            brand_title=args.brand_title,
            user_name=getattr(args, "user_name", None),
            theme=args.wheel_theme,
        )
        target = _save_export(svg, args.wheel_svg)
        exports.append(target)

    if args.wheel_png:
        png_bytes = build_natal_wheel_png(
            report,
            accent_color=args.accent,
            brand_title=args.brand_title,
            user_name=getattr(args, "user_name", None),
            theme=args.wheel_theme,
        )
        target = Path(args.wheel_png).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png_bytes)
        exports.append(target)

    if args.house_map:
        payload = build_house_overlay_map(report)
        target = _save_export(json.dumps(payload, indent=2), args.house_map)
        exports.append(target)

    if args.pdf:
        pdf_bytes = build_natal_report_pdf(
            report,
            accent_color=args.accent,
            brand_title=args.brand_title,
            user_name=getattr(args, "user_name", None),
            brand_url=args.brand_url,
            premium_url=args.premium_url,
            wheel_theme=args.wheel_theme,
        )
        target = Path(args.pdf).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(pdf_bytes)
        exports.append(target)

    return exports


def _date_range(start: date, end: date, step_days: int = 1) -> list[date]:
    if step_days <= 0:
        raise ValueError("--step-days must be greater than 0.")
    if end < start:
        raise ValueError("--date-to must be on or after --date-from.")
    values: list[date] = []
    current = start
    while current <= end:
        values.append(current)
        current = date.fromordinal(current.toordinal() + step_days)
    return values


def _parse_signs(raw: Optional[str]) -> Optional[list[str]]:
    if raw is None:
        return None
    values = [value.strip().upper() for value in raw.split(",") if value.strip()]
    for value in values:
        if value not in ZODIAC_SIGNS:
            raise ValueError(f"Unsupported zodiac sign: {value}")
    return values or None


def _tip_key_for_period(period: Period) -> str:
    return {
        Period.DAILY: "daily_tip",
        Period.WEEKLY: "weekly_tip",
        Period.MONTHLY: "monthly_tip",
        Period.YEARLY: "yearly_tip",
    }[period]


def _build_horoscope_request(args: argparse.Namespace) -> HoroscopeRequest:
    if not args.period:
        raise ValueError("--period is required.")
    return HoroscopeRequest(
        period=args.period,
        sign=args.sign,
        target_date=_parse_date(args.target_date) if args.target_date else None,
        sections=_parse_sections(args.sections),
        birth=_build_birth(args),
        zodiac_system=args.zodiac_system,
        ayanamsa=args.ayanamsa,
        house_system=args.house_system,
        node_type=args.node_type,
        tenant_id=args.tenant_id,
    )


def _build_birthday_request(args: argparse.Namespace) -> BirthdayHoroscopeRequest:
    return BirthdayHoroscopeRequest(
        sign=args.sign,
        target_date=_parse_date(args.target_date) if args.target_date else None,
        sections=_parse_sections(args.sections),
        birth=_build_birth(args),
        zodiac_system=args.zodiac_system,
        ayanamsa=args.ayanamsa,
        house_system=args.house_system,
        node_type=args.node_type,
        tenant_id=args.tenant_id,
    )


def _build_planet_request(args: argparse.Namespace) -> PlanetHoroscopeRequest:
    if not args.period:
        raise ValueError("--period is required for planet reports.")
    if not args.planet:
        raise ValueError("--planet is required for planet reports.")
    return PlanetHoroscopeRequest(
        period=args.period,
        planet=args.planet,
        sign=args.sign,
        target_date=_parse_date(args.target_date) if args.target_date else None,
        sections=_parse_sections(args.sections),
        birth=_build_birth(args),
        zodiac_system=args.zodiac_system,
        ayanamsa=args.ayanamsa,
        house_system=args.house_system,
        node_type=args.node_type,
        tenant_id=args.tenant_id,
    )


def _generate_payload(service: HoroscopeService, args: argparse.Namespace, kind: str):
    if kind == "birthday":
        return service.generate_birthday(_build_birthday_request(args))
    if kind == "planet":
        return service.generate_planet(_build_planet_request(args))
    return service.generate(_build_horoscope_request(args))


def _line_provenance(lines: list[str], details: list[Any], *, insight_key: str) -> list[dict[str, Any]]:
    if not lines:
        return []
    if not details:
        return [{"line": line, "source_factors": [], "why": "No factor details available"} for line in lines]
    sorted_details = sorted(details, key=lambda detail: detail.weight, reverse=True)
    output: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        primary = sorted_details[idx % len(sorted_details)]
        secondary = sorted_details[(idx + 1) % len(sorted_details)]
        why = primary.factor_insights.get(insight_key) or primary.factor_insights.get("lite_meaning") or ""
        output.append(
            {
                "line": line,
                "source_factors": [primary.factor_type, secondary.factor_type] if secondary != primary else [primary.factor_type],
                "why": why,
            }
        )
    return output


def _build_explain_payload(payload) -> dict[str, Any]:
    sections: list[dict[str, Any]] = []
    for insight in payload.sections:
        detail_records: list[dict[str, Any]] = []
        tip_key = _tip_key_for_period(payload.period)
        for detail in insight.factor_details:
            detail_records.append(
                {
                    "factor_type": detail.factor_type,
                    "factor_value": detail.factor_value,
                    "weight": detail.weight,
                    "why": detail.factor_insights.get("lite_meaning"),
                    "reflection": detail.factor_insights.get("reflection"),
                    "caution": detail.factor_insights.get("caution"),
                    "action_hint": detail.factor_insights.get(tip_key) or detail.factor_insights.get("affirmation"),
                }
            )

        sections.append(
            {
                "section": insight.section.value,
                "title": insight.title,
                "intensity": insight.intensity,
                "summary": {
                    "line": insight.summary,
                    "source_factors": [d.factor_type for d in sorted(insight.factor_details, key=lambda x: x.weight, reverse=True)[:3]],
                    "why": "Summary is composed from highest-weighted factor details with deterministic cadence templates.",
                },
                "highlights": _line_provenance(insight.highlights, insight.factor_details, insight_key="motivation"),
                "cautions": _line_provenance(insight.cautions, insight.factor_details, insight_key="caution"),
                "actions": _line_provenance(insight.actions, insight.factor_details, insight_key=tip_key),
                "factors": detail_records,
                "scores": insight.scores,
            }
        )
    return {
        "report_type": payload.report_type.value,
        "sign": payload.sign,
        "period": payload.period.value,
        "window": {"start": payload.start.isoformat(), "end": payload.end.isoformat()},
        "sections": sections,
    }


def _render_explain_text(explain_payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("OPASTRO EXPLAIN")
    lines.append("-" * min(96, _term_width()))
    lines.append(
        f"Type: {explain_payload['report_type']} | Sign: {explain_payload['sign']} | Period: {explain_payload['period']}"
    )
    lines.append("")
    for section in explain_payload["sections"]:
        lines.append(f"{section['section'].replace('_', ' ').title()} ({section['intensity']})")
        lines.append(f"  Summary: {section['summary']['line']}")
        lines.append(f"  Why: {section['summary']['why']}")
        lines.append(f"  Source factors: {', '.join(section['summary']['source_factors'])}")
        if section["highlights"]:
            lines.append("  Highlights provenance:")
            for item in section["highlights"][:3]:
                lines.append(f"    - {item['line']}")
                lines.append(f"      factors: {', '.join(item['source_factors'])}")
        if section["factors"]:
            lines.append("  Factor drivers:")
            for factor in section["factors"][:6]:
                lines.append(
                    f"    - {factor['factor_type']}={factor['factor_value']} (w={factor['weight']:.2f}) -> {factor['why']}"
                )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_explain_markdown(explain_payload: dict[str, Any]) -> str:
    lines: list[str] = ["# OPASTRO EXPLAIN", ""]
    lines.append(
        f"- **Type:** `{explain_payload['report_type']}`  "
        f"- **Sign:** `{explain_payload['sign']}`  "
        f"- **Period:** `{explain_payload['period']}`"
    )
    lines.append("")
    for section in explain_payload["sections"]:
        lines.append(f"## {section['section'].replace('_', ' ').title()} ({section['intensity']})")
        lines.append("")
        lines.append(f"**Summary line**: {section['summary']['line']}")
        lines.append("")
        lines.append(f"**Why**: {section['summary']['why']}")
        lines.append("")
        lines.append(f"**Source factors**: {', '.join('`'+f+'`' for f in section['summary']['source_factors'])}")
        lines.append("")
        if section["factors"]:
            lines.append("### Factor Provenance")
            for factor in section["factors"]:
                lines.append(
                    f"- `{factor['factor_type']}={factor['factor_value']}` (w={factor['weight']:.2f}) — {factor['why']}"
                )
            lines.append("")
    return "\n".join(lines)


def _render_explain_html(explain_payload: dict[str, Any]) -> str:
    body = []
    for section in explain_payload["sections"]:
        factors = "".join(
            f"<li><code>{html_escape(f['factor_type'])}={html_escape(str(f['factor_value']))}</code> "
            f"(w={f['weight']:.2f}) — {html_escape(f.get('why') or '')}</li>"
            for f in section["factors"]
        )
        body.append(
            f"""
            <section class="card">
              <h2>{html_escape(section['section'].replace('_', ' ').title())} <span class="pill">{html_escape(section['intensity'])}</span></h2>
              <p><strong>Summary:</strong> {html_escape(section['summary']['line'])}</p>
              <p><strong>Why:</strong> {html_escape(section['summary']['why'])}</p>
              <p><strong>Source factors:</strong> {html_escape(', '.join(section['summary']['source_factors']))}</p>
              <h3>Factor Provenance</h3>
              <ul>{factors}</ul>
            </section>
            """
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Opastro Explain</title>
<style>
body{{font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f6f8fc;color:#0f172a;margin:0}}
main{{max-width:960px;margin:0 auto;padding:24px 16px}}
.card{{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 8px 20px rgba(15,23,42,.08)}}
h1{{color:#0f766e}} .pill{{font-size:12px;background:#e7fffb;color:#0f766e;padding:2px 7px;border-radius:999px}}
</style></head><body><main>
<h1>OPASTRO EXPLAIN</h1>
<p><strong>Type:</strong> {html_escape(explain_payload['report_type'])} |
<strong>Sign:</strong> {html_escape(explain_payload['sign'])} |
<strong>Period:</strong> {html_escape(explain_payload['period'])}</p>
{''.join(body)}
</main></body></html>"""


def _render_explain_output(explain_payload: dict[str, Any], *, output_format: str, export_path: Optional[str]) -> int:
    if output_format == "json":
        rendered = json.dumps(explain_payload, indent=2, sort_keys=True)
    elif output_format == "markdown":
        rendered = _render_explain_markdown(explain_payload)
    elif output_format == "html":
        rendered = _render_explain_html(explain_payload)
    else:
        rendered = _render_explain_text(explain_payload)

    print(rendered)
    if export_path:
        target = _save_export(rendered, export_path)
        print(f"saved output to {target}", file=sys.stderr)
    return 0


def _show_welcome() -> int:
    print(_gradient_lines(WELCOME_BANNER.strip("\n"), [ACCENT_SOFT_RGB, ACCENT_RGB, ACCENT_DEEP_RGB], bold=True))
    print(_style(f"OPASTRO • Open Core Horoscope Engine • {_app_version()}", COLOR_ACCENT_BOLD))
    print(_wrap("Enterprise-grade deterministic calculations with lightweight open meanings and premium-ready API hooks."))
    _print_divider()
    _print_heading("Commands")
    commands = [
        ("init", "Run guided onboarding and save default profile preferences."),
        ("welcome", "Show the branded home screen and onboarding shortcuts."),
        ("profile", "Save/list/show/use reusable profile defaults."),
        ("catalog", "List all supported periods, sections, signs, and planets."),
        ("doctor", "Inspect Python runtime, executable path, and readiness status."),
        ("horoscope", "Generate a standard period report from sign or birth data."),
        ("birthday", "Generate a yearly birthday-cycle report."),
        ("planet", "Generate a planet-focused report for deeper diagnostics."),
        ("natal", "Generate natal analysis and export wheel/map/pdf assets."),
        ("explain", "Show factor provenance for each section line."),
        ("completion", "Print shell completion scripts for bash/zsh/fish."),
        ("ui", "Launch keyboard-driven interactive report browser."),
        ("batch", "Generate reports across multiple signs and dates."),
        ("serve", "Run the local FastAPI service for integrations."),
    ]
    for name, desc in commands:
        print(_wrap(f"{name:10} {desc}", indent="  "))
    _print_divider()
    _print_heading("Quick Start")
    print(_wrap("opastro init", indent="  "))
    print(_wrap("opastro horoscope --period daily --sign ARIES --target-date 2026-04-03", indent="  "))
    print(_wrap("opastro --help", indent="  "))
    _print_divider()
    print(_gradient_lines(UPSELL_TEXT, [ACCENT_SOFT_RGB, ACCENT_RGB], bold=True))
    return 0


def _handle_welcome(_: argparse.Namespace) -> int:
    return _show_welcome()


def _handle_catalog(_: argparse.Namespace) -> int:
    _print_heading("OPASTRO CATALOG")
    _print_divider()
    print(_style("Periods", "1"))
    for period in Period:
        print(f"  - {period.value}")
    print(_style("Sections", "1"))
    for section in Section:
        print(f"  - {section.value}")
    print(_style("Signs", "1"))
    print(_wrap(", ".join(ZODIAC_SIGNS), indent="  "))
    print(_style("Planets", "1"))
    print(_wrap(", ".join(planet.value for planet in PlanetName), indent="  "))
    return 0


def _dependency_health() -> tuple[list[str], list[str]]:
    modules = {
        "fastapi": "fastapi",
        "pydantic": "pydantic",
        "uvicorn": "uvicorn",
        "redis": "redis",
        "swisseph": "swisseph",
    }
    missing: list[str] = []
    ok: list[str] = []
    for import_name, label in modules.items():
        try:
            importlib.import_module(import_name)
            ok.append(label)
        except Exception:
            missing.append(label)
    return missing, ok


def _doctor_fix(args: argparse.Namespace) -> None:
    command = [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
    if args.dry_run:
        print(f"Fix plan      : {' '.join(command)}")
        return
    print("Applying fix  : Installing project dependencies...")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        print(_style("Fix result    : OK (dependencies installed)", "1;32"))
    else:
        print(_style(f"Fix result    : WARN (pip exited {result.returncode})", "1;33"))
        stderr_preview = "\n".join(result.stderr.splitlines()[-5:])
        if stderr_preview:
            print(stderr_preview)


def _handle_doctor(args: argparse.Namespace) -> int:
    cfg = ServiceConfig()
    _print_heading("OPASTRO DOCTOR")
    _print_divider()
    print(f"Python version : {platform.python_version()}")
    print(f"Python exec    : {sys.executable}")
    print(f"Platform       : {platform.platform()}")
    print(f"Ephemeris path : {cfg.ephemeris.ephemeris_path or 'auto/not-set'}")
    print(f"Zodiac system  : {cfg.ephemeris.zodiac_system}")
    print(f"Ayanamsa       : {cfg.ephemeris.ayanamsa_system}")
    in_venv = sys.prefix != sys.base_prefix
    print(f"Virtual env    : {'yes' if in_venv else 'no'}")

    required = f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+"
    runtime_ok = sys.version_info >= MIN_PYTHON_VERSION
    if sys.version_info >= MIN_PYTHON_VERSION:
        print(_style(f"Runtime check  : OK (Python {required} requirement satisfied)", "1;32"))
    else:
        current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(_style(f"Runtime check  : WARN (running {current}; requires {required})", "1;33"))
        print("Recommendation : Use a Python 3.11+ virtual environment and reinstall opastro.")

    missing_deps, ok_deps = _dependency_health()
    print(f"Deps loaded    : {', '.join(ok_deps) if ok_deps else 'none'}")
    if missing_deps:
        print(_style(f"Deps missing   : {', '.join(missing_deps)}", "1;33"))
    else:
        print(_style("Deps check     : OK", "1;32"))

    if args.fix:
        if not in_venv and not args.dry_run:
            print(_style("Fix blocked   : Refusing to install outside a virtual environment.", "1;33"))
            print("Recommendation : Create a venv first, then run `opastro doctor --fix`.")
            return 0

        _doctor_fix(args)
        if not args.dry_run:
            after_missing, _ = _dependency_health()
            if not after_missing:
                print(_style("Post-fix check : OK", "1;32"))
            else:
                print(_style(f"Post-fix check : WARN (still missing: {', '.join(after_missing)})", "1;33"))
    elif missing_deps or not runtime_ok:
        print("Suggestion     : Run `opastro doctor --fix --dry-run` to preview automatic remediation.")

    return 0


def _detect_local_timezone() -> str:
    tz = datetime.now().astimezone().tzinfo
    if tz is None:
        return "UTC"
    key = getattr(tz, "key", None)
    if isinstance(key, str) and key:
        return key
    name = tz.tzname(None)
    return name or "UTC"


def _prompt_text(label: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    response = input(f"{label}{suffix}: ").strip()
    if not response and default is not None:
        return default
    return response


def _prompt_bool(label: str, default: bool = True) -> bool:
    default_token = "Y/n" if default else "y/N"
    response = input(f"{label} ({default_token}): ").strip().lower()
    if not response:
        return default
    return response in {"y", "yes"}


def _validate_sections(values: Optional[list[str]]) -> Optional[list[str]]:
    if not values:
        return None
    allowed = {section.value for section in Section}
    cleaned = [value for value in values if value in allowed]
    return cleaned or None


def _profile_payload_from_args(
    args: argparse.Namespace,
    *,
    base: Optional[dict[str, Any]] = None,
    interactive: bool = False,
) -> dict[str, Any]:
    profile = dict(base or {})

    user_name = getattr(args, "user_name", None)
    if user_name is not None:
        cleaned = str(user_name).strip()
        if cleaned:
            profile["user_name"] = cleaned
        elif "user_name" in profile:
            profile.pop("user_name", None)

    sign = _normalize_sign(getattr(args, "sign", None))
    if sign is not None:
        profile["sign"] = sign

    sections = _validate_sections(_parse_sections(getattr(args, "sections", None)))
    if sections is not None:
        profile["sections"] = sections

    birth = _build_birth(args)
    if birth is not None:
        profile["birth"] = birth.model_dump(exclude_none=True)

    for field in ("zodiac_system", "ayanamsa", "house_system", "node_type", "tenant_id"):
        value = getattr(args, field, None)
        if value is not None:
            profile[field] = value

    output_format = getattr(args, "output_format", None)
    if output_format is not None:
        profile["output_format"] = output_format

    if interactive:
        for key in list(profile.keys()):
            value = profile[key]
            if value is None or value == "":
                profile.pop(key, None)
    return profile


def _apply_profile_defaults(args: argparse.Namespace) -> None:
    store = ProfileStore()
    profile = store.get_profile()
    if not profile:
        return

    active_profile_name = store.active_profile_name()
    if hasattr(args, "user_name") and getattr(args, "user_name", None) is None:
        from_profile = profile.get("user_name")
        if from_profile:
            args.user_name = str(from_profile)
        elif active_profile_name and active_profile_name != DEFAULT_PROFILE_NAME:
            args.user_name = active_profile_name

    if getattr(args, "sign", None) is None and profile.get("sign"):
        args.sign = profile["sign"]

    birth = profile.get("birth") or {}
    if getattr(args, "birth_date", None) is None and birth.get("date"):
        args.birth_date = birth["date"]
    if getattr(args, "birth_time", None) is None and birth.get("time"):
        args.birth_time = birth["time"]
    if getattr(args, "lat", None) is None and birth.get("coordinates", {}).get("latitude") is not None:
        args.lat = float(birth["coordinates"]["latitude"])
    if getattr(args, "lon", None) is None and birth.get("coordinates", {}).get("longitude") is not None:
        args.lon = float(birth["coordinates"]["longitude"])
    if getattr(args, "timezone", None) is None and birth.get("timezone"):
        args.timezone = birth["timezone"]

    if getattr(args, "sections", None) is None and profile.get("sections"):
        args.sections = ",".join(profile["sections"])

    for field in ("zodiac_system", "ayanamsa", "house_system", "node_type", "tenant_id"):
        if getattr(args, field, None) is None and profile.get(field) is not None:
            setattr(args, field, profile[field])

    if getattr(args, "output_format", None) is None and profile.get("output_format"):
        args.output_format = profile["output_format"]


def _handle_init(args: argparse.Namespace) -> int:
    store = ProfileStore()
    existing = store.get_profile(args.profile) or {}
    detected_tz = _detect_local_timezone()

    _print_heading("OPASTRO INIT")
    _print_divider()
    print(_wrap("Interactive onboarding to save your default profile for repeat report commands."))

    sign_default = existing.get("sign")
    while True:
        sign_raw = _prompt_text("Default sign (optional)", sign_default)
        if not sign_raw:
            sign = None
            break
        try:
            sign = _normalize_sign(sign_raw)
            break
        except ValueError as exc:
            print(f"error: {exc}")

    birth_existing = existing.get("birth") or {}
    wants_birth = _prompt_bool("Save default birth details", default=bool(birth_existing))

    birth_date = None
    birth_time = None
    lat = None
    lon = None
    timezone = None
    if wants_birth:
        birth_date = _prompt_text("Birth date YYYY-MM-DD", birth_existing.get("date"))
        birth_time = _prompt_text("Birth time HH:MM (optional)", birth_existing.get("time"))
        lat_default = birth_existing.get("coordinates", {}).get("latitude")
        lon_default = birth_existing.get("coordinates", {}).get("longitude")
        lat_raw = _prompt_text("Birth latitude (optional)", str(lat_default) if lat_default is not None else None)
        lon_raw = _prompt_text("Birth longitude (optional)", str(lon_default) if lon_default is not None else None)
        timezone = _prompt_text("Timezone", birth_existing.get("timezone") or detected_tz)
        lat = float(lat_raw) if lat_raw else None
        lon = float(lon_raw) if lon_raw else None

    sections_default = ",".join(existing.get("sections", [])) if existing.get("sections") else None
    sections = _prompt_text("Default sections comma list (optional)", sections_default)
    output_format = _prompt_text("Default output format (text/json/markdown/html)", existing.get("output_format", "text"))

    zodiac_system = _prompt_text("Default zodiac system (optional)", existing.get("zodiac_system"))
    ayanamsa = _prompt_text("Default ayanamsa (optional)", existing.get("ayanamsa"))
    house_system = _prompt_text("Default house system (optional)", existing.get("house_system"))
    node_type = _prompt_text("Default node type (optional)", existing.get("node_type"))
    tenant_id = _prompt_text("Default tenant id (optional)", existing.get("tenant_id"))

    profile_args = argparse.Namespace(
        sign=sign,
        birth_date=birth_date or None,
        birth_time=birth_time or None,
        lat=lat,
        lon=lon,
        timezone=timezone or None,
        sections=sections or None,
        zodiac_system=zodiac_system or None,
        ayanamsa=ayanamsa or None,
        house_system=house_system or None,
        node_type=node_type or None,
        tenant_id=tenant_id or None,
        output_format=(output_format or "text").lower(),
    )

    if profile_args.output_format not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported format: {profile_args.output_format}")
    allowed_values = {
        "zodiac_system": {"sidereal", "tropical"},
        "ayanamsa": {"lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"},
        "house_system": {"placidus", "whole_sign", "equal", "koch"},
        "node_type": {"true", "mean"},
    }
    for field, choices in allowed_values.items():
        value = getattr(profile_args, field)
        if value is None:
            continue
        if value not in choices:
            raise ValueError(f"Unsupported value for {field}: {value}")

    payload = _profile_payload_from_args(profile_args, base=existing, interactive=True)
    store.save_profile(args.profile, payload, set_active=True)

    print(_style(f"Saved profile '{args.profile}' and set as active.", "1;32"))
    return 0


def _handle_profile_list(_: argparse.Namespace) -> int:
    store = ProfileStore()
    active = store.active_profile_name()
    names = store.list_profiles()
    if not names:
        print("No profiles found. Run `opastro init` to create one.")
        return 0

    _print_heading("OPASTRO PROFILES")
    _print_divider()
    for name in names:
        marker = "*" if name == active else " "
        print(f"{marker} {name}")
    return 0


def _handle_profile_show(args: argparse.Namespace) -> int:
    store = ProfileStore()
    profile = store.get_profile(args.name)
    target_name = args.name or store.active_profile_name()
    if not profile or not target_name:
        raise ValueError("Profile not found. Use `opastro profile list` to inspect available profiles.")
    payload = {"name": target_name, "active": target_name == store.active_profile_name(), "profile": profile}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _handle_profile_use(args: argparse.Namespace) -> int:
    store = ProfileStore()
    if not store.use_profile(args.name):
        raise ValueError(f"Profile '{args.name}' does not exist.")
    print(_style(f"Active profile set to '{args.name}'.", "1;32"))
    return 0


def _handle_profile_save(args: argparse.Namespace) -> int:
    store = ProfileStore()
    existing = store.get_profile(args.name) or {}
    payload = _profile_payload_from_args(args, base=existing)
    store.save_profile(args.name, payload, set_active=args.set_active)
    status = "and activated" if args.set_active else "updated"
    print(_style(f"Profile '{args.name}' saved ({status}).", "1;32"))
    return 0


def _completion_tokens() -> list[str]:
    tokens: list[str] = []
    for command, aliases in COMMAND_ALIASES.items():
        tokens.append(command)
        tokens.extend(aliases)
    return sorted(set(tokens))


def _completion_script(shell: str) -> str:
    words = " ".join(_completion_tokens())
    if shell == "bash":
        return textwrap.dedent(
            f"""
            _opastro_complete() {{
              local cur="${{COMP_WORDS[COMP_CWORD]}}"
              COMPREPLY=( $(compgen -W "{words}" -- "$cur") )
            }}
            complete -F _opastro_complete opastro
            """
        ).strip()
    if shell == "zsh":
        return textwrap.dedent(
            f"""
            #compdef opastro
            _opastro() {{
              local -a commands
              commands=({words})
              _describe 'command' commands
            }}
            compdef _opastro opastro
            """
        ).strip()
    return textwrap.dedent(
        f"""
        function __fish_opastro_complete
            set -l cmd (commandline -opc)
            if test (count $cmd) -eq 1
                for c in {words}
                    echo $c
                end
            end
        end
        complete -f -c opastro -a "(__fish_opastro_complete)"
        """
    ).strip()


def _handle_completion(args: argparse.Namespace) -> int:
    print(_completion_script(args.shell))
    return 0


def _handle_explain(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    kind = args.kind
    if kind in ("horoscope", "planet") and not args.period:
        raise ValueError("--period is required for explain kind horoscope/planet.")
    if kind == "planet" and not args.planet:
        raise ValueError("--planet is required for explain kind planet.")

    service = HoroscopeService(ServiceConfig())
    payload = _generate_payload(service, args, kind)
    explain_payload = _build_explain_payload(payload)
    return _render_explain_output(
        explain_payload,
        output_format=_resolve_output_format(args),
        export_path=args.export,
    )


def _wrap_for_width(text: str, width: int) -> list[str]:
    if width <= 4:
        return [text[: max(1, width)]]
    parts = textwrap.wrap(text, width=width, break_long_words=False, replace_whitespace=False)
    return parts if parts else [""]


def _run_ui(payload) -> int:
    sections = payload.sections
    if not sections:
        print("No sections available for UI rendering.")
        return 0

    def _ui(stdscr) -> None:
        def _safe_add(y: int, x: int, text: str, max_len: int, attr: int = 0) -> None:
            if max_len <= 0:
                return
            try:
                stdscr.addnstr(y, x, text, max_len, attr)
            except curses.error:
                pass

        def _init_theme() -> dict[str, int]:
            theme = {
                "header": curses.A_BOLD,
                "accent": curses.A_BOLD,
                "selected": curses.A_REVERSE | curses.A_BOLD,
                "muted": curses.A_DIM,
                "body": curses.A_NORMAL,
            }
            if not curses.has_colors():
                return theme
            try:
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, -1)   # accent
                curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)  # selected row
                curses.init_pair(3, curses.COLOR_WHITE, -1)   # body
                curses.init_pair(4, curses.COLOR_CYAN, -1)    # meta
                theme["header"] = curses.color_pair(1) | curses.A_BOLD
                theme["accent"] = curses.color_pair(1) | curses.A_BOLD
                theme["selected"] = curses.color_pair(2) | curses.A_BOLD
                theme["muted"] = curses.color_pair(4)
                theme["body"] = curses.color_pair(3)
            except curses.error:
                return theme
            return theme

        curses.curs_set(0)
        stdscr.keypad(True)
        theme = _init_theme()
        selected = 0
        show_factors = False
        scroll_offset = 0

        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            left_w = max(24, min(38, width // 3))
            right_x = left_w + 2
            right_w = max(20, width - right_x - 1)
            page_h = max(6, height - 5)

            header = (
                f"OPASTRO UI • {payload.sign} • {payload.period.value} • "
                f"sections:{len(sections)} • factors:{'on' if show_factors else 'off'}"
            )
            _safe_add(0, 0, header, width - 1, theme["header"])
            try:
                stdscr.hline(1, 0, ord("─"), width - 1)
            except curses.error:
                stdscr.hline(1, 0, ord("-"), width - 1)

            left_view_h = max(1, height - 4)
            left_start = max(0, selected - (left_view_h // 2))
            left_end = min(len(sections), left_start + left_view_h)
            if left_end - left_start < left_view_h:
                left_start = max(0, left_end - left_view_h)

            for row_idx, idx in enumerate(range(left_start, left_end)):
                section = sections[idx]
                label = f"{section.section.value.replace('_', ' ').title()} ({section.intensity})"
                attr = theme["selected"] if idx == selected else theme["body"]
                _safe_add(2 + row_idx, 0, label, left_w - 1, attr)

            for row in range(2, height - 1):
                try:
                    stdscr.addch(row, left_w, ord("│"), theme["muted"])
                except curses.error:
                    stdscr.addch(row, left_w, ord("|"), theme["muted"])

            section = sections[selected]
            lines: list[tuple[str, str]] = []
            lines.append(("title", section.title))
            lines.append(("blank", ""))
            for item in _wrap_for_width(section.summary, right_w):
                lines.append(("body", item))
            lines.append(("blank", ""))
            lines.append(("label", "Highlights:"))
            for item in section.highlights[:3]:
                for wrapped in _wrap_for_width(f"- {item}", right_w):
                    lines.append(("body", wrapped))
            lines.append(("blank", ""))
            lines.append(("label", "Cautions:"))
            for item in section.cautions[:2]:
                for wrapped in _wrap_for_width(f"- {item}", right_w):
                    lines.append(("body", wrapped))
            lines.append(("blank", ""))
            lines.append(("label", "Actions:"))
            for item in section.actions[:2]:
                for wrapped in _wrap_for_width(f"- {item}", right_w):
                    lines.append(("body", wrapped))

            if show_factors:
                lines.append(("blank", ""))
                lines.append(("label", "Factor drill-down:"))
                for detail in section.factor_details[:8]:
                    desc = detail.factor_insights.get("lite_meaning") or ""
                    for wrapped in _wrap_for_width(
                        f"- {detail.factor_type}={detail.factor_value} ({detail.weight:.2f})",
                        right_w,
                    ):
                        lines.append(("factor", wrapped))
                    if desc:
                        for wrapped in _wrap_for_width(f"  {desc}", right_w):
                            lines.append(("body", wrapped))

            max_scroll = max(0, len(lines) - page_h)
            scroll_offset = max(0, min(scroll_offset, max_scroll))
            visible_lines = lines[scroll_offset : scroll_offset + page_h]
            for idx, (kind, line) in enumerate(visible_lines):
                y = 2 + idx
                if y >= height - 1:
                    break
                attr = theme["body"]
                if kind == "title":
                    attr = theme["accent"]
                elif kind == "label":
                    attr = theme["accent"]
                elif kind == "factor":
                    attr = theme["muted"]
                _safe_add(y, right_x, line, right_w, attr)

            footer = (
                "q/esc quit • ↑↓ or j/k section • enter factors • pgup/pgdn scroll • g top • G end"
            )
            _safe_add(height - 1, 0, footer, width - 1, theme["muted"])

            stdscr.refresh()
            key = stdscr.getch()
            if key in (ord("q"), 27):
                break
            if key in (curses.KEY_UP, ord("k")):
                selected = (selected - 1) % len(sections)
                scroll_offset = 0
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = (selected + 1) % len(sections)
                scroll_offset = 0
            elif key in (10, 13, curses.KEY_ENTER):
                show_factors = not show_factors
                scroll_offset = 0
            elif key in (curses.KEY_NPAGE, ord(" ")):
                scroll_offset += max(1, page_h - 2)
            elif key in (curses.KEY_PPAGE, ord("b")):
                scroll_offset -= max(1, page_h - 2)
            elif key == ord("g"):
                scroll_offset = 0
            elif key == ord("G"):
                scroll_offset = 10**9

    curses.wrapper(_ui)
    return 0


def _handle_ui(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    payload = service.generate(_build_horoscope_request(args))

    if args.no_interactive or not sys.stdout.isatty():
        print("UI fallback mode (non-interactive). Use without --no-interactive in a TTY terminal.")
        return _render_output(payload, output_format="text", export_path=args.export)

    try:
        return _run_ui(payload)
    except curses.error:
        print("UI unavailable in this terminal. Falling back to text output.")
        return _render_output(payload, output_format="text", export_path=args.export)


def _resolve_batch_signs(args: argparse.Namespace) -> list[str]:
    explicit = _parse_signs(args.signs)
    if explicit:
        return explicit
    if args.sign:
        normalized = _normalize_sign(args.sign)
        if normalized:
            return [normalized]
    return list(ZODIAC_SIGNS)


def _resolve_batch_dates(args: argparse.Namespace) -> list[date]:
    if args.target_date and (args.date_from or args.date_to):
        raise ValueError("Use either --target-date or --date-from/--date-to, not both.")
    if args.target_date:
        return [_parse_date(args.target_date)]
    if args.date_from or args.date_to:
        if not args.date_from or not args.date_to:
            raise ValueError("Both --date-from and --date-to are required for date ranges.")
        return _date_range(_parse_date(args.date_from), _parse_date(args.date_to), args.step_days)
    return [date.today()]


def _batch_extension(fmt: str) -> str:
    return {"text": ".txt", "json": ".json", "markdown": ".md", "html": ".html"}[fmt]


def _handle_batch(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    if args.kind == "planet" and not args.planet:
        raise ValueError("--planet is required for kind=planet.")

    service = HoroscopeService(ServiceConfig())
    signs = _resolve_batch_signs(args)
    dates = _resolve_batch_dates(args)

    exports: list[str] = []
    rendered_blobs: list[str] = []
    json_rows: list[dict[str, Any]] = []
    for target in dates:
        for sign in signs:
            item_args = argparse.Namespace(**vars(args))
            item_args.sign = sign
            item_args.target_date = target.isoformat()
            payload = _generate_payload(service, item_args, args.kind)

            if args.output_format == "json" and not args.export_dir:
                json_rows.append(payload.model_dump(mode="json"))
                continue

            rendered = _report_to_string(payload, args.output_format)
            if args.export_dir:
                ext = _batch_extension(args.output_format)
                filename = f"{args.kind}_{payload.period.value}_{payload.sign}_{target.isoformat()}{ext}"
                target_path = Path(args.export_dir).expanduser() / filename
                _save_export(rendered, str(target_path))
                exports.append(str(target_path))
            else:
                rendered_blobs.append(
                    f"=== {args.kind.upper()} {payload.sign} {payload.period.value} {target.isoformat()} ===\n{rendered}"
                )

    if args.output_format == "json" and not args.export_dir:
        print(json.dumps(json_rows, indent=2))
    elif rendered_blobs:
        print("\n\n".join(rendered_blobs))

    print(
        f"batch summary: generated={len(signs) * len(dates)} signs={len(signs)} dates={len(dates)} kind={args.kind}",
        file=sys.stderr,
    )
    if exports:
        print(f"batch export: wrote {len(exports)} files to {Path(args.export_dir).expanduser()}", file=sys.stderr)
    return 0


def _handle_horoscope(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    request = _build_horoscope_request(args)
    return _render_output(
        service.generate(request),
        output_format=_resolve_output_format(args),
        export_path=args.export,
    )


def _handle_birthday(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    request = _build_birthday_request(args)
    return _render_output(
        service.generate_birthday(request),
        output_format=_resolve_output_format(args),
        export_path=args.export,
    )


def _handle_planet(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    request = _build_planet_request(args)
    return _render_output(
        service.generate_planet(request),
        output_format=_resolve_output_format(args),
        export_path=args.export,
    )


def _handle_natal(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    request = _build_natal_request(args)
    report = service.generate_natal_birthchart(request)

    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(_render_natal_text(report))

    exports = _export_natal_assets(report, args)
    for target in exports:
        print(f"saved output to {target}", file=sys.stderr)
    return 0


def _handle_serve(args: argparse.Namespace) -> int:
    uvicorn.run("horoscope_engine.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def _known_command_tokens() -> list[str]:
    tokens: list[str] = []
    for command, aliases in COMMAND_ALIASES.items():
        tokens.append(command)
        tokens.extend(aliases)
    return sorted(set(tokens))


def _suggest_command(token: str) -> str:
    suggestions = difflib.get_close_matches(token, _known_command_tokens(), n=3, cutoff=0.45)
    if suggestions:
        return f"Unknown command '{token}'. Did you mean: {', '.join(suggestions)}?"
    return f"Unknown command '{token}'. Run `opastro --help`."


def main(argv: Optional[list[str]] = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = _build_base_parser()
    if not raw_argv:
        return _show_welcome()

    first = raw_argv[0]
    if not first.startswith("-") and first not in _known_command_tokens():
        print(_suggest_command(first), file=sys.stderr)
        return 2

    try:
        args = parser.parse_args(raw_argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        if hasattr(args, "handler"):
            return args.handler(args)
        parser.error(f"Unsupported command: {args.command}")
        return 2
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
