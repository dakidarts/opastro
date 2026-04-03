from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .ephemeris import EphemerisEngine
from .models import Period, PeriodEvent, PeriodMetrics, ChartSnapshot


@dataclass
class AggregationResult:
    snapshot: ChartSnapshot
    metrics: PeriodMetrics
    notable_events: List[str]
    period_events: List[PeriodEvent]


MAJOR_EXACT_ASPECTS = {"conjunction", "opposition", "trine", "square", "sextile"}
NODAL_BODIES = {"North Node", "South Node"}

BODY_IMPORTANCE = {
    "Sun": 1.20,
    "Moon": 1.05,
    "Mercury": 1.10,
    "Venus": 1.10,
    "Mars": 1.15,
    "Jupiter": 1.35,
    "Saturn": 1.35,
    "Uranus": 1.20,
    "Neptune": 1.20,
    "Pluto": 1.20,
    "Chiron": 1.15,
    "North Node": 1.25,
    "South Node": 1.15,
}

SECTION_BIAS_BY_BODY = {
    "Sun": {"general": 0.9, "career": 0.5, "lifestyle": 0.5},
    "Moon": {"general": 0.8, "love_singles": 0.4, "love_couples": 0.4, "friendship": 0.3, "health": 0.3},
    "Mercury": {"communication": 0.9, "career": 0.4, "friendship": 0.3},
    "Venus": {"love_singles": 0.9, "love_couples": 1.0, "money": 0.5, "friendship": 0.4},
    "Mars": {"career": 0.8, "health": 0.6, "love_singles": 0.3},
    "Jupiter": {"career": 0.8, "money": 0.8, "general": 0.5, "lifestyle": 0.4},
    "Saturn": {"career": 0.8, "health": 0.5, "money": 0.5, "general": 0.4},
    "Uranus": {"lifestyle": 0.7, "communication": 0.4, "general": 0.4},
    "Neptune": {"health": 0.5, "lifestyle": 0.6, "general": 0.4},
    "Pluto": {"general": 0.6, "career": 0.5, "love_couples": 0.4},
    "Chiron": {"health": 0.8, "love_couples": 0.4, "general": 0.4},
    "North Node": {"general": 0.8, "career": 0.4, "love_singles": 0.3},
    "South Node": {"general": 0.7, "lifestyle": 0.4, "friendship": 0.3},
}


def _sample_schedule(period: Period, start: datetime, end: datetime) -> List[datetime]:
    if period == Period.DAILY:
        return [start + (end - start) / 2]
    if period == Period.WEEKLY:
        return [start + timedelta(days=i, hours=12) for i in range(7)]
    if period == Period.MONTHLY:
        step = max(1, (end - start).days // 6)
        return [start + timedelta(days=i, hours=12) for i in range(0, (end - start).days, step)][:6]
    if period == Period.YEARLY:
        return [datetime(start.year, m, 15, 12) for m in range(1, 13)]
    return [start + (end - start) / 2]


def _position_lookup(snapshot: ChartSnapshot) -> Dict[str, object]:
    return {pos.name: pos for pos in snapshot.positions}


def _angle_distance(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def _moon_phase_sep(snapshot: ChartSnapshot) -> Optional[float]:
    lookup = _position_lookup(snapshot)
    sun = lookup.get("Sun")
    moon = lookup.get("Moon")
    if not sun or not moon:
        return None
    return (moon.longitude - sun.longitude) % 360.0


def _eclipse_distances(snapshot: ChartSnapshot) -> Optional[Tuple[float, float, float]]:
    lookup = _position_lookup(snapshot)
    sun = lookup.get("Sun")
    moon = lookup.get("Moon")
    north = lookup.get("North Node")
    south = lookup.get("South Node")
    if not sun or not moon:
        return None

    sun_lon = sun.longitude
    moon_lon = moon.longitude
    north_lon = north.longitude if north else None
    south_lon = south.longitude if south else None

    if north_lon is None and south_lon is not None:
        north_lon = (south_lon + 180.0) % 360.0
    if south_lon is None and north_lon is not None:
        south_lon = (north_lon + 180.0) % 360.0
    if north_lon is None:
        north_lon = 0.0
    if south_lon is None:
        south_lon = 180.0

    sun_moon_sep = _angle_distance(sun_lon, moon_lon)
    sun_node_dist = min(_angle_distance(sun_lon, north_lon), _angle_distance(sun_lon, south_lon))
    moon_node_dist = min(_angle_distance(moon_lon, north_lon), _angle_distance(moon_lon, south_lon))
    return sun_moon_sep, sun_node_dist, moon_node_dist


def _section_bias(event_type: str, body1: Optional[str], body2: Optional[str]) -> Dict[str, float]:
    bias: Dict[str, float] = {"general": 0.6}
    for body in (body1, body2):
        if not body:
            continue
        for section, weight in SECTION_BIAS_BY_BODY.get(body, {}).items():
            bias[section] = bias.get(section, 0.0) + weight

    if event_type in ("eclipse", "lunation"):
        bias["general"] = bias.get("general", 0.0) + 0.6
        bias["love_singles"] = bias.get("love_singles", 0.0) + 0.2
        bias["love_couples"] = bias.get("love_couples", 0.0) + 0.2
    return bias


def _event_priority(event_type: str, body1: Optional[str], body2: Optional[str], exactness: Optional[float]) -> float:
    base = {
        "ingress": 1.15,
        "station": 1.35,
        "lunation": 1.55,
        "eclipse": 1.80,
        "exact_aspect": 1.10,
        "retrograde_emphasis": 0.90,
    }.get(event_type, 1.0)
    body_weight = max(BODY_IMPORTANCE.get(body1 or "", 1.0), BODY_IMPORTANCE.get(body2 or "", 1.0))
    exact_bonus = 0.0
    if exactness is not None:
        exact_bonus = max(0.0, 1.0 - min(1.0, exactness / 8.0)) * 0.4
    return round(base * body_weight + exact_bonus, 3)


def _event_key(event: PeriodEvent) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str], str]:
    return (
        event.event_type,
        event.body1,
        event.body2,
        event.sign,
        event.aspect,
        event.timestamp.date().isoformat(),
    )


def _cluster_window_days(period: Period) -> int:
    if period == Period.DAILY:
        return 1
    if period == Period.WEEKLY:
        return 7
    if period == Period.MONTHLY:
        return 14
    return 45


def _event_signature(event: PeriodEvent) -> Tuple[str, Tuple[str, ...], Optional[str], Optional[str], Optional[str]]:
    bodies = tuple(sorted([body for body in (event.body1, event.body2) if body]))
    station_state = None
    if event.event_type == "station":
        lower = event.description.lower()
        if "retrograde" in lower:
            station_state = "retrograde"
        elif "direct" in lower:
            station_state = "direct"
    return (
        event.event_type,
        bodies,
        event.aspect,
        event.sign,
        station_state,
    )


def _event_rank(event: PeriodEvent) -> Tuple[int, float, float, datetime]:
    has_exactness = 0 if event.exactness is not None else 1
    exactness = event.exactness if event.exactness is not None else 999.0
    return (has_exactness, exactness, -event.narrative_priority, event.timestamp)


def _is_nodal_pair(body1: Optional[str], body2: Optional[str]) -> bool:
    pair = {body for body in (body1, body2) if body}
    return pair == NODAL_BODIES


def _dedupe_period_events(period: Period, period_events: List[PeriodEvent]) -> List[PeriodEvent]:
    # First pass: remove strict duplicates by event_type/body/sign/aspect/date.
    strict: List[PeriodEvent] = []
    seen_keys = set()
    for event in sorted(period_events, key=lambda e: (e.timestamp, -e.narrative_priority)):
        key = _event_key(event)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        strict.append(event)

    # Second pass: cluster repeated windows (exact aspects/lunations/eclipses and similar repeated signatures).
    window_days = _cluster_window_days(period)
    clustered: Dict[Tuple[str, Tuple[str, ...], Optional[str], Optional[str], Optional[str]], List[PeriodEvent]] = {}

    for event in strict:
        signature = _event_signature(event)
        bucket = clustered.setdefault(signature, [])
        merged = False
        for idx, existing in enumerate(bucket):
            delta_days = abs((event.timestamp - existing.timestamp).total_seconds()) / 86400.0
            if delta_days <= window_days:
                if _event_rank(event) < _event_rank(existing):
                    bucket[idx] = event
                merged = True
                break
        if not merged:
            bucket.append(event)

    flattened: List[PeriodEvent] = []
    for events in clustered.values():
        flattened.extend(events)
    return sorted(flattened, key=lambda e: (e.timestamp, -e.narrative_priority))


def aggregate_period(
    ephemeris: EphemerisEngine,
    period: Period,
    start: datetime,
    end: datetime,
    include_houses: bool = False,
    coordinates: Optional[Tuple[float, float]] = None,
) -> AggregationResult:
    samples = _sample_schedule(period, start, end)
    aspect_counts: Dict[str, int] = {}
    retrograde_bodies: Dict[str, int] = {}
    sign_changes: List[str] = []
    period_events: List[PeriodEvent] = []

    previous_snapshot: Optional[ChartSnapshot] = None
    snapshots: List[ChartSnapshot] = []

    for sample in samples:
        snapshot = ephemeris.chart_snapshot(sample, include_houses=include_houses, coordinates=coordinates)
        snapshots.append(snapshot)

        for aspect in snapshot.aspects:
            aspect_counts[aspect.aspect] = aspect_counts.get(aspect.aspect, 0) + 1
            if aspect.exact and aspect.aspect in MAJOR_EXACT_ASPECTS:
                # True/mean nodes are geometrically opposed by construction;
                # surfacing this as an "exact aspect event" creates repetitive timeline noise.
                if _is_nodal_pair(aspect.body1, aspect.body2):
                    continue
                description = (
                    f"{aspect.body1} {aspect.aspect} {aspect.body2} exact on {sample.strftime('%b %d')}"
                )
                period_events.append(
                    PeriodEvent(
                        timestamp=sample,
                        event_type="exact_aspect",
                        body1=aspect.body1,
                        body2=aspect.body2,
                        aspect=aspect.aspect,
                        exactness=aspect.orb,
                        narrative_priority=_event_priority("exact_aspect", aspect.body1, aspect.body2, aspect.orb),
                        section_bias=_section_bias("exact_aspect", aspect.body1, aspect.body2),
                        description=description,
                    )
                )

        for position in snapshot.positions:
            if position.retrograde:
                retrograde_bodies[position.name] = retrograde_bodies.get(position.name, 0) + 1

        if previous_snapshot:
            for position in snapshot.positions:
                prev = next((p for p in previous_snapshot.positions if p.name == position.name), None)
                if not prev:
                    continue
                if prev.sign != position.sign:
                    description = f"{position.name} enters {position.sign} on {sample.strftime('%b %d')}"
                    sign_changes.append(description)
                    period_events.append(
                        PeriodEvent(
                            timestamp=sample,
                            event_type="ingress",
                            body1=position.name,
                            sign=position.sign,
                            narrative_priority=_event_priority("ingress", position.name, None, None),
                            section_bias=_section_bias("ingress", position.name, None),
                            description=description,
                        )
                    )
                if not prev.retrograde and position.retrograde:
                    if position.name in NODAL_BODIES:
                        continue
                    description = f"{position.name} stations retrograde on {sample.strftime('%b %d')}"
                    period_events.append(
                        PeriodEvent(
                            timestamp=sample,
                            event_type="station",
                            body1=position.name,
                            narrative_priority=_event_priority("station", position.name, None, None),
                            section_bias=_section_bias("station", position.name, None),
                            description=description,
                        )
                    )
                if prev.retrograde and not position.retrograde:
                    if position.name in NODAL_BODIES:
                        continue
                    description = f"{position.name} stations direct on {sample.strftime('%b %d')}"
                    period_events.append(
                        PeriodEvent(
                            timestamp=sample,
                            event_type="station",
                            body1=position.name,
                            narrative_priority=_event_priority("station", position.name, None, None),
                            section_bias=_section_bias("station", position.name, None),
                            description=description,
                        )
                    )

        phase_sep = _moon_phase_sep(snapshot)
        if phase_sep is not None:
            near_new = min(phase_sep, abs(360.0 - phase_sep))
            near_full = abs(phase_sep - 180.0)
            if near_new <= 12.0:
                description = f"New Moon window on {sample.strftime('%b %d')}"
                period_events.append(
                    PeriodEvent(
                        timestamp=sample,
                        event_type="lunation",
                        body1="Moon",
                        body2="Sun",
                        exactness=round(near_new, 2),
                        narrative_priority=_event_priority("lunation", "Moon", "Sun", near_new),
                        section_bias=_section_bias("lunation", "Moon", "Sun"),
                        description=description,
                    )
                )
            elif near_full <= 12.0:
                description = f"Full Moon window on {sample.strftime('%b %d')}"
                period_events.append(
                    PeriodEvent(
                        timestamp=sample,
                        event_type="lunation",
                        body1="Moon",
                        body2="Sun",
                        exactness=round(near_full, 2),
                        narrative_priority=_event_priority("lunation", "Moon", "Sun", near_full),
                        section_bias=_section_bias("lunation", "Moon", "Sun"),
                        description=description,
                    )
                )

        eclipse_dist = _eclipse_distances(snapshot)
        if eclipse_dist is not None:
            sun_moon_sep, sun_node_dist, moon_node_dist = eclipse_dist
            is_solar = min(sun_moon_sep, abs(360.0 - sun_moon_sep)) <= 12.0 and sun_node_dist <= 18.0
            is_lunar = abs(sun_moon_sep - 180.0) <= 12.0 and moon_node_dist <= 18.0
            if is_solar or is_lunar:
                description = (
                    f"{'Solar' if is_solar else 'Lunar'} eclipse window on {sample.strftime('%b %d')}"
                )
                exactness = min(sun_node_dist, moon_node_dist)
                period_events.append(
                    PeriodEvent(
                        timestamp=sample,
                        event_type="eclipse",
                        body1="Sun" if is_solar else "Moon",
                        body2="North Node",
                        exactness=round(exactness, 2),
                        narrative_priority=_event_priority("eclipse", "Sun" if is_solar else "Moon", "North Node", exactness),
                        section_bias=_section_bias("eclipse", "Sun" if is_solar else "Moon", "North Node"),
                        description=description,
                    )
                )

        previous_snapshot = snapshot

    snapshot = snapshots[len(snapshots) // 2] if snapshots else ephemeris.chart_snapshot(start)

    unique_events: List[PeriodEvent] = _dedupe_period_events(period, period_events)

    for name in retrograde_bodies.keys():
        description = f"{name} retrograde emphasis"
        unique_events.append(
            PeriodEvent(
                timestamp=snapshot.timestamp,
                event_type="retrograde_emphasis",
                body1=name,
                narrative_priority=_event_priority("retrograde_emphasis", name, None, None),
                section_bias=_section_bias("retrograde_emphasis", name, None),
                description=description,
            )
        )

    ranked = sorted(unique_events, key=lambda e: (-e.narrative_priority, e.timestamp))
    selected_for_timeline = sorted(ranked[:24], key=lambda e: e.timestamp)
    notable_events: List[str] = []
    seen_descriptions = set()
    for event in selected_for_timeline:
        if event.description in seen_descriptions:
            continue
        seen_descriptions.add(event.description)
        notable_events.append(event.description)
        if len(notable_events) >= 12:
            break

    metrics = PeriodMetrics(
        sample_count=len(samples),
        aspect_counts=aspect_counts,
        retrograde_bodies=sorted(retrograde_bodies.keys()),
        sign_changes=sign_changes,
    )

    return AggregationResult(
        snapshot=snapshot,
        metrics=metrics,
        notable_events=notable_events,
        period_events=selected_for_timeline,
    )
