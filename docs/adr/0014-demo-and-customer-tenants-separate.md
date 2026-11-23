# ADR 0014: Demo and customer workspaces are separate tenants; NexaTech is independent

- Status: accepted
- Date: 2026-11-20
- Blueprint reference: section 22 (initial ADR set), ADR-014

## Context
Baseline decision recorded from the system design blueprint (MARKETPULSE_AI_SYSTEM_DESIGN.md, section 22). The blueprint's stated reason: Prevent demo leakage and avoid coupling product identity to demo store.

## Decision
Demo and customer workspaces are separate tenants; NexaTech is independent.

## Alternatives considered
See the blueprint section that this decision supports. Alternatives are expanded here if and when the decision is challenged during implementation.

## Consequences
Prevent demo leakage and avoid coupling product identity to demo store. Any change to this decision requires a new ADR that supersedes this one.

## Verification
First exercised in: Phase 1 onward; Phase 0 keeps retailer/market data out of config. The exit gate of that phase in blueprint section 20 is the acceptance check.
