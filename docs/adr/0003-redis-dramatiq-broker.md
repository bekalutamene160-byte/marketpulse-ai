# ADR 0003: Redis/Dramatiq is the initial job broker; PostgreSQL remains canonical

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-003

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Reliable separate workers without placing business state in Redis.

## Decision
Redis/Dramatiq is the initial job broker; PostgreSQL remains canonical.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Reliable separate workers without placing business state in Redis. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 0 (worker stub); Phase 5 (durable workflows). The exit gate of that phase in blueprint section 20 is the acceptance check.
