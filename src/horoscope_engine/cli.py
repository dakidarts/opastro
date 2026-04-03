from __future__ import annotations

import argparse
import os
import platform
import shutil
import sys
import textwrap
from datetime import date
from typing import Optional

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


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _parse_sections(raw: Optional[str]) -> Optional[list[str]]:
    if not raw:
        return None
    values = [value.strip() for value in raw.split(",") if value.strip()]
    return values or None


def _build_birth(args: argparse.Namespace) -> Optional[BirthData]:
    if not args.birth_date:
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
              opastro horoscope --period daily --sign ARIES --target-date 2026-04-03
              opastro horoscope --period weekly --birth-date 1992-06-15 --birth-time 09:30 --lat 4.0511 --lon 9.7679 --timezone Africa/Douala
              opastro planet --period monthly --planet mercury --sign TAURUS
              opastro serve --host 127.0.0.1 --port 8000 --reload
            """
        ).strip(),
    )
    subparsers = parser.add_subparsers(dest="command")

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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full raw JSON instead of the styled terminal report.",
    )


def _render_json(payload) -> int:
    print(payload.model_dump_json(indent=2))
    return 0


def _style(text: str, code: str) -> str:
    if not sys.stdout.isatty() or os.getenv("NO_COLOR"):
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


def _render_output(payload, as_json: bool) -> int:
    if as_json:
        return _render_json(payload)
    return _render_pretty_report(payload)


def _show_welcome() -> int:
    print(_style(WELCOME_BANNER.strip("\n"), "1;34"))
    print(_style("OPASTRO • Open Core Horoscope Engine", "1;36"))
    print(_wrap("Enterprise-grade deterministic calculations with lightweight open meanings and premium-ready API hooks."))
    _print_divider()
    _print_heading("Commands")
    commands = [
        ("welcome", "Show the branded home screen and onboarding shortcuts."),
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
    expected = "/opt/homebrew/opt/python@3.11/bin/python3.11"
    if sys.executable == expected:
        print(_style("Runtime check  : OK (Homebrew Python 3.11 active)", "1;32"))
    else:
        print(_style(f"Runtime check  : WARN (recommended: {expected})", "1;33"))
    return 0


def _handle_horoscope(args: argparse.Namespace) -> int:
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
    return _render_output(service.generate(request), as_json=args.json)


def _handle_birthday(args: argparse.Namespace) -> int:
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
    return _render_output(service.generate_birthday(request), as_json=args.json)


def _handle_planet(args: argparse.Namespace) -> int:
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
    return _render_output(service.generate_planet(request), as_json=args.json)


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
