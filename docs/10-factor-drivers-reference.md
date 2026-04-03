# Factor Drivers Reference

This document mirrors the active factor system in `src/horoscope_engine/interpretation/renderer.py`.

## Factor Order by Period

### Daily

Order:
1. `sun_in_sign`
2. `moon_in_sign`
3. `rising_sign` (only when houses are available)
4. `transits_archetypes`
5. `aspects`
6. `daily_house_focus` (only when houses are available)

### Weekly

Order:
1. `sun_in_sign`
2. `moon_in_sign`
3. `weekly_moon_phase`
4. `transits_archetypes`
5. `aspects`
6. `planetary_focus`
7. `retrograde_archetypes`
8. `ingress_archetypes`
9. `weekly_theme_archetypes`
10. `weekly_house_focus` (when houses are available)

### Monthly

Order:
1. `sun_in_sign`
2. `monthly_lunation_archetypes`
3. `transits_archetypes`
4. `aspects`
5. `planetary_focus`
6. `retrograde_archetypes`
7. `ingress_archetypes`
8. `eclipse_archetypes`
9. `outer_planet_focus`
10. `monthly_theme_archetypes`
11. `monthly_house_focus` (when houses are available)

### Yearly

Order:
1. `jupiter_in_sign`
2. `saturn_in_sign`
3. `chiron_in_sign`
4. `transits_archetypes`
5. `aspects`
6. `planetary_focus`
7. `retrograde_archetypes`
8. `ingress_archetypes`
9. `eclipse_archetypes`
10. `outer_planet_focus`
11. `nodal_axis`
12. `yearly_house_focus` (when houses are available)
13. `yearly_theme_archetypes`

## Weight Map by Period

### Daily

| Factor | Weight |
|---|---|
| `sun_in_sign` | `1.00` |
| `moon_in_sign` | `1.15` |
| `rising_sign` | `1.00` |
| `transits_archetypes` | `1.30` |
| `aspects` | `1.20` |
| `daily_house_focus` | `1.08` |

### Weekly

| Factor | Weight |
|---|---|
| `sun_in_sign` | `0.90` |
| `moon_in_sign` | `0.95` |
| `weekly_moon_phase` | `1.05` |
| `transits_archetypes` | `1.25` |
| `aspects` | `1.15` |
| `planetary_focus` | `1.10` |
| `retrograde_archetypes` | `1.15` |
| `ingress_archetypes` | `1.05` |
| `weekly_theme_archetypes` | `1.20` |
| `weekly_house_focus` | `1.08` |

### Monthly

| Factor | Weight |
|---|---|
| `sun_in_sign` | `0.85` |
| `monthly_lunation_archetypes` | `1.20` |
| `transits_archetypes` | `1.20` |
| `aspects` | `1.10` |
| `planetary_focus` | `1.15` |
| `retrograde_archetypes` | `1.15` |
| `ingress_archetypes` | `1.05` |
| `eclipse_archetypes` | `1.20` |
| `outer_planet_focus` | `1.10` |
| `monthly_theme_archetypes` | `1.25` |
| `monthly_house_focus` | `1.15` |

### Yearly

| Factor | Weight |
|---|---|
| `jupiter_in_sign` | `1.10` |
| `saturn_in_sign` | `1.10` |
| `chiron_in_sign` | `1.00` |
| `transits_archetypes` | `1.10` |
| `aspects` | `1.00` |
| `planetary_focus` | `1.20` |
| `retrograde_archetypes` | `1.10` |
| `ingress_archetypes` | `1.00` |
| `eclipse_archetypes` | `1.20` |
| `outer_planet_focus` | `1.15` |
| `nodal_axis` | `1.15` |
| `yearly_house_focus` | `1.20` |
| `yearly_theme_archetypes` | `1.30` |

## House Focus Keys

Supported keys:
- `house_1` ... `house_12`

House focus appears as:
- `daily_house_focus`
- `weekly_house_focus`
- `monthly_house_focus`
- `yearly_house_focus`

These require enough house context (typically birth time + coordinates).

## Report-Specific Factor Allowlists

## Birthday reports (`report_type = birthday`)

Birthday reports always render yearly period and allow only:
- `yearly_theme_archetypes`
- `yearly_house_focus`
- `planetary_focus`
- `transits_archetypes`
- `aspects`

## Planet reports (`report_type = planet`)

Planet reports use period-specific allowlists:

- Daily: `transits_archetypes`, `aspects`, `daily_house_focus`
- Weekly: `planetary_focus`, `transits_archetypes`, `aspects`, `weekly_house_focus`, `weekly_theme_archetypes`, `weekly_moon_phase`
- Monthly: `planetary_focus`, `transits_archetypes`, `aspects`, `monthly_house_focus`, `monthly_theme_archetypes`, `monthly_lunation_archetypes`, `eclipse_archetypes`, `retrograde_archetypes`, `ingress_archetypes`
- Yearly: `planetary_focus`, `transits_archetypes`, `aspects`, `yearly_house_focus`, `yearly_theme_archetypes`, `eclipse_archetypes`, `outer_planet_focus`, `nodal_axis`

## Deterministic Behavior Notes

- Factor ordering is fixed by period constants.
- Factor values are computed from snapshot + metrics + period events.
- Theme/archetype picks use stable seeded selection.
- Same input payload produces the same factor map.
