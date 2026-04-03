# CLI UX Roadmap (Next Wave)

This task plan covers the next UX features after `init`, `profile`, and output formatting/export.

## Scope

1. `opastro explain` mode  
Goal: Show transparent factor provenance for each section line.

2. Shell completion + typo suggestions + aliases  
Goal: Faster command discoverability and fewer user-input errors.

3. Rich terminal UI (`opastro ui`)  
Goal: Keyboard-driven navigation and section drill-down.

4. Batch workflows (`opastro batch`)  
Goal: Generate many reports/signs/dates in one command.

5. `opastro doctor --fix`  
Goal: Guided environment remediation for common runtime/setup issues.

## Delivery Plan

## Phase A: Explainability

- Add `opastro explain` command for report payload introspection.
- Include factor list, weights, and applied section drivers.
- Support `--format json|markdown`.

Acceptance:
- Explain output is deterministic for identical input.
- No change to core factor computation behavior.

## Phase B: Command Intelligence

- Add shell completion scripts (bash/zsh/fish).
- Add command alias map (e.g. `opastro h` -> `horoscope`).
- Add suggestion hints for unknown commands.

Acceptance:
- Mistyped commands return ranked suggestions.
- Completion scripts install and run on major shells.

## Phase C: Interactive UI

- Add `opastro ui` with section navigation and period switching.
- Render highlights/cautions/actions with compact cards.
- Keep non-TTY fallback to plain CLI commands.

Acceptance:
- Works in standard terminals without breaking scripting mode.
- All existing report options remain reachable.

## Phase D: Batch and Automation

- Add `opastro batch` for CSV/JSONL input.
- Support `--format` and `--export-dir`.
- Add optional concurrency limit.

Acceptance:
- Deterministic output ordering.
- Clear per-row success/failure reporting.

## Phase E: Doctor Auto-Fix

- Add `opastro doctor --fix` interactive remediation mode.
- Include virtualenv and package checks.
- Include Python version compatibility checks.

Acceptance:
- Dry-run mode available.
- Non-destructive by default.

