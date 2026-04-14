# Development and Testing

## Runtime Baseline

- Python `3.11+`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
```

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
```

## CLI Smoke Checks

```bash
opastro
opastro init --template natal
opastro catalog
opastro doctor
opastro doctor --json
opastro doctor --fix --dry-run
opastro profile list
opastro horoscope --period daily --sign ARIES --target-date 2026-04-03
opastro horoscope --period daily --sign ARIES --target-date 2026-04-03 --json
opastro horoscope --period daily --sign ARIES --format markdown --export /tmp/aries.md
opastro explain --kind horoscope --period daily --sign ARIES --target-date 2026-04-03 --json
opastro completion --shell bash
opastro ui --period daily --sign ARIES --target-date 2026-04-03 --no-interactive
opastro batch --kind horoscope --period daily --signs ARIES,TAURUS --target-date 2026-04-03 --format json
opastro natal --birth-date 1997-08-14 --birth-time 09:30 --lat 4.0511 --lon 9.7679 --timezone Africa/Douala --split --split-dir /tmp/natal-split
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

## Packaging Sanity

```bash
python3 -m pip install -e .
opastro --help
```

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
