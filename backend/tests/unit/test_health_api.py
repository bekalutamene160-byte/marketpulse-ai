from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from marketpulse.application.ports.health import ProbeResult
from marketpulse.application.services.readiness import ReadinessService
from marketpulse.config import Settings
from marketpulse.main import create_app
from tests.fakes import AnyProbe, FakeProbe, RaisingProbe

OK = ProbeResult("ok", latency_ms=2.5)
FAILED = ProbeResult("failed", detail="OperationalError: host=db.internal.example")

MakeApp = Callable[..., FastAPI]


def test_live_reports_alive_and_never_touches_dependencies(make_app: MakeApp) -> None:
    client = TestClient(make_app(RaisingProbe()))  # would blow up if live called any probe
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"
    assert body["service"] == "marketpulse-api"
    assert body["environment"] == "test"


def test_ready_is_200_when_required_dependencies_are_ok(make_app: MakeApp) -> None:
    client = TestClient(make_app(FakeProbe("database", OK)))
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["database"] == {
        "status": "ok",
        "required": True,
        "latency_ms": 2.5,
    }


def test_ready_is_503_when_a_required_dependency_fails(make_app: MakeApp) -> None:
    client = TestClient(make_app(FakeProbe("database", FAILED)))
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_ready_stays_200_when_only_an_optional_dependency_fails(make_app: MakeApp) -> None:
    probes: list[AnyProbe] = [
        FakeProbe("database", OK),
        FakeProbe("redis", FAILED, required=False),
    ]
    response = TestClient(make_app(*probes)).get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["redis"]["status"] == "failed"


def test_ready_is_503_when_the_database_is_not_configured(make_app: MakeApp) -> None:
    client = TestClient(make_app(FakeProbe("database", ProbeResult("not_configured"))))
    assert client.get("/api/v1/health/ready").status_code == 503


def test_public_health_output_leaks_no_internal_detail(make_app: MakeApp) -> None:
    response = TestClient(make_app(FakeProbe("database", FAILED))).get("/api/v1/health/ready")
    assert "db.internal.example" not in response.text
    assert "OperationalError" not in response.text


def test_every_response_has_a_generated_request_id(make_app: MakeApp) -> None:
    response = TestClient(make_app()).get("/api/v1/health/live")
    assert len(response.headers["X-Request-ID"]) == 32  # uuid4 hex


def test_a_valid_client_request_id_is_echoed(make_app: MakeApp) -> None:
    response = TestClient(make_app()).get(
        "/api/v1/health/live", headers={"X-Request-ID": "trace-abc12345"}
    )
    assert response.headers["X-Request-ID"] == "trace-abc12345"


def test_an_unsafe_client_request_id_is_replaced(make_app: MakeApp) -> None:
    response = TestClient(make_app()).get(
        "/api/v1/health/live", headers={"X-Request-ID": "bad id\twith spaces!"}
    )
    assert response.headers["X-Request-ID"] != "bad id\twith spaces!"
    assert len(response.headers["X-Request-ID"]) == 32


def test_unknown_route_uses_the_error_envelope(make_app: MakeApp) -> None:
    response = TestClient(make_app()).get("/api/v1/nope")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_validation_errors_use_the_envelope_and_do_not_echo_input(make_app: MakeApp) -> None:
    app = make_app()

    @app.get("/items/{n}")
    async def item(n: int) -> dict[str, int]:
        return {"n": n}

    response = TestClient(app).get("/items/not-a-number-xyz")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["loc"] == ["path", "n"]
    assert "not-a-number-xyz" not in response.text


def test_unhandled_exceptions_become_a_generic_500_with_a_request_id(make_app: MakeApp) -> None:
    app = make_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret-internal-detail")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom", headers={"X-Request-ID": "trace-boom12345"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["error"]["request_id"] == "trace-boom12345"
    assert response.headers["X-Request-ID"] == "trace-boom12345"
    assert "secret-internal-detail" not in response.text


def test_api_docs_are_not_exposed_in_production() -> None:
    production = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql://u:p@h/db?sslmode=require",
        redis_url="rediss://:p@h:6379",
    )
    client = TestClient(create_app(production, ReadinessService([], 1)))
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
