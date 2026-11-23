# ADR 0001: Modular monolith with separate API and worker processes

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-001

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Avoid premature microservices while preserving runtime isolation.

## Decision
Modular monolith with separate API and worker processes.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Avoid premature microservices while preserving runtime isolation. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 0 (API and worker are separate entrypoints). The exit gate of that phase in blueprint section 20 is the acceptance check.
