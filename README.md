<p align="center">
  <a href="https://numerologyapi.com">
    <img src="https://res.cloudinary.com/ds64xs2lp/image/upload/q_auto/f_auto/v1770073784/the_numerology_api_fzlsli.gif" alt="Opastro Banner" />
  </a>
</p>

# OpAstro Engine (Open Core)

<p align="center">
  <a href="https://pypi.org/project/opastro/"><img src="https://img.shields.io/badge/%F0%9F%93%A6%20PyPI-opastro-blue" alt="PyPI Package"></a>
  <a href="https://numerologyapi.com"><img src="https://img.shields.io/badge/%F0%9F%8C%90%20Website-numerologyapi.com-green" alt="Website"></a>
  <a href="https://github.com/dakidarts/opastro"><img src="https://img.shields.io/badge/%E2%AD%90%20GitHub-dakidarts%2Fopastro-purple" alt="GitHub Repo"></a>
</p>

Opastro is a deterministic horoscope engine built for two use cases:
- a developer-friendly Python library
- a high-UX terminal CLI (`opastro`)

The open-core repo ships calculations + lightweight built-in meanings.
Richer premium narrative packs are available via [numerologyapi.com](https://numerologyapi.com).

## What Is Open Here

- Swiss Ephemeris-based astrology calculations
- Deterministic factor derivation and section scoring
- Built-in lite renderer (no external dataset required)
- FastAPI service endpoints
- Python package + installable CLI
- Test suite covering API, CLI, rendering, caching, and health checks

## What Is Not Included

- Private premium meaning dataset and editorial packs
- Premium content production pipeline assets

## Requirements

- Python `3.11+`

## Install (PyPI)

```bash
python3 -m pip install opastro
```

## Install (Editable, Contributors)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

## CLI

Running with no arguments opens the welcome UI:

```bash
opastro
```

### Command Catalog

| Command | Description |
|---|---|
| `opastro` | Main welcome UI with OPASTRO ASCII banner + quick start |
| `opastro init` | Interactive onboarding to create/update a default profile |
| `opastro profile ...` | Manage saved profiles (`save`, `list`, `show`, `use`) |
| `opastro welcome` | Show welcome UI explicitly |
| `opastro catalog` | List periods, sections, signs, and planets |
| `opastro doctor` | Runtime diagnostics (python path, platform, ephemeris mode) |
| `opastro horoscope` | Generate standard reports (daily/weekly/monthly/yearly) |
| `opastro birthday` | Generate birthday-cycle yearly report |
| `opastro planet` | Generate planet-focused report |
| `opastro explain` | Show why each section line appeared (factor provenance) |
| `opastro completion --shell ...` | Generate shell completion scripts |
| `opastro ui` | Launch interactive TUI with section drill-down |
| `opastro batch` | Multi-sign / multi-date report generation |
| `opastro serve` | Run local FastAPI app |

### Report Flags

- `--period {daily,weekly,monthly,yearly}` (required for `horoscope`, `planet`)
- `--sign ARIES`
- `--target-date YYYY-MM-DD`
- `--sections general,career,money`
- `--birth-date YYYY-MM-DD`
- `--birth-time HH:MM`
- `--lat <float> --lon <float>`
- `--timezone <IANA timezone>`
- `--zodiac-system {sidereal,tropical}`
- `--ayanamsa {lahiri,fagan_bradley,krishnamurti,raman,yukteswar}`
- `--house-system {placidus,whole_sign,equal,koch}`
- `--node-type {true,mean}`
- `--tenant-id <id>`
- `--json`
- `--format {text,json,markdown,html}`
- `--export <path>`

### CLI Examples

```bash
# Interactive setup (creates active default profile)
opastro init

# Save profile defaults without prompts
opastro profile save --name work --sign ARIES --format markdown --set-active

# Switch active profile
opastro profile use work

# Explain why lines appeared
opastro explain --kind horoscope --period daily --sign ARIES --target-date 2026-04-03 --format markdown

# Interactive TUI
opastro ui --period daily --sign ARIES --target-date 2026-04-03

# Batch generation
opastro batch --kind horoscope --period daily --signs ARIES,TAURUS --date-from 2026-04-03 --date-to 2026-04-05 --format markdown --export-dir reports/batch

# Daily sign-mode
opastro horoscope --period daily --sign ARIES --target-date 2026-04-03

# Daily personalized (houses + daily_house_focus enabled if time+coords provided)
opastro horoscope \
  --period daily \
  --target-date 2026-04-03 \
  --birth-date 1992-06-15 \
  --birth-time 09:30 \
  --lat 4.0511 \
  --lon 9.7679 \
  --timezone Africa/Douala

# Birthday-cycle report
opastro birthday --sign TAURUS --target-date 2026-04-03

# Planet-focused monthly report
opastro planet --period monthly --planet mercury --sign TAURUS --target-date 2026-04-03

# Raw JSON output
opastro horoscope --period weekly --sign LEO --json

# Export markdown report
opastro horoscope --period daily --sign ARIES --format markdown --export reports/aries.md
```

## API

Run local API:

```bash
opastro serve --host 127.0.0.1 --port 8000 --reload
```

Or directly:

```bash
uvicorn horoscope_engine.main:app --host 127.0.0.1 --port 8000 --reload
```

### Endpoints

- `GET /health`
- `POST /horoscope`
- `POST /birthday-horoscope`
- `POST /planet-horoscope`
- `GET /metrics`
- `POST /admin/pregenerate`

### Minimal API Call

```bash
curl -X POST http://127.0.0.1:8000/horoscope \
  -H "Content-Type: application/json" \
  -d '{"period":"daily","sign":"ARIES"}'
```

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SE_EPHE_PATH` | auto-detected | Swiss Ephemeris path override |
| `REDIS_URL` | unset | Enable Redis cache if set |
| `REDIS_KEY_PREFIX` | `""` | Redis key prefix |
| `CONTENT_HEALTHCHECK_DISABLE` | `0` | Skip startup content/schema check |
| `CONTENT_HEALTHCHECK_FAIL_FAST` | `0` | Raise startup error when health check issues are found |
| `PREGEN_TOKEN` | unset | Protect `/admin/pregenerate` with `X-Admin-Token` |

## Developer UX Extras

```bash
# Diagnose and preview auto-fixes
opastro doctor --fix --dry-run

# Apply auto-fixes (installs editable package + deps)
opastro doctor --fix

# Generate shell completions
opastro completion --shell bash
opastro completion --shell zsh
opastro completion --shell fish
```

## Testing

```bash
python3 -m pip install -e ".[dev]"
PYTHONPATH=src python3 -m pytest -q
```

## Build And Publish (PyPI)

```bash
# One-time tooling
python3 -m pip install -U build twine

# Clean old artifacts
rm -rf dist build src/*.egg-info

# Build wheel + sdist
python3 -m build

# Validate package metadata/rendering
python3 -m twine check dist/*

# Optional safety pass: upload to TestPyPI first
python3 -m twine upload --repository testpypi dist/*

# Production upload
python3 -m twine upload dist/*
```

## Docs

Start here: [docs/README.md](docs/README.md)

---

<p align="center">
  ⭐ If you find this project useful, give it a star on <a href="https://github.com/dakidarts/opastro">GitHub</a>!
</p>

<p align="center">
  <a href="https://pypi.org/project/opastro/"><img src="https://img.shields.io/pypi/v/opastro.svg" alt="PyPI Version"></a>
  <a href="https://github.com/dakidarts/opastro"><img src="https://img.shields.io/github/stars/dakidarts/opastro.svg" alt="GitHub Stars"></a>
  <a href="https://numerologyapi.com"><img src="https://img.shields.io/badge/Website-numerologyapi.com-blue.svg" alt="Website"></a>
</p>
