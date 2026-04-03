# Quickstart

## Requirements

- Python `3.11+`

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

## First CLI Run

```bash
opastro
```

This opens the main welcome UI with command overview.

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
```

## Important Open-Core Note

- This repository does **not** require external premium content packs for normal operation.
- Rendering uses deterministic, built-in lite meanings.
