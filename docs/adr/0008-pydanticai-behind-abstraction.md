# ADR 0008: PydanticAI behind an internal agent/provider abstraction

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-008

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Typed tool and model integration without exposing framework across the app.

## Decision
PydanticAI behind an internal agent/provider abstraction.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Typed tool and model integration without exposing framework across the app. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 12. The exit gate of that phase in blueprint section 20 is the acceptance check.
