# Content Pipeline (Open-Core Boundary)

## Status

The premium JSON content-pack pipeline is out-of-scope for this open-core repository.

This codebase currently ships with deterministic built-in lite meanings in `renderer.py` and does not require external content packs.

## What Remains in Open-Core

- Optional `content_root` config hook still exists for compatibility.
- Startup content healthcheck can run if `content_root` is explicitly configured.
- Default mode: no content root, healthcheck skipped, built-in narrative layer only.

## Why This Exists

This document clarifies architecture boundaries so contributors do not try to recreate private dataset infrastructure in the open repo.

## If You Configure `content_root`

You may still use:
- `CONTENT_HEALTHCHECK_DISABLE`
- `CONTENT_HEALTHCHECK_FAIL_FAST`

But these checks are optional and not required for normal open-core usage.

## Recommended Contribution Focus

- CLI UX and command workflows
- Factor computation quality
- Deterministic rendering improvements
- API reliability and caching behavior
- Tests and packaging quality
