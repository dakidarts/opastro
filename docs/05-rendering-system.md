# Rendering System

## Purpose

Render deterministic, section-aware horoscope narratives from computed factors.

Open-core rendering is intentionally lightweight and fully code-defined.

## Inputs

Renderer receives:
- `sign`
- `period`
- `sections[]`
- `snapshot` (positions, aspects, optional houses)
- `metrics` (aspect counts, retrogrades, sign changes)
- `period_events`
- optional `focus_body` (planet report)

## Main Stages

1. Compute section scores (`momentum`, `clarity`, `opportunity`, `focus`, `stability`, `connection`)
2. Derive intensity bucket (`quiet|steady|elevated|high`)
3. Build period factor specs in deterministic order
4. Build factor details with lite meaning/action/caution/reflection snippets
5. Compose summary + highlights + cautions + actions
6. Apply smoothing and deterministic phrase variation

## Factor Orders

- Daily: `sun_in_sign`, `moon_in_sign`, `rising_sign`, `transits_archetypes`, `aspects`, `daily_house_focus`
- Weekly: includes `weekly_moon_phase`, `planetary_focus`, `weekly_theme_archetypes`, `weekly_house_focus`
- Monthly: includes lunation/eclipses/theme/house focus
- Yearly: includes Jupiter/Saturn/Chiron + nodal/outer-planet + yearly theme/house focus

## Longform Cadence (Monthly/Yearly)

Monthly and yearly summaries use section-specific cadence profiles.
Each section follows a deterministic ordering of blocks such as:
- intro
- thesis
- breath line
- theme line
- event arc
- influence lines
- contrast line
- dynamic close
- actionable close

This gives each section a distinct paragraph rhythm while preserving deterministic behavior.

## Cadence Bridges

A sparse connector layer inserts deterministic single-line bridge phrases between major longform blocks.

Properties:
- section-specific phrase bank
- deterministic seed selection
- only inserted on selected transitions to avoid bloat

## Deterministic Variation

Renderer uses stable seed selection (`stable_index`) for:
- intro templates
- thesis/contrast variants
- event anchor sets
- support tails
- cadence bridges

## Output Slots

For each section:
- `summary`
- `highlights[]`
- `cautions[]`
- `actions[]`
- `scores`
- `intensity`
- `factor_details[]`

## Open-Core Boundary

Current open-core renderer does **not** load premium meaning packs.
`content_repository` is optional and disabled by default.
