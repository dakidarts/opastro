"""Planetary Scene Renderer — generates premium 2D / faux-3D SVG sky maps.

Consumes a ``ChartSnapshot`` produced by ``EphemerisEngine`` and projects the
planetary longitudes onto a stylised heliocentric (or geocentric-abstract) map
with orbit ellipses, glowing Sun, labelled bodies, optional aspect connectors,
and a perspective grid.
"""
from __future__ import annotations

import math
import random
import subprocess
from typing import Optional

from .models import ChartSnapshot


# ---------------------------------------------------------------------------
# Theme colour palettes
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#000000",
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
    },
}

# Stylised orbit radii – deliberately non-literal for visual clarity.
ORBIT_RADII: dict[str, float] = {
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

MAJOR_PLANET_NAMES = {
    "Mercury", "Venus", "Mars", "Jupiter",
    "Saturn", "Uranus", "Neptune", "Pluto",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _star_field(width: int, height: int, palette: dict[str, str], seed: int = 42) -> str:
    """Generate a scattering of background stars and subtle nebulas."""
    rng = random.Random(seed)
    parts: list[str] = ['<g id="stars">']
    
    # Subtle nebulas
    parts.append(f'''
    <defs>
        <radialGradient id="nebula1" cx="30%" cy="40%" r="50%">
            <stop offset="0%" stop-color="{palette["glow"]}" stop-opacity="0.08"/>
            <stop offset="100%" stop-color="{palette["bg"]}" stop-opacity="0"/>
        </radialGradient>
        <radialGradient id="nebula2" cx="70%" cy="60%" r="60%">
            <stop offset="0%" stop-color="{palette["label"]}" stop-opacity="0.05"/>
            <stop offset="100%" stop-color="{palette["bg"]}" stop-opacity="0"/>
        </radialGradient>
    </defs>
    <rect width="{width}" height="{height}" fill="url(#nebula1)" />
    <rect width="{width}" height="{height}" fill="url(#nebula2)" />
    ''')

    for _ in range(250):
        x = rng.randint(0, width)
        y = rng.randint(0, height)
        r = rng.choice([0.5, 0.8, 1.0, 1.2, 1.5, 2.0])
        opacity = rng.uniform(0.15, 0.9)
        colour = palette["star_bright"] if rng.random() > 0.6 else palette["star_dim"]
        if r >= 1.5:
             parts.append(f'<circle cx="{x}" cy="{y}" r="{r+1}" fill="{colour}" opacity="{opacity * 0.2}" filter="url(#bloom)"/>')
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{colour}" opacity="{opacity:.2f}"/>'
        )
    parts.append("</g>")
    return "\n".join(parts)


def _svg_defs(palette: dict[str, str]) -> str:
    """Reusable SVG definitions: gradients, glow filters."""
    return f"""<defs>
  <radialGradient id="sunGlow" cx="50%" cy="50%" r="50%">
    <stop offset="0%"   stop-color="{palette['sun_core']}" stop-opacity="1"/>
    <stop offset="15%"  stop-color="{palette['sun_mid']}"  stop-opacity="0.85"/>
    <stop offset="50%"  stop-color="{palette['sun_outer']}" stop-opacity="0.25"/>
    <stop offset="100%" stop-color="{palette['sun_outer']}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="dotGlow" cx="50%" cy="50%" r="50%">
    <stop offset="0%"   stop-color="{palette['glow']}" stop-opacity="0.6"/>
    <stop offset="100%" stop-color="{palette['glow']}" stop-opacity="0"/>
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
</defs>"""


def _perspective_grid(
    cx: float, cy: float, tilt: float, palette: dict[str, str],
) -> str:
    """Draw the faux-3D perspective grid (ellipses + radial lines)."""
    parts: list[str] = [f'<g id="grid" stroke="{palette["grid"]}" stroke-width="0.6" fill="none" opacity="0.45">']
    for r in range(80, 900, 80):
        parts.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * tilt}"/>')
    for angle in range(0, 360, 15):
        rad = math.radians(angle)
        x2 = cx + 900 * math.cos(rad)
        y2 = cy + 900 * math.sin(rad) * tilt
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}"/>')
    parts.append("</g>")
    return "\n".join(parts)


def _footer_data_table(width: float, height: float, snapshot: ChartSnapshot, bodies_to_render: list, palette: dict[str, str]) -> str:
    """Draw a minimalist, beautiful table of planetary positions and aspects at the bottom."""
    parts = []
    
    bodies_to_show = [b.name for b in bodies_to_render]
    num_bodies = len(bodies_to_show)
    bodies_rows = math.ceil(num_bodies / 6) if num_bodies > 0 else 0
    
    aspects = sorted((a for a in snapshot.aspects if a.body1 in bodies_to_show and a.body2 in bodies_to_show), key=lambda a: a.orb)[:4]
    aspect_rows = math.ceil(len(aspects) / 2)
    
    max_rows = max(bodies_rows, aspect_rows, 2)
    box_height = max(100, 45 + (max_rows - 1) * 24 + 30)
    table_y = height - box_height - 20
    
    parts.append(f'<rect x="20" y="{table_y}" width="{width - 40}" height="{box_height}" fill="{palette["bg"]}" opacity="0.65" rx="8" />')
    parts.append(f'<rect x="20" y="{table_y}" width="{width - 40}" height="{box_height}" fill="none" stroke="{palette["grid"]}" stroke-width="1" rx="8" opacity="0.8" />')
    
    # Col 1: Planet positions
    parts.append(f'<text x="40" y="{table_y + 24}" fill="{palette["label"]}" font-size="10" font-weight="600" letter-spacing="2" opacity="0.9">PLANETARY POSITIONS</text>')
    
    y_offset = table_y + 45
    x_offset = 40
    col_width = 85
    
    for i, bname in enumerate(bodies_to_show):
        pos = next((p for p in snapshot.positions if p.name == bname), None)
        if not pos:
            continue
        
        row = i // 6
        col = i % 6
        
        px = x_offset + col * col_width
        py = y_offset + row * 24
        
        deg = int(pos.degree_in_sign)
        rx = " Rx" if pos.retrograde else ""
        text_val = f"{deg}° {pos.sign[:3]}{rx}"
        
        parts.append(f'<text x="{px}" y="{py}" fill="{palette["dot"]}" font-size="10" font-weight="500">{bname.upper()}</text>')
        parts.append(f'<text x="{px}" y="{py + 12}" fill="{palette["label"]}" font-size="9" opacity="0.75">{text_val}</text>')
    
    # Col 2: Aspects
    divider_x = x_offset + 6 * col_width + 5
    parts.append(f'<line x1="{divider_x}" y1="{table_y + 15}" x2="{divider_x}" y2="{table_y + box_height - 15}" stroke="{palette["grid"]}" stroke-width="1.5" />')
    
    aspect_x = divider_x + 25
    parts.append(f'<text x="{aspect_x}" y="{table_y + 24}" fill="{palette["label"]}" font-size="10" font-weight="600" letter-spacing="2" opacity="0.9">KEY ASPECTS</text>')
    
    for i, asp in enumerate(aspects):
        row = i // 2
        col = i % 2
        
        px = aspect_x + col * 140
        py = y_offset + row * 24
        
        asp_name = asp.aspect.upper()
        orb = f"{asp.orb:.1f}° orb"
        
        parts.append(f'<text x="{px}" y="{py}" fill="{palette["dot"]}" font-size="10" font-weight="500">{asp.body1[:3]} {asp_name} {asp.body2[:3]}</text>')
        parts.append(f'<text x="{px}" y="{py + 12}" fill="{palette["label"]}" font-size="9" opacity="0.75">{orb}</text>')
        
    return "\\n".join(parts)


def _body_xy(
    longitude: float, radius: float, cx: float, cy: float, tilt: float,
) -> tuple[float, float]:
    """Project a body's ecliptic longitude onto the 2D/perspective canvas."""
    rad = math.radians(longitude - 90)  # 0° points upward
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad) * tilt


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
) -> str:
    palette = THEMES.get(theme, THEMES["dark"])
    width, height = 1200, 800
    cx, cy = width / 2.0, height / 2.0
    tilt = 0.38 if projection == "perspective" else 1.0

    parts: list[str] = []

    # SVG root
    bg_style = "transparent" if transparent_bg else palette["bg"]
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'style="background:{bg_style};font-family:\'Space Grotesk\',\'Inter\',\'Segoe UI\',sans-serif">'
    )

    # Defs (gradients, filters)
    parts.append(_svg_defs(palette))

    # Solid background rect to ensure PNG converters respect the background color
    if not transparent_bg:
        parts.append(f'<rect width="{width}" height="{height}" fill="{palette["bg"]}" />')

    # Star field
    parts.append(_star_field(width, height, palette))

    # Perspective grid
    if projection == "perspective":
        parts.append(_perspective_grid(cx, cy, tilt, palette))

    # Sun (centre)
    parts.append(
        f'<circle cx="{cx}" cy="{cy}" r="50" fill="url(#sunGlow)" filter="url(#bloom)"/>'
        f'<circle cx="{cx}" cy="{cy}" r="6" fill="{palette["sun_core"]}"/>'
    )

    # Decide which bodies to render
    bodies_to_render = []
    for pos in snapshot.positions:
        if pos.name == "Sun":
            continue
        if pos.name not in ORBIT_RADII:
            continue
        if not include_minor_bodies and pos.name not in MAJOR_PLANET_NAMES:
            continue
        bodies_to_render.append(pos)

    # Orbit ellipses
    if include_orbits:
        parts.append(f'<g id="orbits" fill="none">')
        drawn_radii: set[float] = set()
        for pos in bodies_to_render:
            r = ORBIT_RADII[pos.name]
            if r in drawn_radii:
                continue
            drawn_radii.add(r)
            colour = palette["orbit_inner"] if r < 200 else palette["orbit"]
            parts.append(
                f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * tilt}" '
                f'stroke="{colour}" stroke-width="0.7" opacity="0.6"/>'
            )
        parts.append("</g>")

    # Footer Data Table
    parts.append(_footer_data_table(width, height, snapshot, bodies_to_render, palette))

    # Aspect connector lines (subtle)
    if include_aspects and snapshot.aspects:
        parts.append(f'<g id="aspects" stroke="{palette["aspect"]}" stroke-width="0.5" opacity="0.3">')
        body_positions: dict[str, tuple[float, float]] = {}
        for pos in bodies_to_render:
            r = ORBIT_RADII[pos.name]
            body_positions[pos.name] = _body_xy(pos.longitude, r, cx, cy, tilt)
        for asp in snapshot.aspects:
            p1 = body_positions.get(asp.body1)
            p2 = body_positions.get(asp.body2)
            if p1 and p2:
                parts.append(
                    f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" '
                    f'x2="{p2[0]:.1f}" y2="{p2[1]:.1f}"/>'
                )
        parts.append("</g>")

    # Planet dots + labels
    parts.append(f'<g id="bodies">')
    for pos in bodies_to_render:
        r = ORBIT_RADII[pos.name]
        px, py = _body_xy(pos.longitude, r, cx, cy, tilt)

        # Soft glow behind dot
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="10" fill="url(#dotGlow)" opacity="0.5"/>'
        )
        # Planet dot
        parts.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{palette["dot"]}" filter="url(#softBloom)"/>'
        )

        # Label
        if include_labels:
            label = pos.name.upper()
            # Offset label away from centre to reduce collisions
            angle_rad = math.radians(pos.longitude - 90)
            offset = 14
            tx = px + offset * math.cos(angle_rad)
            ty = py + offset * math.sin(angle_rad) * tilt - 4
            anchor = "start"
            if math.cos(angle_rad) < -0.3:
                anchor = "end"
            elif abs(math.cos(angle_rad)) < 0.3:
                anchor = "middle"
            parts.append(
                f'<text x="{tx:.1f}" y="{ty:.1f}" fill="{palette["label"]}" '
                f'font-size="11" font-weight="600" letter-spacing="1.5" '
                f'text-anchor="{anchor}" opacity="0.92">{label}</text>'
            )

    parts.append("</g>")

    # Timestamp watermark (bottom-right)
    ts = snapshot.timestamp.strftime("%Y-%m-%d %H:%M UTC") if snapshot.timestamp else ""
    parts.append(
        f'<text x="{width - 35}" y="{height - 35}" fill="{palette["label"]}" '
        f'font-size="9" text-anchor="end" opacity="0.45">{ts}  •  OPASTRO</text>'
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
    )
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)


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
) -> None:
    """Render a planetary scene SVG then convert to PNG."""
    svg_path = output_path.rsplit(".", 1)[0] + ".svg"
    build_planetary_scene_svg(
        snapshot=snapshot,
        output_path=svg_path,
        theme=theme,
        projection=projection,
        include_labels=include_labels,
        include_orbits=include_orbits,
        include_minor_bodies=include_minor_bodies,
        include_aspects=include_aspects,
        transparent_bg=transparent_bg,
    )
    try:
        import cairosvg  # type: ignore[import-untyped]
        cairosvg.svg2png(url=svg_path, write_to=output_path, scale=2.0)
    except Exception as e:
        try:
            subprocess.run(["rsvg-convert", "-o", output_path, svg_path], check=True)
        except Exception as e2:
            import sys
            print(f"Warning: Could not convert SVG to PNG. Requires 'cairosvg' or 'rsvg-convert'. SVG saved to {svg_path}", file=sys.stderr)
            print(f"Details: {e} | {e2}", file=sys.stderr)
