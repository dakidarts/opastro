# Troubleshooting

## Quick Diagnostic Flow

1. Run `opastro doctor`.
2. Confirm `python3` resolves to a Python `3.11+` runtime.
3. Re-run the same request with `--json` (CLI) or save exact API payload.
4. Check `/health` and `/metrics` when debugging API behavior.
5. Run tests: `PYTHONPATH=src python3 -m pytest -q`.
6. Inspect structured runtime errors: `opastro logger show --limit 10`.

## CLI Issues

### `opastro: command not found`

Cause:
- Package not installed in current environment.

Fix:

```bash
source .venv/bin/activate
python3 -m pip install opastro
# or editable install when working from source:
python3 -m pip install -e .
which opastro
```

### Mistyped command names

Symptom:
- `Unknown command 'horoscpoe'`

Behavior:
- CLI now returns close-match suggestions.

Example:
```bash
opastro horoscpoe
# Unknown command 'horoscpoe'. Did you mean: horoscope?
```

### `Runtime check : WARN` in `opastro doctor`

Cause:
- `python3` is not on a supported Python `3.11+` environment.

Fix:

```bash
python3 --version
which python3
python3 -m pip install opastro
# or editable install when working from source:
python3 -m pip install -e .
opastro doctor
```

Auto-remediation:

```bash
opastro doctor --fix --dry-run
opastro doctor --fix
```

### Inspecting uncaught CLI runtime errors

Behavior:
- Uncaught CLI exceptions are written to a local runtime error log with timestamp, command context, traceback, and suggested fixes.

Commands:

```bash
opastro logger show --limit 20
opastro logger tail
opastro logger path
opastro logger clear
```

### `ModuleNotFoundError: No module named 'horoscope_engine'`

Cause:
- Running module commands without editable install or missing `PYTHONPATH`.

Fix:

```bash
python3 -m pip install opastro
# or editable install when working from source:
python3 -m pip install -e .
# or, for direct module runs:
PYTHONPATH=src python3 -m uvicorn horoscope_engine.main:app --reload
```

## Request Validation Errors

### `sign or birth data is required`

Cause:
- Payload omitted both `sign` and `birth`.

Fix:

```json
{"period": "daily", "sign": "ARIES"}
```

or

```json
{"period": "daily", "birth": {"date": "1992-06-15"}}
```

### `Unsupported zodiac sign`

Cause:
- Invalid sign name.

Valid values:
- `ARIES`, `TAURUS`, `GEMINI`, `CANCER`, `LEO`, `VIRGO`, `LIBRA`, `SCORPIO`, `SAGITTARIUS`, `CAPRICORN`, `AQUARIUS`, `PISCES`

### `Section 'love' is no longer supported`

Cause:
- Legacy section used.

Fix:
- Use `love_singles` and/or `love_couples`.

## House / Personalization Issues

### `rising_sign` and `house_cusps` are `null`

Cause:
- Missing `birth.time` or missing `birth.coordinates`.

Fix:

```json
{
  "period": "daily",
  "birth": {
    "date": "1992-06-15",
    "time": "09:30",
    "coordinates": {"latitude": 4.0511, "longitude": 9.7679},
    "timezone": "Africa/Douala"
  }
}
```

Note:
- In the current codebase, daily personalized requests can include house framing and `daily_house_focus` when time + coordinates are provided.

### Personalized output seems unchanged

Cause:
- Same payload, same deterministic output.

Check:

```bash
PAYLOAD='{"period":"daily","sign":"ARIES","target_date":"2026-04-03"}'
RESP1=$(curl -s -X POST http://127.0.0.1:8000/horoscope -H "Content-Type: application/json" -d "$PAYLOAD")
RESP2=$(curl -s -X POST http://127.0.0.1:8000/horoscope -H "Content-Type: application/json" -d "$PAYLOAD")
diff <(echo "$RESP1" | jq -S .) <(echo "$RESP2" | jq -S .)
```

## Ephemeris Issues

### Unexpected sign placements / planets look off

Cause:
- Different `zodiac_system`/`ayanamsa` assumptions.

Fix:
- Use explicit payload fields (`zodiac_system`, `ayanamsa`, `house_system`, `node_type`) for reproducibility.

### Missing asteroid/planet warnings

Cause:
- Ephemeris files are incomplete or `SE_EPHE_PATH` is wrong.

Fix:

```bash
echo "$SE_EPHE_PATH"
ls -la "$SE_EPHE_PATH"
```

## API / Cache Issues

### `/admin/pregenerate` returns `403`

Cause:
- `PREGEN_TOKEN` is configured and header token does not match.

Fix:

```bash
curl -X POST http://127.0.0.1:8000/admin/pregenerate \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PREGEN_TOKEN" \
  -d '{"period":"daily","target_date":"2026-04-03"}'
```

### Cache seems stale

Checks:
- Confirm request payload is actually different.
- If using Redis, confirm `REDIS_KEY_PREFIX` is environment-specific.
- Inspect `/metrics` for hit/miss behavior.

### Redis connection errors

Cause:
- `REDIS_URL` invalid or Redis unavailable.

Fix:
- Unset `REDIS_URL` to fall back to in-memory TTL cache.
- Or fix Redis endpoint/credentials.

## Startup Healthcheck Messages

Healthcheck runs only when both are true:
- `CONTENT_HEALTHCHECK_DISABLE != 1`
- `content_root` is configured in service config

In default open-core mode, `content_root` is not configured and this check is skipped.
