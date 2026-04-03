# Architecture

## Overview

Opastro is a deterministic pipeline:

1. Resolve runtime config and ephemeris mode
2. Build period time window (`daily`, `weekly`, `monthly`, `yearly`)
3. Compute celestial snapshots/events with Swiss Ephemeris
4. Aggregate period metrics and notable events
5. Derive factor map per period/section
6. Render section insights with open-core lite narrative layer
7. Return response and cache by deterministic key

## High-Level Components

- `api.py` — FastAPI routes, cache orchestration, metrics
- `service.py` — core orchestration across compute + render
- `ephemeris.py` — body positions, aspects, houses, chart snapshots
- `aggregation.py` — period sampling + event summarization
- `interpretation/renderer.py` — scoring + deterministic narrative composition
- `models.py` — request/response schemas and enums
- `cache.py` — in-memory TTL cache + Redis adapter

## Determinism Guarantees

- Stable factor ordering by period
- Stable seeded phrase selection
- Stable cache-key generation (`cache_keys.py`)
- Same input contract -> same output shape and deterministic phrasing choice path

## Sign Mode vs Birth Mode

### Sign mode
- Input: `sign` (+ optional `target_date`)
- No precise house frame
- Fastest path and best cache hit rates

### Birth mode
- Input: `birth.date` and optionally `birth.time` + coordinates
- If `time` + coordinates are present, house frame is applied
- Enables house-focused factor values and richer section specificity

## Open-Core Rendering Model

- Uses deterministic phrase banks in code (`renderer.py`)
- Does not require external premium content packs
- Includes section-specific cadence profiles for monthly/yearly longform outputs
- Includes deterministic cadence connectors for smoother transitions

## API + Cache Flow

1. Validate request body
2. Compute tenant-aware cache key
3. Return cached payload when present
4. Generate via `HoroscopeService` on cache miss
5. Persist JSON to cache with TTL
6. Return response model

## Startup Healthcheck

On API startup:
- If `CONTENT_HEALTHCHECK_DISABLE=1` -> skipped
- If `content_root` is not configured (default open-core) -> skipped
- If enabled + content root present -> runs schema/content checks

## Packaging

- `pyproject.toml` + `setup.cfg` + `setup.py`
- Console script entrypoint: `opastro`
- Package data includes `src/horoscope_engine/data/default_rules.json`
