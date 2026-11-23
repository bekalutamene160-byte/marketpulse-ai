import json
import logging

from marketpulse.core.logging import JsonFormatter, RequestIdFilter, request_id_var


def _record(message: str = "hello %s") -> logging.LogRecord:
    return logging.LogRecord("t", logging.INFO, __file__, 1, message, ("world",), None)


def test_json_formatter_includes_blueprint_fields_and_request_id() -> None:
    token = request_id_var.set("req-12345678")
    try:
        record = _record()
        RequestIdFilter().filter(record)
        data = json.loads(JsonFormatter("marketpulse-api", "test").format(record))
    finally:
        request_id_var.reset(token)

    assert data["message"] == "hello world"
    assert data["severity"] == "INFO"
    assert data["service"] == "marketpulse-api"
    assert data["environment"] == "test"
    assert data["request_id"] == "req-12345678"
    assert "timestamp" in data


def test_an_explicit_request_id_is_not_overwritten_by_the_context() -> None:
    record = _record()
    record.request_id = "explicit-1234"
    RequestIdFilter().filter(record)
    assert record.request_id == "explicit-1234"


def test_default_request_id_outside_a_request_is_a_dash() -> None:
    record = _record()
    RequestIdFilter().filter(record)
    assert record.request_id == "-"
