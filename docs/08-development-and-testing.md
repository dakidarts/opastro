# Development and Testing

## Runtime Baseline

- Python `3.11+`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

## Pre-commit Hooks

This repo uses `pre-commit` to enforce style and catch common issues before they reach CI.

```bash
# Install the git hook scripts
pre-commit install

# Run against all files manually
pre-commit run --all-files
```

Configured hooks:
- `trailing-whitespace`, `end-of-file-fixer`
- `check-yaml`, `check-json`, `check-toml`
- `ruff` lint + auto-fix
- `ruff-format`

## Run Tests

```bash
PYTHONPATH=src python3 -m pytest -q
```

## Useful Targeted Test Runs

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_cli.py
PYTHONPATH=src python3 -m pytest -q tests/test_service.py
PYTHONPATH=src python3 -m pytest -q tests/test_interpretation.py
PYTHONPATH=src python3 -m pytest -q tests/test_cache.py
PYTHONPATH=src python3 -m pytest -q tests/test_healthcheck.py
PYTHONPATH=src python3 -m pytest -q tests/test_api_new_features.py
PYTHONPATH=src python3 -m pytest -q tests/test_fixed_stars.py
```

## CLI Smoke Checks

```bash
opastro
opastro init --template natal
opastro catalog
opastro doctor
opastro doctor --json
opastro doctor --fix --dry-run
opastro doctor --download-ephemeris
opastro profile list
opastro horoscope --period daily --sign ARIES --target-date 2026-04-03
opastro horoscope --period daily --sign ARIES --target-date 2026-04-03 --json
opastro horoscope --period daily --sign ARIES --format markdown --export /tmp/aries.md
opastro explain --kind horoscope --period daily --sign ARIES --target-date 2026-04-03 --json
opastro completion --shell bash
opastro ui --period daily --sign ARIES --target-date 2026-04-03 --no-interactive
opastro batch --kind horoscope --period daily --signs ARIES,TAURUS --target-date 2026-04-03 --format json
opastro natal --birth-date 1997-08-14 --birth-time 09:30 --lat 4.0511 --lon 9.7679 --timezone Africa/Douala --split --split-png --split-layout side-by-side --split-dir /tmp/natal-split
opastro natal --birth-date 1997-08-14 --birth-time 09:30 --lat 4.0511 --lon 9.7679 --timezone Africa/Douala --include-fixed-stars --include-arabic-parts
```

## API Dev Run

```bash
PYTHONPATH=src python3 -m uvicorn horoscope_engine.main:app --reload
```

Health checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/metrics
```

Test new endpoints:

```bash
# Synastry
curl -X POST http://127.0.0.1:8000/synastry \
  -H "Content-Type: application/json" \
  -d '{"birth1":{"date":"1992-06-15","time":"09:30","coordinates":{"latitude":4.0511,"longitude":9.7679},"timezone":"Africa/Douala"},"birth2":{"date":"1997-08-14","time":"18:00","coordinates":{"latitude":48.8566,"longitude":2.3522},"timezone":"Europe/Paris"}}'

# Transit timeline
curl -X POST http://127.0.0.1:8000/natal-birthchart/transits \
  -H "Content-Type: application/json" \
  -d '{"birth":{"date":"1992-06-15","time":"09:30","coordinates":{"latitude":4.0511,"longitude":9.7679},"timezone":"Africa/Douala"},"date_from":"2026-05-01","date_to":"2026-05-31"}'
```

## Docker Dev Run

```bash
docker compose up --build
```

Services:
- API on `http://localhost:8000` with hot reload
- Redis on `localhost:6379` (optional, set `REDIS_URL=redis://localhost:6379/0`)

## Packaging Sanity

```bash
python3 -m pip install -e .
opastro --help
```

## CI / GitHub Actions

The CI workflow (`.github/workflows/ci.yml`) runs on every push/PR to `main`:

1. **Lint job** (Python 3.12)
   - `ruff check .`
   - `ruff format --check .`

2. **Test matrix** (Python 3.11 and 3.12)
   - Install with `pip install -e ".[dev]"`
   - `PYTHONPATH=src pytest -q`

## Release CI

GitHub release automation runs on tag pushes matching `v*`:
- validates tag version against `setup.cfg`
- runs full tests
- builds wheel + sdist
- runs `twine check`
- uploads built artifacts to workflow and GitHub release

## Contribution Guardrails

- Keep output deterministic for identical payloads.
- Do not make external premium datasets mandatory.
- Keep section-level voice separation intact.
- Keep longform cadence behavior deterministic.
- Add/adjust tests whenever changing factor logic or rendering cadence.
- Run `ruff check . && ruff format .` before committing.
