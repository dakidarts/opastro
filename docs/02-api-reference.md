# API Reference

Base URL (local): `http://127.0.0.1:8000`

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/horoscope` | Standard period report |
| `POST` | `/birthday-horoscope` | Birthday-cycle yearly report |
| `POST` | `/planet-horoscope` | Planet-focused report |
| `POST` | `/natal-birthchart` | Natal chart snapshot + sign derivation report |
| `POST` | `/natal-birthchart/wheel.svg` | Render natal wheel as SVG |
| `POST` | `/natal-birthchart/wheel.png` | Render natal wheel as PNG |
| `POST` | `/natal-birthchart/house-overlay` | Return natal house overlay JSON map |
| `POST` | `/natal-birthchart/report.pdf` | Download branded natal PDF report |
| `GET` | `/metrics` | Request/cache metrics snapshot |
| `POST` | `/admin/pregenerate` | Cache pre-generation utility |

## `POST /horoscope`

### Request body

```json
{
  "period": "daily",
  "sign": "ARIES",
  "target_date": "2026-04-03",
  "sections": ["general", "career"],
  "zodiac_system": "tropical",
  "ayanamsa": "lahiri",
  "house_system": "placidus",
  "node_type": "true",
  "tenant_id": "public"
}
```

Either `sign` or `birth` is required.
Default zodiac mode is `tropical` when `zodiac_system` is omitted.

### Optional birth payload

```json
{
  "birth": {
    "date": "1992-06-15",
    "time": "09:30",
    "coordinates": {"latitude": 4.0511, "longitude": 9.7679},
    "timezone": "Africa/Douala"
  }
}
```

### Response

Returns `HoroscopeResponse` (see [03-request-response-contract.md](./03-request-response-contract.md)).

## `POST /birthday-horoscope`

### Request body

```json
{
  "sign": "TAURUS",
  "target_date": "2026-04-03",
  "sections": ["general", "money"]
}
```

Notes:
- If `birth` is included, yearly range is aligned to the birthday cycle.
- If `birth` is omitted, `target_date` is required.

## `POST /planet-horoscope`

### Request body

```json
{
  "period": "monthly",
  "planet": "mercury",
  "sign": "TAURUS",
  "target_date": "2026-04-03",
  "sections": ["general", "communication"]
}
```

## `POST /natal-birthchart`

### Request body

```json
{
  "birth": {
    "date": "2004-06-14",
    "time": "09:30",
    "coordinates": {"latitude": 4.0511, "longitude": 9.7679},
    "timezone": "Africa/Douala"
  },
  "zodiac_system": "tropical",
  "house_system": "placidus"
}
```

Notes:
- `birth.date` is required.
- `birth.time` is optional (defaults to noon in engine logic).
- `rising_sign` and full `house_cusps` require both `birth.time` and coordinates.
- Alias route: `POST /natal-birthchart-report`.
- Response includes `premium_insights` with:
  - dominant signature and aspect patterns,
  - planet condition scoring,
  - house rulership intelligence + life-area vectors,
  - deterministic transit timing overlay windows,
  - relationship and career premium modules.

## Natal Asset Endpoints

All natal asset endpoints accept the same request body as `POST /natal-birthchart`.

- `POST /natal-birthchart/wheel.svg`  
  Returns `image/svg+xml` wheel chart output.
- `POST /natal-birthchart/wheel.png`  
  Returns `image/png` wheel chart output.
- `POST /natal-birthchart/house-overlay`  
  Returns JSON house overlay map with house spans, occupants, life-area vectors, sign polarity/element percentages, and ASC/MC angle data.
- `POST /natal-birthchart/report.pdf`  
  Returns `application/pdf` with branded sectioned natal summary.

## Headers

Optional tenant header (all report endpoints):

- `X-Tenant-Id: <tenant>`

Admin pregen header:

- `X-Admin-Token: <token>`

## `GET /metrics`

Response shape:

```json
{
  "requests": 42,
  "cache_hits": 30,
  "cache_misses": 12,
  "avg_latency_ms": 18.3
}
```

## `POST /admin/pregenerate`

### Request body

```json
{
  "period": "daily",
  "target_date": "2026-04-03",
  "tenant_id": "public"
}
```

Requires valid `X-Admin-Token` if `PREGEN_TOKEN` is configured.

## Error Handling

- `400` — invalid payload (validation/domain errors)
- `403` — invalid admin token
- `500` — server/runtime error

## Startup Healthcheck Behavior

- If `CONTENT_HEALTHCHECK_DISABLE=1`, startup content check is skipped.
- If no `content_root` is configured (default open-core mode), content check is skipped.
- `CONTENT_HEALTHCHECK_FAIL_FAST=1` only matters when content check runs.
