"""Planetary Scene Renderer — generates premium 2D / faux-3D SVG sky maps.

Consumes a ``ChartSnapshot`` produced by ``EphemerisEngine`` and projects the
planetary longitudes onto a stylised heliocentric (or geocentric-abstract) map
with orbit ellipses, glowing Sun, labelled bodies, optional aspect connectors,
and a perspective grid.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import random
import subprocess
import tempfile
from typing import Any

from .models import BodyPosition, ChartSnapshot


# ---------------------------------------------------------------------------
# Theme colour palettes
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#02040c",
        "grid": "#0e1e2e",
        "orbit": "#1a3050",
        "orbit_inner": "#1f4466",
        "label": "#88bbdd",
        "dot": "#ffffff",
        "aspect": "#224466",
        "star_dim": "#334455",
        "star_bright": "#ffffff",
        "sun_core": "#ffffff",
        "sun_mid": "#ffcc88",
        "sun_outer": "#ff8800",
        "au_label": "#2299aa",
        "glow": "#3388bb",
        "milky_way": "#28476f",
        "retrograde": "#d889a7",
    },
    "neon-blue": {
        "bg": "#050510",
        "grid": "#001133",
        "orbit": "#003366",
        "orbit_inner": "#005599",
        "label": "#00eeff",
        "dot": "#ffffff",
        "aspect": "#003355",
        "star_dim": "#112244",
        "star_bright": "#88ccff",
        "sun_core": "#ffffff",
        "sun_mid": "#88ddff",
        "sun_outer": "#0066cc",
        "au_label": "#00cccc",
        "glow": "#0099ff",
        "milky_way": "#164a7a",
        "retrograde": "#ff77bb",
    },
    "observatory": {
        "bg": "#0a0a14",
        "grid": "#181828",
        "orbit": "#2a2a44",
        "orbit_inner": "#3a3a5a",
        "label": "#9999cc",
        "dot": "#ddddff",
        "aspect": "#2a2a44",
        "star_dim": "#222233",
        "star_bright": "#ccccee",
        "sun_core": "#ffffee",
        "sun_mid": "#eedd99",
        "sun_outer": "#cc9944",
        "au_label": "#7777aa",
        "glow": "#6666aa",
        "milky_way": "#45456e",
        "retrograde": "#cc88aa",
    },
    "gold-premium": {
        "bg": "#0a0806",
        "grid": "#1a1408",
        "orbit": "#332a11",
        "orbit_inner": "#4d3f1a",
        "label": "#d4aa55",
        "dot": "#fff8e0",
        "aspect": "#33280e",
        "star_dim": "#1a1408",
        "star_bright": "#ffe8a0",
        "sun_core": "#ffffff",
        "sun_mid": "#ffdd88",
        "sun_outer": "#cc8800",
        "au_label": "#aa8833",
        "glow": "#ddaa44",
        "milky_way": "#655025",
        "retrograde": "#d47766",
    },
}

# Fallback radii for snapshots created by older callers without distance data.
ORBIT_RADII: dict[str, float] = {
    "Moon": 72,
    "Earth": 245,
    "Mercury": 70,
    "Venus": 115,
    "Mars": 200,
    "Jupiter": 280,
    "Saturn": 360,
    "Uranus": 430,
    "Neptune": 500,
    "Pluto": 560,
    # minor / dwarf
    "Chiron": 320,
    "Ceres": 240,
    "Eris": 620,
    "Pallas": 245,
    "Juno": 250,
    "Vesta": 235,
    "Lilith": 155,
    "North Node": 160,
    "South Node": 165,
}

DISTANCE_MIN_AU = 0.002
DISTANCE_MAX_AU = 50.0
SCENE_RADIUS_MIN = 76.0
SCENE_RADIUS_MAX = 548.0
ASTEROID_NAMES = {"Chiron", "Ceres", "Eris", "Pallas", "Juno", "Vesta"}
NODE_NAMES = {"North Node", "South Node", "Lilith"}
BODY_MARKER_RADIUS = {
    "Moon": 5.0,
    "Earth": 8.5,
    "Mercury": 5.0,
    "Venus": 7.0,
    "Mars": 7.0,
    "Jupiter": 13.0,
    "Saturn": 14.0,
    "Uranus": 10.0,
    "Neptune": 10.0,
    "Pluto": 6.0,
}


def _load_constellation_catalog() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "data" / "constellations.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"stars": [], "segments": [], "labels": []}


CONSTELLATION_CATALOG = _load_constellation_catalog()

MAJOR_PLANET_NAMES = {
    "Earth",
    "Mercury",
    "Venus",
    "Mars",
    "Jupiter",
    "Saturn",
    "Uranus",
    "Neptune",
    "Pluto",
}

ZODIAC_SIGNS = (
    "ARIES",
    "TAURUS",
    "GEMINI",
    "CANCER",
    "LEO",
    "VIRGO",
    "LIBRA",
    "SCORPIO",
    "SAGITTARIUS",
    "CAPRICORN",
    "AQUARIUS",
    "PISCES",
)


def _longitude_to_sign(longitude: float) -> tuple[str, float]:
    normalized = longitude % 360.0
    index = int(normalized // 30.0)
    return ZODIAC_SIGNS[index], normalized % 30.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _star_field(
    width: int, height: int, palette: dict[str, str], seed: int = 42
) -> str:
    """Generate a deterministic atmospheric star field with restrained twinkle."""
    rng = random.Random(seed)
    parts: list[str] = [
        '<g id="stars" aria-label="Animated star field" data-animated="true">'
    ]

    # Broad, low-opacity bands keep the dark sky from reading as a flat fill.
    parts.append(f'''
    <rect width="{width}" height="{height}" fill="url(#nebula1)" />
    <rect width="{width}" height="{height}" fill="url(#nebula2)" />
    <path d="M -90 680 C 190 470, 420 550, 675 365 S 1040 185, 1290 120"
          fill="none" stroke="{palette["milky_way"]}" stroke-width="150"
          stroke-linecap="round" opacity="0.10" filter="url(#nebulaBlur)"/>
    <path d="M -90 680 C 190 470, 420 550, 675 365 S 1040 185, 1290 120"
          fill="none" stroke="{palette["milky_way"]}" stroke-width="50"
          stroke-linecap="round" opacity="0.06"/>
    ''')

    for index in range(420):
        x = rng.uniform(8, width - 8)
        y = rng.uniform(8, height - 8)
        r = rng.choice([0.45, 0.6, 0.8, 1.0, 1.15, 1.4, 1.8])
        opacity = rng.uniform(0.18, 0.82)
        colour = palette["star_bright"] if rng.random() > 0.48 else palette["star_dim"]
        if r >= 1.4:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r + 1.1:.1f}" fill="{colour}" '
                f'opacity="{opacity * 0.18:.2f}" filter="url(#bloom)"/>'
            )
        star = (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{colour}" '
            f'opacity="{opacity:.2f}" data-star-index="{index}"/>'
        )
        # Phases and periods are seeded, so a repeated export is stable while
        # still producing independent, slow natural-looking brightness changes.
        if colour == palette["star_bright"] and rng.random() > 0.68:
            duration = rng.uniform(3.8, 11.5)
            phase = -rng.uniform(0.0, duration)
            low = max(0.08, opacity * rng.uniform(0.45, 0.72))
            high = min(1.0, opacity * rng.uniform(1.05, 1.35))
            star = star.replace(
                "/>",
                f'><animate attributeName="opacity" values="{low:.2f};{high:.2f};{low:.2f}" '
                f'keyTimes="0;0.53;1" dur="{duration:.2f}s" begin="{phase:.2f}s" '
                'repeatCount="indefinite"/></circle>',
            )
        parts.append(star)
    parts.append("</g>")
    return "\n".join(parts)


def _svg_defs(palette: dict[str, str]) -> str:
    """Reusable SVG definitions: gradients, glow filters."""
    return f"""<defs>
  <linearGradient id="skyGradient" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{palette["bg"]}"/>
    <stop offset="55%" stop-color="#050b18"/>
    <stop offset="100%" stop-color="#010207"/>
  </linearGradient>
  <radialGradient id="nebula1" cx="30%" cy="40%" r="58%">
    <stop offset="0%" stop-color="{palette["glow"]}" stop-opacity="0.13"/>
    <stop offset="55%" stop-color="{palette["glow"]}" stop-opacity="0.035"/>
    <stop offset="100%" stop-color="{palette["bg"]}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="nebula2" cx="74%" cy="63%" r="68%">
    <stop offset="0%" stop-color="{palette["label"]}" stop-opacity="0.08"/>
    <stop offset="100%" stop-color="{palette["bg"]}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="sunGlow" cx="50%" cy="50%" r="50%">
    <stop offset="0%"   stop-color="{palette["sun_core"]}" stop-opacity="1"/>
    <stop offset="15%"  stop-color="{palette["sun_mid"]}"  stop-opacity="0.85"/>
    <stop offset="50%"  stop-color="{palette["sun_outer"]}" stop-opacity="0.25"/>
    <stop offset="100%" stop-color="{palette["sun_outer"]}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="dotGlow" cx="50%" cy="50%" r="50%">
    <stop offset="0%"   stop-color="{palette["glow"]}" stop-opacity="0.6"/>
    <stop offset="100%" stop-color="{palette["glow"]}" stop-opacity="0"/>
  </radialGradient>
  <filter id="bloom" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur"/>
    <feMerge>
      <feMergeNode in="blur"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
  <filter id="softBloom" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="2" result="blur"/>
    <feMerge>
      <feMergeNode in="blur"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
  <filter id="nebulaBlur" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur stdDeviation="26"/>
  </filter>
  <marker id="motionArrow" markerWidth="7" markerHeight="7" refX="5.5" refY="3.5"
          orient="auto" markerUnits="userSpaceOnUse">
    <path d="M 0 0 L 7 3.5 L 0 7 z" fill="{palette["label"]}"/>
  </marker>
  <radialGradient id="mercurySurface" cx="35%" cy="30%" r="75%">
    <stop offset="0%" stop-color="#e4e1d8"/>
    <stop offset="60%" stop-color="#8f9298"/>
    <stop offset="100%" stop-color="#3e4752"/>
  </radialGradient>
  <radialGradient id="venusSurface" cx="36%" cy="28%" r="80%">
    <stop offset="0%" stop-color="#f8e3a1"/>
    <stop offset="58%" stop-color="#c9873d"/>
    <stop offset="100%" stop-color="#6e351e"/>
  </radialGradient>
  <radialGradient id="earthSurface" cx="35%" cy="25%" r="78%">
    <stop offset="0%" stop-color="#86d6ff"/>
    <stop offset="62%" stop-color="#2d6caf"/>
    <stop offset="100%" stop-color="#0c2457"/>
  </radialGradient>
  <radialGradient id="marsSurface" cx="30%" cy="28%" r="78%">
    <stop offset="0%" stop-color="#f49a68"/>
    <stop offset="58%" stop-color="#b64a35"/>
    <stop offset="100%" stop-color="#4b1b27"/>
  </radialGradient>
  <radialGradient id="jupiterSurface" cx="32%" cy="22%" r="80%">
    <stop offset="0%" stop-color="#f4dfbb"/>
    <stop offset="55%" stop-color="#c38f67"/>
    <stop offset="100%" stop-color="#654c4a"/>
  </radialGradient>
  <radialGradient id="saturnSurface" cx="32%" cy="22%" r="80%">
    <stop offset="0%" stop-color="#f4dfad"/>
    <stop offset="60%" stop-color="#c29a62"/>
    <stop offset="100%" stop-color="#71553e"/>
  </radialGradient>
  <radialGradient id="iceSurface" cx="32%" cy="24%" r="80%">
    <stop offset="0%" stop-color="#c4f4ff"/>
    <stop offset="62%" stop-color="#5eaccc"/>
    <stop offset="100%" stop-color="#1d4270"/>
  </radialGradient>
  <radialGradient id="plutoSurface" cx="32%" cy="25%" r="80%">
    <stop offset="0%" stop-color="#e2c9b9"/>
    <stop offset="60%" stop-color="#9a746e"/>
    <stop offset="100%" stop-color="#493e55"/>
  </radialGradient>
  <radialGradient id="moonSurface" cx="34%" cy="28%" r="80%">
    <stop offset="0%" stop-color="#f5f1df"/>
    <stop offset="58%" stop-color="#aaa9aa"/>
    <stop offset="100%" stop-color="#4e5663"/>
  </radialGradient>
</defs>"""


def _perspective_grid(
    cx: float,
    cy: float,
    tilt: float,
    palette: dict[str, str],
) -> str:
    """Draw the faux-3D perspective grid (ellipses + radial lines)."""
    parts: list[str] = [
        f'<g id="grid" stroke="{palette["grid"]}" stroke-width="0.6" fill="none" opacity="0.45">'
    ]
    for r in range(80, 900, 80):
        parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * tilt}"/>')
    for angle in range(0, 360, 15):
        rad = math.radians(angle)
        x2 = cx + 900 * math.cos(rad)
        y2 = cy + 900 * math.sin(rad) * tilt
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
    parts.append("</g>")
    return "\n".join(parts)


def _footer_data_table(
    width: float,
    height: float,
    snapshot: ChartSnapshot,
    bodies_to_render: list,
    palette: dict[str, str],
) -> str:
    """Draw a minimalist, beautiful table of planetary positions and aspects at the bottom."""
    parts = []

    body_by_name = {body.name: body for body in bodies_to_render}
    bodies_to_show = list(body_by_name)
    num_bodies = len(bodies_to_show)
    bodies_rows = math.ceil(num_bodies / 6) if num_bodies > 0 else 0

    aspects = sorted(
        (
            a
            for a in snapshot.aspects
            if a.body1 in bodies_to_show and a.body2 in bodies_to_show
        ),
        key=lambda a: a.orb,
    )[:4]
    aspect_rows = math.ceil(len(aspects) / 2)

    max_rows = max(bodies_rows, aspect_rows, 2)
    box_height = max(100, 45 + (max_rows - 1) * 24 + 30)
    table_y = height - box_height - 20

    parts.append(
        f'<rect x="20" y="{table_y}" width="{width - 40}" height="{box_height}" fill="{palette["bg"]}" opacity="0.65" rx="8" />'
    )
    parts.append(
        f'<rect x="20" y="{table_y}" width="{width - 40}" height="{box_height}" fill="none" stroke="{palette["grid"]}" stroke-width="1" rx="8" opacity="0.8" />'
    )

    # Col 1: Planet positions
    parts.append(
        f'<text x="40" y="{table_y + 24}" fill="{palette["label"]}" font-size="10" font-weight="600" letter-spacing="2" opacity="0.9">PLANETARY POSITIONS</text>'
    )

    y_offset = table_y + 45
    x_offset = 40
    col_width = 85

    for i, bname in enumerate(bodies_to_show):
        pos = body_by_name.get(bname)
        if not pos:
            continue

        row = i // 6
        col = i % 6

        px = x_offset + col * col_width
        py = y_offset + row * 24

        deg = int(pos.degree_in_sign)
        rx = " Rx" if pos.retrograde else ""
        text_val = f"{deg}° {pos.sign[:3]}{rx}"

        parts.append(
            f'<text x="{px}" y="{py}" fill="{palette["dot"]}" font-size="10" font-weight="500">{bname.upper()}</text>'
        )
        parts.append(
            f'<text x="{px}" y="{py + 12}" fill="{palette["label"]}" font-size="9" opacity="0.75">{text_val}</text>'
        )

    # Col 2: Aspects
    divider_x = x_offset + 6 * col_width + 5
    parts.append(
        f'<line x1="{divider_x}" y1="{table_y + 15}" x2="{divider_x}" y2="{table_y + box_height - 15}" stroke="{palette["grid"]}" stroke-width="1.5" />'
    )

    aspect_x = divider_x + 25
    parts.append(
        f'<text x="{aspect_x}" y="{table_y + 24}" fill="{palette["label"]}" font-size="10" font-weight="600" letter-spacing="2" opacity="0.9">KEY ASPECTS</text>'
    )

    for i, asp in enumerate(aspects):
        row = i // 2
        col = i % 2

        px = aspect_x + col * 140
        py = y_offset + row * 24

        asp_name = asp.aspect.upper()
        orb = f"{asp.orb:.1f}° orb"

        parts.append(
            f'<text x="{px}" y="{py}" fill="{palette["dot"]}" font-size="10" font-weight="500">{asp.body1[:3]} {asp_name} {asp.body2[:3]}</text>'
        )
        parts.append(
            f'<text x="{px}" y="{py + 12}" fill="{palette["label"]}" font-size="9" opacity="0.75">{orb}</text>'
        )

    return "\n".join(parts)


def _body_radius(position: Any) -> float:
    """Map an ephemeris distance to a readable logarithmic scene radius."""
    distance = position.distance_au
    if (
        position.name in NODE_NAMES
        or distance is None
        or not math.isfinite(distance)
        or distance <= 0
    ):
        return ORBIT_RADII.get(position.name, 300.0)
    clipped = min(max(distance, DISTANCE_MIN_AU), DISTANCE_MAX_AU)
    fraction = math.log(clipped / DISTANCE_MIN_AU) / math.log(
        DISTANCE_MAX_AU / DISTANCE_MIN_AU
    )
    return SCENE_RADIUS_MIN + fraction * (SCENE_RADIUS_MAX - SCENE_RADIUS_MIN)


def _earth_position(snapshot: ChartSnapshot) -> BodyPosition | None:
    """Derive Earth's heliocentric scene position from the geocentric Sun."""
    sun = next(
        (position for position in snapshot.positions if position.name == "Sun"), None
    )
    if sun is None:
        return None
    tropical_longitude = (sun.tropical_longitude + 180.0) % 360.0
    sidereal_longitude = (sun.sidereal_longitude + 180.0) % 360.0
    use_tropical = snapshot.zodiac_system.lower() == "tropical"
    longitude = tropical_longitude if use_tropical else sidereal_longitude
    sign, degree_in_sign = _longitude_to_sign(longitude)
    tropical_sign, _ = _longitude_to_sign(tropical_longitude)
    sidereal_sign, _ = _longitude_to_sign(sidereal_longitude)
    return BodyPosition(
        name="Earth",
        longitude=longitude,
        tropical_longitude=tropical_longitude,
        sidereal_longitude=sidereal_longitude,
        latitude=-sun.latitude,
        speed=sun.speed,
        sign=sign,
        tropical_sign=tropical_sign,
        sidereal_sign=sidereal_sign,
        degree_in_sign=degree_in_sign,
        house=None,
        retrograde=sun.speed < 0,
        ayanamsa_value=sun.ayanamsa_value,
        distance_au=sun.distance_au or 1.0,
    )


def _body_xy(
    longitude: float,
    radius: float,
    cx: float,
    cy: float,
    tilt: float,
    latitude: float = 0.0,
) -> tuple[float, float]:
    """Project ecliptic longitude and latitude into the faux-3D scene."""
    rad = math.radians(longitude - 90)  # 0° points upward
    latitude = max(-90.0, min(90.0, latitude))
    out_of_plane = (
        math.sin(math.radians(latitude)) * radius * (0.18 if tilt < 1 else 0.24)
    )
    return (
        cx + radius * math.cos(rad),
        cy + radius * math.sin(rad) * tilt - out_of_plane,
    )


def _polar_xy(
    longitude: float,
    radius: float,
    cx: float,
    cy: float,
    tilt: float,
) -> tuple[float, float]:
    rad = math.radians(longitude - 90)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad) * tilt


def _zodiac_band(
    cx: float,
    cy: float,
    tilt: float,
    palette: dict[str, str],
) -> str:
    """Draw exact 30-degree tropical zodiac sectors and degree ticks."""
    inner_radius = 42.0
    outer_radius = 72.0
    parts = [
        '<g id="zodiac-band" data-coordinate-frame="tropical-ecliptic" '
        'aria-label="Tropical zodiac reference band">',
        f'<ellipse cx="{cx}" cy="{cy}" rx="{inner_radius}" ry="{inner_radius * tilt:.1f}" '
        f'fill="none" stroke="{palette["grid"]}" stroke-width="0.8" opacity="0.8"/>',
        f'<ellipse cx="{cx}" cy="{cy}" rx="{outer_radius}" ry="{outer_radius * tilt:.1f}" '
        f'fill="none" stroke="{palette["orbit_inner"]}" stroke-width="0.9" opacity="0.75"/>',
    ]
    for index, sign in enumerate(ZODIAC_SIGNS):
        start = index * 30.0
        end = start + 30.0
        inner_start = _polar_xy(start, inner_radius, cx, cy, tilt)
        outer_start = _polar_xy(start, outer_radius, cx, cy, tilt)
        outer_end = _polar_xy(end, outer_radius, cx, cy, tilt)
        inner_end = _polar_xy(end, inner_radius, cx, cy, tilt)
        fill = palette["orbit_inner"] if index % 2 == 0 else palette["orbit"]
        parts.append(
            f'<path d="M {inner_start[0]:.1f} {inner_start[1]:.1f} '
            f"L {outer_start[0]:.1f} {outer_start[1]:.1f} "
            f"A {outer_radius:.1f} {outer_radius * tilt:.1f} 0 0 1 "
            f"{outer_end[0]:.1f} {outer_end[1]:.1f} "
            f"L {inner_end[0]:.1f} {inner_end[1]:.1f} "
            f"A {inner_radius:.1f} {inner_radius * tilt:.1f} 0 0 0 "
            f'{inner_start[0]:.1f} {inner_start[1]:.1f} Z" '
            f'fill="{fill}" opacity="0.12" stroke="{palette["grid"]}" '
            f'stroke-width="0.45" data-sign="{sign}"/>'
        )
        label_x, label_y = _polar_xy(start + 15.0, outer_radius + 10.0, cx, cy, tilt)
        parts.append(
            f'<text x="{label_x:.1f}" y="{label_y + 2:.1f}" fill="{palette["label"]}" '
            f'font-size="7" letter-spacing="1" text-anchor="middle" opacity="0.68" '
            f'data-sign-label="{sign}">{sign}</text>'
        )

    for degree in range(0, 360, 5):
        major = degree % 30 == 0
        tick_start = outer_radius + (1.0 if not major else 0.0)
        tick_end = outer_radius + (4.0 if not major else 7.0)
        start = _polar_xy(degree, tick_start, cx, cy, tilt)
        end = _polar_xy(degree, tick_end, cx, cy, tilt)
        parts.append(
            f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" '
            f'x2="{end[0]:.1f}" y2="{end[1]:.1f}" '
            f'stroke="{palette["label"]}" stroke-width="{1.0 if major else 0.45}" '
            f'opacity="{0.65 if major else 0.3}" data-degree="{degree}"/>'
        )
    parts.append("</g>")
    return "\n".join(parts)


def _motion_layer(
    positions: list[Any],
    body_radii: dict[str, float],
    cx: float,
    cy: float,
    tilt: float,
    palette: dict[str, str],
) -> str:
    """Show short local motion trails from each body's instantaneous speed."""
    parts = [
        '<g id="motion-trails" fill="none" aria-label="Instantaneous planetary motion">'
    ]
    for position in positions:
        speed = float(position.speed)
        if not math.isfinite(speed) or abs(speed) < 0.001:
            continue
        radius = body_radii[position.name]
        span = min(38.0, max(8.0, abs(speed) * 5.0))
        start_longitude = position.longitude - math.copysign(span, speed)
        start = _body_xy(
            start_longitude,
            radius,
            cx,
            cy,
            tilt,
            position.latitude,
        )
        current = _body_xy(
            position.longitude,
            radius,
            cx,
            cy,
            tilt,
            position.latitude,
        )
        direction = "retrograde" if speed < 0 else "direct"
        colour = palette["retrograde"] if speed < 0 else palette["label"]
        trail_days = span / abs(speed)
        parts.append(
            f'<path d="M {start[0]:.1f} {start[1]:.1f} '
            f"A {radius:.1f} {radius * tilt:.1f} 0 0 {1 if speed > 0 else 0} "
            f'{current[0]:.1f} {current[1]:.1f}" stroke="{colour}" '
            f'stroke-width="1.4" stroke-dasharray="2 4" opacity="0.62" '
            'marker-end="url(#motionArrow)" '
            f'data-body="{escape(position.name)}" data-speed-deg-day="{speed:.5f}" '
            f'data-motion-direction="{direction}" data-trail-days="{trail_days:.2f}"/>'
        )
    parts.append("</g>")
    return "\n".join(parts)


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _precess_equatorial(
    ra_deg: float, dec_deg: float, timestamp: datetime
) -> tuple[float, float]:
    """Precess catalog J2000 coordinates to the snapshot epoch."""
    epoch = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    days = (_utc_timestamp(timestamp) - epoch).total_seconds() / 86400.0
    centuries = days / 36525.0
    zeta = (
        2306.2181 * centuries + 0.30188 * centuries**2 + 0.017998 * centuries**3
    ) / 3600.0
    z = (
        2306.2181 * centuries + 1.09468 * centuries**2 + 0.018203 * centuries**3
    ) / 3600.0
    theta = (
        2004.3109 * centuries - 0.42665 * centuries**2 - 0.041833 * centuries**3
    ) / 3600.0

    ra = math.radians(ra_deg)
    dec = math.radians(dec_deg)
    zeta_rad = math.radians(zeta)
    z_rad = math.radians(z)
    theta_rad = math.radians(theta)
    a = math.cos(dec) * math.sin(ra + zeta_rad)
    b = math.cos(theta_rad) * math.cos(dec) * math.cos(ra + zeta_rad) - math.sin(
        theta_rad
    ) * math.sin(dec)
    c = math.sin(theta_rad) * math.cos(dec) * math.cos(ra + zeta_rad) + math.cos(
        theta_rad
    ) * math.sin(dec)
    return (math.degrees(math.atan2(a, b) + z_rad) % 360.0, math.degrees(math.asin(c)))


def _equatorial_to_ecliptic(
    ra_deg: float, dec_deg: float, timestamp: datetime
) -> tuple[float, float]:
    ra, dec = _precess_equatorial(ra_deg, dec_deg, timestamp)
    utc = _utc_timestamp(timestamp)
    epoch = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    centuries = (utc - epoch).total_seconds() / 86400.0 / 36525.0
    obliquity = math.radians(
        23.43929111 - 0.013004167 * centuries - 0.000000164 * centuries**2
    )
    ra_rad = math.radians(ra)
    dec_rad = math.radians(dec)
    longitude = (
        math.degrees(
            math.atan2(
                math.sin(ra_rad) * math.cos(obliquity)
                + math.tan(dec_rad) * math.sin(obliquity),
                math.cos(ra_rad),
            )
        )
        % 360.0
    )
    latitude = math.degrees(
        math.asin(
            math.sin(dec_rad) * math.cos(obliquity)
            - math.cos(dec_rad) * math.sin(obliquity) * math.sin(ra_rad)
        )
    )
    return longitude, latitude


def _sky_xy(
    longitude: float,
    latitude: float,
    cx: float,
    cy: float,
    tilt: float,
) -> tuple[float, float]:
    """Project an ecliptic sky position using a north-pole polar map."""
    clamped_latitude = max(-90.0, min(90.0, latitude))
    radius = (90.0 - clamped_latitude) / 180.0 * (SCENE_RADIUS_MAX + 12)
    rad = math.radians(longitude - 90)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad) * tilt


def _constellation_layer(
    snapshot: ChartSnapshot,
    cx: float,
    cy: float,
    tilt: float,
    palette: dict[str, str],
) -> str:
    """Draw catalog-backed stars and line figures in the ecliptic sky frame."""
    catalog_stars = {
        star["id"]: star
        for star in CONSTELLATION_CATALOG.get("stars", [])
        if isinstance(star, dict) and "id" in star
    }
    projected: dict[str, tuple[float, float]] = {}
    for star_id, star in catalog_stars.items():
        longitude, latitude = _equatorial_to_ecliptic(
            float(star["ra_deg"]),
            float(star["dec_deg"]),
            snapshot.timestamp,
        )
        projected[star_id] = _sky_xy(longitude, latitude, cx, cy, tilt)

    parts = [
        '<g id="constellations" data-frame="ICRS-J2000-precessed-ecliptic" '
        'aria-label="Catalog constellation overlay">',
        f'<g id="constellation-lines" fill="none" stroke="{palette["label"]}" '
        'stroke-width="0.75" stroke-dasharray="2 5" opacity="0.32">',
    ]
    for segment in CONSTELLATION_CATALOG.get("segments", []):
        start = projected.get(segment.get("from"))
        end = projected.get(segment.get("to"))
        if start is None or end is None:
            continue
        constellation = escape(str(segment.get("constellation", "")))
        parts.append(
            f'<line x1="{start[0]:.1f}" y1="{start[1]:.1f}" '
            f'x2="{end[0]:.1f}" y2="{end[1]:.1f}" '
            f'data-constellation="{constellation}"/>'
        )
    parts.append("</g>")
    parts.append('<g id="catalog-stars">')
    for star_id, star in catalog_stars.items():
        point = projected.get(star_id)
        if point is None:
            continue
        magnitude = float(star.get("magnitude", 4.0))
        radius = max(0.9, min(3.0, 2.7 - magnitude * 0.42))
        opacity = max(0.42, min(1.0, 1.08 - magnitude * 0.1))
        name = escape(str(star.get("name", star_id)))
        parts.append(
            f'<circle cx="{point[0]:.1f}" cy="{point[1]:.1f}" r="{radius:.2f}" '
            f'fill="{palette["star_bright"]}" opacity="{opacity:.2f}" '
            f'data-star="{escape(star_id)}"><title>{name}</title></circle>'
        )
    parts.append("</g>")
    parts.append('<g id="constellation-labels" fill="none">')
    for label in CONSTELLATION_CATALOG.get("labels", []):
        if not isinstance(label, dict):
            continue
        longitude, latitude = _equatorial_to_ecliptic(
            float(label["ra_deg"]),
            float(label["dec_deg"]),
            snapshot.timestamp,
        )
        x, y = _sky_xy(longitude, latitude, cx, cy, tilt)
        constellation = escape(str(label.get("constellation", "")))
        name = escape(str(label.get("name", constellation)))
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" fill="{palette["label"]}" '
            f'font-size="8" letter-spacing="1.5" opacity="0.52" '
            f'data-constellation-label="{constellation}">{name}</text>'
        )
    parts.append("</g>")
    parts.append("</g>")
    return "\n".join(parts)


def _body_label_placement(
    position: Any,
    x: float,
    y: float,
    tilt: float,
    occupied: list[tuple[float, float, float, float]],
    width: float = 1200.0,
    height: float = 800.0,
) -> tuple[float, float, str]:
    """Place a body label deterministically while avoiding nearby labels."""
    angle = math.radians(position.longitude - 90)
    radial_x = math.cos(angle)
    radial_y = math.sin(angle) * tilt
    tangent_x = -math.sin(angle)
    tangent_y = math.cos(angle) * tilt
    offset = BODY_MARKER_RADIUS.get(position.name, 5.0) + 11.0
    label_width = max(44.0, len(position.name) * 7.2)
    anchor = "start"
    if radial_x < -0.3:
        anchor = "end"
    elif abs(radial_x) < 0.3:
        anchor = "middle"

    base_x = x + radial_x * offset
    base_y = y + radial_y * offset - 4.0
    candidates = [
        (0.0, 0.0),
        (16.0, 0.0),
        (-16.0, 0.0),
        (30.0, 0.0),
        (-30.0, 0.0),
        (0.0, -18.0),
        (0.0, 18.0),
    ]

    def box_for(tx: float, ty: float) -> tuple[float, float, float, float]:
        if anchor == "start":
            left, right = tx, tx + label_width
        elif anchor == "end":
            left, right = tx - label_width, tx
        else:
            left, right = tx - label_width / 2.0, tx + label_width / 2.0
        return left, ty - 12.0, right, ty + 3.0

    def overlap(box: tuple[float, float, float, float]) -> int:
        left, top, right, bottom = box
        return sum(
            left < previous_right + 4
            and right > previous_left - 4
            and top < previous_bottom + 4
            and bottom > previous_top - 4
            for previous_left, previous_top, previous_right, previous_bottom in occupied
        )

    best: tuple[float, float, str, tuple[float, float, float, float], float] | None = (
        None
    )
    for tangent_offset, radial_offset in candidates:
        tx = base_x + tangent_x * tangent_offset + radial_x * radial_offset
        ty = base_y + tangent_y * tangent_offset + radial_y * radial_offset
        box = box_for(tx, ty)
        left, top, right, bottom = box
        out_of_bounds = (
            max(0.0, 22.0 - left)
            + max(0.0, right - (width - 22.0))
            + max(0.0, 28.0 - top)
            + max(0.0, bottom - (height - 148.0))
        )
        score = overlap(box) * 1000.0 + out_of_bounds * 10.0
        candidate = (tx, ty, anchor, box, score)
        if best is None or candidate[-1] < best[-1]:
            best = candidate

    assert best is not None
    tx, ty, selected_anchor, box, _ = best
    occupied.append(box)
    return tx, ty, selected_anchor


def _asteroid_points(radius: float, name: str) -> str:
    seed = int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    points = []
    for index in range(8):
        angle = math.tau * index / 8.0
        point_radius = radius * rng.uniform(0.72, 1.12)
        points.append(
            f"{math.cos(angle) * point_radius:.1f},{math.sin(angle) * point_radius:.1f}"
        )
    return " ".join(points)


def _body_marker(position: Any, x: float, y: float, palette: dict[str, str]) -> str:
    """Return a graphical marker instead of a generic position dot."""
    name = position.name
    marker_radius = BODY_MARKER_RADIUS.get(name, 5.0)
    marker_id = "marker-" + name.lower().replace(" ", "-")
    label = escape(name)
    distance = (
        f"{position.distance_au:.9f}" if position.distance_au is not None else "unknown"
    )
    parts = [
        f'<g id="{marker_id}" data-body="{label}" aria-label="{label} ephemeris marker" '
        f'data-longitude="{position.longitude:.6f}" data-latitude="{position.latitude:.6f}" '
        f'data-distance-au="{distance}" data-speed-deg-day="{position.speed:.6f}" '
        f'data-retrograde="{str(position.retrograde).lower()}" transform="translate({x:.1f} {y:.1f})">',
        f"<title>{label}: {position.longitude:.3f} degrees ecliptic, {position.speed:.3f} degrees/day</title>",
    ]
    if name == "Moon":
        parts.extend(
            [
                f'<circle r="{marker_radius}" fill="url(#moonSurface)" stroke="#f6f1df" stroke-width="0.7"/>',
                '<circle cx="-1.8" cy="-1.4" r="1.2" fill="#777985" opacity="0.55"/>',
                '<circle cx="2.0" cy="1.8" r="0.9" fill="#777985" opacity="0.45"/>',
            ]
        )
    elif name == "Earth":
        parts.extend(
            [
                f'<defs><clipPath id="clip-{marker_id}"><circle r="{marker_radius}"/></clipPath></defs>',
                f'<circle r="{marker_radius}" fill="url(#earthSurface)" stroke="#b4efff" stroke-width="0.7"/>',
                f'<g clip-path="url(#clip-{marker_id})">',
                '<path d="M -10 -4 C -7 -8 -3 -7 -2 -4 C 0 -3 0 -1 -2 0 C -4 1 -5 4 -8 3 C -10 1 -12 -1 -10 -4 Z" fill="#4cad76"/>',
                '<path d="M 1 -8 C 4 -7 7 -5 8 -2 C 6 -1 5 1 3 1 C 1 -1 -1 -2 0 -4 Z" fill="#6fbe78"/>',
                '<path d="M 2 2 C 5 1 8 2 10 5 C 7 8 3 9 0 7 C -1 5 0 3 2 2 Z" fill="#4b9f70"/>',
                '<path d="M -10 1 C -6 0 -3 2 1 2 C 4 2 7 0 11 1" fill="none" stroke="#d5f6ff" stroke-width="1.2" opacity="0.72"/>',
                '<path d="M -8 6 C -4 5 0 6 4 5 C 7 4 9 5 11 6" fill="none" stroke="#d5f6ff" stroke-width="0.9" opacity="0.56"/>',
                "</g>",
            ]
        )
    elif name == "Mercury":
        parts.extend(
            [
                f'<circle r="{marker_radius}" fill="url(#mercurySurface)" stroke="#d5d2c6" stroke-width="0.5"/>',
                '<circle cx="-1.4" cy="1.0" r="1.0" fill="#525864" opacity="0.7"/>',
                '<circle cx="1.9" cy="-1.8" r="0.75" fill="#5b616a" opacity="0.65"/>',
            ]
        )
    elif name == "Venus":
        parts.extend(
            [
                f'<circle r="{marker_radius}" fill="url(#venusSurface)" stroke="#ffe5a5" stroke-width="0.5"/>',
                f'<path d="M {-marker_radius * 0.8:.1f} -1 C -2 -{marker_radius * 0.7:.1f}, 3 2, {marker_radius * 0.75:.1f} 0" fill="none" stroke="#ffeab0" stroke-width="1.1" opacity="0.55"/>',
            ]
        )
    elif name == "Mars":
        parts.extend(
            [
                f'<circle r="{marker_radius}" fill="url(#marsSurface)" stroke="#ffb08b" stroke-width="0.5"/>',
                f'<ellipse cx="0" cy="{-marker_radius * 0.72:.1f}" rx="{marker_radius * 0.38:.1f}" ry="{marker_radius * 0.16:.1f}" fill="#ffd3ba" opacity="0.65"/>',
                f'<path d="M {-marker_radius * 0.75:.1f} 1 C -2 3, 2 4, {marker_radius * 0.7:.1f} 1" fill="none" stroke="#702b32" stroke-width="1" opacity="0.55"/>',
            ]
        )
    elif name == "Jupiter":
        parts.extend(
            [
                f'<defs><clipPath id="clip-{marker_id}"><circle r="{marker_radius}"/></clipPath></defs>',
                f'<circle r="{marker_radius}" fill="url(#jupiterSurface)" stroke="#f2d4ad" stroke-width="0.5"/>',
                f'<g clip-path="url(#clip-{marker_id})" opacity="0.72">',
                f'<path d="M {-marker_radius} -6 H {marker_radius}" stroke="#e9c69e" stroke-width="2"/>',
                f'<path d="M {-marker_radius} 0 H {marker_radius}" stroke="#8a5c57" stroke-width="2.2"/>',
                f'<path d="M {-marker_radius} 6 H {marker_radius}" stroke="#f1d9b3" stroke-width="1.5"/>',
                '<ellipse cx="3" cy="3" rx="3.3" ry="1.8" fill="#a95d4e"/>',
                "</g>",
            ]
        )
    elif name == "Saturn":
        parts.extend(
            [
                '<g transform="rotate(-14)">',
                f'<ellipse rx="{marker_radius * 2.2:.1f}" ry="{marker_radius * 1.08:.1f}" fill="none" stroke="#8e704e" stroke-width="2.8" opacity="0.72"/>',
                f'<ellipse rx="{marker_radius * 1.68:.1f}" ry="{marker_radius * 0.78:.1f}" fill="none" stroke="#f1dcb0" stroke-width="1.2" opacity="0.78"/>',
                "</g>",
                f'<circle r="{marker_radius}" fill="url(#saturnSurface)" stroke="#f4d9a0" stroke-width="0.5"/>',
                f'<path d="M {-marker_radius * 0.8:.1f} -2 H {marker_radius * 0.8:.1f}" stroke="#edd09b" stroke-width="1.2" opacity="0.55"/>',
                '<g transform="rotate(-14)" fill="none">',
                f'<path d="M {-marker_radius * 2.2:.1f} 0 A {marker_radius * 2.2:.1f} {marker_radius * 1.08:.1f} 0 0 0 {marker_radius * 2.2:.1f} 0" stroke="#f1dcb0" stroke-width="1.2" opacity="0.68"/>',
                "</g>",
            ]
        )
    elif name in {"Uranus", "Neptune"}:
        parts.extend(
            [
                f'<ellipse rx="{marker_radius * 1.55:.1f}" ry="{marker_radius * 0.25:.1f}" fill="none" stroke="#93d9e4" stroke-width="0.8" opacity="0.45"/>',
                f'<circle r="{marker_radius}" fill="url(#iceSurface)" stroke="#c3f5ff" stroke-width="0.5"/>',
                f'<path d="M {-marker_radius * 0.7:.1f} 2 C -2 4, 2 4, {marker_radius * 0.7:.1f} 2" fill="none" stroke="#bcecff" stroke-width="0.9" opacity="0.55"/>',
            ]
        )
    elif name == "Pluto":
        parts.extend(
            [
                f'<circle r="{marker_radius}" fill="url(#plutoSurface)" stroke="#f2d6c2" stroke-width="0.5"/>',
                f'<path d="M {-marker_radius * 0.55:.1f} -1 C -1 -{marker_radius * 0.65:.1f}, {marker_radius * 0.65:.1f} -{marker_radius * 0.2:.1f}, {marker_radius * 0.4:.1f} 2" fill="none" stroke="#f1dfd0" stroke-width="1.1" opacity="0.6"/>',
            ]
        )
    elif name in ASTEROID_NAMES:
        parts.extend(
            [
                f'<polygon points="{_asteroid_points(marker_radius + 1.2, name)}" fill="#aa8068" stroke="#edc1a0" stroke-width="0.6"/>',
                '<circle cx="-1.2" cy="0.6" r="0.8" fill="#634b4d" opacity="0.8"/>',
            ]
        )
    elif name in NODE_NAMES:
        parts.append(
            f'<path d="M 0 -{marker_radius:.1f} L {marker_radius:.1f} 0 L 0 {marker_radius:.1f} '
            f'L -{marker_radius:.1f} 0 Z" fill="none" stroke="{palette["label"]}" stroke-width="1.2"/>'
        )
    else:
        parts.append(
            f'<circle r="{marker_radius}" fill="{palette["dot"]}" stroke="{palette["label"]}" stroke-width="0.6"/>'
        )
    parts.append("</g>")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _generate_planetary_scene_svg_content(
    snapshot: ChartSnapshot,
    theme: str,
    projection: str,
    include_labels: bool,
    include_orbits: bool,
    include_minor_bodies: bool,
    include_aspects: bool,
    transparent_bg: bool = False,
    include_zodiac_band: bool = True,
    include_motion: bool = True,
) -> str:
    palette = THEMES.get(theme, THEMES["dark"])
    width, height = 1200, 800
    cx, cy = width / 2.0, height / 2.0
    tilt = 0.38 if projection == "perspective" else 1.0
    timestamp_seed = int.from_bytes(
        hashlib.blake2b(
            _utc_timestamp(snapshot.timestamp).isoformat().encode("utf-8"),
            digest_size=8,
        ).digest(),
        "big",
    )

    parts: list[str] = []

    # SVG root
    bg_style = "transparent" if transparent_bg else palette["bg"]
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'role="img" aria-labelledby="scene-title scene-description" '
        f"style=\"background:{bg_style};font-family:'Space Grotesk','Inter','Segoe UI',sans-serif\">"
    )
    parts.append('<title id="scene-title">OpAstro planetary scene</title>')
    parts.append(
        '<desc id="scene-description">A geocentric ecliptic sky scene with '
        "ephemeris-positioned bodies, catalog constellation lines, and an animated star field.</desc>"
    )
    parts.append(
        "<style>@media (prefers-reduced-motion: reduce) { "
        "#stars animate, #marker-sun animate { display: none; } }</style>"
    )
    parts.append(
        f'<metadata data-timestamp="{escape(snapshot.timestamp.isoformat())}" '
        'data-coordinate-frame="geocentric-ecliptic"/>'
    )

    # Defs (gradients, filters)
    parts.append(_svg_defs(palette))

    # Solid background rect to ensure PNG converters respect the background color.
    if not transparent_bg:
        parts.append(
            f'<rect width="{width}" height="{height}" fill="url(#skyGradient)" />'
        )

    # Atmospheric star field and catalog-backed constellation overlay.
    parts.append(_star_field(width, height, palette, seed=timestamp_seed))
    parts.append(_constellation_layer(snapshot, cx, cy, tilt, palette))

    # Perspective grid
    if projection == "perspective":
        parts.append(_perspective_grid(cx, cy, tilt, palette))
    if include_zodiac_band:
        parts.append(_zodiac_band(cx, cy, tilt, palette))

    # The ephemeris is geocentric, so the Sun is the scene anchor. Its marker
    # is intentionally richer than the body markers because it is the focal point.
    parts.append(
        '<g id="marker-sun" data-body="Sun" aria-label="Sun" data-animated="true">'
        f'<circle cx="{cx}" cy="{cy}" r="52" fill="url(#sunGlow)" filter="url(#bloom)"/>'
        f'<circle cx="{cx}" cy="{cy}" r="13" fill="{palette["sun_core"]}" stroke="{palette["sun_mid"]}" stroke-width="1"/>'
        f'<circle cx="{cx}" cy="{cy}" r="22" fill="none" stroke="{palette["sun_mid"]}" stroke-width="1" opacity="0.45">'
        '<animate attributeName="r" values="20;24;20" dur="6.4s" repeatCount="indefinite"/>'
        "</circle>"
        "</g>"
    )

    # Decide which bodies to render
    scene_positions = list(snapshot.positions)
    earth = _earth_position(snapshot)
    if earth is not None:
        scene_positions.append(earth)
    bodies_to_render = []
    for pos in scene_positions:
        if pos.name == "Sun":
            continue
        if not include_minor_bodies and pos.name not in MAJOR_PLANET_NAMES | {"Moon"}:
            continue
        bodies_to_render.append(pos)
    body_radii = {pos.name: _body_radius(pos) for pos in bodies_to_render}

    # Orbit bands are a logarithmic visual encoding of the ephemeris distance,
    # not an assertion that geocentric distances are heliocentric semimajor axes.
    if include_orbits:
        parts.append(
            f'<g id="orbits" fill="none" stroke-linecap="round" '
            f'data-distance-scale="logarithmic" stroke="{palette["orbit"]}">'
        )
        drawn_radii: set[float] = set()
        for pos in bodies_to_render:
            radius = body_radii[pos.name]
            rounded_radius = round(radius, 1)
            if rounded_radius in drawn_radii:
                continue
            drawn_radii.add(rounded_radius)
            colour = palette["orbit_inner"] if radius < 220 else palette["orbit"]
            parts.append(
                f'<ellipse cx="{cx}" cy="{cy}" rx="{radius:.1f}" ry="{radius * tilt:.1f}" '
                f'stroke="{colour}" stroke-width="0.75" opacity="0.58" '
                f'data-distance-au="{pos.distance_au if pos.distance_au is not None else "fallback"}"/>'
            )
        parts.append("</g>")

    if include_motion:
        parts.append(_motion_layer(bodies_to_render, body_radii, cx, cy, tilt, palette))

    # Aspect connector lines (subtle)
    if include_aspects and snapshot.aspects:
        parts.append(
            f'<g id="aspects" stroke="{palette["aspect"]}" stroke-width="0.5" opacity="0.3">'
        )
        body_positions: dict[str, tuple[float, float]] = {}
        for pos in bodies_to_render:
            body_positions[pos.name] = _body_xy(
                pos.longitude,
                body_radii[pos.name],
                cx,
                cy,
                tilt,
                pos.latitude,
            )
        for asp in snapshot.aspects:
            p1 = body_positions.get(asp.body1)
            p2 = body_positions.get(asp.body2)
            if p1 and p2:
                parts.append(
                    f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" '
                    f'x2="{p2[0]:.1f}" y2="{p2[1]:.1f}"/>'
                )
        parts.append("</g>")

    # Graphical planet, moon, dwarf, asteroid, and node markers.
    parts.append('<g id="bodies" aria-label="Ephemeris body markers">')
    occupied_label_boxes: list[tuple[float, float, float, float]] = []
    for pos in bodies_to_render:
        radius = body_radii[pos.name]
        px, py = _body_xy(
            pos.longitude,
            radius,
            cx,
            cy,
            tilt,
            pos.latitude,
        )

        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{BODY_MARKER_RADIUS.get(pos.name, 5.0) * 2.4:.1f}" '
            f'fill="url(#dotGlow)" opacity="0.5"/>'
        )
        parts.append(_body_marker(pos, px, py, palette))

        if include_labels:
            label = escape(pos.name.upper())
            tx, ty, anchor = _body_label_placement(
                pos,
                px,
                py,
                tilt,
                occupied_label_boxes,
                width,
                height,
            )
            parts.append(
                f'<text x="{tx:.1f}" y="{ty:.1f}" fill="{palette["label"]}" '
                f'font-size="11" font-weight="600" letter-spacing="1.5" '
                f'text-anchor="{anchor}" opacity="0.92" data-label-for="{label}">{label}</text>'
            )

    parts.append("</g>")

    # Keep the data table visually above the bottom of the star field.
    parts.append(_footer_data_table(width, height, snapshot, bodies_to_render, palette))

    # Timestamp watermark (bottom-right)
    ts = (
        _utc_timestamp(snapshot.timestamp).strftime("%Y-%m-%d %H:%M UTC")
        if snapshot.timestamp
        else ""
    )
    parts.append(
        f'<text x="{width - 35}" y="{height - 35}" fill="{palette["label"]}" '
        f'font-size="9" text-anchor="end" opacity="0.45">{ts}  |  OPASTRO</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


def build_planetary_scene_svg(
    snapshot: ChartSnapshot,
    output_path: str,
    theme: str = "dark",
    projection: str = "perspective",
    include_labels: bool = True,
    include_orbits: bool = True,
    include_minor_bodies: bool = True,
    include_aspects: bool = True,
    transparent_bg: bool = False,
    include_zodiac_band: bool = True,
    include_motion: bool = True,
) -> None:
    """Render a planetary scene to an SVG file."""
    content = _generate_planetary_scene_svg_content(
        snapshot=snapshot,
        theme=theme,
        projection=projection,
        include_labels=include_labels,
        include_orbits=include_orbits,
        include_minor_bodies=include_minor_bodies,
        include_aspects=include_aspects,
        transparent_bg=transparent_bg,
        include_zodiac_band=include_zodiac_band,
        include_motion=include_motion,
    )
    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def build_planetary_scene_png(
    snapshot: ChartSnapshot,
    output_path: str,
    theme: str = "dark",
    projection: str = "perspective",
    include_labels: bool = True,
    include_orbits: bool = True,
    include_minor_bodies: bool = True,
    include_aspects: bool = True,
    transparent_bg: bool = False,
    include_zodiac_band: bool = True,
    include_motion: bool = True,
) -> None:
    """Render a planetary scene SVG then convert to PNG."""
    target = Path(output_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".svg",
        prefix="opastro-scene-",
        dir=target.parent,
        encoding="utf-8",
        delete=False,
    ) as temporary:
        svg_path = Path(temporary.name)
    build_planetary_scene_svg(
        snapshot=snapshot,
        output_path=str(svg_path),
        theme=theme,
        projection=projection,
        include_labels=include_labels,
        include_orbits=include_orbits,
        include_minor_bodies=include_minor_bodies,
        include_aspects=include_aspects,
        transparent_bg=transparent_bg,
        include_zodiac_band=include_zodiac_band,
        include_motion=include_motion,
    )
    try:
        import cairosvg  # type: ignore[import-untyped]

        cairosvg.svg2png(url=str(svg_path), write_to=str(target), scale=2.0)
    except Exception as e:
        try:
            subprocess.run(
                ["rsvg-convert", "-o", str(target), str(svg_path)], check=True
            )
        except Exception as e2:
            import sys

            print(
                "Warning: Could not convert SVG to PNG. Requires "
                "'cairosvg' or 'rsvg-convert'.",
                file=sys.stderr,
            )
            print(f"Details: {e} | {e2}", file=sys.stderr)
    finally:
        svg_path.unlink(missing_ok=True)
