# ADR 0009: Deterministic Python services own arithmetic, matching acceptance, and opportunity scores

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-009

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Reproducibility and reduced hallucination risk.

## Decision
Deterministic Python services own arithmetic, matching acceptance, and opportunity scores.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Reproducibility and reduced hallucination risk. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phases 8 and 11. The exit gate of that phase in blueprint section 20 is the acceptance check.
