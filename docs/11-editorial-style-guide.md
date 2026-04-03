# Editorial Style Guide (Open Core)

This guide documents the current renderer text standards for the open-core lite layer.

## Non-Negotiables

- Determinism is mandatory.
- Factor computation logic is not editorially modified.
- Section voices must remain distinct.
- Wording should be original and not derived from premium copy.

## Lite Tone Principles

- Clear, practical, and concise over mystical vagueness.
- Actionable phrasing over generic motivation.
- Distinct section framing (career should not sound like health, etc.).
- Neutral confidence: helpful without hype.

## Section Voice Anchors

| Section | Core voice |
|---|---|
| `general` | priorities, pacing, strategic clarity |
| `love_singles` | standards, reciprocity, emotional availability |
| `love_couples` | repair quality, trust, communication |
| `career` | execution, leverage, visibility |
| `friendship` | reciprocity, boundaries, social quality |
| `health` | recovery rhythm, load management, sustainability |
| `money` | value, risk control, discipline |
| `communication` | clarity, timing, precision |
| `lifestyle` | routine architecture, repeatability, low-friction systems |

## Summary Structure

The renderer composes:
- intro line
- factor-driven meaning/thesis lines
- period-aware pacing lines
- section-specific close

For monthly/yearly, longform cadence profiles are section-specific and deterministic.

## Monthly/Yearly Cadence Separation

Longform blocks are arranged with section-level cadence maps (`LONGFORM_CADENCE_BY_PERIOD`), creating different rhythm between adjacent sections.

Cadence blocks may include:
- `intro`
- `focus`
- `thesis`
- `breath`
- `theme`
- `events`
- `influences`
- `contrast`
- `dynamic_close`
- `close`

## Bridge Connectors

A minimal deterministic bridge layer separates major longform blocks:
- section-specific bridge phrase banks
- deterministic selection via stable seed
- sparse insertion to avoid repetitive filler

## Highlight / Caution / Action Quality Rules

Highlights:
- observable and section-specific
- avoid generic “good things are coming” phrasing

Cautions:
- constructive and non-fear-based
- avoid absolutist language

Actions:
- concrete, small, and executable
- prefer one clear move over broad advice

## Repetition Control

- Adjacent sections should not reuse the same breath line.
- Monthly/yearly closing lines should not collapse into one template.
- Transition connectors should sharpen section boundaries, not blur them.

## Regression Checklist for Text Edits

- [ ] Same payload produces identical output
- [ ] Section voices are still clearly separable
- [ ] Monthly/yearly cadence remains varied by section
- [ ] Bridge connectors remain deterministic
- [ ] No premium-copy echoes introduced
