# ADR 0002: PostgreSQL is the production system of record from the first vertical slice

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-002

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Preserve transactional history, JSONB, RLS, and queue/outbox patterns.

## Decision
PostgreSQL is the production system of record from the first vertical slice.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Preserve transactional history, JSONB, RLS, and queue/outbox patterns. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 0 (config rejects non-PostgreSQL URLs); Phase 1 (schema, RLS). The exit gate of that phase in blueprint section 20 is the acceptance check.
