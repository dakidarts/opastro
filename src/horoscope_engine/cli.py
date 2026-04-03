from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from datetime import date, datetime
from html import escape as html_escape
from io import StringIO
import json
import os
import platform
from pathlib import Path
import shutil
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
    Period,
    PlanetHoroscopeRequest,
    PlanetName,
    Section,
    ZODIAC_SIGNS,
)
from .profiles import DEFAULT_PROFILE_NAME, ProfileStore
from .service import HoroscopeService

WELCOME_BANNER = r"""
   ____  ____   ___   _____ _______ ____   ____ 
  / __ \/ __ \ /   | / ___//_  __// __ \ / __ \
 / / / / /_/ // /| | \__ \  / /  / /_/ // / / /
/ /_/ / ____// ___ |___/ / / /  / _, _// /_/ / 
\____/_/    /_/  |_/____/ /_/  /_/ |_| \____/  
"""

UPSELL_TEXT = "✨ Want deeper insights?\n→ Unlock full readings: https://numerologyapi.com"

DEFAULT_WRAP_WIDTH = 96
MIN_PYTHON_VERSION = (3, 11)
OUTPUT_FORMATS = ("text", "json", "markdown", "html")


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
    parser = argparse.ArgumentParser(
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
              opastro serve --host 127.0.0.1 --port 8000 --reload
            """
        ).strip(),
    )
    subparsers = parser.add_subparsers(dest="command")

    init = subparsers.add_parser(
        "init",
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
        help="Show the Opastro home screen and quick command guide.",
        description="Display the branded Opastro welcome UI and command overview.",
    )
    welcome.set_defaults(handler=_handle_welcome)

    catalog = subparsers.add_parser(
        "catalog",
        help="List supported periods, sections, signs, and planets.",
        description="Print the command catalog for scripting and onboarding.",
    )
    catalog.set_defaults(handler=_handle_catalog)

    doctor = subparsers.add_parser(
        "doctor",
        help="Run local environment diagnostics for Opastro.",
        description="Check Python runtime, executable path, and key engine readiness flags.",
    )
    doctor.set_defaults(handler=_handle_doctor)

    profile = subparsers.add_parser(
        "profile",
        help="Manage saved CLI profiles (save/list/show/use).",
        description="Manage reusable defaults for sign/birth/preferences.",
    )
    profile.set_defaults(handler=_handle_profile_list)
    profile_sub = profile.add_subparsers(dest="profile_command")

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
        help="Generate a standard horoscope report.",
        description="Generate deterministic horoscope output for a sign or birth profile.",
    )
    _add_common_report_args(horoscope, require_period=True)
    horoscope.set_defaults(handler=_handle_horoscope)

    birthday = subparsers.add_parser(
        "birthday",
        help="Generate a birthday-cycle report.",
        description="Generate a yearly birthday-cycle report with lite meanings.",
    )
    _add_common_report_args(birthday, require_period=False)
    birthday.set_defaults(handler=_handle_birthday)

    planet = subparsers.add_parser(
        "planet",
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

    serve = subparsers.add_parser(
        "serve",
        help="Run the FastAPI service locally.",
        description="Run the Opastro API server for app and integration development.",
    )
    serve.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
    serve.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000).")
    serve.add_argument("--reload", action="store_true", help="Enable dev reload mode.")
    serve.set_defaults(handler=_handle_serve)

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
        help="Zodiac system override.",
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


def _add_profile_fields(parser: argparse.ArgumentParser) -> None:
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
    if not colorize or not sys.stdout.isatty() or os.getenv("NO_COLOR"):
        return text
    return f"\033[{code}m{text}\033[0m"


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


def _print_heading(label: str) -> None:
    print(_style(label, "1;36"))


def _print_divider(char: str = "─") -> None:
    print(_style(char * _term_width(), "2"))


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
        print(_style(f"{section_label} ({insight.intensity})", "1;33"))
        print(_wrap(insight.summary, indent="  "))

        if insight.highlights:
            print(_style("  Highlights", "1"))
            for item in insight.highlights[:3]:
                print(_wrap_bullet(item))
        if insight.cautions:
            print(_style("  Cautions", "1"))
            for item in insight.cautions[:2]:
                print(_wrap_bullet(item))
        if insight.actions:
            print(_style("  Actions", "1"))
            for item in insight.actions[:2]:
                print(_wrap_bullet(item))
        _print_divider("·")

    print(_style(UPSELL_TEXT, "1;35"))
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


def _show_welcome() -> int:
    print(_style(WELCOME_BANNER.strip("\n"), "1;34"))
    print(_style("OPASTRO • Open Core Horoscope Engine", "1;36"))
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
    print(_style(UPSELL_TEXT, "1;35"))
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


def _handle_doctor(_: argparse.Namespace) -> int:
    cfg = ServiceConfig()
    _print_heading("OPASTRO DOCTOR")
    _print_divider()
    print(f"Python version : {platform.python_version()}")
    print(f"Python exec    : {sys.executable}")
    print(f"Platform       : {platform.platform()}")
    print(f"Ephemeris path : {cfg.ephemeris.ephemeris_path or 'auto/not-set'}")
    print(f"Zodiac system  : {cfg.ephemeris.zodiac_system}")
    print(f"Ayanamsa       : {cfg.ephemeris.ayanamsa_system}")
    required = f"{MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+"
    if sys.version_info >= MIN_PYTHON_VERSION:
        print(_style(f"Runtime check  : OK (Python {required} requirement satisfied)", "1;32"))
    else:
        current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(_style(f"Runtime check  : WARN (running {current}; requires {required})", "1;33"))
        print("Recommendation : Use a Python 3.11+ virtual environment and reinstall opastro.")
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
    profile = ProfileStore().get_profile()
    if not profile:
        return

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


def _handle_horoscope(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    request = HoroscopeRequest(
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
    return _render_output(
        service.generate(request),
        output_format=_resolve_output_format(args),
        export_path=args.export,
    )


def _handle_birthday(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    request = BirthdayHoroscopeRequest(
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
    return _render_output(
        service.generate_birthday(request),
        output_format=_resolve_output_format(args),
        export_path=args.export,
    )


def _handle_planet(args: argparse.Namespace) -> int:
    _apply_profile_defaults(args)
    service = HoroscopeService(ServiceConfig())
    request = PlanetHoroscopeRequest(
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
    return _render_output(
        service.generate_planet(request),
        output_format=_resolve_output_format(args),
        export_path=args.export,
    )


def _handle_serve(args: argparse.Namespace) -> int:
    uvicorn.run("horoscope_engine.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    parser = _build_base_parser()
    if not raw_argv:
        return _show_welcome()

    args = parser.parse_args(raw_argv)
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
