# ADR 0004: Transactional outbox for publishing background work and domain events

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-004

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Prevent commit/publish split-brain and support recovery.

## Decision
Transactional outbox for publishing background work and domain events.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Prevent commit/publish split-brain and support recovery. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 5. The exit gate of that phase in blueprint section 20 is the acceptance check.
