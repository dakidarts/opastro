<p align="center">
  <a href="https://opastro.com">
    <img src="https://res.cloudinary.com/ds64xs2lp/image/upload/q_auto/f_auto/v1775313441/cover_gh1cdn.jpg" alt="OpAstro Banner" />
  </a>
</p>

# Opastro Documentation

<p align="center">
  <a href="https://pypi.org/project/opastro/"><img src="https://img.shields.io/badge/%F0%9F%93%A6%20PyPI-opastro-blue" alt="PyPI Package"></a>
  <a href="https://opastro.com"><img src="https://img.shields.io/badge/%F0%9F%8C%90%20Website-opastro.com-green" alt="Website"></a>
  <a href="https://github.com/dakidarts/opastro"><img src="https://img.shields.io/badge/%E2%AD%90%20GitHub-dakidarts%2Fopastro-purple" alt="GitHub Repo"></a>
</p>

This docs set tracks the current open-core codebase and CLI.

## Python Import Namespace

The branded SDK namespace is available at:
- `src/opastro/__init__.py`

Use whichever import style fits your app:

```python
import opastro as oa

service = oa.HoroscopeService(oa.ServiceConfig())
print(oa.__version__)
```

```python
from opastro import HoroscopeService, ServiceConfig, HoroscopeRequest, Period
```

```python
from opastro.config import ServiceConfig
from opastro.models import HoroscopeRequest, Period
from opastro.service import HoroscopeService
```

Install from PyPI:

```bash
python3 -m pip install opastro
```

## Start In 5 Minutes

```bash
python3 -m pip install -U opastro
opastro doctor
opastro logger show --limit 5
opastro horoscope --period daily --sign ARIES --target-date 2026-04-03
```

Then continue with [01-quickstart.md](./01-quickstart.md) for the full command tour.

## Quick Navigation

1. [01-quickstart.md](./01-quickstart.md)
2. [02-api-reference.md](./02-api-reference.md)
3. [03-request-response-contract.md](./03-request-response-contract.md)
4. [08-development-and-testing.md](./08-development-and-testing.md)

## Core System Docs

- [04-architecture.md](./04-architecture.md)
- [05-rendering-system.md](./05-rendering-system.md)
- [10-factor-drivers-reference.md](./10-factor-drivers-reference.md)
- [11-editorial-style-guide.md](./11-editorial-style-guide.md)

## Runtime Docs

- [07-operations-and-env.md](./07-operations-and-env.md)
- [09-troubleshooting.md](./09-troubleshooting.md)
- [12-personalization-playbook.md](./12-personalization-playbook.md)

## Open-Core Boundary

- [06-content-pipeline.md](./06-content-pipeline.md)

## Internal Tasks

Task planning notes are kept under `docs/tasks/` as local, untracked working files.
