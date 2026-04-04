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
- `user_name` (optional, chart personalization display name)
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
- `user_name` (optional personalization value, echoed from request/profile)
- `snapshot` (`ChartSnapshot`)
- `notable_events` (list of strings)
- `premium_insights` (optional)

### `premium_insights` (`NatalPremiumInsights`)

Fields:
- `dominant_signature`
- `aspect_patterns[]`
- `planet_conditions[]`
- `house_rulership[]`
- `life_area_vectors[]`
- `timing_overlay`
- `relationship_module`
- `career_module`

`dominant_signature` includes:
- `element_balance`
- `modality_balance`
- `dominant_element`
- `dominant_modality`
- `angular_emphasis`
- `top_planets[]`

`aspect_patterns[]` item includes:
- `pattern` (e.g. `grand_trine`, `t_square`, `kite`, `stellium`)
- `bodies[]`
- `confidence` (`0.0` to `1.0`)
- `description`

`planet_conditions[]` item includes:
- `planet`
- `sign`
- `house`
- `retrograde`
- `strength`
- `notes[]`

`house_rulership[]` item includes:
- `house`
- `area`
- `cusp_sign`
- `rulers[]`
- `ruler_placements[]` (`planet`, `sign`, `house`, `retrograde`, `strength`)
- `emphasis`
- `notes[]`

`life_area_vectors[]` item includes:
- `area`
- `houses[]`
- `score` (`0` to `100`)
- `emphasis` (`quiet` | `steady` | `elevated` | `high`)
- `drivers[]`

`timing_overlay` includes:
- `generated_for`
- `activations[]` (`start_date`, `end_date`, `transit_planet`, `natal_planet`, `aspect`, `orb`, `intensity`, `summary`)

`relationship_module` / `career_module` include:
- `score` (`0` to `100`)
- `highlights[]`
- `cautions[]`
- `actions[]`

## Natal Asset Contracts

These endpoints reuse `NatalBirthchartRequest`:
- `POST /natal-birthchart/wheel.svg` -> `image/svg+xml` (optional query: `theme=night|day`)
- `POST /natal-birthchart/wheel.png` -> `image/png` (optional query: `theme=night|day`)
- `POST /natal-birthchart/house-overlay` -> JSON map:
- `report_type`, `sign`, `birth_date`, `user_name`
- `sign_polarity`, `element_percentages` (`fire`, `earth`, `air`, `water`)
- `ascendant` / `midheaven` (`sign`, `longitude`)
- `house_system`, `rising_sign`
- `houses[]` (`house`, `cusp_longitude`, `cusp_sign`, `start_longitude`, `end_longitude`, `midpoint_longitude`, `arc_degrees`, `wraps_aries`, `occupants[]`)
- `life_area_vectors[]` (`area`, `score`, `emphasis`, `drivers[]`)
- `POST /natal-birthchart/report.pdf` -> `application/pdf` (optional query: `theme=night|day`)

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
