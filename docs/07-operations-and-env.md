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
| `REDIS_URL` | unset | Redis URL; if unset, in-memory TTL cache is used |
| `REDIS_KEY_PREFIX` | `""` | Prefix applied to Redis keys |
| `CONTENT_HEALTHCHECK_DISABLE` | `0` | `1` disables startup content checks |
| `CONTENT_HEALTHCHECK_FAIL_FAST` | `0` | `1` raises startup error when content checks fail |
| `PREGEN_TOKEN` | unset | Token guard for `/admin/pregenerate` |

## Cache Behavior

- Default: in-process TTL cache (`cache_ttl_seconds` from `ServiceConfig`, default 3600s)
- Redis mode: enabled when `REDIS_URL` is set

## Local Ops Commands

```bash
# CLI doctor
opastro doctor

# Runtime logger
opastro logger show --limit 10

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
- [ ] Cache mode chosen (in-memory or Redis)
- [ ] `PREGEN_TOKEN` configured (if using admin pregen endpoint)
- [ ] `/health`, `/metrics`, and report endpoints verified
