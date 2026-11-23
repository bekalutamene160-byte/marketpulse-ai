# ADR 0017: SSE/polling before WebSockets

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-017

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Simpler reliable dashboard refresh; DB is still authoritative.

## Decision
SSE/polling before WebSockets.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Simpler reliable dashboard refresh; DB is still authoritative. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 2 onward. The exit gate of that phase in blueprint section 20 is the acceptance check.
