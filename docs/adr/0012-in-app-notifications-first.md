# ADR 0012: In-app notifications first; email as an adapter

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-012

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Core alerting works without mandatory paid email vendor.

## Decision
In-app notifications first; email as an adapter.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Core alerting works without mandatory paid email vendor. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 9. The exit gate of that phase in blueprint section 20 is the acceptance check.
