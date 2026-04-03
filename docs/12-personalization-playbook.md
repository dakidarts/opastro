# Personalization Playbook

This guide explains how to use sign-mode and birth-mode in the current open-core engine.

## Personalization Modes

## Sign mode

Input:
- `sign` (with `period`)

Characteristics:
- broad/public interpretation
- no personalized house frame
- highest cache reuse

Example:

```json
{
  "period": "daily",
  "sign": "TAURUS",
  "target_date": "2026-04-03"
}
```

## Birth mode

Input:
- `birth.date` required for sign derivation
- `birth.time` + `birth.coordinates` required for precise house frame

Characteristics:
- personalized chart context
- house-driven factor enrichment when time + coordinates are available
- lower cache reuse (more unique payloads)

Example:

```json
{
  "period": "weekly",
  "target_date": "2026-04-03",
  "birth": {
    "date": "1992-06-15",
    "time": "09:30",
    "coordinates": {"latitude": 4.0511, "longitude": 9.7679},
    "timezone": "Africa/Douala"
  }
}
```

## House Behavior Matrix

| Input quality | Rising sign | House cusps | House focus factors |
|---|---|---|---|
| `sign` only | `null` | `null` | omitted |
| `birth.date` only | derived sign possible | `null` | omitted |
| `birth.date + time` only | `null` | `null` | omitted |
| `birth.date + coordinates` only | `null` | `null` | omitted |
| `birth.date + time + coordinates` | populated | populated | enabled for period |

Notes:
- Daily personalized reports can include `daily_house_focus` if time + coordinates are provided.
- Weekly/monthly/yearly personalized reports can include corresponding house-focus factors.

## Mode-Selection Recommendations

Use sign mode when:
- building public/free experiences
- optimizing cache efficiency
- user birth details are unavailable

Use birth mode when:
- user has complete birth details
- personalized house context is required
- premium/coaching-quality interpretation is desired

## High-Signal Request Practices

- Always set `target_date` explicitly for reproducibility.
- Send only needed `sections` to reduce payload size.
- Keep zodiac/house/node overrides explicit when comparing outputs:
  - `zodiac_system`
  - `ayanamsa`
  - `house_system`
  - `node_type`

## Tenant and Cache Isolation

You can isolate cache and analytics scope with `tenant_id` or `X-Tenant-Id`:

```json
{"period": "daily", "sign": "ARIES", "tenant_id": "free-tier"}
```

```json
{"period": "daily", "sign": "ARIES", "tenant_id": "premium-tier"}
```

## Determinism Check Pattern

```bash
PAYLOAD='{"period":"weekly","sign":"ARIES","target_date":"2026-04-03"}'
RESP1=$(curl -s -X POST http://127.0.0.1:8000/horoscope -H "Content-Type: application/json" -d "$PAYLOAD")
RESP2=$(curl -s -X POST http://127.0.0.1:8000/horoscope -H "Content-Type: application/json" -d "$PAYLOAD")
diff <(echo "$RESP1" | jq -S .) <(echo "$RESP2" | jq -S .)
```

## API Integration Pattern

1. Start users in sign mode.
2. Collect birth data progressively.
3. Upgrade to birth mode once `date + time + coordinates` are available.
4. Keep payload contracts stable for deterministic user history.

## Related Docs

- [02-api-reference.md](./02-api-reference.md)
- [03-request-response-contract.md](./03-request-response-contract.md)
- [10-factor-drivers-reference.md](./10-factor-drivers-reference.md)
