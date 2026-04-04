# Request / Response Contract

This document summarizes the active Pydantic contracts in `src/horoscope_engine/models.py`.

## Enums

### `Period`
- `daily`
- `weekly`
- `monthly`
- `yearly`

### `Section`
- `general`
- `love_singles`
- `love_couples`
- `career`
- `friendship`
- `health`
- `money`
- `communication`
- `lifestyle`

### `PlanetName`
- `sun`, `moon`, `mercury`, `venus`, `mars`, `jupiter`, `saturn`, `uranus`, `neptune`, `pluto`, `chiron`

### Other enums
- `ZodiacSystem`: `sidereal`, `tropical`
- `AyanamsaSystem`: `lahiri`, `fagan_bradley`, `krishnamurti`, `raman`, `yukteswar`
- `HouseSystem`: `placidus`, `whole_sign`, `equal`, `koch`
- `NodeType`: `true`, `mean`

## Request Models

## `HoroscopeRequest`

Fields:
- `period` (required)
- `sign` (optional, uppercase zodiac sign)
- `target_date` (optional, ISO date)
- `birth` (optional)
- `sections` (optional list of `Section`)
- `zodiac_system`, `ayanamsa`, `house_system`, `node_type` (optional)
- `tenant_id` (optional, max length 64)

Validation notes:
- `sign` is normalized to uppercase and validated against zodiac signs.
- Section `love` is rejected; use `love_singles` and/or `love_couples`.
- `sign` or `birth` must be present at service level.

## `BirthdayHoroscopeRequest`

Fields:
- `sign` (optional)
- `target_date` (optional; required if `birth` missing)
- `birth` (optional)
- `sections`, system overrides, `tenant_id` (optional)

## `PlanetHoroscopeRequest`

Fields:
- `period` (required)
- `planet` (required)
- `sign`/`birth` and other optional fields similar to `HoroscopeRequest`

## `NatalBirthchartRequest`

Fields:
- `birth` (required)
- `zodiac_system`, `ayanamsa`, `house_system`, `node_type` (optional)
- `tenant_id` (optional, max length 64)

## Shared Birth Model

```json
{
  "date": "1992-06-15",
  "time": "09:30",
  "coordinates": {"latitude": 4.0511, "longitude": 9.7679},
  "timezone": "Africa/Douala"
}
```

## Response Model: `HoroscopeResponse`

Top-level fields:
- `report_type`: `horoscope` | `birthday` | `planet`
- `sign`
- `period`
- `start`, `end`
- `data`
- `sections`

## Response Model: `NatalBirthchartResponse`

Top-level fields:
- `report_type`: `natal_birthchart`
- `sign` (derived from natal sun sign)
- `birth`
- `snapshot` (`ChartSnapshot`)
- `notable_events` (list of strings)

## `data` (`PeriodCelestialData`)
- `period`, `start`, `end`
- `snapshot` (`ChartSnapshot`)
- `metrics` (`PeriodMetrics`, optional)
- `notable_events` (list of strings)
- `period_events` (structured event list)
- `factor_values` (map of factor type -> factor value)

## `sections[]` (`SectionInsight`)
- `section`
- `title`
- `summary`
- `highlights[]`
- `cautions[]`
- `actions[]`
- `scores` (`momentum`, `clarity`, `opportunity`, `focus`, `stability`, `connection`)
- `intensity` (`quiet` | `steady` | `elevated` | `high`)
- `factor_details[]`

## Example Response Skeleton

```json
{
  "report_type": "horoscope",
  "sign": "ARIES",
  "period": "daily",
  "start": "2026-04-03T00:00:00",
  "end": "2026-04-04T00:00:00",
  "data": {
    "period": "daily",
    "snapshot": {"sun_sign": "PISCES", "moon_sign": "LIBRA", "positions": [], "aspects": []},
    "metrics": {"sample_count": 1, "aspect_counts": {}, "retrograde_bodies": [], "sign_changes": []},
    "notable_events": [],
    "period_events": [],
    "factor_values": {"sun_in_sign": "PISCES", "moon_in_sign": "LIBRA"}
  },
  "sections": [
    {
      "section": "general",
      "title": "General daily outlook: ...",
      "summary": "...",
      "highlights": ["..."],
      "cautions": ["..."],
      "actions": ["..."],
      "scores": {"momentum": 60.0, "clarity": 58.0, "opportunity": 62.0, "focus": 59.0, "stability": 55.0, "connection": 57.0},
      "intensity": "elevated",
      "factor_details": []
    }
  ]
}
```
