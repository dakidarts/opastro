# Factor Drivers Reference

Factor drivers are the deterministic inputs used to select and score section lines.

## Core Factors

- `sun_in_sign`
- `moon_in_sign`
- `transits_archetypes`
- `aspects`
- `planetary_focus`

## Period-Specific Factors

| Period | Additional factors |
|---|---|
| Daily | `daily_house_focus` |
| Weekly | `weekly_house_focus`, `weekly_theme_archetypes`, `weekly_moon_phase` |
| Monthly | `monthly_house_focus`, `monthly_theme_archetypes`, `monthly_lunation_archetypes`, `eclipse_archetypes`, `retrograde_archetypes`, `ingress_archetypes` |
| Yearly | `yearly_house_focus`, `yearly_theme_archetypes`, `eclipse_archetypes`, `outer_planet_focus`, `nodal_axis` |

## Birthday Allowlist

Birthday reports restrict factor drivers to:
- `yearly_theme_archetypes`
- `yearly_house_focus`
- `planetary_focus`
- `transits_archetypes`
- `aspects`

## Planet Allowlist by Period

Planet-focused reports filter to a smaller set of drivers relevant to the selected planet.

## Advanced Natal Factors

### Fixed Stars

When `include_fixed_stars=true` on a natal request, the snapshot includes conjunctions to major fixed stars:

| Star | Nature | Magnitude | Recommended Orb |
|---|---|---|---|
| Regulus | mixed | 1.35 | 2.0° |
| Spica | benefic | 0.98 | 2.0° |
| Algol | malefic | 2.12 | 1.5° |
| Antares | malefic | 0.96 | 2.0° |
| Aldebaran | malefic | 0.85 | 2.0° |
| Pollux | mixed | 1.14 | 1.5° |
| Vega | benefic | 0.03 | 2.0° |
| Sirius | benefic | -1.46 | 2.0° |
| Arcturus | benefic | -0.05 | 2.0° |
| Deneb Algedi | mixed | 2.85 | 1.5° |

Notes:
- Fixed stars require the `sefstars.txt` ephemeris file.
- Run `opastro doctor --download-ephemeris` to fetch it automatically.
- If the file is missing, `fixed_stars[]` returns an empty list silently.

### Arabic Parts

When `include_arabic_parts=true` and house data is available, the snapshot includes:

- **Part of Fortune** = Ascendant + Moon − Sun (day birth) / Ascendant + Sun − Moon (night birth)
- **Part of Spirit** = Ascendant + Sun − Moon (day birth) / Ascendant + Moon − Sun (night birth)

Notes:
- Arabic parts require both `birth.time` and `birth.coordinates` (for ascendant calculation).
- The `formula` field in the response indicates which formula was used based on day/night birth.
