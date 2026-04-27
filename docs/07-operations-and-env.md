# Operations and Environment

## Runtime Modes

## Default open-core mode
- `content_root` not configured
- built-in lite rendering active
- startup content healthcheck skipped automatically

## Optional compatibility mode
- configure `content_root`
- startup content healthcheck can run against schema/content directories

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SE_EPHE_PATH` | auto-detected | Swiss Ephemeris file path override |
| `REDIS_URL` | unset | Redis URL; if unset, SQLite on-disk cache is used |
| `REDIS_KEY_PREFIX` | `""` | Prefix applied to Redis keys |
| `OPASTRO_CACHE_PATH` | `~/.cache/opastro/cache.sqlite` | SQLite cache database path when Redis is unavailable |
| `CONTENT_HEALTHCHECK_DISABLE` | `0` | `1` disables startup content checks |
| `CONTENT_HEALTHCHECK_FAIL_FAST` | `0` | `1` raises startup error when content checks fail |
| `PREGEN_TOKEN` | unset | Token guard for `/admin/pregenerate` |
| `OPASTRO_ANALYTICS` | `0` | Opt-in local anonymous CLI analytics events (`1` enables) |
| `OPASTRO_RATE_LIMIT_RPS` | `10` | Requests per second per client/API key |
| `OPASTRO_RATE_LIMIT_BURST` | `20` | Burst bucket size for rate limiting |
| `OPASTRO_REQUIRE_API_KEY` | `0` | Set to `1` to enforce `X-API-Key` header validation |
| `OPASTRO_API_KEYS` | unset | Comma-separated list of valid API keys |

## Cache Behavior

- **Default**: SQLite-backed persistent cache (`cache_ttl_seconds` from `ServiceConfig`, default 3600s)
- **Redis mode**: enabled when `REDIS_URL` is set
- The SQLite cache survives process restarts and is stored at `~/.cache/opastro/cache.sqlite` by default.

## Logging

- All API requests emit structured JSON logs via `StructuredLogger`.
- Every response includes an `X-Request-Id` header for distributed tracing.
- Set `X-Request-Id` on incoming requests to propagate trace context.

## Rate Limiting

Rate limiting is active by default with a token-bucket algorithm keyed by:
1. `X-API-Key` header
2. `X-Tenant-Id` header
3. Client IP (fallback)

Health (`/health`) and metrics (`/metrics`) endpoints are exempt.

## API Key Authentication

Optional enforcement via environment:

```bash
export OPASTRO_REQUIRE_API_KEY=1
export OPASTRO_API_KEYS="pk_prod_abc,pk_prod_def"
```

All report endpoints then require:

```bash
curl -X POST http://127.0.0.1:8000/horoscope \
  -H "Content-Type: application/json" \
  -H "X-API-Key: pk_prod_abc" \
  -d '{"period":"daily","sign":"ARIES"}'
```

## Local Ops Commands

```bash
# CLI doctor
opastro doctor
opastro doctor --json
opastro doctor --download-ephemeris

# Runtime logger
opastro logger show --limit 10

# Opt-in analytics
OPASTRO_ANALYTICS=1 opastro catalog

# Run API
opastro serve --host 127.0.0.1 --port 8000 --reload

# Health endpoint
curl http://127.0.0.1:8000/health

# Metrics endpoint
curl http://127.0.0.1:8000/metrics
```

## Pregeneration

```bash
curl -X POST http://127.0.0.1:8000/admin/pregenerate \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $PREGEN_TOKEN" \
  -d '{"period":"daily","target_date":"2026-04-03"}'
```

## Deployment Checklist

- [ ] Python 3.11 runtime available
- [ ] Swiss Ephemeris path resolved (`SE_EPHE_PATH` if needed)
- [ ] Cache mode chosen (SQLite default or Redis)
- [ ] `PREGEN_TOKEN` configured (if using admin pregen endpoint)
- [ ] Rate limits tuned (`OPASTRO_RATE_LIMIT_RPS`, `OPASTRO_RATE_LIMIT_BURST`)
- [ ] API keys configured (if `OPASTRO_REQUIRE_API_KEY=1`)
- [ ] `/health`, `/metrics`, and report endpoints verified
