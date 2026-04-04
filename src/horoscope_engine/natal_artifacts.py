from __future__ import annotations

import json
import math
from datetime import date
from io import BytesIO
from typing import Any, Optional

from .models import NatalBirthchartResponse, ZODIAC_SIGNS

ACCENT_DEFAULT = "#3ddd77"
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


def _polar_xy(cx: float, cy: float, radius: float, longitude: float) -> tuple[float, float]:
    angle = math.radians((longitude % 360.0) - 90.0)
    return (cx + radius * math.cos(angle), cy + radius * math.sin(angle))


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


def build_natal_wheel_svg(
    report: NatalBirthchartResponse,
    *,
    accent_color: str = ACCENT_DEFAULT,
    size: int = 1080,
    brand_title: str = "OPASTRO",
) -> str:
    size = max(640, int(size))
    cx = size / 2.0
    cy = size / 2.0
    ring_outer = size * 0.45
    ring_inner = size * 0.30
    planet_radius = size * 0.255
    sign_label_radius = size * 0.41
    house_label_radius = size * 0.335

    sign_lines: list[str] = []
    sign_labels: list[str] = []
    for idx, sign in enumerate(ZODIAC_SIGNS):
        start_lon = idx * 30.0
        x1, y1 = _polar_xy(cx, cy, ring_inner, start_lon)
        x2, y2 = _polar_xy(cx, cy, ring_outer, start_lon)
        sign_lines.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            'stroke="#334155" stroke-width="1.6" opacity="0.85" />'
        )

        mid_lon = start_lon + 15.0
        lx, ly = _polar_xy(cx, cy, sign_label_radius, mid_lon)
        sign_labels.append(
            f'<text x="{lx:.2f}" y="{ly:.2f}" text-anchor="middle" dominant-baseline="middle" '
            'font-size="21" font-family="Menlo, Consolas, monospace" fill="#e2e8f0">'
            f"{sign[:3]}</text>"
        )

    house_lines: list[str] = []
    house_labels: list[str] = []
    cusps = report.snapshot.house_cusps or []
    if len(cusps) == 12:
        for idx, cusp in enumerate(cusps):
            hx1, hy1 = _polar_xy(cx, cy, ring_inner * 0.92, cusp)
            hx2, hy2 = _polar_xy(cx, cy, ring_outer * 0.98, cusp)
            house_lines.append(
                f'<line x1="{hx1:.2f}" y1="{hy1:.2f}" x2="{hx2:.2f}" y2="{hy2:.2f}" '
                f'stroke="{accent_color}" stroke-width="2.0" opacity="0.95" />'
            )
            mid = (cusp + 15.0) % 360.0
            tx, ty = _polar_xy(cx, cy, house_label_radius, mid)
            house_labels.append(
                f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="middle" dominant-baseline="middle" '
                f'font-size="16" font-family="Menlo, Consolas, monospace" fill="{accent_color}">{idx + 1}</text>'
            )

    points: list[str] = []
    point_labels: list[str] = []
    legend_lines: list[str] = []
    focus_positions = [pos for pos in report.snapshot.positions if pos.name in PLANET_STYLE]
    for idx, position in enumerate(focus_positions):
        x, y = _polar_xy(cx, cy, planet_radius, position.longitude)
        color = PLANET_STYLE.get(position.name, "#f8fafc")
        points.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="6.2" fill="{color}" stroke="#0f172a" stroke-width="1.1" />'
        )
        point_labels.append(
            f'<text x="{x:.2f}" y="{(y - 14):.2f}" text-anchor="middle" dominant-baseline="middle" '
            'font-size="12" font-family="Menlo, Consolas, monospace" fill="#f8fafc">'
            f"{position.name[:2].upper()}</text>"
        )
        legend_y = size * 0.14 + (idx * 24)
        legend_lines.append(
            f'<circle cx="{size * 0.78:.2f}" cy="{legend_y:.2f}" r="5.0" fill="{color}" />'
            f'<text x="{size * 0.80:.2f}" y="{legend_y + 1.5:.2f}" font-size="14" '
            'font-family="Menlo, Consolas, monospace" fill="#cbd5e1">'
            f"{position.name} {position.sign}</text>"
        )

    background = (
        '<defs>'
        '<radialGradient id="wheelBg" cx="35%" cy="25%" r="85%">'
        '<stop offset="0%" stop-color="#0b1324" />'
        '<stop offset="60%" stop-color="#101b31" />'
        '<stop offset="100%" stop-color="#0a1223" />'
        "</radialGradient>"
        "</defs>"
    )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  {background}
  <rect x="0" y="0" width="{size}" height="{size}" fill="url(#wheelBg)" />
  <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ring_outer:.2f}" fill="none" stroke="{accent_color}" stroke-width="3.2" />
  <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ring_inner:.2f}" fill="none" stroke="#334155" stroke-width="2.4" />
  {''.join(sign_lines)}
  {''.join(house_lines)}
  {''.join(sign_labels)}
  {''.join(house_labels)}
  <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{ring_inner * 0.64:.2f}" fill="#0f172a" stroke="#1e293b" stroke-width="1.2" />
  {''.join(points)}
  {''.join(point_labels)}
  <text x="{size * 0.08:.2f}" y="{size * 0.09:.2f}" font-size="34" font-family="Menlo, Consolas, monospace" fill="{accent_color}" font-weight="700">{brand_title}</text>
  <text x="{size * 0.08:.2f}" y="{size * 0.12:.2f}" font-size="15" font-family="Menlo, Consolas, monospace" fill="#94a3b8">
    Natal Wheel • {report.sign} • {report.birth.date.isoformat()}
  </text>
  {''.join(legend_lines)}
</svg>
"""


def build_natal_wheel_png(
    report: NatalBirthchartResponse,
    *,
    accent_color: str = ACCENT_DEFAULT,
    size: int = 1080,
    brand_title: str = "OPASTRO",
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
    )
    return cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=size, output_height=size)


def build_house_overlay_map(report: NatalBirthchartResponse) -> dict[str, Any]:
    cusps = report.snapshot.house_cusps or []
    house_rows: list[dict[str, Any]] = []
    positions = [pos for pos in report.snapshot.positions if pos.name in PLANET_STYLE]

    if len(cusps) == 12:
        signs = [ZODIAC_SIGNS[int((cusp % 360.0) // 30)] for cusp in cusps]
        for idx, cusp in enumerate(cusps):
            house_no = idx + 1
            next_cusp = cusps[(idx + 1) % 12]
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
                    "start_longitude": round(float(cusp % 360.0), 6),
                    "end_longitude": round(float(next_cusp % 360.0), 6),
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

    return {
        "report_type": report.report_type.value,
        "sign": report.sign,
        "birth_date": report.birth.date.isoformat(),
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
    brand_url: str = "https://opastro.com",
    premium_url: str = "https://numerologyapi.com",
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
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

    title_style = styles["Heading1"].clone("title")
    title_style.textColor = accent
    subtitle_style = styles["Heading3"].clone("subtitle")
    subtitle_style.textColor = colors.HexColor("#0f172a")
    body_style = styles["BodyText"].clone("body")
    body_style.leading = 14
    body_style.spaceAfter = 6
    small_style = styles["BodyText"].clone("small")
    small_style.fontSize = 9.5
    small_style.textColor = colors.HexColor("#475569")

    story = [
        Paragraph(f"{brand_title} Natal Birthchart Report", title_style),
        Paragraph(
            f"Birth Date: {report.birth.date.isoformat()} • Sun Sign: {report.sign} • "
            f"Rising Sign: {report.snapshot.rising_sign or 'N/A'}",
            small_style,
        ),
        Paragraph(f"{brand_url} • Premium narrative upgrade: {premium_url}", small_style),
        Spacer(1, 8),
    ]

    planet_rows = [["Planet", "Sign", "House", "Retro"]]
    for position in sorted([p for p in report.snapshot.positions if p.name in PLANET_STYLE], key=lambda x: x.name):
        planet_rows.append(
            [
                position.name,
                position.sign,
                str(position.house or "-"),
                "yes" if position.retrograde else "no",
            ]
        )
    planet_table = Table(planet_rows, colWidths=[52 * mm, 32 * mm, 22 * mm, 22 * mm], repeatRows=1)
    planet_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), accent),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#94a3b8")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
            ]
        )
    )
    story.append(Paragraph("Planetary Snapshot", subtitle_style))
    story.append(planet_table)
    story.append(Spacer(1, 10))

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
            for activation in premium.timing_overlay.activations[:8]:
                story.append(
                    Paragraph(
                        f"{activation.start_date.isoformat()} to {activation.end_date.isoformat()} — "
                        f"{activation.transit_planet} {activation.aspect} {activation.natal_planet} "
                        f"(intensity {activation.intensity:.2f})",
                        body_style,
                    )
                )
                story.append(Paragraph(activation.summary, small_style))

    overlay_json = json.dumps(build_house_overlay_map(report), indent=2)
    story.append(Spacer(1, 8))
    story.append(Paragraph("House Overlay Map (JSON excerpt)", subtitle_style))
    story.append(Paragraph(overlay_json[:1800].replace("\n", "<br/>"), small_style))

    def _paint_brand(canvas, doc_obj) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(accent)
        canvas.drawString(14 * mm, 7 * mm, f"{brand_title} • {brand_url}")
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(200 * mm, 7 * mm, f"Generated: {date.today().isoformat()}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_paint_brand, onLaterPages=_paint_brand)
    return stream.getvalue()
