# ADR 0018: LLM provider outage must not stop deterministic operations

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-018

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Protect core product reliability and cost flexibility.

## Decision
LLM provider outage must not stop deterministic operations.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Protect core product reliability and cost flexibility. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 12; Phase 0 keeps the core free of any LLM dependency. The exit gate of that phase in blueprint section 20 is the acceptance check.
