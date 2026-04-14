# 5-Minute Quickstart

## Requirements

- Python `3.11+`

## Install (PyPI, Recommended)

```bash
python3 -m pip install opastro
```

## Install (Editable, Contributors)

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

## Python Library Import (Branded)

```python
import opastro as oa
from datetime import date

service = oa.HoroscopeService(oa.ServiceConfig())
response = service.generate(
    oa.HoroscopeRequest(period=oa.Period.DAILY, sign="ARIES", target_date=date(2026, 4, 3))
)
print(response.sign)
```

Alternative explicit module-style imports:

```python
from opastro.config import ServiceConfig
from opastro.models import HoroscopeRequest, Period
from opastro.service import HoroscopeService
```

## First CLI Run

```bash
opastro --version
opastro
```

This opens the main welcome UI with command overview.

## Save Defaults (Recommended)

```bash
opastro init
opastro init --template natal
opastro profile list
opastro profile save --name natal --set-active --user-name "Dakidarts" --wheel-theme day --accent "#3ddd77"
```

## Enable Completions

```bash
opastro completion --shell bash
# or: zsh / fish
```

## Generate Reports

### Daily sign-mode

```bash
opastro horoscope --period daily --sign ARIES --target-date 2026-04-03
```

### Weekly personalized mode

```bash
opastro horoscope \
  --period weekly \
  --target-date 2026-04-03 \
  --birth-date 1992-06-15 \
  --birth-time 09:30 \
  --lat 4.0511 \
  --lon 9.7679 \
  --timezone Africa/Douala
```

### JSON output mode

```bash
opastro horoscope --period monthly --sign TAURUS --json
```

### Markdown export mode

```bash
opastro horoscope --period daily --sign ARIES --format markdown --export reports/aries.md
```

### Explain mode (line provenance)

```bash
opastro explain --kind horoscope --period daily --sign ARIES --target-date 2026-04-03 --json
```

### Interactive UI

```bash
opastro ui --period daily --sign ARIES --target-date 2026-04-03
```

Controls:
- `↑↓` / `j,k` section navigation
- `enter` toggle factor drill-down
- `pgup` / `pgdn` content scroll
- `g` / `G` jump top/end
- `q` or `esc` quit

### Batch mode

```bash
opastro batch --kind horoscope --period daily --signs ARIES,TAURUS --date-from 2026-04-03 --date-to 2026-04-05 --format markdown --export-dir reports/batch
```

### Natal exports (day/night wheel theme)

```bash
opastro natal \
  --user-name "Dakidarts" \
  --birth-date 1997-08-14 \
  --birth-time 09:30 \
  --lat 4.0511 \
  --lon 9.7679 \
  --timezone Africa/Douala \
  --wheel-theme day \
  --wheel-svg reports/natal-wheel.svg \
  --wheel-png reports/natal-wheel.png \
  --pdf reports/natal-report.pdf
```

### Natal split wheel exports (main + legends)

```bash
opastro natal \
  --birth-date 1997-08-14 \
  --birth-time 09:30 \
  --lat 4.0511 \
  --lon 9.7679 \
  --timezone Africa/Douala \
  --split \
  --split-dir reports/natal-split
```

### Natal split PNG exports with layout control

```bash
opastro natal \
  --birth-date 1997-08-14 \
  --birth-time 09:30 \
  --lat 4.0511 \
  --lon 9.7679 \
  --timezone Africa/Douala \
  --split \
  --split-png \
  --split-layout stacked \
  --split-dir reports/natal-split-stacked
```

## Run API

```bash
opastro serve --host 127.0.0.1 --port 8000 --reload
```

## First API Call

```bash
curl -X POST http://127.0.0.1:8000/horoscope \
  -H "Content-Type: application/json" \
  -d '{"period":"daily","sign":"ARIES"}'
```

## Verify Setup

```bash
opastro doctor
opastro doctor --json
opastro logger show --limit 5
```

## Important Open-Core Note

- This repository does **not** require external premium content packs for normal operation.
- Rendering uses deterministic, built-in lite meanings.
