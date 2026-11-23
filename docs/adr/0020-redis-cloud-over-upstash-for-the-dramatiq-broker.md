# ADR 0020: Redis Cloud free database, not Upstash free, for the Dramatiq broker

- Status: accepted, provisional until the Redis Cloud limits are confirmed in its console
- Date: 2026-11-20
- Blueprint reference: ADR-003, 19.2 (managed Redis), 19.5

## Context
ADR-0019 moves development Redis to the cloud. Upstash was the first candidate. Upstash's free plan
is metered per command (500,000 commands per month at the time of checking). A Dramatiq worker
polls Redis continuously even with no jobs.

## Evidence
Measured on 2026-11-20 with a real Redis server and a real Dramatiq worker, idle, no tasks:
roughly 480 to 500 commands per minute. That extrapolates to about 21 million commands per 30 days
for a worker left running. At that rate the 500,000 command allowance lasts roughly 17 hours of
worker uptime. The measurement used Dramatiq's defaults and one process; fewer threads and the
real broker settings may change the number, but not by the 40x needed to fit.

## Decision
Use the Redis Cloud free database as the development broker (ADR-003 is unchanged: Redis is only
transport, PostgreSQL is canonical). Redis Cloud advertises a fixed-size free database rather than
a per-command meter.

## Not verified yet
The documentation pages read did not state a command or throughput cap, nor any inactivity deletion
rule for the Redis Cloud free database. Before relying on it, confirm both in the console and record
the result here. If Redis Cloud turns out to be unsuitable, the fallback is to run the worker only
during active development sessions on Upstash's pay-as-you-go plan, or to defer the worker's
always-on behavior to Phase 5, when it first matters.

## Consequences
- Because Redis is only transport and workflow state lives in PostgreSQL (ADR-003, ADR-004), losing
  the Redis database loses no business data. Phase 5 must make that true and test it.
- The adapter is the Dramatiq `RedisBroker`; swapping providers changes only `MP_REDIS_URL`.
- Production requires TLS (`rediss://`), enforced in `config.py`.

## Verification
`uv run pytest -m integration` passes against the real Redis URL, and
`uv run dramatiq marketpulse.worker.app` starts and stays up.
