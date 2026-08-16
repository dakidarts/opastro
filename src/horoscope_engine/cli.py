from __future__ import annotations

import argparse
from dataclasses import dataclass

try:
    import curses
except ImportError:  # pragma: no cover - exercised on platforms without curses
    curses = None
import difflib
import hashlib
import importlib
import json
import os
import platform
import random
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import traceback
import webbrowser
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone
from html import escape as html_escape
from io import StringIO
from pathlib import Path
from typing import Any, Callable, Optional

import uvicorn

from .config import ServiceConfig
from .ephemeris import MINOR_BODIES, EphemerisEngine
from .ephemeris_downloader import (
    DOWNLOADABLE_EPHE_FILES,
    MANUAL_EPHE_FILES,
    ensure_minor_body_ephemeris_report,
    missing_ephemeris_files,
)
from .models import (
    ZODIAC_SIGNS,
    BirthData,
    BirthdayHoroscopeRequest,
    CelestialEventsRequest,
    Coordinates,
    HoroscopeRequest,
    NatalBirthchartRequest,
    Period,
    PlanetHoroscopeRequest,
    PlanetName,
    Section,
)
from .natal_artifacts import (
    build_house_overlay_map,
    build_natal_report_pdf,
    build_natal_wheel_png,
    build_natal_wheel_png_split,
    build_natal_wheel_svg,
    build_natal_wheel_svg_split,
)
from .profiles import DEFAULT_PROFILE_NAME, ProfileStore
from .scene_renderer import build_planetary_scene_png, build_planetary_scene_svg
from .service import HoroscopeService
from .update_checker import UpdateCheckResult, check_for_update, update_notice
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
    "logger": ["log"],
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
    "events": ["calendar", "celestial"],
    "render": ["visuals"],
}

ACCENT_RGB = (61, 221, 119)  # #3ddd77
HOME_SUBTLE_RGB = (83, 80, 98)  # #535062
ACCENT_SOFT_RGB = (148, 244, 183)
ACCENT_FADE_RGB = (108, 230, 151)
ACCENT_DEEP_RGB = (46, 187, 101)
COLOR_ACCENT = f"38;2;{ACCENT_RGB[0]};{ACCENT_RGB[1]};{ACCENT_RGB[2]}"
COLOR_ACCENT_BOLD = f"1;{COLOR_ACCENT}"
COLOR_ACCENT_DIM = (
    f"38;2;{ACCENT_FADE_RGB[0]};{ACCENT_FADE_RGB[1]};{ACCENT_FADE_RGB[2]}"
)
COLOR_ACCENT_SOFT = (
    f"38;2;{ACCENT_SOFT_RGB[0]};{ACCENT_SOFT_RGB[1]};{ACCENT_SOFT_RGB[2]}"
)
COLOR_ACCENT_DEEP = (
    f"38;2;{ACCENT_DEEP_RGB[0]};{ACCENT_DEEP_RGB[1]};{ACCENT_DEEP_RGB[2]}"
)
RUNTIME_LOG_FILENAME = "runtime-errors.log"
ANALYTICS_LOG_FILENAME = "analytics-events.log"
INIT_TEMPLATES: dict[str, dict[str, Any]] = {
    "api": {
        "output_format": "json",
        "tenant_id": "public-api",
        "zodiac_system": "tropical",
    },
    "cli": {
        "output_format": "text",
        "sections": ["general", "career", "money"],
        "zodiac_system": "tropical",
    },
    "natal": {
        "wheel_theme": "day",
        "accent": "#3ddd77",
        "brand_title": "OPASTRO",
        "brand_url": "https://opastro.com",
        "premium_url": "https://numerologyapi.com",
        "output_format": "markdown",
        "zodiac_system": "tropical",
    },
}


class OpastroArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        return _render_themed_help(self)


@dataclass
class _UICommandResult:
    name: str
    command: list[str]
    stdout: str
    stderr: str
    returncode: int


@dataclass
class _UIState:
    selected: int = 0
    show_factors: bool = False
    scroll_offset: int = 0
    help_visible: bool = False
    requested_period: Optional[str] = None
    filter_query: str = ""
    filter_requested: bool = False
    compact: bool = False
    home_palette: Optional[str] = None
    home_action_requested: bool = False
    home_open_requested: bool = False
    home_message: str = ""
    refresh_requested: bool = False
    cta_visible: bool = False
    cta_selected: int = 0
    cta_open_requested: bool = False
    status_message: str = ""
    result_page: Optional[_UICommandResult] = None
    result_scroll_offset: int = 0
    result_filter_query: str = ""
    result_filter_requested: bool = False
    result_rerun_requested: bool = False


@dataclass(frozen=True)
class _UIEventKey:
    value: str


@dataclass
class _UIEventSection:
    section: _UIEventKey
    title: str
    summary: str
    highlights: list[str]
    cautions: list[str]
    actions: list[str]
    intensity: str
    factor_details: list[Any]


@dataclass
class _UIEventsPayload:
    period: Period
    sign: str
    sections: list[_UIEventSection]
    response: Any


_UI_HOME_COMMANDS = (
    (
        "init",
        "Create a reusable profile and starter configuration.",
        "opastro init --template natal",
    ),
    (
        "profile",
        "Save, inspect, and activate reusable report profiles.",
        "opastro profile list",
    ),
    (
        "horoscope",
        "Generate a daily, weekly, monthly, or yearly reading.",
        "opastro horoscope --period daily --sign ARIES",
    ),
    (
        "birthday",
        "Generate a birthday-cycle report.",
        "opastro birthday --sign ARIES",
    ),
    (
        "planet",
        "Focus a report on one planet across a chosen period.",
        "opastro planet --period daily --planet mars --sign ARIES",
    ),
    (
        "natal",
        "Build a personalized birth chart and visual report.",
        "opastro natal --help",
    ),
    (
        "events",
        "Explore the global celestial calendar.",
        "opastro events --period monthly",
    ),
    (
        "explain",
        "Trace the factors behind every rendered section line.",
        "opastro explain --kind horoscope --period daily --sign ARIES",
    ),
    (
        "doctor",
        "Check runtime, dependencies, and ephemeris readiness.",
        "opastro doctor",
    ),
    (
        "logger",
        "Inspect local runtime errors and suggested fixes.",
        "opastro logger show --limit 5",
    ),
    (
        "catalog",
        "Browse supported signs, planets, periods, and sections.",
        "opastro catalog",
    ),
    (
        "completion",
        "Print bash, zsh, or fish shell completion scripts.",
        "opastro completion --shell zsh",
    ),
    (
        "batch",
        "Generate reports across signs and dates.",
        "opastro batch --help",
    ),
    (
        "render",
        "Create planetary scenes and visual exports.",
        "opastro render --help",
    ),
    (
        "serve",
        "Run the local FastAPI integration server.",
        "opastro serve --help",
    ),
)

_UI_HOME_CTAS = (
    ("website", "Explore the OpAstro CLI platform.", "https://opastro.com"),
    (
        "premium",
        "Unlock richer readings and editorial depth.",
        "https://numerologyapi.com",
    ),
    (
        "docs",
        "Read the open-core quickstart and API guides.",
        "https://github.com/dakidarts/opastro/tree/main/docs",
    ),
)


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
        value is not None
        for value in (args.birth_time, args.lat, args.lon, args.timezone)
    )
    if not args.birth_date:
        if has_birth_extras:
            raise ValueError(
                "Provide --birth-date when using --birth-time, --lat/--lon, or --timezone."
            )
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
              opastro logger show --limit 5
              opastro planet --period monthly --planet mercury --sign TAURUS
              opastro natal --birth-date 1997-08-14 --birth-time 09:30 --lat 4.0511 --lon 9.7679 --pdf reports/natal.pdf
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
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="Disable the best-effort latest-release update check for this invocation.",
    )
    parser.add_argument(
        "--force-update-check",
        action="store_true",
        help="Bypass the local update-check cache for this invocation.",
    )
    subparsers = parser.add_subparsers(
        dest="command", parser_class=OpastroArgumentParser
    )

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
    init.add_argument(
        "--template",
        choices=sorted(INIT_TEMPLATES),
        help="Starter template presets: api, cli, natal.",
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
    catalog.add_argument(
        "--json",
        action="store_true",
        help="Output the catalog as JSON for scripts and IDE integrations.",
    )
    catalog.set_defaults(handler=_handle_catalog)

    doctor = subparsers.add_parser(
        "doctor",
        aliases=COMMAND_ALIASES["doctor"],
        help="Run local environment diagnostics for Opastro.",
        description="Check Python runtime, executable path, and key engine readiness flags.",
    )
    doctor.add_argument(
        "--json",
        action="store_true",
        help="Output diagnostics as JSON for CI/automation.",
    )
    doctor.add_argument(
        "--fix",
        action="store_true",
        help="Attempt automatic fixes for detected dependency/runtime gaps.",
    )
    doctor.add_argument(
        "--dry-run",
        action="store_true",
        help="Show fix commands without executing them.",
    )
    doctor.add_argument(
        "--download-ephemeris",
        action="store_true",
        help="Download supported optional asteroid/dwarf-body ephemeris files.",
    )
    doctor.set_defaults(handler=_handle_doctor)

    logger = subparsers.add_parser(
        "logger",
        aliases=COMMAND_ALIASES["logger"],
        help="Inspect and manage runtime error logs with suggested fixes.",
        description="Show, tail, clear, or locate structured CLI runtime error logs.",
    )
    logger.set_defaults(handler=_handle_logger_show, logger_command="show")
    logger_sub = logger.add_subparsers(
        dest="logger_command", parser_class=OpastroArgumentParser
    )

    logger_show = logger_sub.add_parser(
        "show",
        help="Show recent runtime error entries (default action).",
        description="Display structured runtime errors with command context and suggested fixes.",
    )
    logger_show.add_argument(
        "-n",
        "--limit",
        type=int,
        default=20,
        help="Number of most recent entries to show.",
    )
    logger_show.add_argument(
        "--json", action="store_true", help="Render log entries as JSON."
    )
    logger_show.add_argument(
        "--verbose",
        action="store_true",
        help="Include traceback snippets in text mode.",
    )
    logger_show.set_defaults(handler=_handle_logger_show)

    logger_tail = logger_sub.add_parser(
        "tail",
        help="Show a compact recent slice of runtime errors.",
        description="Alias-style compact view for the most recent runtime failures.",
    )
    logger_tail.add_argument(
        "-n",
        "--limit",
        type=int,
        default=8,
        help="Number of most recent entries to show.",
    )
    logger_tail.add_argument(
        "--json", action="store_true", help="Render log entries as JSON."
    )
    logger_tail.add_argument(
        "--verbose",
        action="store_true",
        help="Include traceback snippets in text mode.",
    )
    logger_tail.set_defaults(handler=_handle_logger_show)

    logger_path = logger_sub.add_parser(
        "path",
        help="Print runtime log file path.",
        description="Print absolute path to the current runtime error log file.",
    )
    logger_path.set_defaults(handler=_handle_logger_path)

    logger_clear = logger_sub.add_parser(
        "clear",
        help="Clear runtime error log entries.",
        description="Remove all stored runtime error entries from the local log.",
    )
    logger_clear.set_defaults(handler=_handle_logger_clear)

    profile = subparsers.add_parser(
        "profile",
        aliases=COMMAND_ALIASES["profile"],
        help="Manage saved CLI profiles (save/list/show/use).",
        description="Manage reusable defaults for sign/birth/preferences.",
    )
    profile.set_defaults(handler=_handle_profile_list)
    profile_sub = profile.add_subparsers(
        dest="profile_command", parser_class=OpastroArgumentParser
    )

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
    profile_show.add_argument(
        "--name", help="Profile name. Defaults to active profile."
    )
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
    profile_save.add_argument(
        "--name", required=True, help="Profile name to create/update."
    )
    profile_save.add_argument(
        "--set-active",
        action="store_true",
        help="Set this profile as active after saving.",
    )
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
        choices=[
            "sun",
            "moon",
            "mercury",
            "venus",
            "mars",
            "jupiter",
            "saturn",
            "uranus",
            "neptune",
            "pluto",
            "chiron",
        ],
        help="Planet to focus in the report.",
    )
    planet.set_defaults(handler=_handle_planet)

    events = subparsers.add_parser(
        "events",
        aliases=COMMAND_ALIASES["events"],
        help="Generate a global celestial event calendar.",
        description=(
            "List exact aspects, ingresses, stations, lunations, eclipse windows, "
            "and retrograde emphasis for a standard period."
        ),
    )
    events.add_argument(
        "--period",
        choices=[period.value for period in Period],
        default=Period.MONTHLY.value,
        help="Calendar window (default: monthly).",
    )
    events.add_argument(
        "--target-date",
        help="Date anchoring the calendar window (defaults to today).",
    )
    events.add_argument(
        "--zodiac-system", choices=["tropical", "sidereal"], default=None
    )
    events.add_argument(
        "--ayanamsa",
        choices=["lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"],
        default=None,
    )
    events.add_argument(
        "--house-system", choices=["placidus", "whole_sign", "equal", "koch"]
    )
    events.add_argument("--node-type", choices=["true", "mean"])
    events.add_argument("--tenant-id", help="Tenant identifier for cache isolation.")
    events.add_argument(
        "--format",
        dest="events_format",
        choices=["text", "json", "ics"],
        default="text",
        help="Output format (default: text).",
    )
    events.add_argument("--export", help="Optional output file path.")
    events.set_defaults(handler=_handle_celestial_events)

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
    serve.add_argument(
        "--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)."
    )
    serve.add_argument(
        "--port", type=int, default=8000, help="Bind port (default: 8000)."
    )
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
    explain.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly", "yearly"],
        help="Report period.",
    )
    explain.add_argument(
        "--planet",
        choices=[p.value for p in PlanetName],
        help="Planet required for kind=planet.",
    )
    _add_common_report_args(explain, require_period=False)
    explain.set_defaults(handler=_handle_explain)

    completion = subparsers.add_parser(
        "completion",
        aliases=COMMAND_ALIASES["completion"],
        help="Print shell completion script.",
        description="Generate shell completion for bash/zsh/fish.",
    )
    completion.add_argument(
        "--shell", choices=["bash", "zsh", "fish"], required=True, help="Target shell."
    )
    completion.set_defaults(handler=_handle_completion)

    ui = subparsers.add_parser(
        "ui",
        aliases=COMMAND_ALIASES["ui"],
        help="Interactive TUI report browser with section drill-down.",
        description="Launch curses-based keyboard UI for report navigation.",
    )
    ui.add_argument(
        "--kind",
        choices=["horoscope", "birthday", "planet", "events"],
        default="horoscope",
        help="Report mode to browse (default: horoscope).",
    )
    ui.add_argument(
        "--planet",
        choices=[p.value for p in PlanetName],
        help="Planet required for --kind planet.",
    )
    ui.add_argument(
        "--period",
        choices=["daily", "weekly", "monthly", "yearly"],
        help="Report period; omit it for the interactive home deck.",
    )
    _add_common_report_args(ui, require_period=False)
    ui.add_argument(
        "--no-interactive",
        action="store_true",
        help="Fallback to static text render (no curses).",
    )
    ui.add_argument(
        "--ascii",
        action="store_true",
        help="Use ASCII dividers and markers for limited terminals.",
    )
    ui.set_defaults(handler=_handle_ui)

    batch = subparsers.add_parser(
        "batch",
        aliases=COMMAND_ALIASES["batch"],
        help="Batch-generate reports for multiple signs and dates.",
        description="Run deterministic generation across many sign/date combinations.",
    )
    batch.add_argument(
        "--kind", choices=["horoscope", "birthday", "planet"], default="horoscope"
    )
    batch.add_argument(
        "--period", required=True, choices=["daily", "weekly", "monthly", "yearly"]
    )
    batch.add_argument(
        "--planet",
        choices=[p.value for p in PlanetName],
        help="Required for kind=planet.",
    )
    batch.add_argument(
        "--signs",
        help="Comma-separated signs. Defaults to profile sign or all zodiac signs.",
    )
    batch.add_argument(
        "--sign",
        help="Generate one sign. Equivalent to a one-item --signs value.",
    )
    batch.add_argument("--target-date", help="Single ISO date YYYY-MM-DD.")
    batch.add_argument("--date-from", help="Range start ISO date YYYY-MM-DD.")
    batch.add_argument("--date-to", help="Range end ISO date YYYY-MM-DD.")
    batch.add_argument(
        "--step-days",
        type=int,
        default=1,
        help="Step days for date ranges (default: 1).",
    )
    batch.add_argument("--sections", help="Comma-separated sections.")
    batch.add_argument("--birth-date", help="Birth date in ISO format YYYY-MM-DD.")
    batch.add_argument("--birth-time", help="Birth time in HH:MM format.")
    batch.add_argument("--lat", type=float, help="Birth latitude.")
    batch.add_argument("--lon", type=float, help="Birth longitude.")
    batch.add_argument("--timezone", help="IANA timezone.")
    batch.add_argument("--zodiac-system", choices=["sidereal", "tropical"])
    batch.add_argument(
        "--ayanamsa",
        choices=["lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"],
    )
    batch.add_argument(
        "--house-system", choices=["placidus", "whole_sign", "equal", "koch"]
    )
    batch.add_argument("--node-type", choices=["true", "mean"])
    batch.add_argument("--tenant-id", help="Tenant identifier.")
    batch.add_argument(
        "--format", dest="output_format", choices=OUTPUT_FORMATS, default="text"
    )
    batch.add_argument("--export-dir", help="Directory for per-item exports.")
    batch.set_defaults(handler=_handle_batch)

    render = subparsers.add_parser(
        "render",
        aliases=COMMAND_ALIASES["render"],
        help="Generate visual artifacts and premium planetary scenes.",
        description="Render visual outputs directly.",
    )
    # Default handler to show help if no subcommand is provided.
    render.set_defaults(handler=lambda args: render.print_help() or 0)
    render_sub = render.add_subparsers(
        dest="render_command", parser_class=OpastroArgumentParser
    )

    planetary_scene = render_sub.add_parser(
        "planetary-scene",
        help="Generate a 2D/2.5D solar system or celestial scene.",
        description="Render deterministic planetary positions onto a beautifully stylised map.",
    )
    planetary_scene.add_argument(
        "--datetime",
        help="ISO date-time to render, e.g., 2026-04-16T12:00:00Z. Defaults to now.",
    )
    planetary_scene.add_argument(
        "--theme",
        choices=["dark", "neon-blue", "observatory", "gold-premium"],
        default="dark",
        help="Color theme for the scene.",
    )
    planetary_scene.add_argument(
        "--format", choices=["svg", "png"], default="svg", help="Output format."
    )
    planetary_scene.add_argument(
        "--projection",
        choices=["perspective", "top-down"],
        default="perspective",
        help="Perspective or top-down grid style.",
    )
    planetary_scene.add_argument(
        "--include-labels",
        action="store_true",
        default=True,
        help="Include planetary labels (default true).",
    )
    planetary_scene.add_argument(
        "--no-labels",
        action="store_false",
        dest="include_labels",
        help="Omit planetary labels.",
    )
    planetary_scene.add_argument(
        "--include-orbits",
        action="store_true",
        default=True,
        help="Include orbit rings (default true).",
    )
    planetary_scene.add_argument(
        "--no-orbits",
        action="store_false",
        dest="include_orbits",
        help="Omit orbit rings.",
    )
    planetary_scene.add_argument(
        "--include-minor-bodies",
        action="store_true",
        default=False,
        help="Include chiron, nodes, etc. (default false).",
    )
    planetary_scene.add_argument(
        "--include-aspects",
        action="store_true",
        default=False,
        help="Draw aspect connector lines (default false).",
    )
    planetary_scene.add_argument(
        "--include-zodiac-band",
        action="store_true",
        default=True,
        help="Draw the tropical zodiac reference band (default true).",
    )
    planetary_scene.add_argument(
        "--no-zodiac-band",
        action="store_false",
        dest="include_zodiac_band",
        help="Omit the tropical zodiac reference band.",
    )
    planetary_scene.add_argument(
        "--include-motion",
        action="store_true",
        default=True,
        help="Draw direct/retrograde motion trails (default true).",
    )
    planetary_scene.add_argument(
        "--no-motion",
        action="store_false",
        dest="include_motion",
        help="Omit instantaneous motion trails.",
    )
    planetary_scene.add_argument(
        "--transparent",
        action="store_true",
        default=False,
        help="Render with a transparent background (PNG/SVG).",
    )
    planetary_scene.add_argument(
        "--export", help="Output file path.", default="planetary_scene.svg"
    )
    planetary_scene.set_defaults(handler=_handle_render_planetary_scene)

    return parser


def _add_common_report_args(
    parser: argparse.ArgumentParser, *, require_period: bool
) -> None:
    if require_period:
        parser.add_argument(
            "--period",
            required=True,
            choices=["daily", "weekly", "monthly", "yearly"],
            help="Report period.",
        )
    parser.add_argument("--sign", help="Zodiac sign (e.g. ARIES, TAURUS, GEMINI).")
    parser.add_argument(
        "--target-date", help="ISO date used to anchor the report, format YYYY-MM-DD."
    )
    parser.add_argument(
        "--sections",
        help="Comma-separated sections. Example: general,career,money",
    )
    parser.add_argument("--birth-date", help="Birth date in ISO format YYYY-MM-DD.")
    parser.add_argument("--birth-time", help="Birth time in HH:MM format.")
    parser.add_argument(
        "--lat", type=float, help="Birth latitude for personalized house calculations."
    )
    parser.add_argument(
        "--lon", type=float, help="Birth longitude for personalized house calculations."
    )
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
    parser.add_argument(
        "--lat", type=float, help="Birth latitude for house calculations."
    )
    parser.add_argument(
        "--lon", type=float, help="Birth longitude for house calculations."
    )
    parser.add_argument("--timezone", help="IANA timezone, e.g. Africa/Douala.")
    parser.add_argument(
        "--user-name", help="Display name for personalized natal chart branding."
    )
    parser.add_argument("--zodiac-system", choices=["sidereal", "tropical"])
    parser.add_argument(
        "--ayanamsa",
        choices=["lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"],
    )
    parser.add_argument(
        "--house-system", choices=["placidus", "whole_sign", "equal", "koch"]
    )
    parser.add_argument("--node-type", choices=["true", "mean"])
    parser.add_argument("--tenant-id", help="Tenant identifier.")
    parser.add_argument("--json", action="store_true", help="Output raw natal JSON.")
    parser.add_argument("--wheel-svg", help="Export wheel chart as SVG.")
    parser.add_argument(
        "--split",
        action="store_true",
        help="Split wheel SVG into parts (full/main/legends).",
    )
    parser.add_argument(
        "--split-png",
        action="store_true",
        help="Export split wheel parts as PNG (main/legends/combined).",
    )
    parser.add_argument(
        "--split-layout",
        choices=["stacked", "side-by-side"],
        default="side-by-side",
        help="Presentation layout for split/composed wheel outputs.",
    )
    parser.add_argument(
        "--split-dir", help="Directory for split wheel parts when using --split."
    )
    parser.add_argument("--wheel-png", help="Export wheel chart as PNG.")
    parser.add_argument("--house-map", help="Export house overlay map JSON.")
    parser.add_argument("--pdf", help="Export branded natal PDF report.")
    parser.add_argument(
        "--brand-title", default=None, help="Brand title for exported assets."
    )
    parser.add_argument("--brand-url", default=None, help="Brand URL for PDF footer.")
    parser.add_argument(
        "--premium-url", default=None, help="Premium URL callout in PDF."
    )
    parser.add_argument(
        "--accent", default=None, help="Hex accent color for visual exports."
    )
    parser.add_argument(
        "--wheel-theme",
        choices=["night", "day"],
        default=None,
        help="Wheel color theme for SVG/PNG/PDF exports.",
    )
    parser.add_argument(
        "--include-fixed-stars",
        action="store_true",
        help="Include fixed star positions in the natal snapshot.",
    )
    parser.add_argument(
        "--include-arabic-parts",
        action="store_true",
        help="Include Arabic parts (Part of Fortune, Part of Spirit) in the natal snapshot.",
    )


def _add_profile_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--user-name", help="Default display name for personalized natal charts."
    )
    parser.add_argument("--sign", help="Default zodiac sign, e.g. ARIES.")
    parser.add_argument(
        "--birth-date", help="Default birth date in ISO format YYYY-MM-DD."
    )
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
        "--wheel-theme", choices=["night", "day"], help="Default natal wheel theme."
    )
    parser.add_argument("--accent", help="Default natal accent hex color.")
    parser.add_argument("--brand-title", help="Default natal brand title for exports.")
    parser.add_argument("--brand-url", help="Default natal brand URL for PDF footer.")
    parser.add_argument(
        "--premium-url", help="Default natal premium URL callout for PDF."
    )
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
    force_color = (
        os.getenv("CLICOLOR_FORCE") or os.getenv("FORCE_COLOR") or ""
    ).strip()
    if force_color and force_color not in {"0", "false", "False"}:
        return True
    term = (os.getenv("TERM") or "").strip().lower()
    if term == "dumb":
        return False
    return sys.stdout.isatty()


def _supports_truecolor() -> bool:
    if (os.getenv("OPASTRO_TRUECOLOR") or "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }:
        return True
    if (os.getenv("OPASTRO_TRUECOLOR") or "").strip().lower() in {
        "0",
        "false",
        "off",
        "no",
    }:
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


def _gradient_lines(
    block: str, colors: list[tuple[int, int, int]], *, bold: bool = False
) -> str:
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
    columns = shutil.get_terminal_size((DEFAULT_WRAP_WIDTH, 20)).columns
    return max(20, min(DEFAULT_WRAP_WIDTH, columns))


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
    if _ascii_terminal():
        return {
            "h": "-",
            "v": "|",
            "tl": "+",
            "tr": "+",
            "bl": "+",
            "br": "+",
            "tm": "+",
            "bm": "+",
            "lm": "+",
            "rm": "+",
            "mm": "+",
        }
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


def _ascii_terminal(explicit: bool = False) -> bool:
    if explicit:
        return True
    mode = (os.getenv("OPASTRO_ASCII") or "").strip().lower()
    if mode in {"1", "true", "on", "yes"}:
        return True
    encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
    return bool(encoding and "utf" not in encoding)


def _ui_glyphs(*, ascii_mode: bool = False) -> dict[str, str]:
    if _ascii_terminal(ascii_mode):
        return {
            "bullet": "-",
            "rule": "-",
            "divider": "|",
            "marker": ">",
            "nav": "up/down",
        }
    return {
        "bullet": "•",
        "rule": "─",
        "divider": "│",
        "marker": "▸",
        "nav": "↑↓",
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
    left_width = min(
        max(left_min_width, max(len(value) for value in left_seed)), left_max_width
    )
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


def _formatter_action_strings(
    parser: argparse.ArgumentParser, action: argparse.Action
) -> tuple[str, str]:
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
    lines.append(
        _gradient_lines(
            "OPASTRO HELP", [ACCENT_SOFT_RGB, ACCENT_RGB, ACCENT_DEEP_RGB], bold=True
        )
    )
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
            f"{key}={value}"
            for key, value in list(payload.data.factor_values.items())[:6]
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
        preview = ", ".join(
            f"`{key}={value}`"
            for key, value in list(payload.data.factor_values.items())[:6]
        )
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
        highlights = "".join(
            f"<li>{html_escape(item)}</li>" for item in insight.highlights[:3]
        )
        cautions = "".join(
            f"<li>{html_escape(item)}</li>" for item in insight.cautions[:2]
        )
        actions = "".join(
            f"<li>{html_escape(item)}</li>" for item in insight.actions[:2]
        )
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
            html_escape(f"{key}={value}")
            for key, value in list(payload.data.factor_values.items())[:6]
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
    {"".join(section_blocks)}
    <footer>{html_escape(UPSELL_TEXT).replace(chr(10), "<br/>")}</footer>
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


def _render_output(
    payload, *, output_format: str, export_path: Optional[str] = None
) -> int:
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
        target.write_text(rendered, encoding="utf-8")
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
    target.write_text(content, encoding="utf-8")
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
        include_fixed_stars=getattr(args, "include_fixed_stars", False),
        include_arabic_parts=getattr(args, "include_arabic_parts", False),
    )


def _render_natal_text(report) -> str:
    lines: list[str] = []
    lines.append("OPASTRO NATAL REPORT")
    lines.append("".ljust(min(96, _term_width()), "─"))
    lines.append(
        f"Sign: {report.sign} | Birth: {report.birth.date.isoformat()} | "
        f"Rising: {report.snapshot.rising_sign or 'N/A'} | Houses: {report.snapshot.house_system or 'N/A'}"
    )
    lines.append(
        f"Positions: {len(report.snapshot.positions)} | Aspects: {len(report.snapshot.aspects)}"
    )
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
    if report.snapshot.fixed_stars:
        lines.append(f"Fixed stars: {len(report.snapshot.fixed_stars)}")
    if report.snapshot.arabic_parts:
        for part in report.snapshot.arabic_parts:
            lines.append(
                f"{part.name}: {part.sign} {part.degree_in_sign:.1f}° ({part.formula})"
            )
    lines.append("")
    lines.append(UPSELL_TEXT)
    return "\n".join(lines)


def _export_natal_assets(report, args: argparse.Namespace) -> list[Path]:
    exports: list[Path] = []
    accent = args.accent or "#3ddd77"
    brand_title = args.brand_title or "OPASTRO"
    brand_url = args.brand_url or "https://opastro.com"
    premium_url = args.premium_url or "https://numerologyapi.com"
    wheel_theme = args.wheel_theme or "night"
    split_requested = bool(args.split or args.split_png)
    split_payload: Optional[dict[str, Any]] = None
    if split_requested:
        split_payload = build_natal_wheel_svg_split(
            report,
            accent_color=accent,
            brand_title=brand_title,
            user_name=getattr(args, "user_name", None),
            theme=wheel_theme,
            split_layout=args.split_layout,
        )

    if args.wheel_svg:
        svg = (
            split_payload["full_svg"]
            if split_payload
            else build_natal_wheel_svg(
                report,
                accent_color=accent,
                brand_title=brand_title,
                user_name=getattr(args, "user_name", None),
                theme=wheel_theme,
            )
        )
        target = _save_export(svg, args.wheel_svg)
        exports.append(target)

    if split_payload:
        if args.split_dir:
            split_dir = Path(args.split_dir).expanduser()
            base_name = "natal-wheel"
            if args.wheel_svg:
                base_name = Path(args.wheel_svg).expanduser().stem
        elif args.wheel_svg:
            wheel_svg_path = Path(args.wheel_svg).expanduser()
            split_dir = wheel_svg_path.parent
            base_name = wheel_svg_path.stem
        else:
            split_dir = Path("reports/natal-split").expanduser()
            base_name = "natal-wheel"
        split_dir.mkdir(parents=True, exist_ok=True)

        if not args.wheel_svg or args.split_dir:
            full_target = split_dir / f"{base_name}.full.svg"
            full_target.write_text(split_payload["full_svg"])
            exports.append(full_target)

        main_target = split_dir / f"{base_name}.main.svg"
        legends_target = split_dir / f"{base_name}.legends.svg"
        combined_target = split_dir / f"{base_name}.combined.svg"
        main_target.write_text(split_payload["main_wheel_svg"])
        legends_target.write_text(split_payload["legends_svg"])
        combined_target.write_text(split_payload["combined_svg"])
        exports.append(main_target)
        exports.append(legends_target)
        exports.append(combined_target)

        if args.split_png:
            png_parts = build_natal_wheel_png_split(
                report,
                accent_color=accent,
                brand_title=brand_title,
                user_name=getattr(args, "user_name", None),
                theme=wheel_theme,
                split_layout=args.split_layout,
            )
            main_png_target = split_dir / f"{base_name}.main.png"
            legends_png_target = split_dir / f"{base_name}.legends.png"
            combined_png_target = split_dir / f"{base_name}.combined.png"
            main_png_target.write_bytes(png_parts["main_wheel_png"])
            legends_png_target.write_bytes(png_parts["legends_png"])
            combined_png_target.write_bytes(png_parts["combined_png"])
            exports.append(main_png_target)
            exports.append(legends_png_target)
            exports.append(combined_png_target)

    if args.wheel_png:
        png_bytes = build_natal_wheel_png(
            report,
            accent_color=accent,
            brand_title=brand_title,
            user_name=getattr(args, "user_name", None),
            theme=wheel_theme,
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
            accent_color=accent,
            brand_title=brand_title,
            user_name=getattr(args, "user_name", None),
            brand_url=brand_url,
            premium_url=premium_url,
            wheel_theme=wheel_theme,
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


def _build_celestial_events_request(args: argparse.Namespace) -> CelestialEventsRequest:
    return CelestialEventsRequest(
        period=args.period or Period.MONTHLY.value,
        target_date=_parse_date(args.target_date) if args.target_date else None,
        zodiac_system=getattr(args, "zodiac_system", None),
        ayanamsa=getattr(args, "ayanamsa", None),
        house_system=getattr(args, "house_system", None),
        node_type=getattr(args, "node_type", None),
        tenant_id=getattr(args, "tenant_id", None),
    )


def _build_ui_events_payload(response: Any) -> _UIEventsPayload:
    sections: list[_UIEventSection] = []
    for event in response.events:
        timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        exactness = (
            f" Orb: {event.exactness:.2f} degrees."
            if event.exactness is not None
            else ""
        )
        references = [
            value for value in (event.body1, event.body2, event.sign) if value
        ]
        priority = event.narrative_priority
        intensity = (
            "high" if priority >= 1.5 else "elevated" if priority >= 1.0 else "steady"
        )
        sections.append(
            _UIEventSection(
                section=_UIEventKey(event.event_type),
                title=event.description,
                summary=f"{timestamp} | {event.event_type}.{exactness}",
                highlights=[
                    f"References: {', '.join(references)}"
                    if references
                    else "Global ephemeris event",
                    f"Narrative priority: {priority:.3f}",
                ],
                cautions=[],
                actions=[],
                intensity=intensity,
                factor_details=[],
            )
        )
    if not sections:
        sections.append(
            _UIEventSection(
                section=_UIEventKey("calendar"),
                title="No notable celestial events",
                summary="The selected period contains no events in the current event catalog.",
                highlights=[],
                cautions=[],
                actions=[],
                intensity="quiet",
                factor_details=[],
            )
        )
    return _UIEventsPayload(
        period=response.period,
        sign="GLOBAL",
        sections=sections,
        response=response,
    )


def _generate_payload(service: HoroscopeService, args: argparse.Namespace, kind: str):
    if kind == "events":
        return _build_ui_events_payload(
            service.generate_celestial_events(_build_celestial_events_request(args))
        )
    if kind == "birthday":
        return service.generate_birthday(_build_birthday_request(args))
    if kind == "planet":
        return service.generate_planet(_build_planet_request(args))
    return service.generate(_build_horoscope_request(args))


def _line_provenance(
    lines: list[str], details: list[Any], *, insight_key: str
) -> list[dict[str, Any]]:
    if not lines:
        return []
    if not details:
        return [
            {"line": line, "source_factors": [], "why": "No factor details available"}
            for line in lines
        ]
    sorted_details = sorted(details, key=lambda detail: detail.weight, reverse=True)
    output: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        primary = sorted_details[idx % len(sorted_details)]
        secondary = sorted_details[(idx + 1) % len(sorted_details)]
        why = (
            primary.factor_insights.get(insight_key)
            or primary.factor_insights.get("lite_meaning")
            or ""
        )
        output.append(
            {
                "line": line,
                "source_factors": [primary.factor_type, secondary.factor_type]
                if secondary != primary
                else [primary.factor_type],
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
                    "action_hint": detail.factor_insights.get(tip_key)
                    or detail.factor_insights.get("affirmation"),
                }
            )

        sections.append(
            {
                "section": insight.section.value,
                "title": insight.title,
                "intensity": insight.intensity,
                "summary": {
                    "line": insight.summary,
                    "source_factors": [
                        d.factor_type
                        for d in sorted(
                            insight.factor_details, key=lambda x: x.weight, reverse=True
                        )[:3]
                    ],
                    "why": "Summary is composed from highest-weighted factor details with deterministic cadence templates.",
                },
                "highlights": _line_provenance(
                    insight.highlights, insight.factor_details, insight_key="motivation"
                ),
                "cautions": _line_provenance(
                    insight.cautions, insight.factor_details, insight_key="caution"
                ),
                "actions": _line_provenance(
                    insight.actions, insight.factor_details, insight_key=tip_key
                ),
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
        lines.append(
            f"{section['section'].replace('_', ' ').title()} ({section['intensity']})"
        )
        lines.append(f"  Summary: {section['summary']['line']}")
        lines.append(f"  Why: {section['summary']['why']}")
        lines.append(
            f"  Source factors: {', '.join(section['summary']['source_factors'])}"
        )
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
        lines.append(
            f"## {section['section'].replace('_', ' ').title()} ({section['intensity']})"
        )
        lines.append("")
        lines.append(f"**Summary line**: {section['summary']['line']}")
        lines.append("")
        lines.append(f"**Why**: {section['summary']['why']}")
        lines.append("")
        lines.append(
            f"**Source factors**: {', '.join('`' + f + '`' for f in section['summary']['source_factors'])}"
        )
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
              <h2>{html_escape(section["section"].replace("_", " ").title())} <span class="pill">{html_escape(section["intensity"])}</span></h2>
              <p><strong>Summary:</strong> {html_escape(section["summary"]["line"])}</p>
              <p><strong>Why:</strong> {html_escape(section["summary"]["why"])}</p>
              <p><strong>Source factors:</strong> {html_escape(", ".join(section["summary"]["source_factors"]))}</p>
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
<p><strong>Type:</strong> {html_escape(explain_payload["report_type"])} |
<strong>Sign:</strong> {html_escape(explain_payload["sign"])} |
<strong>Period:</strong> {html_escape(explain_payload["period"])}</p>
{"".join(body)}
</main></body></html>"""


def _render_explain_output(
    explain_payload: dict[str, Any], *, output_format: str, export_path: Optional[str]
) -> int:
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


def _show_welcome(update_info: UpdateCheckResult | None = None) -> int:
    print(
        _gradient_lines(
            WELCOME_BANNER.strip("\n"),
            [ACCENT_SOFT_RGB, ACCENT_RGB, ACCENT_DEEP_RGB],
            bold=True,
        )
    )
    print(
        _style(
            f"OPASTRO • Open Core Horoscope Engine • {_app_version()}",
            COLOR_ACCENT_BOLD,
        )
    )
    notice = update_notice(update_info) if update_info else None
    if notice:
        print(_style(notice, "1;33"))
    print(
        _wrap(
            "Enterprise-grade deterministic calculations with lightweight open meanings."
        )
    )
    _print_divider()
    _print_heading("Commands")
    commands = [
        ("init", "Run guided onboarding and save default profile preferences."),
        ("welcome", "Show the branded home screen and onboarding shortcuts."),
        ("profile", "Save/list/show/use reusable profile defaults."),
        ("catalog", "List all supported periods, sections, signs, and planets."),
        ("doctor", "Inspect Python runtime, executable path, and readiness status."),
        ("logger", "Inspect runtime error logs and recommended fixes."),
        ("horoscope", "Generate a standard period report from sign or birth data."),
        ("birthday", "Generate a yearly birthday-cycle report."),
        ("planet", "Generate a planet-focused report for deeper diagnostics."),
        ("events", "Browse global celestial events or export an iCalendar feed."),
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
    print(
        _wrap(
            "opastro horoscope --period daily --sign ARIES --target-date 2026-08-17",
            indent="  ",
        )
    )
    print(_wrap("opastro --help", indent="  "))
    _print_divider()
    print(_gradient_lines(UPSELL_TEXT, [ACCENT_SOFT_RGB, ACCENT_RGB], bold=True))
    return 0


def _handle_welcome(args: argparse.Namespace) -> int:
    return _show_welcome(getattr(args, "update_info", None))


def _catalog_payload() -> dict[str, Any]:
    return {
        "version": _app_version(),
        "periods": [period.value for period in Period],
        "sections": [section.value for section in Section],
        "signs": list(ZODIAC_SIGNS),
        "planets": [planet.value for planet in PlanetName],
    }


def _handle_catalog(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(_catalog_payload(), indent=2, sort_keys=True))
        return 0
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


def _terminal_diagnostics() -> dict[str, Any]:
    term = (os.getenv("TERM") or "").strip()
    colorterm = (os.getenv("COLORTERM") or "").strip()
    color_mode = (os.getenv("OPASTRO_COLOR") or "auto").strip().lower()
    no_color = bool(os.getenv("NO_COLOR")) or color_mode in {
        "0",
        "false",
        "never",
        "off",
        "disabled",
    }
    truecolor = colorterm.lower() in {"truecolor", "24bit"}
    return {
        "term": term or None,
        "colorterm": colorterm or None,
        "color_mode": color_mode,
        "color_enabled": _should_colorize(),
        "no_color": no_color,
        "truecolor": truecolor,
    }


def _doctor_fix(*, dry_run: bool, emit_text: bool = True) -> dict[str, Any]:
    command = [sys.executable, "-m", "pip", "install", "-e", ".[dev]"]
    payload: dict[str, Any] = {
        "requested": True,
        "dry_run": bool(dry_run),
        "command": command,
    }
    if dry_run:
        payload["status"] = "planned"
        if emit_text:
            print(f"Fix plan      : {' '.join(command)}")
        return payload
    if emit_text:
        print("Applying fix  : Installing project dependencies...")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    payload["status"] = "ok" if result.returncode == 0 else "warn"
    payload["returncode"] = result.returncode
    if result.returncode == 0:
        if emit_text:
            print(_style("Fix result    : OK (dependencies installed)", "1;32"))
    else:
        stderr_preview = "\n".join(result.stderr.splitlines()[-5:])
        payload["stderr_preview"] = stderr_preview
        if emit_text:
            print(
                _style(f"Fix result    : WARN (pip exited {result.returncode})", "1;33")
            )
        if stderr_preview:
            if emit_text:
                print(stderr_preview)
    return payload


def _handle_doctor(args: argparse.Namespace) -> int:
    cfg = ServiceConfig()
    if not args.json:
        _print_heading("OPASTRO DOCTOR")
        _print_divider()
        print(f"OpAstro version: {_app_version()}")
        print(f"Python version : {platform.python_version()}")
        print(f"Python exec    : {sys.executable}")
        print(f"Platform       : {platform.platform()}")
        terminal = _terminal_diagnostics()
        print(
            "Color support  : "
            f"{'enabled' if terminal['color_enabled'] else 'disabled'} "
            f"(TERM={terminal['term'] or 'unset'})"
        )
        print(f"Config dir     : {_config_dir()}")
        print(f"Ephemeris path : {cfg.ephemeris.ephemeris_path or 'auto/not-set'}")
        print(f"Zodiac system  : {cfg.ephemeris.zodiac_system}")
        print(f"Ayanamsa       : {cfg.ephemeris.ayanamsa_system}")
    in_venv = sys.prefix != sys.base_prefix
    if not args.json:
        print(f"Virtual env    : {'yes' if in_venv else 'no'}")

    required = f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+"
    runtime_ok = sys.version_info >= MIN_PYTHON_VERSION
    if not args.json:
        if sys.version_info >= MIN_PYTHON_VERSION:
            print(
                _style(
                    f"Runtime check  : OK (Python {required} requirement satisfied)",
                    "1;32",
                )
            )
        else:
            current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            print(
                _style(
                    f"Runtime check  : WARN (running {current}; requires {required})",
                    "1;33",
                )
            )
            print(
                "Recommendation : Use a Python 3.11+ virtual environment and reinstall opastro."
            )

    missing_deps, ok_deps = _dependency_health()
    if not args.json:
        print(f"Deps loaded    : {', '.join(ok_deps) if ok_deps else 'none'}")
        if missing_deps:
            print(_style(f"Deps missing   : {', '.join(missing_deps)}", "1;33"))
        else:
            print(_style("Deps check     : OK", "1;32"))

    payload: dict[str, Any] = {
        "opastro_version": _app_version(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "config_dir": str(_config_dir()),
        "terminal": _terminal_diagnostics(),
        "analytics": {
            "enabled": _analytics_enabled(),
            "path": str(_analytics_log_path()),
        },
        "ephemeris_path": cfg.ephemeris.ephemeris_path or "auto/not-set",
        "zodiac_system": str(cfg.ephemeris.zodiac_system),
        "ayanamsa": str(cfg.ephemeris.ayanamsa_system),
        "virtual_env": in_venv,
        "runtime_ok": runtime_ok,
        "runtime_required": required,
        "dependencies": {
            "loaded": ok_deps,
            "missing": missing_deps,
            "ok": not missing_deps,
        },
        "fix": {"requested": bool(args.fix), "dry_run": bool(args.dry_run)},
    }
    if not runtime_ok:
        payload["runtime_recommendation"] = (
            "Use a Python 3.11+ virtual environment and reinstall opastro."
        )

    if args.fix:
        if not in_venv and not args.dry_run:
            payload["fix"] = {
                "requested": True,
                "dry_run": False,
                "blocked": True,
                "reason": "outside_virtualenv",
                "recommendation": "Create a venv first, then run `opastro doctor --fix`.",
            }
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
                return 0
            print(
                _style(
                    "Fix blocked   : Refusing to install outside a virtual environment.",
                    "1;33",
                )
            )
            print(
                "Recommendation : Create a venv first, then run `opastro doctor --fix`."
            )
            return 0

        payload["fix"] = _doctor_fix(dry_run=args.dry_run, emit_text=not args.json)
        if not args.dry_run:
            after_missing, _ = _dependency_health()
            payload["post_fix"] = {
                "missing": after_missing,
                "ok": not after_missing,
            }
            if not after_missing:
                if not args.json:
                    print(_style("Post-fix check : OK", "1;32"))
            else:
                if not args.json:
                    print(
                        _style(
                            f"Post-fix check : WARN (still missing: {', '.join(after_missing)})",
                            "1;33",
                        )
                    )
    elif missing_deps or not runtime_ok:
        payload["suggestion"] = (
            "Run `opastro doctor --fix --dry-run` to preview automatic remediation."
        )
        if not args.json:
            print(
                "Suggestion     : Run `opastro doctor --fix --dry-run` to preview automatic remediation."
            )

    # Ephemeris health check
    ephe_missing = missing_ephemeris_files(cfg.ephemeris.ephemeris_path)
    downloadable_missing = {
        filename: description
        for filename, description in DOWNLOADABLE_EPHE_FILES.items()
        if filename in ephe_missing
    }
    manual_missing = {
        filename: description
        for filename, description in MANUAL_EPHE_FILES.items()
        if filename in ephe_missing
    }
    ephemeris_dir = (
        Path(cfg.ephemeris.ephemeris_path).expanduser()
        if cfg.ephemeris.ephemeris_path
        else Path.home() / ".cache" / "opastro" / "ephemeris"
    )
    minor_names = [b.name for b in MINOR_BODIES]
    payload["minor_bodies_available"] = minor_names
    payload["ephemeris_files_missing"] = ephe_missing
    payload["ephemeris_files_downloadable"] = downloadable_missing
    payload["ephemeris_files_manual"] = manual_missing
    payload["fixed_star_catalogue"] = {
        "available": "sefstars.txt" not in manual_missing,
        "optional": True,
        "path": str(ephemeris_dir / "sefstars.txt"),
        "required_for": "include_fixed_stars",
    }

    if not args.json:
        print(f"Minor bodies   : {', '.join(minor_names) if minor_names else 'none'}")
        if ephe_missing:
            status = "MISSING"
            if not downloadable_missing and manual_missing:
                status = "OPTIONAL MISSING"
            print(
                _style(
                    f"Ephemeris files: {status} ({', '.join(ephe_missing)})",
                    "1;33",
                )
            )
            if downloadable_missing:
                print(
                    "Recommendation : Run `opastro doctor --download-ephemeris` to fetch supported optional files."
                )
            if manual_missing:
                print(
                    "Fixed stars    : Install `sefstars.txt` manually and point `SE_EPHE_PATH` at its directory."
                )
            else:
                print(_style("Fixed stars    : OK", "1;32"))
        else:
            print(_style("Ephemeris files: OK", "1;32"))
            print(_style("Fixed stars    : OK", "1;32"))

    if args.download_ephemeris:
        if not args.json:
            _print_heading("Downloading Ephemeris Files")
        try:
            download_report = ensure_minor_body_ephemeris_report(
                cfg.ephemeris.ephemeris_path
            )
            downloaded = download_report.downloaded
            payload["downloaded"] = [str(p) for p in downloaded]
            payload["downloadable_files_missing_after_download"] = (
                download_report.missing_downloadable
            )
            payload["ephemeris_files_missing_after_download"] = missing_ephemeris_files(
                cfg.ephemeris.ephemeris_path
            )
            if not args.json:
                if downloaded:
                    for path in downloaded:
                        print(f"  Downloaded   : {path}")
                if download_report.missing_downloadable:
                    print(
                        _style(
                            "Download result: INCOMPLETE (supported files still missing).",
                            "1;33",
                        )
                    )
                elif downloaded:
                    print(_style("Download result: OK", "1;32"))
                else:
                    print("Download result: No supported files needed downloading.")
                if manual_missing:
                    print(
                        "Fixed-star note : `sefstars.txt` is not auto-downloaded; install it manually for fixed-star output."
                    )
        except Exception as exc:
            payload["download_error"] = str(exc)
            if not args.json:
                print(_style(f"Download error : {exc}", "1;31"))
        # Refresh minor body list after download
        # (requires re-import, so just report what we have)
        payload["minor_bodies_available_after_download"] = minor_names

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))

    return 0


def _config_dir() -> Path:
    override = os.getenv("OPASTRO_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "opastro"


def _runtime_log_path() -> Path:
    return _config_dir() / RUNTIME_LOG_FILENAME


def _analytics_log_path() -> Path:
    return _config_dir() / ANALYTICS_LOG_FILENAME


def _analytics_enabled() -> bool:
    mode = (os.getenv("OPASTRO_ANALYTICS") or "").strip().lower()
    return mode in {"1", "true", "on", "yes", "enabled"}


def _canonical_command_name(token: Optional[str]) -> str:
    if not token:
        return "welcome"
    if token.startswith("-"):
        return "root"
    if token in COMMAND_ALIASES:
        return token
    for command, aliases in COMMAND_ALIASES.items():
        if token in aliases:
            return command
    return token


def _failure_category_for_exception(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return "validation"
    if isinstance(exc, (ModuleNotFoundError, ImportError)):
        return "dependency"
    if isinstance(exc, PermissionError):
        return "permission"
    if isinstance(exc, FileNotFoundError):
        return "filesystem"
    if isinstance(exc, RuntimeError):
        return "runtime"
    return "unknown"


def _record_analytics_event(
    *,
    command: str,
    exit_code: int,
    duration_ms: int,
    failure_category: Optional[str] = None,
) -> None:
    if not _analytics_enabled():
        return
    payload: dict[str, Any] = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "opastro_version": _app_version(),
        "python_major_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "command": command,
        "exit_code": int(exit_code),
        "status": "ok" if int(exit_code) == 0 else "error",
        "duration_ms": max(0, int(duration_ms)),
    }
    if failure_category:
        payload["failure_category"] = failure_category
    try:
        target = _analytics_log_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
    except Exception:
        # Analytics should never block command execution.
        return


def _analytics_exit(
    *,
    command: str,
    started_at: float,
    exit_code: int,
    failure_category: Optional[str] = None,
) -> int:
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    _record_analytics_event(
        command=command,
        exit_code=exit_code,
        duration_ms=elapsed_ms,
        failure_category=failure_category,
    )
    return exit_code


def _dedupe_lines(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = " ".join(value.strip().split())
        if not clean:
            continue
        token = clean.lower()
        if token in seen:
            continue
        seen.add(token)
        output.append(clean)
    return output


def _suggest_runtime_fixes(exc: Exception) -> list[str]:
    message = str(exc)
    lowered = message.lower()
    fixes: list[str] = []

    if "provide --birth-date" in lowered:
        fixes.append(
            "Add `--birth-date YYYY-MM-DD` whenever using `--birth-time`, `--lat/--lon`, or `--timezone`."
        )
    if "both --lat and --lon together" in lowered:
        fixes.append(
            "Pass both `--lat` and `--lon` together for personalized house calculations."
        )
    if "unsupported zodiac sign" in lowered:
        fixes.append(f"Use a valid uppercase sign: {', '.join(ZODIAC_SIGNS)}.")
    if "profile not found" in lowered:
        fixes.append(
            "Run `opastro profile list` to inspect profiles, or `opastro init` to create one."
        )
    if "unsupported format" in lowered:
        fixes.append("Use one of `--format text|json|markdown|html`.")
    if "unsupported value for" in lowered:
        fixes.append(
            "Run the command with `--help` to view valid choices for that flag."
        )
    if "--planet is required" in lowered:
        fixes.append(
            "Add `--planet` when running `planet` or planet-focused batch/explain flows."
        )
    if "invalid isoformat string" in lowered or "invalid isoformat" in lowered:
        fixes.append("Use ISO date format `YYYY-MM-DD` and time format `HH:MM`.")
    if "timezone" in lowered and ("invalid" in lowered or "not found" in lowered):
        fixes.append("Use a valid IANA timezone like `Africa/Douala` or `UTC`.")
    if "no module named" in lowered:
        fixes.append(
            "Run `opastro doctor`, then `opastro doctor --fix` inside a Python 3.11+ virtual environment."
        )
    if "permission denied" in lowered or "read-only file system" in lowered:
        fixes.append("Choose a writable output location and verify file permissions.")
    if "no such file or directory" in lowered:
        fixes.append(
            "Verify all input/output paths and create parent directories before exporting."
        )

    if not fixes:
        fixes.extend(
            [
                "Run `opastro doctor` to validate runtime and dependency readiness.",
                "Check command syntax with `opastro <command> --help`.",
            ]
        )
    fixes.append("Inspect structured error history with `opastro logger show`.")
    return _dedupe_lines(fixes)


def _serialize_runtime_error(argv: list[str], exc: Exception) -> dict[str, Any]:
    tb_text = "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__)
    ).strip()
    return {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "opastro_version": _app_version(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "cwd": str(Path.cwd()),
        "command": argv,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "suggested_fixes": _suggest_runtime_fixes(exc),
        "traceback": tb_text[-8000:] if tb_text else "",
    }


def _append_runtime_error_log(entry: dict[str, Any]) -> Optional[Path]:
    try:
        path = _runtime_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True, sort_keys=True))
            handle.write("\n")
        return path
    except Exception:
        return None


def _read_runtime_error_log(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            clean = line.strip()
            if not clean:
                continue
            try:
                payload = json.loads(clean)
                if isinstance(payload, dict):
                    entries.append(payload)
                else:
                    raise ValueError("Runtime entry is not an object.")
            except Exception:
                entries.append(
                    {
                        "timestamp": "unknown",
                        "error_type": "LogParseError",
                        "error_message": f"Could not parse log entry line {line_no}.",
                        "command": [],
                        "suggested_fixes": [
                            "Run `opastro logger clear` to reset a corrupted log file.",
                        ],
                        "traceback": "",
                    }
                )
    return entries


def _render_logger_rows(entries: list[dict[str, Any]], *, verbose: bool) -> None:
    for index, entry in enumerate(entries, start=1):
        stamp = str(entry.get("timestamp", "unknown"))
        error_type = str(entry.get("error_type", "Error"))
        message = str(entry.get("error_message", "unknown runtime failure"))
        command_tokens = entry.get("command")
        command = " ".join(command_tokens) if isinstance(command_tokens, list) else ""
        command_line = f"opastro {command}".strip()
        fixes = entry.get("suggested_fixes")
        if not isinstance(fixes, list):
            fixes = []

        print(_style(f"Entry {index} • {stamp}", COLOR_ACCENT_BOLD))
        print(_wrap(f"  Command : {command_line}"))
        print(_wrap(f"  Error   : {error_type}: {message}"))
        if fixes:
            print(_style("  Suggested fixes", COLOR_ACCENT_SOFT))
            for fix in fixes:
                print(_wrap_bullet(str(fix), indent="    - "))
        if verbose:
            traceback_text = str(entry.get("traceback", "")).strip()
            if traceback_text:
                print(_style("  Traceback", COLOR_ACCENT_SOFT))
                for line in traceback_text.splitlines()[-10:]:
                    print(_wrap(f"    {line}"))
        if index != len(entries):
            _print_divider("·")


def _handle_logger_show(args: argparse.Namespace) -> int:
    path = _runtime_log_path()
    raw_limit = getattr(args, "limit", 20)
    try:
        limit = max(1, int(raw_limit))
    except (TypeError, ValueError):
        limit = 20
    verbose = bool(getattr(args, "verbose", False))
    output_json = bool(getattr(args, "json", False))

    all_entries = _read_runtime_error_log(path)
    recent = all_entries[-limit:]

    if output_json:
        print(json.dumps(recent, indent=2, sort_keys=True))
        return 0

    _print_heading("OPASTRO LOGGER")
    _print_divider()
    print(_wrap(f"Log file      : {path}"))
    print(_wrap(f"Entries shown : {len(recent)} of {len(all_entries)} (limit={limit})"))
    _print_divider()
    if not recent:
        print(
            _wrap(
                "No runtime errors logged yet. New uncaught CLI exceptions will be recorded automatically."
            )
        )
        return 0

    _render_logger_rows(recent, verbose=verbose)
    return 0


def _handle_logger_path(_: argparse.Namespace) -> int:
    print(_runtime_log_path())
    return 0


def _handle_logger_clear(_: argparse.Namespace) -> int:
    path = _runtime_log_path()
    if path.exists():
        path.unlink()
        print(_style(f"Cleared runtime error log: {path}", "1;32"))
    else:
        print(_wrap(f"No runtime error log found at: {path}"))
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


def _init_defaults(
    existing: dict[str, Any], template_name: Optional[str], detected_tz: str
) -> dict[str, Any]:
    defaults = dict(existing)
    if not template_name:
        return defaults
    template = INIT_TEMPLATES.get(template_name, {})
    for key, value in template.items():
        if key == "sections":
            if not defaults.get("sections"):
                defaults["sections"] = list(value) if isinstance(value, list) else value
            continue
        if defaults.get(key) in (None, "", []):
            defaults[key] = value
    birth = defaults.get("birth")
    if template_name == "natal":
        if not isinstance(birth, dict):
            birth = {}
        birth.setdefault("timezone", detected_tz)
        defaults["birth"] = birth
    return defaults


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

    for field in (
        "zodiac_system",
        "ayanamsa",
        "house_system",
        "node_type",
        "tenant_id",
        "wheel_theme",
    ):
        value = getattr(args, field, None)
        if value is not None:
            profile[field] = value

    for field in ("accent", "brand_title", "brand_url", "premium_url"):
        value = getattr(args, field, None)
        if value is not None:
            cleaned = str(value).strip()
            if cleaned:
                profile[field] = cleaned
            elif field in profile:
                profile.pop(field, None)

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
    if (
        getattr(args, "lat", None) is None
        and birth.get("coordinates", {}).get("latitude") is not None
    ):
        args.lat = float(birth["coordinates"]["latitude"])
    if (
        getattr(args, "lon", None) is None
        and birth.get("coordinates", {}).get("longitude") is not None
    ):
        args.lon = float(birth["coordinates"]["longitude"])
    if getattr(args, "timezone", None) is None and birth.get("timezone"):
        args.timezone = birth["timezone"]

    if getattr(args, "sections", None) is None and profile.get("sections"):
        args.sections = ",".join(profile["sections"])

    for field in (
        "zodiac_system",
        "ayanamsa",
        "house_system",
        "node_type",
        "tenant_id",
        "wheel_theme",
        "accent",
        "brand_title",
        "brand_url",
        "premium_url",
    ):
        if getattr(args, field, None) is None and profile.get(field) is not None:
            setattr(args, field, profile[field])

    if getattr(args, "output_format", None) is None and profile.get("output_format"):
        args.output_format = profile["output_format"]


def _handle_init(args: argparse.Namespace) -> int:
    store = ProfileStore()
    existing = store.get_profile(args.profile) or {}
    detected_tz = _detect_local_timezone()
    defaults = _init_defaults(existing, getattr(args, "template", None), detected_tz)

    _print_heading("OPASTRO INIT")
    _print_divider()
    print(
        _wrap(
            "Interactive onboarding to save your default profile for repeat report commands."
        )
    )
    if args.template:
        print(_wrap(f"Starter template loaded: {args.template}"))

    user_name = _prompt_text(
        "Default display name for natal charts (optional)", defaults.get("user_name")
    )

    sign_default = defaults.get("sign")
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

    birth_existing = defaults.get("birth") or {}
    wants_birth = _prompt_bool(
        "Save default birth details", default=bool(birth_existing)
    )

    birth_date = None
    birth_time = None
    lat = None
    lon = None
    timezone = None
    if wants_birth:
        birth_date = _prompt_text("Birth date YYYY-MM-DD", birth_existing.get("date"))
        birth_time = _prompt_text(
            "Birth time HH:MM (optional)", birth_existing.get("time")
        )
        lat_default = birth_existing.get("coordinates", {}).get("latitude")
        lon_default = birth_existing.get("coordinates", {}).get("longitude")
        lat_raw = _prompt_text(
            "Birth latitude (optional)",
            str(lat_default) if lat_default is not None else None,
        )
        lon_raw = _prompt_text(
            "Birth longitude (optional)",
            str(lon_default) if lon_default is not None else None,
        )
        timezone = _prompt_text(
            "Timezone", birth_existing.get("timezone") or detected_tz
        )
        lat = float(lat_raw) if lat_raw else None
        lon = float(lon_raw) if lon_raw else None
        if not (birth_date or "").strip():
            # Keep onboarding forgiving: if birth date is omitted, treat birth defaults as not set.
            birth_date = None
            birth_time = None
            lat = None
            lon = None
            timezone = None

    sections_default = (
        ",".join(defaults.get("sections", [])) if defaults.get("sections") else None
    )
    sections = _prompt_text("Default sections comma list (optional)", sections_default)
    output_format = _prompt_text(
        "Default output format (text/json/markdown/html)",
        defaults.get("output_format", "text"),
    )

    zodiac_system = _prompt_text(
        "Default zodiac system (optional)", defaults.get("zodiac_system")
    )
    ayanamsa = _prompt_text("Default ayanamsa (optional)", defaults.get("ayanamsa"))
    house_system = _prompt_text(
        "Default house system (optional)", defaults.get("house_system")
    )
    node_type = _prompt_text("Default node type (optional)", defaults.get("node_type"))
    tenant_id = _prompt_text("Default tenant id (optional)", defaults.get("tenant_id"))
    wheel_theme = _prompt_text(
        "Default natal wheel theme (night/day, optional)", defaults.get("wheel_theme")
    )
    accent = _prompt_text("Default natal accent hex (optional)", defaults.get("accent"))
    brand_title = _prompt_text(
        "Default natal brand title (optional)", defaults.get("brand_title")
    )
    brand_url = _prompt_text(
        "Default natal brand URL (optional)", defaults.get("brand_url")
    )
    premium_url = _prompt_text(
        "Default natal premium URL (optional)", defaults.get("premium_url")
    )

    profile_args = argparse.Namespace(
        user_name=user_name or None,
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
        wheel_theme=wheel_theme or None,
        accent=accent or None,
        brand_title=brand_title or None,
        brand_url=brand_url or None,
        premium_url=premium_url or None,
        output_format=(output_format or "text").lower(),
    )

    if profile_args.output_format not in OUTPUT_FORMATS:
        raise ValueError(f"Unsupported format: {profile_args.output_format}")
    allowed_values = {
        "zodiac_system": {"sidereal", "tropical"},
        "ayanamsa": {"lahiri", "fagan_bradley", "krishnamurti", "raman", "yukteswar"},
        "house_system": {"placidus", "whole_sign", "equal", "koch"},
        "node_type": {"true", "mean"},
        "wheel_theme": {"night", "day"},
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
        raise ValueError(
            "Profile not found. Use `opastro profile list` to inspect available profiles."
        )
    payload = {
        "name": target_name,
        "active": target_name == store.active_profile_name(),
        "profile": profile,
    }
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
    parts = textwrap.wrap(
        text, width=width, break_long_words=False, replace_whitespace=False
    )
    return parts if parts else [""]


def _filter_ui_sections(sections: list[Any], query: str) -> list[Any]:
    needle = query.strip().casefold()
    if not needle:
        return sections
    return [
        section
        for section in sections
        if needle in section.section.value.casefold()
        or needle in section.title.casefold()
        or needle in section.intensity.casefold()
    ]


def _filter_home_items(palette: str, query: str) -> tuple[tuple[str, str, str], ...]:
    items = _UI_HOME_COMMANDS if palette == "commands" else _UI_HOME_CTAS
    tokens = query.strip().casefold().split()
    if not tokens:
        return items
    return tuple(
        item
        for item in items
        if all(_home_query_matches(item, palette, token) for token in tokens)
    )


def _home_query_matches(
    item: tuple[str, str, str], palette: str, query_token: str
) -> bool:
    values = (
        (*item, *COMMAND_ALIASES.get(item[0], ())) if palette == "commands" else item
    )
    words = set(re.findall(r"[a-z0-9_]+", " ".join(values).casefold()))
    if query_token in words:
        return True
    return len(query_token) >= 2 and any(query_token in word for word in words)


def _home_command_args(target: str) -> list[str]:
    """Convert a displayed ``opastro ...`` example into safe argv parts."""
    parts = shlex.split(target)
    if parts and parts[0] == "opastro":
        return parts[1:]
    return parts


def _execute_home_command(stdscr, name: str, target: str) -> _UICommandResult:
    """Run a selected command example and capture its terminal result."""
    if name == "ui":
        return _UICommandResult(
            name=name,
            command=["ui"],
            stdout="",
            stderr="Already inside `opastro ui`; choose another command.",
            returncode=1,
        )

    command = _home_command_args(target)
    if not command:
        return _UICommandResult(
            name=name,
            command=[],
            stdout="",
            stderr=f"No runnable example is configured for {name}.",
            returncode=1,
        )

    try:
        curses.endwin()
    except curses.error:
        pass

    try:
        completed = subprocess.run(
            [sys.executable, "-m", "horoscope_engine", *command],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        status = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
    except KeyboardInterrupt:
        status = 130
        stdout = ""
        stderr = "Command cancelled by user."
    except Exception as exc:
        status = 1
        stdout = ""
        stderr = f"Could not launch command: {exc}"

    try:
        curses.reset_prog_mode()
        stdscr.keypad(True)
        stdscr.clear()
        stdscr.refresh()
    except curses.error:
        pass
    return _UICommandResult(
        name=name,
        command=command,
        stdout=stdout,
        stderr=stderr,
        returncode=status,
    )


def _ui_command_result_lines(
    result: _UICommandResult, width: int
) -> list[tuple[str, str]]:
    """Build styled, wrapped lines for a command result page."""
    status = "OK" if result.returncode == 0 else f"EXIT {result.returncode}"
    command_line = "opastro " + shlex.join(result.command)
    lines: list[tuple[str, str]] = [
        ("title", f"RESULT PAGE {result.name.upper()}"),
        ("meta", f"Status: {status}"),
        ("meta", f"Command: {command_line}"),
        ("blank", ""),
    ]

    def _append_stream(label: str, content: str, kind: str) -> None:
        cleaned = re.sub(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", content)
        if not cleaned.strip():
            return
        lines.append(("label", label))
        for raw_line in cleaned.rstrip("\n").split("\n"):
            for wrapped in _wrap_for_width(raw_line, width):
                lines.append((kind, wrapped))
        lines.append(("blank", ""))

    _append_stream("Output", result.stdout, "body")
    _append_stream("Diagnostics", result.stderr, "warning")
    if not result.stdout.strip() and not result.stderr.strip():
        lines.extend(
            [
                ("body", "The command completed without terminal output."),
                ("blank", ""),
            ]
        )
    lines.append(("muted", "Press Enter or Esc to return to the home deck."))
    return lines


def _filter_ui_result_lines(
    lines: list[tuple[str, str]], query: str
) -> list[tuple[str, str]]:
    """Keep result metadata and matching lines for in-page result search."""
    needle = query.strip().casefold()
    if not needle:
        return lines
    metadata = lines[:4]
    matches = [(kind, line) for kind, line in lines[4:] if needle in line.casefold()]
    filtered = [
        *metadata,
        ("label", f"Matches for: {query.strip()} ({len(matches)})"),
        ("blank", ""),
    ]
    if matches:
        filtered.extend(matches)
    else:
        filtered.append(("warning", "No result lines match this search."))
    filtered.extend(
        [
            ("blank", ""),
            ("muted", "Press c to clear the result search."),
        ]
    )
    return filtered


def _apply_ui_key(
    state: _UIState,
    key: int,
    *,
    section_count: int,
    page_height: int,
    curses_module: Any = None,
    allow_period_switch: bool = True,
    home_mode: bool = False,
    cta_count: int = 0,
) -> bool:
    """Apply one keypress and return whether the UI should keep running."""
    keys = curses_module or curses
    key_up = getattr(keys, "KEY_UP", -1001)
    key_down = getattr(keys, "KEY_DOWN", -1002)
    key_enter = getattr(keys, "KEY_ENTER", -1003)
    key_next_page = getattr(keys, "KEY_NPAGE", -1004)
    key_previous_page = getattr(keys, "KEY_PPAGE", -1005)
    step = max(1, page_height - 2)

    if key == ord("q"):
        return False
    if home_mode:
        if state.result_page:
            if key in (27, 10, 13, key_enter):
                state.result_page = None
                state.result_scroll_offset = 0
                state.result_filter_query = ""
                state.home_message = ""
                return True
            if key in (key_up, ord("k")):
                state.result_scroll_offset = max(0, state.result_scroll_offset - 1)
            elif key in (key_down, ord("j")):
                state.result_scroll_offset += 1
            elif key in (key_next_page, ord(" ")):
                state.result_scroll_offset += step
            elif key in (key_previous_page, ord("b")):
                state.result_scroll_offset = max(0, state.result_scroll_offset - step)
            elif key == ord("g"):
                state.result_scroll_offset = 0
            elif key == ord("G"):
                state.result_scroll_offset = 10**9
            elif key == ord("/"):
                state.result_filter_requested = True
            elif key == ord("c"):
                state.result_filter_query = ""
                state.result_scroll_offset = 0
            elif key in (ord("r"), ord("R")):
                state.result_rerun_requested = True
            return True
        if key == 27:
            if state.help_visible:
                state.help_visible = False
                return True
            if state.home_palette:
                state.home_palette = None
                state.filter_query = ""
                state.selected = 0
                state.home_message = ""
                return True
            return False
        if key in (ord("/"), ord("@")):
            state.home_palette = "commands" if key == ord("/") else "cta"
            state.filter_query = ""
            state.selected = 0
            state.home_message = ""
            state.filter_requested = True
            return True
        if key in (ord("?"), ord("h")):
            state.help_visible = not state.help_visible
            state.home_message = ""
            return True
        if key == ord("c") and state.home_palette:
            state.filter_query = ""
            state.selected = 0
            state.home_message = ""
            return True
        if key == ord("o") and state.home_palette == "cta" and section_count:
            state.home_open_requested = True
            return True
        if key in (key_up, ord("k")) and section_count:
            state.selected = (state.selected - 1) % section_count
        elif key in (key_down, ord("j")) and section_count:
            state.selected = (state.selected + 1) % section_count
        elif key in (10, 13, key_enter) and section_count and state.home_palette:
            state.home_action_requested = True
        return True
    if key in (27,):
        if state.help_visible:
            state.help_visible = False
            return True
        if state.cta_visible:
            state.cta_visible = False
            state.cta_selected = 0
            state.status_message = "Links drawer closed."
            return True
        return False
    if key == ord("@") and cta_count:
        state.cta_visible = not state.cta_visible
        state.cta_selected = 0
        state.status_message = (
            "Links drawer opened. Use arrows, Enter, or o."
            if state.cta_visible
            else "Links drawer closed."
        )
        return True
    if state.cta_visible:
        if key in (ord("?"), ord("h")):
            state.help_visible = not state.help_visible
        elif key == ord("o"):
            state.cta_open_requested = True
        elif key in (key_up, ord("k")):
            state.cta_selected = (state.cta_selected - 1) % cta_count
        elif key in (key_down, ord("j")):
            state.cta_selected = (state.cta_selected + 1) % cta_count
        elif key in (10, 13, key_enter):
            name, _, target = _UI_HOME_CTAS[state.cta_selected]
            state.status_message = f"Selected {name}: {target}"
        return True
    if key == ord("/"):
        state.filter_requested = True
        return True
    if key == ord("c"):
        state.filter_query = ""
        state.selected = 0
        state.scroll_offset = 0
        state.status_message = "Section filter cleared."
        return True
    if key in (ord("?"), ord("h")):
        state.help_visible = not state.help_visible
        state.scroll_offset = 0
        return True
    if key == ord("d"):
        state.compact = not state.compact
        state.scroll_offset = 0
        state.status_message = (
            "Compact density enabled." if state.compact else "Expanded density enabled."
        )
        return True
    if key in (ord("r"), ord("R")):
        state.refresh_requested = True
        state.status_message = "Refreshing the current report..."
        return True
    if allow_period_switch and key in (
        ord("1"),
        ord("2"),
        ord("3"),
        ord("4"),
    ):
        state.requested_period = {
            ord("1"): "daily",
            ord("2"): "weekly",
            ord("3"): "monthly",
            ord("4"): "yearly",
        }[key]
        return True
    if section_count <= 0:
        return True
    if key in (key_up, ord("k")):
        state.selected = (state.selected - 1) % section_count
        state.scroll_offset = 0
    elif key in (key_down, ord("j")):
        state.selected = (state.selected + 1) % section_count
        state.scroll_offset = 0
    elif key in (10, 13, key_enter):
        state.show_factors = not state.show_factors
        state.scroll_offset = 0
        state.status_message = (
            "Factor drill-down expanded."
            if state.show_factors
            else "Factor drill-down collapsed."
        )
    elif key in (key_next_page, ord(" ")):
        state.scroll_offset += step
    elif key in (key_previous_page, ord("b")):
        state.scroll_offset = max(0, state.scroll_offset - step)
    elif key == ord("g"):
        state.scroll_offset = 0
        state.status_message = "Moved to the top of this section."
    elif key == ord("G"):
        state.scroll_offset = 10**9
        state.status_message = "Moved to the end of this section."
    return True


def _ui_terminal_reason(*, min_columns: int = 72) -> Optional[str]:
    if curses is None:
        return "curses is unavailable on this platform"
    if (os.getenv("TERM") or "").strip().lower() == "dumb":
        return "TERM=dumb does not support the interactive UI"
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return "stdin and stdout must both be interactive terminals"
    size = shutil.get_terminal_size((DEFAULT_WRAP_WIDTH, 20))
    if size.columns < min_columns or size.lines < 10:
        return f"terminal is too small; resize to at least {min_columns}x10"
    return None


def _render_ui_fallback(
    payload,
    args: argparse.Namespace,
    reason: str,
    update_info: UpdateCheckResult | None = None,
) -> int:
    print(f"UI fallback mode: {reason}.", file=sys.stderr)
    notice = update_notice(update_info) if update_info else None
    if notice:
        print(notice, file=sys.stderr)
    if isinstance(payload, _UIEventsPayload):
        output_format = _resolve_output_format(args)
        if output_format == "json":
            rendered = payload.response.model_dump_json(indent=2)
        else:
            rendered = _render_celestial_events_text(payload.response)
        if args.export:
            target = _save_export(rendered, args.export)
            print(f"saved output to {target}", file=sys.stderr)
        else:
            print(rendered, end="" if rendered.endswith("\n") else "\n")
        return 0
    return _render_output(
        payload,
        output_format=_resolve_output_format(args),
        export_path=args.export,
    )


def _prompt_ui_filter(
    stdscr, state: _UIState, theme: dict[str, int], prompt: str | None = None
) -> None:
    height, width = stdscr.getmaxyx()
    prompt = prompt or "Filter sections (Enter apply, Esc cancel): "
    prompt_x = min(len(prompt), max(0, width - 1))
    max_len = max(1, width - prompt_x - 1)
    previous = state.filter_query
    try:
        curses.echo()
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        _safe_ui_add = getattr(stdscr, "addnstr", None)
        if _safe_ui_add is not None:
            stdscr.addnstr(height - 1, 0, prompt, max(1, width - 1), theme["muted"])
        raw = stdscr.getstr(height - 1, prompt_x, max_len)
        if isinstance(raw, bytes):
            state.filter_query = raw.decode("utf-8", errors="replace").strip()
        else:
            state.filter_query = str(raw).strip()
    except curses.error:
        state.filter_query = previous
    finally:
        curses.noecho()
        try:
            curses.curs_set(0)
        except curses.error:
            pass
    state.selected = 0
    state.scroll_offset = 0


def _home_payload() -> dict[str, Any]:
    return {
        "mode": "home",
        "version": _app_version(),
        "commands": [
            {
                "name": name,
                "aliases": COMMAND_ALIASES.get(name, []),
                "description": description,
                "example": example,
            }
            for name, description, example in _UI_HOME_COMMANDS
        ],
        "ctas": [
            {"name": name, "description": description, "target": target}
            for name, description, target in _UI_HOME_CTAS
        ],
    }


def _render_ui_home_text() -> str:
    lines = [
        WELCOME_BANNER.strip("\n"),
        f"Open Core Horoscope Engine • {_app_version()}".center(_term_width()),
        "A small command deck for exploring deterministic celestial calculations.",
        "",
        "Commands",
    ]
    lines.extend(
        f"  {name:<10} {description}" for name, description, _ in _UI_HOME_COMMANDS
    )
    lines.extend(
        [
            "",
            "Shortcuts",
            "  /          Search commands",
            "  @          Explore website, docs, and premium CTAs",
            "  h / ?      Show home controls",
            "  Enter      Run a selected command or select a CTA",
            "  o          Open the selected CTA",
            "  q / Esc    Quit",
            "",
            "→ https://opastro.com",
            "→ https://numerologyapi.com",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_ui_home_fallback(
    args: argparse.Namespace,
    reason: str,
    update_info: UpdateCheckResult | None = None,
) -> int:
    print(f"UI home fallback: {reason}.", file=sys.stderr)
    notice = update_notice(update_info) if update_info else None
    if notice:
        print(notice, file=sys.stderr)
    rendered = _render_ui_home_text()
    if args.export:
        target = _save_export(rendered, args.export)
        print(f"saved output to {target}", file=sys.stderr)
    else:
        print(rendered, end="")
    return 0


def _run_ui_home(
    *,
    ascii_mode: bool = False,
    update_info: UpdateCheckResult | None = None,
) -> int:
    if curses is None:
        raise RuntimeError("curses is unavailable on this platform")

    def _ui(stdscr) -> None:
        def _safe_add(y: int, x: int, text: str, max_len: int, attr: int = 0) -> None:
            if max_len <= 0 or y < 0 or x < 0:
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
                "background": curses.A_NORMAL,
                "subtle": curses.A_DIM,
                "glow": curses.A_BOLD,
                "warning": curses.A_BOLD,
            }
            if not _should_colorize() or not curses.has_colors():
                return theme
            try:
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
                curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)
                curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)
                curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)
                curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_GREEN)
                curses.init_pair(6, curses.COLOR_YELLOW, curses.COLOR_BLACK)
                subtle_color = curses.COLOR_WHITE
                subtle_attr = curses.A_DIM
                can_change_color = getattr(curses, "can_change_color", None)
                color_count = getattr(curses, "COLORS", 0)
                if can_change_color and can_change_color() and color_count >= 256:
                    try:
                        subtle_color = color_count - 1
                        curses.init_color(
                            subtle_color,
                            round(HOME_SUBTLE_RGB[0] * 1000 / 255),
                            round(HOME_SUBTLE_RGB[1] * 1000 / 255),
                            round(HOME_SUBTLE_RGB[2] * 1000 / 255),
                        )
                        subtle_attr = 0
                    except curses.error:
                        subtle_color = curses.COLOR_WHITE
                        subtle_attr = curses.A_DIM
                curses.init_pair(7, subtle_color, curses.COLOR_BLACK)
                theme["header"] = curses.color_pair(1) | curses.A_BOLD
                theme["accent"] = curses.color_pair(1) | curses.A_BOLD
                theme["selected"] = curses.color_pair(2) | curses.A_BOLD
                theme["muted"] = curses.color_pair(4)
                theme["body"] = curses.color_pair(3)
                theme["background"] = curses.color_pair(3)
                theme["subtle"] = curses.color_pair(3) | curses.A_DIM
                theme["glow"] = curses.color_pair(5) | curses.A_BOLD
                theme["warning"] = curses.color_pair(6) | curses.A_BOLD
                theme["subtle"] = curses.color_pair(7) | subtle_attr
            except curses.error:
                return theme
            return theme

        curses.curs_set(0)
        stdscr.keypad(True)
        timeout = getattr(stdscr, "timeout", None)
        if timeout:
            timeout(120)
        theme = _init_theme()
        background = getattr(stdscr, "bkgd", None)
        if background is not None:
            background(" ", theme["background"])
        state = _UIState()
        glyphs = _ui_glyphs(ascii_mode=ascii_mode)
        glow_rng = random.Random()
        next_glow_at = time.monotonic() + glow_rng.uniform(8.0, 10.0)
        glow_started_at: float | None = None
        glow_duration = 1.6
        frame = 0

        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            now = time.monotonic()
            if glow_started_at is None and now >= next_glow_at:
                glow_started_at = now
            elif glow_started_at is not None and now - glow_started_at > glow_duration:
                glow_started_at = None
                next_glow_at = now + glow_rng.uniform(8.0, 10.0)
            palette = state.home_palette
            items = (
                _filter_home_items(palette, state.filter_query)
                if palette
                else _UI_HOME_COMMANDS
            )
            if items:
                state.selected = min(state.selected, len(items) - 1)
            else:
                state.selected = 0

            # A deterministic starfield keeps the home screen animated without
            # introducing randomness into screenshots or terminal recordings.
            logo = WELCOME_BANNER.strip("\n").splitlines()
            art_pixels = [
                (row, char_x)
                for row, line in enumerate(logo)
                for char_x, char in enumerate(line)
                if char != " "
            ]
            glow_pixels: set[tuple[int, int]] = set()
            if glow_started_at is not None:
                progress = min(1.0, (now - glow_started_at) / glow_duration)
                pixel_index = round(progress * max(0, len(art_pixels) - 1))
                for offset in (-1, 0, 1):
                    candidate = pixel_index + offset
                    if 0 <= candidate < len(art_pixels):
                        glow_pixels.add(art_pixels[candidate])

            star_chars = ".+*"
            for index in range(42):
                star_x = (index * 37 + 11) % max(1, width)
                star_y = 2 + ((index * 17 + frame // 8) % max(1, height - 4))
                if star_y < height - 1:
                    star = star_chars[(index + frame // 5) % len(star_chars)]
                    _safe_add(star_y, star_x, star, 1, theme["muted"])

            logo_start = 2
            for row, line in enumerate(logo):
                logo_x = max(0, (width - len(line)) // 2)
                _safe_add(
                    logo_start + row,
                    logo_x,
                    line,
                    max(1, width - logo_x - 1),
                    theme["accent"],
                )
                for char_x, char in enumerate(line):
                    if (row, char_x) in glow_pixels:
                        _safe_add(
                            logo_start + row,
                            logo_x + char_x,
                            char,
                            1,
                            theme["glow"],
                        )

            title_y = min(height - 2, logo_start + len(logo) + 1)
            title = f"Open Core Horoscope Engine {glyphs['bullet']} {_app_version()}"
            title_x = max(0, (width - len(title)) // 2)
            _safe_add(
                title_y,
                title_x,
                title,
                max(1, width - title_x - 1),
                theme["header"],
            )

            content_y = title_y + 3
            if state.result_page and content_y < height - 2:
                result_lines = _filter_ui_result_lines(
                    _ui_command_result_lines(state.result_page, max(1, width - 4)),
                    state.result_filter_query,
                )
                result_page_h = max(1, height - content_y - 4)
                max_result_scroll = max(0, len(result_lines) - result_page_h)
                state.result_scroll_offset = max(
                    0, min(state.result_scroll_offset, max_result_scroll)
                )
                result_status = (
                    "OK" if state.result_page.returncode == 0 else "ATTENTION"
                )
                result_header = (
                    f"RESULT STREAM {glyphs['bullet']} {result_status} "
                    f"{glyphs['bullet']} scroll {state.result_scroll_offset + 1}/"
                    f"{max_result_scroll + 1}"
                )
                if state.result_filter_query:
                    result_header += (
                        f" {glyphs['bullet']} find:{state.result_filter_query}"
                    )
                _safe_add(
                    content_y,
                    2,
                    result_header,
                    max(1, width - 3),
                    theme["accent"],
                )
                try:
                    stdscr.hline(content_y + 1, 2, ord(glyphs["rule"]), width - 4)
                except curses.error:
                    pass
                visible_result_lines = result_lines[
                    state.result_scroll_offset : state.result_scroll_offset
                    + result_page_h
                ]
                for row, (kind, line) in enumerate(visible_result_lines):
                    y = content_y + 2 + row
                    if y >= height - 2:
                        break
                    attr = theme["body"]
                    if kind == "title" or kind == "label":
                        attr = theme["accent"]
                    elif kind == "meta" or kind == "muted":
                        attr = theme["subtle"]
                    elif kind == "warning":
                        attr = theme["warning"]
                    _safe_add(y, 2, line, max(1, width - 3), attr)
            elif state.help_visible and content_y < height - 2:
                help_lines = (
                    "Home deck controls",
                    "↑↓ / j / k       Move through the selected palette",
                    "/                 Search every OpAstro command",
                    "@                 Browse website, docs, and premium links",
                    "Enter             Run a command or select a CTA",
                    "o                 Open the selected CTA in your browser",
                    "c                 Clear the active palette search",
                    "h / ?             Toggle this help panel",
                    "Esc               Close the panel or palette",
                    "q                 Quit",
                )
                for row, line in enumerate(help_lines):
                    if content_y + row >= height - 2:
                        break
                    _safe_add(
                        content_y + row,
                        2,
                        line,
                        max(1, width - 3),
                        theme["accent"] if row == 0 else theme["body"],
                    )
            elif content_y < height - 2 and not palette:
                left_x = 2
                right_x = max(width // 2, 42)
                _safe_add(
                    content_y,
                    left_x,
                    "COMMAND DECK",
                    max(1, right_x - left_x - 2),
                    theme["accent"],
                )
                _safe_add(
                    content_y,
                    right_x,
                    "NEXT ORBIT",
                    max(1, width - right_x - 1),
                    theme["accent"],
                )
                for row, (name, description, _) in enumerate(_UI_HOME_COMMANDS):
                    y = content_y + 2 + row
                    if y >= height - 2:
                        break
                    _safe_add(
                        y,
                        left_x,
                        f"{name:<10}",
                        max(1, right_x - left_x - 2),
                        theme["body"],
                    )
                    _safe_add(
                        y,
                        right_x,
                        description,
                        max(1, width - right_x - 1),
                        theme["subtle"],
                    )
                for row, (name, description, _) in enumerate(_UI_HOME_CTAS):
                    y = content_y + 2 + row
                    if y >= height - 2:
                        break
                    _safe_add(
                        y,
                        right_x,
                        f"@ {name:<8} {description}",
                        max(1, width - right_x - 1),
                        theme["subtle"],
                    )
                _safe_add(
                    content_y + 9,
                    left_x,
                    "Press / to search commands or @ to open useful links.",
                    max(1, width - 3),
                    theme["muted"],
                )
            elif content_y < height - 2:
                palette_label = (
                    "COMMAND PALETTE /" if palette == "commands" else "ORBIT PALETTE @"
                )
                _safe_add(
                    content_y, 2, palette_label, max(1, width - 3), theme["accent"]
                )
                _safe_add(
                    content_y + 1,
                    2,
                    (
                        "Type a filter, then Enter runs the command. Esc closes the palette."
                        if palette == "commands"
                        else "Type a filter, Enter selects, and o opens the CTA."
                    ),
                    max(1, width - 3),
                    theme["muted"],
                )
                for row, (name, description, target) in enumerate(items):
                    y = content_y + 3 + row
                    if y >= height - 3:
                        break
                    marker = glyphs["marker"] if row == state.selected else " "
                    detail = target
                    _safe_add(
                        y,
                        2,
                        f"{marker} {name:<12} {detail}",
                        max(1, width - 3),
                        theme["selected"] if row == state.selected else theme["body"],
                    )
                if state.home_message:
                    _safe_add(
                        height - 3,
                        2,
                        state.home_message,
                        max(1, width - 3),
                        theme["accent"],
                    )

            if update_info and height > 2:
                _safe_add(
                    height - 2,
                    2,
                    update_notice(update_info) or "",
                    max(1, width - 3),
                    theme["muted"],
                )
            if state.result_page:
                footer = (
                    "↑↓/j/k scroll  pgup/pgdn page  / find  c clear  r rerun  "
                    "g/G top/end  Enter/Esc home  q quit"
                )
            else:
                footer = "↑↓/j/k select  / commands  @ links & CTAs  Enter run/select  o open  q/Esc quit"
            _safe_add(height - 1, 0, footer, max(1, width - 1), theme["muted"])
            stdscr.refresh()
            key = stdscr.getch()
            if key == -1:
                frame += 1
                continue
            if not _apply_ui_key(
                state,
                key,
                section_count=len(items),
                page_height=max(1, height - content_y - 4),
                home_mode=True,
            ):
                break
            if state.filter_requested:
                state.filter_requested = False
                prompt = (
                    "Search commands (Enter apply): "
                    if state.home_palette == "commands"
                    else "Search links and CTAs (Enter apply): "
                )
                _prompt_ui_filter(stdscr, state, theme, prompt=prompt)
            if state.result_filter_requested:
                state.result_filter_requested = False
                _prompt_ui_filter(
                    stdscr,
                    state,
                    theme,
                    prompt="Find in result (Enter apply, Esc cancel): ",
                )
                state.result_filter_query = state.filter_query
                state.filter_query = ""
                state.result_scroll_offset = 0
            if state.result_rerun_requested and state.result_page:
                state.result_rerun_requested = False
                previous_result = state.result_page
                target = "opastro " + shlex.join(previous_result.command)
                state.result_page = _execute_home_command(
                    stdscr, previous_result.name, target
                )
                state.result_filter_query = ""
                state.result_scroll_offset = 0
            if state.home_action_requested:
                state.home_action_requested = False
                chosen = _filter_home_items(
                    state.home_palette or "commands", state.filter_query
                )
                if chosen and state.selected < len(chosen):
                    name, _, target = chosen[state.selected]
                    if state.home_palette == "commands":
                        state.result_page = _execute_home_command(stdscr, name, target)
                        state.result_scroll_offset = 0
                        state.home_palette = None
                        state.filter_query = ""
                        state.home_message = ""
                    else:
                        state.home_message = f"Selected {name}: {target}"
            if state.home_open_requested:
                state.home_open_requested = False
                chosen = _filter_home_items("cta", state.filter_query)
                if chosen and state.selected < len(chosen):
                    name, _, target = chosen[state.selected]
                    try:
                        opened = webbrowser.open(target)
                    except Exception:
                        opened = False
                    state.home_message = (
                        f"Opened {name}: {target}"
                        if opened
                        else f"Could not open {target}; use the URL directly."
                    )

    curses.wrapper(_ui)
    return 0


def _run_ui(
    payload,
    *,
    ascii_mode: bool = False,
    payload_loader: Optional[Callable[[str], Any]] = None,
    allow_period_switch: bool = True,
    mode_label: str = "horoscope",
    update_info: UpdateCheckResult | None = None,
) -> int:
    if curses is None:
        raise RuntimeError("curses is unavailable on this platform")
    sections = payload.sections
    if not sections:
        print("No sections available for UI rendering.")
        return 0

    def _ui(stdscr) -> None:
        nonlocal payload, sections

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
                "background": curses.A_NORMAL,
                "stars": curses.A_DIM,
            }
            if not _should_colorize() or not curses.has_colors():
                return theme
            try:
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # accent
                curses.init_pair(
                    2, curses.COLOR_BLACK, curses.COLOR_GREEN
                )  # selected row
                curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)  # body
                curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)  # meta
                theme["header"] = curses.color_pair(1) | curses.A_BOLD
                theme["accent"] = curses.color_pair(1) | curses.A_BOLD
                theme["selected"] = curses.color_pair(2) | curses.A_BOLD
                theme["muted"] = curses.color_pair(4)
                theme["body"] = curses.color_pair(3)
                theme["background"] = curses.color_pair(3)
                theme["stars"] = curses.color_pair(1) | curses.A_DIM
            except curses.error:
                return theme
            return theme

        curses.curs_set(0)
        stdscr.keypad(True)
        theme = _init_theme()
        background = getattr(stdscr, "bkgd", None)
        if background is not None:
            background(" ", theme["background"])
        state = _UIState()
        glyphs = _ui_glyphs(ascii_mode=ascii_mode)
        timeout = getattr(stdscr, "timeout", None)
        if timeout:
            timeout(140)
        frame = 0

        def _process_pending_actions() -> None:
            nonlocal payload, sections

            if state.filter_requested:
                state.filter_requested = False
                _prompt_ui_filter(stdscr, state, theme)
                state.status_message = (
                    f"Filter active: {state.filter_query}"
                    if state.filter_query
                    else "Section filter cleared."
                )

            if state.requested_period:
                requested_period = state.requested_period
                state.requested_period = None
                if payload_loader:
                    try:
                        payload = payload_loader(requested_period)
                        sections = payload.sections
                        state.selected = 0
                        state.show_factors = False
                        state.scroll_offset = 0
                        state.status_message = f"Loaded {requested_period} report."
                    except Exception as exc:
                        state.status_message = (
                            f"Could not load {requested_period}: {exc}"
                        )
                else:
                    state.status_message = "Period switching is unavailable here."

            if state.refresh_requested:
                state.refresh_requested = False
                if payload_loader:
                    current_period = payload.period.value
                    try:
                        payload = payload_loader(current_period)
                        sections = payload.sections
                        state.selected = 0
                        state.show_factors = False
                        state.scroll_offset = 0
                        state.status_message = f"Refreshed {current_period} report."
                    except Exception as exc:
                        state.status_message = f"Could not refresh report: {exc}"
                else:
                    state.status_message = "Refresh is unavailable for this report."

            if state.cta_open_requested:
                state.cta_open_requested = False
                name, _, target = _UI_HOME_CTAS[state.cta_selected]
                try:
                    opened = webbrowser.open(target)
                except Exception:
                    opened = False
                state.status_message = (
                    f"Opened {name}: {target}"
                    if opened
                    else f"Could not open {target}; use the URL directly."
                )

        def _compact_lines(visible_sections: list[Any], line_width: int):
            lines: list[tuple[str, str]] = []
            if state.cta_visible and not state.help_visible:
                lines.extend(
                    [
                        ("title", "OPASTRO LINKS @"),
                        ("blank", ""),
                        ("body", "j/k move • Enter select • o open • Esc close"),
                        ("blank", ""),
                    ]
                )
                for idx, (name, description, target) in enumerate(_UI_HOME_CTAS):
                    marker = glyphs["marker"] if idx == state.cta_selected else " "
                    kind = "cta_selected" if idx == state.cta_selected else "label"
                    lines.append((kind, f"{marker} {name}"))
                    lines.extend(
                        ("body", f"  {wrapped}")
                        for wrapped in _wrap_for_width(description, line_width)
                    )
                    lines.extend(
                        ("factor", f"  {wrapped}")
                        for wrapped in _wrap_for_width(target, line_width)
                    )
                    lines.append(("blank", ""))
                return lines
            if state.help_visible:
                return [
                    ("title", "Compact report controls"),
                    ("blank", ""),
                    ("body", "j/k or arrows     Select a section"),
                    ("body", "Enter             Factor details"),
                    ("body", "Space/pgup/pgdn  Scroll content"),
                    ("body", "/                 Filter sections"),
                    ("body", "r                 Refresh report"),
                    ("body", "@                 Links and CTAs"),
                    ("body", "h/?               Close this help"),
                    ("body", "q/Esc             Quit"),
                ]
            if not visible_sections:
                return [
                    ("title", "No matching sections"),
                    ("blank", ""),
                    ("body", f"No section matches: {state.filter_query}"),
                    ("body", "Press / to change the filter or c to clear it."),
                ]

            section = visible_sections[state.selected]
            lines.extend(
                [
                    ("title", section.title),
                    ("meta", f"Intensity: {section.intensity}"),
                    ("blank", ""),
                ]
            )
            lines.extend(
                ("body", wrapped)
                for wrapped in _wrap_for_width(section.summary, line_width)
            )
            lines.append(("blank", ""))
            for label, values in (
                ("Highlights", section.highlights[:2]),
                ("Cautions", section.cautions[:1]),
                ("Actions", section.actions[:1]),
            ):
                lines.append(("label", f"{label}:"))
                for value in values:
                    lines.extend(
                        ("body", wrapped)
                        for wrapped in _wrap_for_width(f"- {value}", line_width)
                    )
                lines.append(("blank", ""))
            if state.show_factors:
                lines.append(("label", "Factor drill-down:"))
                for detail in section.factor_details[:3]:
                    lines.extend(
                        ("factor", wrapped)
                        for wrapped in _wrap_for_width(
                            f"- {detail.factor_type}={detail.factor_value} ({detail.weight:.2f})",
                            line_width,
                        )
                    )
            return lines

        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            star_chars = ".+*" if ascii_mode else ".·*"
            for index in range(28):
                star_x = (index * 41 + 13 + frame // 9) % max(1, width)
                star_y = 2 + ((index * 19 + frame // 16) % max(1, height - 4))
                if star_y < height - 2:
                    try:
                        stdscr.addch(
                            star_y, star_x, ord(star_chars[index % 3]), theme["stars"]
                        )
                    except curses.error:
                        pass
            visible_sections = _filter_ui_sections(sections, state.filter_query)
            if visible_sections:
                state.selected = min(state.selected, len(visible_sections) - 1)
            if height < 10:
                _safe_add(
                    0,
                    0,
                    "Terminal too small for the UI. Resize to at least 42x10.",
                    max(1, width - 1),
                    theme["accent"],
                )
                _safe_add(
                    min(2, max(0, height - 1)),
                    0,
                    "Press q or Esc to quit.",
                    max(1, width - 1),
                    theme["muted"],
                )
                stdscr.refresh()
                key = stdscr.getch()
                if not _apply_ui_key(
                    state,
                    key,
                    section_count=len(visible_sections),
                    page_height=max(1, height - 5),
                    allow_period_switch=allow_period_switch,
                    cta_count=len(_UI_HOME_CTAS),
                ):
                    break
                _process_pending_actions()
                continue
            if width < 72:
                compact_width = max(18, width - 3)
                compact_header = (
                    f"OPASTRO {glyphs['bullet']} {mode_label} {glyphs['bullet']} "
                    f"{payload.sign} {glyphs['bullet']} {payload.period.value} "
                    f"{glyphs['bullet']} COMPACT"
                )
                _safe_add(0, 0, compact_header, width - 1, theme["header"])
                try:
                    stdscr.hline(1, 0, ord(glyphs["rule"]), width - 1)
                except curses.error:
                    pass
                lines = _compact_lines(visible_sections, compact_width)
                compact_page_h = max(2, height - 5)
                max_scroll = max(0, len(lines) - compact_page_h)
                state.scroll_offset = max(0, min(state.scroll_offset, max_scroll))
                for row, (kind, line) in enumerate(
                    lines[state.scroll_offset : state.scroll_offset + compact_page_h]
                ):
                    y = 2 + row
                    if y >= height - 2:
                        break
                    attr = theme["body"]
                    if kind in {"title", "label"}:
                        attr = theme["accent"]
                    elif kind == "factor":
                        attr = theme["muted"]
                    elif kind == "cta_selected":
                        attr = theme["selected"]
                    _safe_add(y, 1, line, max(1, width - 2), attr)
                if state.status_message:
                    _safe_add(
                        height - 2,
                        0,
                        f"{glyphs['bullet']} {state.status_message}",
                        width - 1,
                        theme["muted"],
                    )
                _safe_add(
                    height - 1,
                    0,
                    "j/k section  Enter factors  / filter  r refresh  @ links  q quit",
                    width - 1,
                    theme["muted"],
                )
                stdscr.refresh()
                key = stdscr.getch()
                if key == -1:
                    frame += 1
                    continue
                if not _apply_ui_key(
                    state,
                    key,
                    section_count=len(visible_sections),
                    page_height=compact_page_h,
                    allow_period_switch=allow_period_switch,
                    cta_count=len(_UI_HOME_CTAS),
                ):
                    break
                _process_pending_actions()
                continue
            left_w = max(24, min(38, width // 3))
            right_x = left_w + 2
            right_w = max(20, width - right_x - 1)
            page_h = max(6, height - 5)

            header = (
                f"OPASTRO UI {glyphs['bullet']} {mode_label} {glyphs['bullet']} {payload.sign} {glyphs['bullet']} "
                f"{payload.period.value} {glyphs['bullet']} sections:{len(visible_sections)}/{len(sections)} "
                f"{glyphs['bullet']} factors:{'on' if state.show_factors else 'off'} "
                f"{glyphs['bullet']} density:{'compact' if state.compact else 'expanded'}"
            )
            notice = update_notice(update_info) if update_info else None
            if notice:
                header += f" {glyphs['bullet']} update:{update_info.latest_version}"
            _safe_add(0, 0, header, width - 1, theme["header"])
            try:
                stdscr.hline(1, 0, ord(glyphs["rule"]), width - 1)
            except curses.error:
                stdscr.hline(1, 0, ord("-"), width - 1)

            left_view_h = max(1, height - 4)
            left_start = max(0, state.selected - (left_view_h // 2))
            left_end = min(len(visible_sections), left_start + left_view_h)
            if left_end - left_start < left_view_h:
                left_start = max(0, left_end - left_view_h)

            for row_idx, idx in enumerate(range(left_start, left_end)):
                section = visible_sections[idx]
                marker = glyphs["marker"] if idx == state.selected else " "
                label = f"{marker} {section.section.value.replace('_', ' ').title()} ({section.intensity})"
                attr = theme["selected"] if idx == state.selected else theme["body"]
                _safe_add(2 + row_idx, 0, label, left_w - 1, attr)

            for row in range(2, height - 1):
                try:
                    stdscr.addch(row, left_w, ord(glyphs["divider"]), theme["muted"])
                except curses.error:
                    stdscr.addch(row, left_w, ord("|"), theme["muted"])

            lines: list[tuple[str, str]] = []
            if state.cta_visible and not state.help_visible:
                lines.extend(
                    [
                        ("title", "OPASTRO LINKS @"),
                        ("blank", ""),
                        ("body", "Move with arrows or j/k. Enter selects; o opens."),
                        ("blank", ""),
                    ]
                )
                for idx, (name, description, target) in enumerate(_UI_HOME_CTAS):
                    marker = glyphs["marker"] if idx == state.cta_selected else " "
                    kind = "cta_selected" if idx == state.cta_selected else "label"
                    lines.append((kind, f"{marker} {name}"))
                    for wrapped in _wrap_for_width(description, right_w):
                        lines.append(("body", f"  {wrapped}"))
                    for wrapped in _wrap_for_width(target, right_w):
                        lines.append(("factor", f"  {wrapped}"))
                    lines.append(("blank", ""))
            elif state.help_visible:
                lines.extend(
                    [
                        ("title", "Keyboard shortcuts"),
                        ("blank", ""),
                        *(
                            [
                                (
                                    "body",
                                    "Events mode       Select an event; filter by type with /",
                                ),
                                ("blank", ""),
                            ]
                            if mode_label == "events"
                            else []
                        ),
                        ("body", "Up/Down or j/k  Select a section"),
                        ("body", "Enter             Toggle factor details"),
                        ("body", "Space/Page Down   Scroll forward"),
                        ("body", "b/Page Up         Scroll backward"),
                        ("body", "g/G               Jump to top/end"),
                        ("body", "h/?               Toggle this help"),
                        ("body", "/                 Filter sections"),
                        ("body", "c                 Clear section filter"),
                        ("body", "d                 Toggle compact/expanded density"),
                        ("body", "r                 Refresh the current report"),
                        ("body", "@                 Open links and CTA drawer"),
                        ("body", "o                 Open the selected CTA"),
                        (
                            "body",
                            (
                                "1-4               Switch report period"
                                if allow_period_switch
                                else "1-4               Period switching unavailable"
                            ),
                        ),
                        ("body", "q/Esc             Quit"),
                    ]
                )
            else:
                if not visible_sections:
                    lines.extend(
                        [
                            ("title", "No matching sections"),
                            ("blank", ""),
                            ("body", f"No section matches: {state.filter_query}"),
                            ("body", "Press / to change the filter or c to clear it."),
                        ]
                    )
                    section = None
                else:
                    section = visible_sections[state.selected]
                    lines.append(("title", section.title))
                    lines.append(("blank", ""))
                    summary_lines = _wrap_for_width(section.summary, right_w)
                    if state.compact:
                        summary_lines = summary_lines[:2]
                    for item in summary_lines:
                        lines.append(("body", item))
                    lines.append(("blank", ""))
                    lines.append(("label", "Highlights:"))
                    highlight_limit = 1 if state.compact else 3
                    for item in section.highlights[:highlight_limit]:
                        for wrapped in _wrap_for_width(f"- {item}", right_w):
                            lines.append(("body", wrapped))
                    lines.append(("blank", ""))
                    lines.append(("label", "Cautions:"))
                    caution_limit = 1 if state.compact else 2
                    for item in section.cautions[:caution_limit]:
                        for wrapped in _wrap_for_width(f"- {item}", right_w):
                            lines.append(("body", wrapped))
                    lines.append(("blank", ""))
                    lines.append(("label", "Actions:"))
                    action_limit = 1 if state.compact else 2
                    for item in section.actions[:action_limit]:
                        for wrapped in _wrap_for_width(f"- {item}", right_w):
                            lines.append(("body", wrapped))

                    if state.show_factors:
                        lines.append(("blank", ""))
                        lines.append(("label", "Factor drill-down:"))
                        factor_limit = 4 if state.compact else 8
                        for detail in section.factor_details[:factor_limit]:
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
            state.scroll_offset = max(0, min(state.scroll_offset, max_scroll))
            visible_lines = lines[state.scroll_offset : state.scroll_offset + page_h]
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
                elif kind == "cta_selected":
                    attr = theme["selected"]
                _safe_add(y, right_x, line, right_w, attr)

            if state.status_message:
                _safe_add(
                    height - 2,
                    0,
                    f"{glyphs['bullet']} {state.status_message}",
                    width - 1,
                    theme["muted"],
                )
            footer = (
                f"q/esc quit {glyphs['bullet']} {glyphs['nav']}/j/k section {glyphs['bullet']} "
                f"enter factors {glyphs['bullet']} pgup/pgdn scroll {glyphs['bullet']} "
                f"h/? help {glyphs['bullet']} / filter {glyphs['bullet']} d density {glyphs['bullet']} "
                f"r refresh {glyphs['bullet']} @ links"
            )
            if allow_period_switch:
                footer += f" {glyphs['bullet']} 1-4 period"
            _safe_add(height - 1, 0, footer, width - 1, theme["muted"])

            stdscr.refresh()
            key = stdscr.getch()
            if key == -1:
                frame += 1
                continue
            if not _apply_ui_key(
                state,
                key,
                section_count=len(visible_sections),
                page_height=page_h,
                allow_period_switch=allow_period_switch,
                cta_count=len(_UI_HOME_CTAS),
            ):
                break
            _process_pending_actions()

    curses.wrapper(_ui)
    return 0


def _handle_ui(args: argparse.Namespace) -> int:
    explicit_output_requested = bool(
        args.export
        or getattr(args, "json", False)
        or getattr(args, "output_format", None) is not None
    )
    _apply_profile_defaults(args)

    # `opastro ui` without a report period is the interactive home deck. A
    # supplied period keeps the existing report browser contract unchanged.
    if not args.period and args.kind == "horoscope":
        if getattr(args, "json", False):
            print(json.dumps(_home_payload(), indent=2, sort_keys=True))
            return 0
        if args.no_interactive or getattr(args, "output_format", None) is not None:
            reason = (
                "static output requested"
                if explicit_output_requested
                else "--no-interactive"
            )
            return _render_ui_home_fallback(
                args, reason, getattr(args, "update_info", None)
            )
        terminal_reason = _ui_terminal_reason()
        if terminal_reason:
            return _render_ui_home_fallback(
                args, terminal_reason, getattr(args, "update_info", None)
            )
        try:
            return _run_ui_home(
                ascii_mode=getattr(args, "ascii", False),
                update_info=getattr(args, "update_info", None),
            )
        except KeyboardInterrupt:
            print("UI cancelled.", file=sys.stderr)
            return 130
        except curses.error:
            return _render_ui_home_fallback(
                args,
                "curses could not initialize",
                getattr(args, "update_info", None),
            )

    service = HoroscopeService(ServiceConfig())
    payload = _generate_payload(service, args, args.kind)

    if args.no_interactive or explicit_output_requested:
        reason = (
            "static output requested"
            if explicit_output_requested
            else "--no-interactive"
        )
        return _render_ui_fallback(
            payload, args, reason, getattr(args, "update_info", None)
        )

    terminal_reason = _ui_terminal_reason(min_columns=42)
    if terminal_reason:
        return _render_ui_fallback(
            payload, args, terminal_reason, getattr(args, "update_info", None)
        )

    try:

        def _load_period(period: str):
            period_args = argparse.Namespace(**vars(args))
            period_args.period = period
            return _generate_payload(service, period_args, args.kind)

        mode_label = args.kind
        if args.kind == "planet":
            mode_label = f"planet:{args.planet}"

        return _run_ui(
            payload,
            ascii_mode=getattr(args, "ascii", False),
            payload_loader=_load_period,
            allow_period_switch=args.kind != "birthday",
            mode_label=mode_label,
            update_info=getattr(args, "update_info", None),
        )
    except KeyboardInterrupt:
        print("UI cancelled.", file=sys.stderr)
        return 130
    except curses.error:
        return _render_ui_fallback(
            payload,
            args,
            "curses could not initialize",
            getattr(args, "update_info", None),
        )


def _resolve_batch_signs(args: argparse.Namespace) -> list[str]:
    explicit = _parse_signs(args.signs)
    if explicit:
        return explicit
    sign = getattr(args, "sign", None)
    if sign:
        normalized = _normalize_sign(sign)
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
            raise ValueError(
                "Both --date-from and --date-to are required for date ranges."
            )
        return _date_range(
            _parse_date(args.date_from), _parse_date(args.date_to), args.step_days
        )
    return [date.today()]


def _batch_extension(fmt: str) -> str:
    return {"text": ".txt", "json": ".json", "markdown": ".md", "html": ".html"}[fmt]


def _handle_batch(args: argparse.Namespace) -> int:
    from tqdm import tqdm

    _apply_profile_defaults(args)
    if args.kind == "planet" and not args.planet:
        raise ValueError("--planet is required for kind=planet.")

    service = HoroscopeService(ServiceConfig())
    signs = _resolve_batch_signs(args)
    dates = _resolve_batch_dates(args)

    exports: list[str] = []
    rendered_blobs: list[str] = []
    json_rows: list[dict[str, Any]] = []
    total_items = len(signs) * len(dates)
    pbar = tqdm(total=total_items, desc="Batch generating", unit="report")
    for target in dates:
        for sign in signs:
            item_args = argparse.Namespace(**vars(args))
            item_args.sign = sign
            item_args.target_date = target.isoformat()
            payload = _generate_payload(service, item_args, args.kind)

            if args.output_format == "json" and not args.export_dir:
                json_rows.append(payload.model_dump(mode="json"))
            else:
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
            pbar.update(1)
    pbar.close()

    if args.output_format == "json" and not args.export_dir:
        print(json.dumps(json_rows, indent=2))
    elif rendered_blobs:
        print("\n\n".join(rendered_blobs))

    print(
        f"batch summary: generated={total_items} signs={len(signs)} dates={len(dates)} kind={args.kind}",
        file=sys.stderr,
    )
    if exports:
        print(
            f"batch export: wrote {len(exports)} files to {Path(args.export_dir).expanduser()}",
            file=sys.stderr,
        )
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


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _ics_datetime(value: datetime) -> str:
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _render_celestial_events_text(response) -> str:
    lines = [
        "OPASTRO CELESTIAL EVENTS",
        f"Period: {response.period.value}",
        f"Window: {response.start.date()} to {response.end.date()}",
        f"Events: {len(response.events)}",
        "",
    ]
    if response.events:
        for event in response.events:
            timestamp = event.timestamp.strftime("%Y-%m-%d %H:%M UTC")
            detail = event.description
            if event.exactness is not None:
                detail += f" | orb {event.exactness:.2f}°"
            lines.append(f"{timestamp} | {event.event_type} | {detail}")
    else:
        lines.append("No notable celestial events in this window.")
    if response.metrics.retrograde_bodies:
        lines.extend(
            [
                "",
                "Retrograde emphasis: " + ", ".join(response.metrics.retrograde_bodies),
            ]
        )
    return "\n".join(lines) + "\n"


def _render_celestial_events_ics(response) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OpAstro//Celestial Events//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{_ics_escape(f'OpAstro {response.period.value} Celestial Events')}",
    ]
    for event in response.events:
        seed = "|".join(
            [
                event.event_type,
                event.timestamp.isoformat(),
                event.description,
            ]
        )
        uid = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24] + "@opastro"
        start = _ics_datetime(event.timestamp)
        end = _ics_datetime(event.timestamp + timedelta(hours=1))
        description = event.event_type
        if event.exactness is not None:
            description += f"; exactness={event.exactness:.2f} degrees"
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{start}",
                f"DTSTART:{start}",
                f"DTEND:{end}",
                f"SUMMARY:{_ics_escape(event.description)}",
                f"DESCRIPTION:{_ics_escape(description)}",
                f"X-OPASTRO-EVENT-TYPE:{_ics_escape(event.event_type)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _handle_celestial_events(args: argparse.Namespace) -> int:
    service = HoroscopeService(ServiceConfig())
    request = _build_celestial_events_request(args)
    response = service.generate_celestial_events(request)
    if args.events_format == "json":
        rendered = response.model_dump_json(indent=2)
    elif args.events_format == "ics":
        rendered = _render_celestial_events_ics(response)
    else:
        rendered = _render_celestial_events_text(response)

    if args.export:
        target = _save_export(rendered, args.export)
        print(f"saved output to {target}", file=sys.stderr)
    else:
        print(rendered, end="" if rendered.endswith("\n") else "\n")
    return 0


def _handle_natal(args: argparse.Namespace) -> int:
    from tqdm import tqdm

    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    request = _build_natal_request(args)

    # Progress for generation
    with tqdm(
        total=2,
        desc="Natal report",
        unit="step",
        disable=sys.stdout.isatty() is False and os.getenv("CI") == "1",
    ) as pbar:
        report = service.generate_natal_birthchart(request)
        pbar.update(1)

        if args.json:
            print(report.model_dump_json(indent=2))
        else:
            print(_render_natal_text(report))
        pbar.update(1)

    exports = _export_natal_assets(report, args)
    if exports:
        for target in tqdm(exports, desc="Exporting assets", unit="file", leave=False):
            print(f"saved output to {target}", file=sys.stderr)
    return 0


def _handle_render_planetary_scene(args: argparse.Namespace) -> int:
    config = ServiceConfig()
    ephemeris = EphemerisEngine(config.ephemeris)

    if args.datetime:
        # replace Z with +00:00 for fromisoformat compatibility in 3.11
        dt_str = args.datetime.replace("Z", "+00:00")
        target_dt = datetime.fromisoformat(dt_str)
    else:
        target_dt = datetime.now()

    # Obtain positions directly as a snapshot
    snapshot = ephemeris.chart_snapshot(target_dt)

    export_path = args.export
    if args.format == "png" and export_path.endswith(".svg"):
        export_path = export_path.replace(".svg", ".png")
    elif args.format == "svg" and export_path.endswith(".png"):
        export_path = export_path.replace(".png", ".svg")

    if args.format == "png":
        build_planetary_scene_png(
            snapshot=snapshot,
            output_path=export_path,
            theme=args.theme,
            projection=args.projection,
            include_labels=args.include_labels,
            include_orbits=args.include_orbits,
            include_minor_bodies=args.include_minor_bodies,
            include_aspects=args.include_aspects,
            transparent_bg=args.transparent,
            include_zodiac_band=args.include_zodiac_band,
            include_motion=args.include_motion,
        )
    else:
        build_planetary_scene_svg(
            snapshot=snapshot,
            output_path=export_path,
            theme=args.theme,
            projection=args.projection,
            include_labels=args.include_labels,
            include_orbits=args.include_orbits,
            include_minor_bodies=args.include_minor_bodies,
            include_aspects=args.include_aspects,
            transparent_bg=args.transparent,
            include_zodiac_band=args.include_zodiac_band,
            include_motion=args.include_motion,
        )
    print(f"saved output to {export_path}", file=sys.stderr)
    return 0


def _handle_serve(args: argparse.Namespace) -> int:
    uvicorn.run(
        "horoscope_engine.main:app", host=args.host, port=args.port, reload=args.reload
    )
    return 0


def _known_command_tokens() -> list[str]:
    tokens: list[str] = []
    for command, aliases in COMMAND_ALIASES.items():
        tokens.append(command)
        tokens.extend(aliases)
    return sorted(set(tokens))


def _suggest_command(token: str) -> str:
    suggestions = difflib.get_close_matches(
        token, _known_command_tokens(), n=3, cutoff=0.45
    )
    if suggestions:
        return f"Unknown command '{token}'. Did you mean: {', '.join(suggestions)}?"
    return f"Unknown command '{token}'. Run `opastro --help`."


def _maybe_check_for_update(
    *,
    no_update_check: bool = False,
    force_update_check: bool = False,
) -> UpdateCheckResult | None:
    if no_update_check:
        return None
    mode = (os.getenv("OPASTRO_UPDATE_CHECK") or "").strip().lower()
    if mode in {"0", "false", "off", "disabled", "no"}:
        return None
    if not force_update_check and mode not in {"1", "true", "always", "force"}:
        if not sys.stdout.isatty() and not sys.stderr.isatty():
            return None
    return check_for_update(force=force_update_check)


def main(argv: Optional[list[str]] = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    started_at = time.perf_counter()
    analytics_command = _canonical_command_name(raw_argv[0] if raw_argv else None)
    parser = _build_base_parser()
    if not raw_argv:
        update_info = _maybe_check_for_update()
        code = _show_welcome(update_info)
        return _analytics_exit(command="welcome", started_at=started_at, exit_code=code)

    # UX shorthand: allow `opastro logger --limit 5` to behave like
    # `opastro logger show --limit 5` while preserving `logger --help`.
    if (
        len(raw_argv) >= 2
        and raw_argv[0] in {"logger", *COMMAND_ALIASES.get("logger", [])}
        and raw_argv[1].startswith("-")
        and raw_argv[1] not in {"-h", "--help"}
    ):
        raw_argv = [raw_argv[0], "show", *raw_argv[1:]]

    first = raw_argv[0]
    if not first.startswith("-") and first not in _known_command_tokens():
        print(_suggest_command(first), file=sys.stderr)
        return _analytics_exit(
            command=analytics_command,
            started_at=started_at,
            exit_code=2,
            failure_category="unknown_command",
        )

    try:
        args = parser.parse_args(raw_argv)
    except SystemExit as exc:
        code = int(exc.code)
        return _analytics_exit(
            command=analytics_command,
            started_at=started_at,
            exit_code=code,
            failure_category="argparse" if code else None,
        )
    try:
        analytics_command = _canonical_command_name(
            getattr(args, "command", analytics_command)
        )
        update_info = _maybe_check_for_update(
            no_update_check=getattr(args, "no_update_check", False),
            force_update_check=getattr(args, "force_update_check", False),
        )
        args.update_info = update_info
        notice = update_notice(update_info) if update_info else None
        if notice and analytics_command not in {"ui", "welcome"}:
            print(notice, file=sys.stderr)
        if hasattr(args, "handler"):
            code = int(args.handler(args))
            return _analytics_exit(
                command=analytics_command, started_at=started_at, exit_code=code
            )
        print(f"error: Unsupported command: {args.command}", file=sys.stderr)
        return _analytics_exit(
            command=analytics_command,
            started_at=started_at,
            exit_code=2,
            failure_category="unsupported_command",
        )
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return _analytics_exit(
            command=analytics_command,
            started_at=started_at,
            exit_code=130,
            failure_category="cancelled",
        )
    except Exception as exc:
        entry = _serialize_runtime_error(raw_argv, exc)
        log_path = _append_runtime_error_log(entry)
        print(f"error: {exc}", file=sys.stderr)
        for fix in entry["suggested_fixes"][:3]:
            print(f"suggestion: {fix}", file=sys.stderr)
        if log_path is not None:
            print(f"runtime log: {log_path}", file=sys.stderr)
        print("inspect logs: opastro logger show --limit 5", file=sys.stderr)
        return _analytics_exit(
            command=analytics_command,
            started_at=started_at,
            exit_code=2,
            failure_category=_failure_category_for_exception(exc),
        )


if __name__ == "__main__":
    raise SystemExit(main())
