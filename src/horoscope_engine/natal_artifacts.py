from __future__ import annotations

import math
import re
from datetime import date, datetime
from io import BytesIO
from typing import Any, Optional

from .models import NatalBirthchartResponse, ZODIAC_SIGNS

ACCENT_DEFAULT = "#3ddd77"
SYMBOL_FONT_STACK = (
    "'Apple Symbols','Segoe UI Symbol','Noto Sans Symbols2','Symbola',"
    "'DejaVu Sans','Arial Unicode MS','Helvetica','Arial',sans-serif"
)
TEXT_FONT_STACK = "'Menlo','Consolas','SFMono-Regular','DejaVu Sans Mono','Liberation Mono',monospace"

ZODIAC_SYMBOL_CODEPOINT = {
    "ARIES": 0x2648,
    "TAURUS": 0x2649,
    "GEMINI": 0x264A,
    "CANCER": 0x264B,
    "LEO": 0x264C,
    "VIRGO": 0x264D,
    "LIBRA": 0x264E,
    "SCORPIO": 0x264F,
    "SAGITTARIUS": 0x2650,
    "CAPRICORN": 0x2651,
    "AQUARIUS": 0x2652,
    "PISCES": 0x2653,
}
PLANET_STYLE = {
    "Sun": "#f59e0b",
    "Moon": "#60a5fa",
    "Mercury": "#22c55e",
    "Venus": "#ec4899",
    "Mars": "#ef4444",
    "Jupiter": "#8b5cf6",
    "Saturn": "#64748b",
    "Uranus": "#06b6d4",
    "Neptune": "#0ea5e9",
    "Pluto": "#9333ea",
    "Chiron": "#14b8a6",
}
PLANET_SYMBOL_CODEPOINT = {
    "Sun": 0x2609,
    "Moon": 0x263D,
    "Mercury": 0x263F,
    "Venus": 0x2640,
    "Mars": 0x2642,
    "Jupiter": 0x2643,
    "Saturn": 0x2644,
    "Uranus": 0x2645,
    "Neptune": 0x2646,
    "Pluto": 0x2647,
    "Chiron": 0x26B7,
}
PLANET_TOKEN = {
    "Sun": "Su",
    "Moon": "Mo",
    "Mercury": "Me",
    "Venus": "Ve",
    "Mars": "Ma",
    "Jupiter": "Ju",
    "Saturn": "Sa",
    "Uranus": "Ur",
    "Neptune": "Ne",
    "Pluto": "Pl",
    "Chiron": "Ch",
}
ASPECT_SYMBOL_TEXT = {
    "conjunction": "●",
    "opposition": "☍",
    "trine": "△",
    "square": "□",
    "sextile": "*",
    "quincunx": "∿",
    "semi-sextile": "+",
    "semi-square": "∠",
    "sesquiquadrate": "⟂",
}
ASPECT_TOKEN = {
    "conjunction": "Conj",
    "opposition": "Opp",
    "trine": "Tri",
    "square": "Sqr",
    "sextile": "Sxt",
    "quincunx": "Qnx",
    "semi-sextile": "SSx",
    "semi-square": "SSq",
    "sesquiquadrate": "Sesq",
}
ASPECT_LINE_COLOR = {
    "conjunction": "#f59e0b",
    "opposition": "#ef4444",
    "trine": "#22c55e",
    "square": "#f97316",
    "sextile": "#38bdf8",
    "quincunx": "#a78bfa",
}
ASPECT_PRIORITY = {
    "conjunction": 0,
    "opposition": 1,
    "trine": 2,
    "square": 3,
    "sextile": 4,
    "quincunx": 5,
}
MASCULINE_SIGNS = {"ARIES", "GEMINI", "LEO", "LIBRA", "SAGITTARIUS", "AQUARIUS"}
WHEEL_THEME_PALETTES = {
    "night": {
        "bg_0": "#0b1730",
        "bg_1": "#101d38",
        "bg_2": "#0a1326",
        "panel_fill": "#0c1730",
        "panel_opacity": 0.78,
        "sign_line": "#2b3f63",
        "ring_inner": "#34486a",
        "center_fill": "#0d1832",
        "center_stroke": "#1e2f4a",
        "divider": "#2a3f64",
        "subtitle": "#8fa2c2",
    },
    "day": {
        "bg_0": "#1a5f45",
        "bg_1": "#154f3a",
        "bg_2": "#0f3527",
        "panel_fill": "#132a22",
        "panel_opacity": 0.74,
        "sign_line": "#3f6f58",
        "ring_inner": "#4f8069",
        "center_fill": "#153426",
        "center_stroke": "#2f5f4a",
        "divider": "#3f6f58",
        "subtitle": "#b5d6c4",
    },
}


def _symbol(codepoint: Optional[int], fallback: str = "?") -> str:
    if codepoint is None:
        return fallback
    try:
        return chr(codepoint)
    except Exception:
        return fallback


def _polar_xy(cx: float, cy: float, radius: float, longitude: float) -> tuple[float, float]:
    angle = math.radians((longitude % 360.0) - 90.0)
    return (cx + radius * math.cos(angle), cy + radius * math.sin(angle))


def _cluster_tangent_offsets(items: list[tuple[str, float]], max_gap: float = 4.5) -> dict[str, float]:
    if not items:
        return {}
    sorted_items = sorted(items, key=lambda item: item[1] % 360.0)
    clusters: list[list[tuple[str, float]]] = []
    current: list[tuple[str, float]] = [sorted_items[0]]

    for item in sorted_items[1:]:
        prev = current[-1]
        if ((item[1] - prev[1]) % 360.0) <= max_gap:
            current.append(item)
        else:
            clusters.append(current)
            current = [item]
    clusters.append(current)

    if len(clusters) > 1:
        first = clusters[0]
        last = clusters[-1]
        if ((first[0][1] + 360.0 - last[-1][1]) % 360.0) <= max_gap:
            merged = last + first
            clusters = [merged] + clusters[1:-1]

    offsets: dict[str, float] = {}
    for cluster in clusters:
        count = len(cluster)
        center = (count - 1) / 2.0
        for idx, (name, _) in enumerate(cluster):
            offsets[name] = (idx - center) * 14.0
    return offsets


def _house_from_cusps(longitude: float, cusps: list[float]) -> Optional[int]:
    if len(cusps) != 12:
        return None
    lon = longitude % 360.0
    normalized = [(cusp % 360.0) for cusp in cusps]
    for idx in range(12):
        start = normalized[idx]
        end = normalized[(idx + 1) % 12]
        arc = (end - start) % 360.0
        if arc <= 0:
            continue
        offset = (lon - start) % 360.0
        if offset < arc or (idx == 11 and offset <= arc):
            return idx + 1
    return None


def _major_aspect_rows(report: NatalBirthchartResponse, limit: int = 12) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for aspect in report.snapshot.aspects:
        if aspect.body1 not in PLANET_STYLE or aspect.body2 not in PLANET_STYLE:
            continue
        if aspect.aspect not in ASPECT_SYMBOL_TEXT:
            continue
        rows.append(
            {
                "body1": aspect.body1,
                "body2": aspect.body2,
                "aspect": aspect.aspect,
                "orb": float(aspect.orb),
                "exact": bool(aspect.exact),
            }
        )
    rows.sort(key=lambda item: (item["orb"], ASPECT_PRIORITY.get(item["aspect"], 99), item["body1"], item["body2"]))
    return rows[:limit]


def _sign_polarity(sign: str) -> str:
    return "masculine" if sign.upper() in MASCULINE_SIGNS else "feminine"


def _element_percentages(report: NatalBirthchartResponse) -> dict[str, float]:
    premium = report.premium_insights
    if premium and premium.dominant_signature and premium.dominant_signature.element_balance:
        base = premium.dominant_signature.element_balance
        return {
            "fire": round(float(base.get("fire", 0.0)) * 100.0, 1),
            "earth": round(float(base.get("earth", 0.0)) * 100.0, 1),
            "air": round(float(base.get("air", 0.0)) * 100.0, 1),
            "water": round(float(base.get("water", 0.0)) * 100.0, 1),
        }

    buckets = {"fire": 0.0, "earth": 0.0, "air": 0.0, "water": 0.0}
    sign_to_element = {
        "ARIES": "fire",
        "TAURUS": "earth",
        "GEMINI": "air",
        "CANCER": "water",
        "LEO": "fire",
        "VIRGO": "earth",
        "LIBRA": "air",
        "SCORPIO": "water",
        "SAGITTARIUS": "fire",
        "CAPRICORN": "earth",
        "AQUARIUS": "air",
        "PISCES": "water",
    }
    positions = [position for position in report.snapshot.positions if position.name in PLANET_STYLE]
    total = float(len(positions) or 1)
    for position in positions:
        element = sign_to_element.get(position.sign)
        if element:
            buckets[element] += 1.0
    return {key: round((value / total) * 100.0, 1) for key, value in buckets.items()}


def _angle_data(report: NatalBirthchartResponse) -> dict[str, Optional[dict[str, Any]]]:
    asc: Optional[dict[str, Any]] = None
    mc: Optional[dict[str, Any]] = None
    cusps = report.snapshot.house_cusps or []

    if report.snapshot.rising_sign:
        asc_lon = float(cusps[0]) if len(cusps) == 12 else None
        asc = {
            "sign": report.snapshot.rising_sign,
            "longitude": round(asc_lon, 6) if asc_lon is not None else None,
        }
    if len(cusps) == 12:
        mc_lon = float(cusps[9])
        mc = {
            "sign": ZODIAC_SIGNS[int((mc_lon % 360.0) // 30)],
            "longitude": round(mc_lon, 6),
        }
    return {"ascendant": asc, "midheaven": mc}


def _degree_in_sign(longitude: Optional[float]) -> Optional[float]:
    if longitude is None:
        return None
    return round(float(longitude) % 30.0, 2)


def _resolve_wheel_theme(theme: Optional[str]) -> str:
    normalized = (theme or "night").strip().lower()
    if normalized not in WHEEL_THEME_PALETTES:
        return "night"
    return normalized


def build_natal_wheel_svg(
    report: NatalBirthchartResponse,
    *,
    accent_color: str = ACCENT_DEFAULT,
    size: int = 1080,
    brand_title: str = "OPASTRO",
    user_name: Optional[str] = None,
    theme: str = "night",
) -> str:
    wheel_theme = _resolve_wheel_theme(theme)
    palette = WHEEL_THEME_PALETTES[wheel_theme]
    width = max(760, int(size))
    top_margin = width * 0.07
    cx = width * 0.34
    ring_outer = width * 0.25
    ring_inner = width * 0.17
    cy = top_margin + ring_outer + (width * 0.11)
    planet_radius = width * 0.145
    sign_symbol_radius = width * 0.225
    sign_name_radius = width * 0.205
    house_label_radius = width * 0.185

    sign_lines: list[str] = []
    sign_labels: list[str] = []
    for idx, sign in enumerate(ZODIAC_SIGNS):
        start_lon = idx * 30.0
        x1, y1 = _polar_xy(cx, cy, ring_inner, start_lon)
        x2, y2 = _polar_xy(cx, cy, ring_outer, start_lon)
        sign_lines.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{palette["sign_line"]}" stroke-width="1.7" opacity="0.90" />'
        )

        mid_lon = start_lon + 15.0
        sx, sy = _polar_xy(cx, cy, sign_symbol_radius, mid_lon)
        nx, ny = _polar_xy(cx, cy, sign_name_radius, mid_lon)
        sign_labels.append(
            f'<text x="{sx:.2f}" y="{sy:.2f}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="24" font-family="{SYMBOL_FONT_STACK}" fill="#e2e8f0">'
            f"{_symbol(ZODIAC_SYMBOL_CODEPOINT.get(sign), sign[:2])}</text>"
        )
        sign_labels.append(
            f'<text x="{nx:.2f}" y="{ny:.2f}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="13" font-family="{TEXT_FONT_STACK}" fill="#9fb0cd">{sign[:3]}</text>'
        )

    cusps = report.snapshot.house_cusps or []
    house_lines: list[str] = []
    house_labels: list[str] = []
    if len(cusps) == 12:
        house_starts = list(cusps)
    else:
        house_starts = [idx * 30.0 for idx in range(12)]
    for idx, cusp in enumerate(house_starts):
        hx1, hy1 = _polar_xy(cx, cy, ring_inner * 0.88, cusp)
        hx2, hy2 = _polar_xy(cx, cy, ring_outer * 0.99, cusp)
        house_lines.append(
            f'<line x1="{hx1:.2f}" y1="{hy1:.2f}" x2="{hx2:.2f}" y2="{hy2:.2f}" '
            f'stroke="{accent_color}" stroke-width="2.0" opacity="0.95" />'
        )
        next_cusp = house_starts[(idx + 1) % 12]
        arc = (next_cusp - cusp) % 360.0
        mid = (cusp + (arc / 2.0)) % 360.0
        tx, ty = _polar_xy(cx, cy, house_label_radius, mid)
        house_labels.append(
            f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="17" font-family="{TEXT_FONT_STACK}" fill="{accent_color}" font-weight="700">{idx + 1}</text>'
        )

    focus_positions = sorted(
        [pos for pos in report.snapshot.positions if pos.name in PLANET_STYLE],
        key=lambda item: item.longitude,
    )
    point_map: dict[str, tuple[float, float]] = {}
    for position in focus_positions:
        point_map[position.name] = _polar_xy(cx, cy, planet_radius, position.longitude)

    aspect_rows = _major_aspect_rows(report, limit=12)
    aspect_lines: list[str] = []
    for row in aspect_rows:
        if row["aspect"] == "conjunction":
            continue
        p1 = point_map.get(row["body1"])
        p2 = point_map.get(row["body2"])
        if not p1 or not p2:
            continue
        color = ASPECT_LINE_COLOR.get(row["aspect"], "#94a3b8")
        width_line = 1.6 if row["exact"] else 1.1
        aspect_lines.append(
            f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" '
            f'stroke="{color}" stroke-width="{width_line:.2f}" opacity="0.58" />'
        )

    angle_info = _angle_data(report)
    asc = angle_info["ascendant"]
    mc = angle_info["midheaven"]
    angle_marks: list[str] = []

    def _draw_angle_mark(name: str, longitude: Optional[float], color: str) -> None:
        if longitude is None:
            return
        x1, y1 = _polar_xy(cx, cy, ring_outer * 0.98, longitude)
        x2, y2 = _polar_xy(cx, cy, ring_outer * 1.07, longitude)
        tx, ty = _polar_xy(cx, cy, ring_outer * 1.12, longitude)
        angle_marks.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="{color}" stroke-width="2.6" opacity="0.95" />'
        )
        angle_marks.append(
            f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="12.5" font-family="{TEXT_FONT_STACK}" fill="{color}" font-weight="700">{name}</text>'
        )

    _draw_angle_mark("ASC", asc["longitude"] if asc else None, "#22d3ee")
    _draw_angle_mark("MC", mc["longitude"] if mc else None, "#f59e0b")

    points: list[str] = []
    point_labels: list[str] = []
    label_offsets = _cluster_tangent_offsets([(pos.name, pos.longitude) for pos in focus_positions], max_gap=5.0)
    for position in focus_positions:
        x, y = point_map[position.name]
        color = PLANET_STYLE.get(position.name, "#f8fafc")
        points.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6.3" fill="{color}" stroke="#0f172a" stroke-width="1.15" />'
        )
        theta = math.radians((position.longitude % 360.0) - 90.0)
        tangent_x = -math.sin(theta)
        tangent_y = math.cos(theta)
        base_lx, base_ly = _polar_xy(cx, cy, planet_radius - 21.0, position.longitude)
        tangent_offset = label_offsets.get(position.name, 0.0)
        lx = base_lx + (tangent_x * tangent_offset)
        ly = base_ly + (tangent_y * tangent_offset)
        point_labels.append(
            f'<line x1="{x:.2f}" y1="{y:.2f}" x2="{lx:.2f}" y2="{ly:.2f}" '
            'stroke="#90a4c5" stroke-width="0.9" opacity="0.75" />'
        )
        point_labels.append(
            f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="15" font-family="{SYMBOL_FONT_STACK}" fill="#f8fafc">'
            f"{_symbol(PLANET_SYMBOL_CODEPOINT.get(position.name), position.name[:2].upper())}</text>"
        )

    element_pct = _element_percentages(report)
    sign_polarity = _sign_polarity(report.sign)

    planet_row_h = 24.0
    profile_row_h = 18.0
    planet_card_x = width * 0.62
    planet_card_y = top_margin
    planet_card_w = width * 0.33
    section_gap = max(12.0, width * 0.012)
    aspect_visible_rows = aspect_rows[:6]
    legend_card_x = planet_card_x
    legend_card_w = planet_card_w
    legend_inner_w = max(220.0, legend_card_w - 30.0)
    sign_columns = 3 if legend_inner_w >= 320.0 else 2
    sign_rows = int(math.ceil(len(ZODIAC_SIGNS) / sign_columns))
    sign_row_h = 26.0

    display_name = (user_name or report.user_name or brand_title).strip() or brand_title
    house_system_label = {
        "P": "Placidus",
        "W": "Whole Sign",
        "E": "Equal",
        "K": "Koch",
    }.get((report.snapshot.house_system or "").upper(), report.snapshot.house_system or "N/A")
    coords = report.birth.coordinates
    coords_text = (
        f"{coords.latitude:.4f}, {coords.longitude:.4f}"
        if coords is not None
        else "N/A"
    )
    generated_dt = datetime.now().astimezone()
    generation_text = generated_dt.strftime("%a, %d %b %Y %H:%M %Z")
    metadata_lines = [
        f"Name: {display_name}",
        f"Birth: {report.birth.date.isoformat()} {report.birth.time or '12:00'}",
        f"Coords: {coords_text}",
        f"TZ: {report.birth.timezone or 'N/A'}",
        f"House: {house_system_label}",
        f"Zodiac: {(report.snapshot.zodiac_system or 'N/A').title()}",
        f"Generated: {generation_text}",
    ]

    metadata_title_y = planet_card_y + 22.0
    metadata_first_line_y = metadata_title_y + 20.0
    metadata_line_h = 15.0
    metadata_last_line_y = metadata_first_line_y + ((len(metadata_lines) - 1) * metadata_line_h)
    metadata_block_h = (metadata_last_line_y - planet_card_y) + 20.0
    planet_header_y = planet_card_y + metadata_block_h + 12.0
    profile_line_count = 5
    planet_card_h = (
        metadata_block_h
        + 62.0
        + (len(focus_positions) * planet_row_h)
        + (profile_line_count * profile_row_h)
        + 18.0
    )

    legend_card_y = planet_card_y + planet_card_h + section_gap
    aspect_section_h = 52.0 + (len(aspect_visible_rows) * 22.0)
    signs_section_h = 44.0 + (sign_rows * sign_row_h)
    legend_divider_gap = 14.0
    legend_card_h = 18.0 + aspect_section_h + legend_divider_gap + signs_section_h + 16.0
    wheel_bottom = cy + ring_outer
    right_column_bottom = legend_card_y + legend_card_h
    content_bottom = max(
        wheel_bottom + (width * 0.05),
        right_column_bottom + (width * 0.04),
    )
    height = int(max(width * 1.06, content_bottom))

    planet_rows_svg: list[str] = []
    planet_rows_svg.append(
        f'<text x="{planet_card_x + 16:.2f}" y="{metadata_title_y:.2f}" font-size="17" font-family="{TEXT_FONT_STACK}" '
        f'fill="{accent_color}" font-weight="700">Profile Context</text>'
    )
    for idx, line in enumerate(metadata_lines):
        y = metadata_first_line_y + (idx * metadata_line_h)
        planet_rows_svg.append(
            f'<text x="{planet_card_x + 16:.2f}" y="{y:.2f}" font-size="11.6" font-family="{TEXT_FONT_STACK}" fill="#c9d8ef">{line}</text>'
        )
    planet_rows_svg.append(
        f'<text x="{planet_card_x + 16:.2f}" y="{planet_header_y:.2f}" font-size="17" font-family="{TEXT_FONT_STACK}" '
        f'fill="{accent_color}" font-weight="700">Planets &amp; Symbols</text>'
    )
    planet_rows_svg.append(
        f'<text x="{planet_card_x + 16:.2f}" y="{planet_header_y + 22:.2f}" font-size="11.5" font-family="{TEXT_FONT_STACK}" fill="#8ca0c2">'
        "Symbol   Planet      Sign    House   Retro</text>"
    )
    for idx, position in enumerate(focus_positions):
        y = planet_header_y + 42 + (idx * planet_row_h)
        symbol = _symbol(PLANET_SYMBOL_CODEPOINT.get(position.name), position.name[:2].upper())
        sign_symbol = _symbol(ZODIAC_SYMBOL_CODEPOINT.get(position.sign), position.sign[:2])
        retro = "R" if position.retrograde else "-"
        planet_rows_svg.append(
            f'<text x="{planet_card_x + 18:.2f}" y="{y:.2f}" font-size="15" font-family="{SYMBOL_FONT_STACK}" fill="{PLANET_STYLE.get(position.name)}">{symbol}</text>'
            f'<text x="{planet_card_x + 44:.2f}" y="{y:.2f}" font-size="13" font-family="{TEXT_FONT_STACK}" fill="#d7e2f4">{position.name[:8].ljust(8)}</text>'
            f'<text x="{planet_card_x + 130:.2f}" y="{y:.2f}" font-size="14" font-family="{SYMBOL_FONT_STACK}" fill="#d7e2f4">{sign_symbol}</text>'
            f'<text x="{planet_card_x + 154:.2f}" y="{y:.2f}" font-size="12.5" font-family="{TEXT_FONT_STACK}" fill="#d7e2f4">{position.sign[:3]}</text>'
            f'<text x="{planet_card_x + 212:.2f}" y="{y:.2f}" font-size="12.5" font-family="{TEXT_FONT_STACK}" fill="#d7e2f4">{position.house or "-"}</text>'
            f'<text x="{planet_card_x + 238:.2f}" y="{y:.2f}" font-size="12.5" font-family="{TEXT_FONT_STACK}" fill="#d7e2f4">{retro}</text>'
        )

    profile_start_y = planet_header_y + 44 + (len(focus_positions) * planet_row_h) + 8
    asc_text = "-"
    if asc:
        asc_degree = _degree_in_sign(asc["longitude"])
        asc_text = f"{asc['sign']}" + (f" ({asc_degree:.2f}°)" if asc_degree is not None else "")
    mc_text = "-"
    if mc:
        mc_degree = _degree_in_sign(mc["longitude"])
        mc_text = f"{mc['sign']}" + (f" ({mc_degree:.2f}°)" if mc_degree is not None else "")
    profile_lines = [
        ("Profile", accent_color, 13.5, True),
        (f"Polarity: {sign_polarity.title()}", "#d7e2f4", 12.2, False),
        (
            f"Elem %  F {element_pct['fire']:.1f}  E {element_pct['earth']:.1f}  A {element_pct['air']:.1f}  W {element_pct['water']:.1f}",
            "#d7e2f4",
            11.4,
            False,
        ),
        (f"ASC: {asc_text}", "#9be7ff", 12.0, False),
        (f"MC:  {mc_text}", "#ffd586", 12.0, False),
    ]
    for idx, (line, color, font_size, bold) in enumerate(profile_lines):
        y = profile_start_y + (idx * profile_row_h)
        weight = ' font-weight="700"' if bold else ""
        planet_rows_svg.append(
            f'<text x="{planet_card_x + 16:.2f}" y="{y:.2f}" font-size="{font_size}" font-family="{TEXT_FONT_STACK}" '
            f'fill="{color}"{weight}>{line}</text>'
        )

    aspect_rows_svg: list[str] = []
    aspect_section_top = legend_card_y + 18.0
    aspect_title_y = aspect_section_top + 14.0
    aspect_subhead_y = aspect_title_y + 22.0
    aspect_rows_start_y = aspect_subhead_y + 22.0
    aspect_rows_svg.append(
        f'<text x="{legend_card_x + 16:.2f}" y="{aspect_title_y:.2f}" font-size="17" font-family="{TEXT_FONT_STACK}" '
        f'fill="{accent_color}" font-weight="700">Aspects &amp; Symbols</text>'
    )
    aspect_rows_svg.append(
        f'<text x="{legend_card_x + 16:.2f}" y="{aspect_subhead_y:.2f}" font-size="11.5" font-family="{TEXT_FONT_STACK}" fill="#8ca0c2">'
        "Sy   Pair                           Orb</text>"
    )
    for idx, row in enumerate(aspect_visible_rows):
        y = aspect_rows_start_y + (idx * 22.0)
        symbol = ASPECT_SYMBOL_TEXT.get(row["aspect"], "*")
        pair = f"{row['body1'][:3]} {row['aspect'][:4]} {row['body2'][:3]}"
        aspect_rows_svg.append(
            f'<text x="{legend_card_x + 18:.2f}" y="{y:.2f}" font-size="14" font-family="{SYMBOL_FONT_STACK}" fill="{ASPECT_LINE_COLOR.get(row["aspect"], "#d7e2f4")}">{symbol}</text>'
            f'<text x="{legend_card_x + 42:.2f}" y="{y:.2f}" font-size="12.5" font-family="{TEXT_FONT_STACK}" fill="#d7e2f4">{pair}</text>'
            f'<text x="{legend_card_x + legend_card_w - 52:.2f}" y="{y:.2f}" font-size="12.5" font-family="{TEXT_FONT_STACK}" fill="#d7e2f4">{row["orb"]:.2f}</text>'
        )

    signs_grid_svg: list[str] = []
    signs_section_top = aspect_section_top + aspect_section_h + legend_divider_gap
    signs_title_y = signs_section_top + 14.0
    signs_rows_start_y = signs_title_y + 30.0
    divider_y = signs_section_top - (legend_divider_gap * 0.5)
    signs_grid_svg.append(
        f'<line x1="{legend_card_x + 14:.2f}" y1="{divider_y:.2f}" x2="{legend_card_x + legend_card_w - 14:.2f}" y2="{divider_y:.2f}" stroke="{palette["divider"]}" stroke-width="1.1" opacity="0.9" />'
    )
    signs_grid_svg.append(
        f'<text x="{legend_card_x + 16:.2f}" y="{signs_title_y:.2f}" font-size="17" font-family="{TEXT_FONT_STACK}" '
        f'fill="{accent_color}" font-weight="700">Signs &amp; Symbols</text>'
    )
    cell_w = (legend_card_w - 30.0) / sign_columns
    for idx, sign in enumerate(ZODIAC_SIGNS):
        row_idx = idx // sign_columns
        col_idx = idx % sign_columns
        x = legend_card_x + 16 + (col_idx * cell_w)
        y = signs_rows_start_y + (row_idx * sign_row_h)
        symbol = _symbol(ZODIAC_SYMBOL_CODEPOINT.get(sign), sign[:2])
        signs_grid_svg.append(
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="16" font-family="{SYMBOL_FONT_STACK}" fill="#e2e8f0">{symbol}</text>'
            f'<text x="{(x + 22):.2f}" y="{y:.2f}" font-size="12.5" font-family="{TEXT_FONT_STACK}" fill="#d7e2f4">{sign.title()}</text>'
        )

    background = (
        '<defs>'
        '<radialGradient id="wheelBg" cx="30%" cy="18%" r="88%">'
        f'<stop offset="0%" stop-color="{palette["bg_0"]}" />'
        f'<stop offset="55%" stop-color="{palette["bg_1"]}" />'
        f'<stop offset="100%" stop-color="{palette["bg_2"]}" />'
        "</radialGradient>"
        "</defs>"
    )

    wheel_title = f"Natal Wheel • {report.sign} • {report.birth.date.isoformat()}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  {background}
  <rect x="0" y="0" width="{width}" height="{height}" fill="url(#wheelBg)" />

  <g id="main-wheel">
    <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ring_outer:.2f}" fill="none" stroke="{accent_color}" stroke-width="3.1" />
    <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ring_inner:.2f}" fill="none" stroke="{palette["ring_inner"]}" stroke-width="2.3" />
    <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ring_inner * 0.63:.2f}" fill="{palette["center_fill"]}" stroke="{palette["center_stroke"]}" stroke-width="1.0" opacity="0.95" />

    {''.join(sign_lines)}
    {''.join(house_lines)}
    {''.join(sign_labels)}
    {''.join(house_labels)}
    {''.join(aspect_lines)}
    {''.join(points)}
    {''.join(point_labels)}
    {''.join(angle_marks)}

    <text x="{width * 0.06:.2f}" y="{(top_margin + 18):.2f}" font-size="44" font-family="{TEXT_FONT_STACK}" fill="{accent_color}" font-weight="700">{display_name}</text>
    <text x="{width * 0.06:.2f}" y="{(top_margin + 44):.2f}" font-size="16" font-family="{TEXT_FONT_STACK}" fill="{palette["subtitle"]}">{wheel_title}</text>
  </g>

  <g id="legends">
    <rect x="{planet_card_x:.2f}" y="{planet_card_y:.2f}" width="{planet_card_w:.2f}" height="{planet_card_h:.2f}" rx="14" fill="{palette["panel_fill"]}" opacity="{palette["panel_opacity"]:.2f}" />
    <rect x="{legend_card_x:.2f}" y="{legend_card_y:.2f}" width="{legend_card_w:.2f}" height="{legend_card_h:.2f}" rx="14" fill="{palette["panel_fill"]}" opacity="{palette["panel_opacity"]:.2f}" />
    {''.join(planet_rows_svg)}
    {''.join(aspect_rows_svg)}
    {''.join(signs_grid_svg)}
  </g>
</svg>
"""


def _extract_svg_attr(svg: str, attr: str) -> Optional[str]:
    match = re.search(rf'{attr}="([^"]+)"', svg)
    if not match:
        return None
    return match.group(1)


def _extract_svg_defs(svg: str) -> str:
    match = re.search(r"(<defs>.*?</defs>)", svg, flags=re.DOTALL)
    return match.group(1) if match else ""


def _extract_svg_group(svg: str, group_id: str) -> str:
    pattern = rf'<g id="{re.escape(group_id)}">(.*?)</g>'
    match = re.search(pattern, svg, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _compose_svg(
    *,
    width: str,
    height: str,
    view_box: str,
    defs_block: str,
    body: str,
    include_background: bool,
) -> str:
    bg = ""
    if include_background:
        bg = f'<rect x="0" y="0" width="{width}" height="{height}" fill="url(#wheelBg)" />'
    defs = f"\n  {defs_block}" if defs_block else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{view_box}">'
        f"{defs}\n  {bg}\n  {body}\n</svg>\n"
    )


def build_natal_wheel_svg_split(
    report: NatalBirthchartResponse,
    *,
    accent_color: str = ACCENT_DEFAULT,
    size: int = 1080,
    brand_title: str = "OPASTRO",
    user_name: Optional[str] = None,
    theme: str = "night",
) -> dict[str, Any]:
    full_svg = build_natal_wheel_svg(
        report,
        accent_color=accent_color,
        size=size,
        brand_title=brand_title,
        user_name=user_name,
        theme=theme,
    )
    width = _extract_svg_attr(full_svg, "width") or str(max(760, int(size)))
    height = _extract_svg_attr(full_svg, "height") or str(int(max(760, int(size)) * 1.06))
    view_box = _extract_svg_attr(full_svg, "viewBox") or f"0 0 {width} {height}"
    defs_block = _extract_svg_defs(full_svg)
    main_group = _extract_svg_group(full_svg, "main-wheel")
    legends_group = _extract_svg_group(full_svg, "legends")

    main_svg = _compose_svg(
        width=width,
        height=height,
        view_box=view_box,
        defs_block=defs_block,
        body=f'<g id="main-wheel">{main_group}</g>' if main_group else "",
        include_background=True,
    )
    legends_svg = _compose_svg(
        width=width,
        height=height,
        view_box=view_box,
        defs_block=defs_block,
        body=f'<g id="legends">{legends_group}</g>' if legends_group else "",
        include_background=False,
    )
    return {
        "full_svg": full_svg,
        "main_wheel_svg": main_svg,
        "legends_svg": legends_svg,
        "width": int(float(width)),
        "height": int(float(height)),
        "theme": _resolve_wheel_theme(theme),
    }


def build_natal_wheel_png(
    report: NatalBirthchartResponse,
    *,
    accent_color: str = ACCENT_DEFAULT,
    size: int = 1080,
    brand_title: str = "OPASTRO",
    user_name: Optional[str] = None,
    theme: str = "night",
) -> bytes:
    try:
        import cairosvg
    except Exception as exc:
        raise RuntimeError("PNG rendering requires cairosvg. Install with `pip install cairosvg`.") from exc
    svg = build_natal_wheel_svg(
        report,
        accent_color=accent_color,
        size=size,
        brand_title=brand_title,
        user_name=user_name,
        theme=theme,
    )
    width = max(760, int(size))
    height = int(width * 1.2)
    match = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg)
    if match:
        vb_width = float(match.group(1))
        vb_height = float(match.group(2))
        if vb_width > 0:
            height = max(1, int((vb_height / vb_width) * width))
    return cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=width,
        output_height=height,
        unsafe=True,
    )


def build_house_overlay_map(report: NatalBirthchartResponse) -> dict[str, Any]:
    cusps = report.snapshot.house_cusps or []
    house_rows: list[dict[str, Any]] = []
    positions = [pos for pos in report.snapshot.positions if pos.name in PLANET_STYLE]

    if len(cusps) == 12:
        signs = [ZODIAC_SIGNS[int((cusp % 360.0) // 30)] for cusp in cusps]
        for idx, cusp in enumerate(cusps):
            house_no = idx + 1
            next_cusp = cusps[(idx + 1) % 12]
            start = float(cusp % 360.0)
            end = float(next_cusp % 360.0)
            arc = (end - start) % 360.0
            occupants = []
            for position in positions:
                planet_house = position.house or _house_from_cusps(position.longitude, cusps)
                if planet_house == house_no:
                    occupants.append(position.name)
            house_rows.append(
                {
                    "house": house_no,
                    "cusp_longitude": round(float(cusp), 6),
                    "cusp_sign": signs[idx],
                    "start_longitude": round(start, 6),
                    "end_longitude": round(end, 6),
                    "midpoint_longitude": round((start + (arc / 2.0)) % 360.0, 6),
                    "arc_degrees": round(arc, 6),
                    "wraps_aries": end < start,
                    "occupants": sorted(occupants),
                }
            )
    else:
        for idx in range(12):
            sign = ZODIAC_SIGNS[(ZODIAC_SIGNS.index(report.sign) + idx) % 12]
            house_rows.append(
                {
                    "house": idx + 1,
                    "cusp_longitude": None,
                    "cusp_sign": sign,
                    "start_longitude": None,
                    "end_longitude": None,
                    "midpoint_longitude": None,
                    "arc_degrees": 30.0,
                    "wraps_aries": False,
                    "occupants": sorted(pos.name for pos in positions if pos.sign == sign),
                }
            )

    premium = report.premium_insights
    vectors = []
    if premium:
        vectors = [
            {
                "area": item.area,
                "score": item.score,
                "emphasis": item.emphasis,
                "drivers": item.drivers,
            }
            for item in premium.life_area_vectors
        ]

    element_pct = _element_percentages(report)
    angle_info = _angle_data(report)

    return {
        "report_type": report.report_type.value,
        "user_name": report.user_name,
        "sign": report.sign,
        "birth_date": report.birth.date.isoformat(),
        "sign_polarity": _sign_polarity(report.sign),
        "element_percentages": element_pct,
        "ascendant": angle_info["ascendant"],
        "midheaven": angle_info["midheaven"],
        "house_system": report.snapshot.house_system,
        "rising_sign": report.snapshot.rising_sign,
        "houses": house_rows,
        "life_area_vectors": vectors,
    }


def build_natal_report_pdf(
    report: NatalBirthchartResponse,
    *,
    accent_color: str = ACCENT_DEFAULT,
    brand_title: str = "OPASTRO",
    user_name: Optional[str] = None,
    wheel_theme: str = "night",
    brand_url: str = "https://opastro.com",
    premium_url: str = "https://numerologyapi.com",
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise RuntimeError("PDF rendering requires reportlab. Install with `pip install reportlab`.") from exc

    def _color_from_hex(value: str):
        clean = value.strip().lstrip("#")
        if len(clean) != 6:
            clean = "3ddd77"
        return colors.HexColor(f"#{clean}")

    stream = BytesIO()
    doc = SimpleDocTemplate(
        stream,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"{brand_title} Natal Birthchart Report",
    )
    styles = getSampleStyleSheet()
    accent = _color_from_hex(accent_color)
    pdf_theme = _resolve_wheel_theme(wheel_theme)
    pdf_palette = {
        "night": {
            "subtitle": "#0f3b2a",
            "body": "#10271e",
            "small": "#3f6655",
            "panel_bg": "#f0f7f3",
            "grid": "#aac9b9",
            "row_a": "#f7fcf9",
            "row_b": "#ffffff",
            "header_bg": "#d8ebdf",
        },
        "day": {
            "subtitle": "#14633f",
            "body": "#0e3d28",
            "small": "#3d6d57",
            "panel_bg": "#f4fbf6",
            "grid": "#b8d8c6",
            "row_a": "#fbfffc",
            "row_b": "#f2fbf5",
            "header_bg": "#def4e6",
        },
    }[pdf_theme]

    title_style = styles["Heading1"].clone("title")
    title_style.textColor = accent
    subtitle_style = styles["Heading3"].clone("subtitle")
    subtitle_style.textColor = colors.HexColor(pdf_palette["subtitle"])
    body_style = styles["BodyText"].clone("body")
    body_style.leading = 14
    body_style.spaceAfter = 6
    body_style.textColor = colors.HexColor(pdf_palette["body"])
    small_style = styles["BodyText"].clone("small")
    small_style.fontSize = 9.5
    small_style.textColor = colors.HexColor(pdf_palette["small"])

    story: list[Any] = [
        Paragraph(f"{(user_name or report.user_name or brand_title).strip() or brand_title} Natal Birthchart Report", title_style),
        Paragraph(
            f"Birth Date: {report.birth.date.isoformat()} • Sun Sign: {report.sign} • "
            f"Rising Sign: {report.snapshot.rising_sign or 'N/A'}",
            small_style,
        ),
        Paragraph(f"{brand_url} • Premium narrative upgrade: {premium_url}", small_style),
        Spacer(1, 8),
    ]

    try:
        wheel_png = build_natal_wheel_png(
            report,
            accent_color=accent_color,
            brand_title=brand_title,
            user_name=user_name,
            theme=wheel_theme,
            size=760,
        )
        image = Image(BytesIO(wheel_png), width=88 * mm, height=127 * mm)
        image.hAlign = "CENTER"
        story.append(image)
        story.append(Spacer(1, 8))
    except Exception:
        # Keep PDF generation resilient even if PNG conversion fails in target env.
        pass

    element_pct = _element_percentages(report)
    angle_info = _angle_data(report)
    asc = angle_info["ascendant"]
    mc = angle_info["midheaven"]
    asc_text = "-"
    if asc:
        asc_deg = _degree_in_sign(asc["longitude"])
        asc_text = f"{asc['sign']}" + (f" ({asc_deg:.2f}°)" if asc_deg is not None else "")
    mc_text = "-"
    if mc:
        mc_deg = _degree_in_sign(mc["longitude"])
        mc_text = f"{mc['sign']}" + (f" ({mc_deg:.2f}°)" if mc_deg is not None else "")

    story.append(Paragraph("Sign Profile", subtitle_style))
    profile_rows = [
        ["Polarity", _sign_polarity(report.sign).title(), "ASC", asc_text],
        [
            "Fire / Earth",
            f"{element_pct['fire']:.1f}% / {element_pct['earth']:.1f}%",
            "MC",
            mc_text,
        ],
        ["Air / Water", f"{element_pct['air']:.1f}% / {element_pct['water']:.1f}%", "Sign", report.sign],
    ]
    profile_table = Table(profile_rows, colWidths=[30 * mm, 52 * mm, 22 * mm, 64 * mm])
    profile_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(pdf_palette["panel_bg"])),
                ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor(pdf_palette["grid"])),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(pdf_palette["grid"])),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(pdf_palette["body"])),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor(pdf_palette["panel_bg"]), colors.HexColor(pdf_palette["row_b"])]),
            ]
        )
    )
    story.append(profile_table)
    story.append(Spacer(1, 8))

    planet_rows = [["Sy", "Planet", "Sign", "House", "R"]]
    for position in sorted([p for p in report.snapshot.positions if p.name in PLANET_STYLE], key=lambda x: x.name):
        planet_symbol = PLANET_TOKEN.get(position.name, position.name[:2].title())
        planet_rows.append(
            [
                planet_symbol,
                position.name,
                position.sign,
                str(position.house or "-"),
                "R" if position.retrograde else "-",
            ]
        )
    planet_table = Table(planet_rows, colWidths=[12 * mm, 40 * mm, 46 * mm, 20 * mm, 16 * mm], repeatRows=1)
    planet_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), accent),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 0), (4, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(pdf_palette["grid"])),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(pdf_palette["row_a"]), colors.HexColor(pdf_palette["row_b"])]),
            ]
            )
        )
    story.append(Paragraph("Planetary Snapshot", subtitle_style))
    story.append(planet_table)
    story.append(Spacer(1, 10))

    aspect_rows = _major_aspect_rows(report, limit=8)
    if aspect_rows:
        story.append(Paragraph("Top Aspect Matrix", subtitle_style))
        aspect_table_rows = [["Sy", "Aspect", "Bodies", "Orb"]]
        for row in aspect_rows:
            symbol = ASPECT_TOKEN.get(row["aspect"], row["aspect"][:3].title())
            aspect_table_rows.append(
                [
                    symbol,
                    row["aspect"].replace("-", " ").title(),
                    f"{row['body1']} / {row['body2']}",
                    f"{row['orb']:.2f}",
                ]
            )
        aspect_table = Table(aspect_table_rows, colWidths=[12 * mm, 36 * mm, 82 * mm, 18 * mm], repeatRows=1)
        aspect_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(pdf_palette["header_bg"])),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (0, -1), "CENTER"),
                    ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(pdf_palette["grid"])),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(pdf_palette["row_b"]), colors.HexColor(pdf_palette["row_a"])]),
                ]
            )
        )
        story.append(aspect_table)
        story.append(Spacer(1, 8))

    premium = report.premium_insights
    if premium:
        dominant = premium.dominant_signature
        story.append(Paragraph("Dominant Signature", subtitle_style))
        story.append(
            Paragraph(
                f"Dominant element: <b>{dominant.dominant_element.title()}</b> • "
                f"Dominant modality: <b>{dominant.dominant_modality.title()}</b> • "
                f"Top planets: <b>{', '.join(dominant.top_planets[:3]) or 'N/A'}</b>",
                body_style,
            )
        )

        if premium.life_area_vectors:
            story.append(Paragraph("Life Area Vectors", subtitle_style))
            for vector in premium.life_area_vectors[:5]:
                story.append(
                    Paragraph(
                        f"{vector.area.replace('_', ' ').title()}: "
                        f"<b>{vector.score:.1f}</b> ({vector.emphasis}) — drivers: {', '.join(vector.drivers)}",
                        body_style,
                    )
                )

        if premium.relationship_module:
            module = premium.relationship_module
            story.append(Paragraph("Relationship Module", subtitle_style))
            story.append(Paragraph(f"Score: <b>{module.score:.1f}</b>", body_style))
            for line in module.highlights[:3]:
                story.append(Paragraph(f"• {line}", body_style))
            for line in module.cautions[:2]:
                story.append(Paragraph(f"Caution: {line}", small_style))
            for line in module.actions[:2]:
                story.append(Paragraph(f"Action: {line}", small_style))

        if premium.career_module:
            module = premium.career_module
            story.append(Paragraph("Career Module", subtitle_style))
            story.append(Paragraph(f"Score: <b>{module.score:.1f}</b>", body_style))
            for line in module.highlights[:3]:
                story.append(Paragraph(f"• {line}", body_style))
            for line in module.cautions[:2]:
                story.append(Paragraph(f"Caution: {line}", small_style))
            for line in module.actions[:2]:
                story.append(Paragraph(f"Action: {line}", small_style))

        if premium.timing_overlay and premium.timing_overlay.activations:
            story.append(Paragraph("Timing Overlay (next windows)", subtitle_style))
            timing_rows = [["Window", "Transit", "Intensity"]]
            for activation in premium.timing_overlay.activations[:6]:
                timing_rows.append(
                    [
                        f"{activation.start_date.isoformat()} to {activation.end_date.isoformat()}",
                        f"{activation.transit_planet} {activation.aspect} {activation.natal_planet}",
                        f"{activation.intensity:.2f}",
                    ]
                )
            timing_table = Table(timing_rows, colWidths=[66 * mm, 78 * mm, 18 * mm], repeatRows=1)
            timing_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(pdf_palette["header_bg"])),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(pdf_palette["grid"])),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(pdf_palette["row_b"]), colors.HexColor(pdf_palette["row_a"])]),
                    ]
                )
            )
            story.append(timing_table)

    overlay = build_house_overlay_map(report)
    story.append(Spacer(1, 8))
    story.append(Paragraph("House Overlay Highlights", subtitle_style))
    houses = overlay.get("houses", [])
    ranked = sorted(houses, key=lambda item: (-len(item.get("occupants", [])), item.get("house", 99)))
    house_rows = [["House", "Sign", "Arc", "Occupants"]]
    for item in ranked[:8]:
        house_rows.append(
            [
                f"H{item.get('house')}",
                str(item.get("cusp_sign") or "-"),
                f"{item.get('arc_degrees', 0):.1f}°",
                ", ".join(item.get("occupants", [])[:4]) or "-",
            ]
        )
    house_table = Table(house_rows, colWidths=[18 * mm, 30 * mm, 24 * mm, 90 * mm], repeatRows=1)
    house_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(pdf_palette["header_bg"])),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor(pdf_palette["grid"])),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor(pdf_palette["row_b"]), colors.HexColor(pdf_palette["row_a"])]),
            ]
        )
    )
    story.append(house_table)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            f"Overlay mode: {overlay.get('house_system') or 'estimated'} • Rising: {overlay.get('rising_sign') or 'N/A'}",
            small_style,
        )
    )

    def _paint_brand(canvas, doc_obj) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(accent)
        canvas.drawString(14 * mm, 7 * mm, f"{brand_title} • {brand_url}")
        canvas.setFillColor(colors.HexColor(pdf_palette["small"]))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(200 * mm, 7 * mm, f"Generated: {date.today().isoformat()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_paint_brand, onLaterPages=_paint_brand)
    return stream.getvalue()
