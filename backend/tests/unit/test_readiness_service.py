from marketpulse.application.ports.health import ProbeResult
from marketpulse.application.services.readiness import ReadinessService
from tests.fakes import FakeProbe, RaisingProbe, SlowProbe

OK = ProbeResult("ok", latency_ms=1.0)
FAILED = ProbeResult("failed", detail="OperationalError")
UNSET = ProbeResult("not_configured")


async def test_ready_when_all_required_probes_are_ok() -> None:
    service = ReadinessService([FakeProbe("db", OK), FakeProbe("redis", OK, required=False)], 1)
    assert (await service.check()).ready is True


async def test_not_ready_when_a_required_probe_fails() -> None:
    service = ReadinessService([FakeProbe("db", FAILED)], 1)
    assert (await service.check()).ready is False


async def test_optional_failure_does_not_block_readiness() -> None:
    service = ReadinessService([FakeProbe("db", OK), FakeProbe("redis", FAILED, required=False)], 1)
    report = await service.check()
    assert report.ready is True
    assert {c.name: c.result.status for c in report.checks} == {"db": "ok", "redis": "failed"}


async def test_required_but_not_configured_is_not_ready() -> None:
    service = ReadinessService([FakeProbe("db", UNSET)], 1)
    assert (await service.check()).ready is False


async def test_a_raising_probe_becomes_a_failed_check_without_leaking_its_message() -> None:
    report = await ReadinessService([RaisingProbe()], 1).check()
    assert report.checks[0].result.status == "failed"
    assert report.checks[0].result.detail == "RuntimeError"
    assert "secret-internal-detail" not in repr(report)


async def test_a_hanging_probe_times_out() -> None:
    report = await ReadinessService([SlowProbe()], timeout_seconds=0.05).check()
    assert report.checks[0].result.status == "failed"
    assert report.checks[0].result.detail == "timeout"


async def test_no_probes_means_ready() -> None:
    assert (await ReadinessService([], 1).check()).ready is True
