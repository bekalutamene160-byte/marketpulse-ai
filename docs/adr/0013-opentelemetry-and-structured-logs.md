# ADR 0013: OpenTelemetry + structured JSON logs; Phoenix for agent evaluation/tracing

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-013

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Portable observability with a practical self-hosted tool.

## Decision
OpenTelemetry + structured JSON logs; Phoenix for agent evaluation/tracing.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Portable observability with a practical self-hosted tool. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 0 (JSON logs with request IDs); later phases (traces). The exit gate of that phase in blueprint section 20 is the acceptance check.
