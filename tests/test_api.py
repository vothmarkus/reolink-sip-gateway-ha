"""Tests for HTTP behavior and the SSE parser."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

import pytest

from custom_components.reolink_sip_gateway.api import (
    GatewayAPIClient,
    GatewayAuthenticationError,
    GatewayCommandError,
    GatewayProtocolError,
    api_url_from_host,
    gateway_host_from_api_url,
    normalize_api_url,
    normalize_gateway_host,
)


class FakeContent:
    """Minimal line-oriented aiohttp StreamReader stand-in."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = deque(lines)

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        return self._lines.popleft() if self._lines else b""


class FakeResponse:
    """Minimal async response context manager."""

    def __init__(
        self,
        status: int,
        payload: Any | None = None,
        lines: list[bytes] | None = None,
    ) -> None:
        self.status = status
        self._payload = payload
        self.content = FakeContent(lines or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def json(self, content_type=None):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Record requests and return prepared responses."""

    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.popleft()

    def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.popleft()


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("http://ha.local:18099", "http://ha.local:18099/api/v1"),
        ("http://ha.local:18099/api/v1/", "http://ha.local:18099/api/v1"),
        (
            "https://192.168.1.2:18099/api/v1/info",
            "https://192.168.1.2:18099/api/v1",
        ),
    ],
)
def test_normalize_api_url(raw, normalized):
    assert normalize_api_url(raw) == normalized


@pytest.mark.parametrize(
    "raw",
    ["", "ha.local:18099", "ftp://ha.local/api/v1", "http://ha.local/wrong"],
)
def test_normalize_api_url_rejects_invalid_values(raw):
    with pytest.raises(ValueError):
        normalize_api_url(raw)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        (
            " 1C33278A-Reolink-SIP-Gateway ",
            "1c33278a-reolink-sip-gateway",
        ),
        ("ha.home.", "ha.home"),
        ("127.0.0.1", "127.0.0.1"),
    ],
)
def test_normalize_gateway_host(raw, normalized):
    assert normalize_gateway_host(raw) == normalized


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "http://addon",
        "addon:18099",
        "addon/api/v1",
        "addon_name",
        "-addon",
        "addon..local",
    ],
)
def test_normalize_gateway_host_rejects_urls_ports_and_invalid_names(raw):
    with pytest.raises(ValueError):
        normalize_gateway_host(raw)


def test_hostname_builds_fixed_internal_api_url():
    host = "1c33278a-reolink-sip-gateway"
    assert api_url_from_host(host) == f"http://{host}:18099/api/v1"


def test_stored_v010_url_is_presented_as_hostname():
    assert (
        gateway_host_from_api_url("http://homeassistant.local:18099/api/v1")
        == "homeassistant.local"
    )


def test_get_info_uses_bearer_token(info_payload):
    async def run_test() -> None:
        session = FakeSession(FakeResponse(200, info_payload))
        client = GatewayAPIClient(session, "http://ha.local:18099", "secret")
        info = await client.async_get_info()
        assert info.gateway_version == "1.2.0"
        method, url, kwargs = session.calls[0]
        assert method == "GET"
        assert url == "http://ha.local:18099/api/v1/info"
        assert kwargs["headers"]["Authorization"] == "Bearer secret"

    asyncio.run(run_test())


def test_rejected_token_raises_authentication_error():
    async def run_test() -> None:
        session = FakeSession(
            FakeResponse(
                401,
                {"error": {"code": "unauthorized", "message": "no"}},
            )
        )
        client = GatewayAPIClient(session, "http://ha.local:18099", "bad")
        with pytest.raises(GatewayAuthenticationError):
            await client.async_get_info()

    asyncio.run(run_test())


def test_busy_test_call_preserves_gateway_error_code():
    async def run_test() -> None:
        session = FakeSession(
            FakeResponse(
                409,
                {"error": {"code": "call_busy", "message": "busy"}},
            )
        )
        client = GatewayAPIClient(session, "http://ha.local:18099", "secret")
        with pytest.raises(GatewayCommandError) as caught:
            await client.async_start_test_call()
        assert caught.value.code == "call_busy"
        assert caught.value.status == 409

    asyncio.run(run_test())


def test_route_test_call_uses_route_specific_endpoint():
    async def run_test() -> None:
        session = FakeSession(FakeResponse(202, {"status": "accepted"}))
        client = GatewayAPIClient(session, "http://ha.local:18099", "secret")
        await client.async_start_test_call("wohnung_1")
        method, url, _ = session.calls[0]
        assert method == "POST"
        assert url == "http://ha.local:18099/api/v1/routes/wohnung_1/test"

    asyncio.run(run_test())


def test_info_http_error_is_reported_as_protocol_error():
    async def run_test() -> None:
        session = FakeSession(
            FakeResponse(
                404,
                {"error": {"code": "not_found", "message": "missing"}},
            )
        )
        client = GatewayAPIClient(session, "http://ha.local:18099", "secret")
        with pytest.raises(GatewayProtocolError):
            await client.async_get_info()

    asyncio.run(run_test())


def test_sse_status_and_dtmf_events(status_payload, dtmf_payload):
    async def run_test() -> None:
        status_data = json.dumps(status_payload, separators=(",", ":")).encode()
        dtmf_data = json.dumps(dtmf_payload, separators=(",", ":")).encode()
        session = FakeSession(
            FakeResponse(
                200,
                lines=[
                    b": keepalive\n",
                    b"event: status\n",
                    b"id: 7\n",
                    b"data: " + status_data + b"\n",
                    b"\n",
                    b"event: dtmf\n",
                    b"data: " + dtmf_data + b"\n",
                    b"\n",
                ],
            )
        )
        client = GatewayAPIClient(session, "http://ha.local:18099", "secret")
        stream = client.async_stream_events()
        snapshot = await anext(stream)
        dtmf = await anext(stream)
        await stream.aclose()
        assert snapshot.revision == 7
        assert snapshot.call.last_caller_number == "+4912345"
        assert dtmf.digit == "#"
        assert dtmf.duration_ms == 120
        assert dtmf.remote_number == "**620"
        assert dtmf.call_id == "call-123@example.org"
        assert dtmf.instance_id == "12345678-1234-5678-9234-567812345678"
        assert session.calls[0][2]["headers"]["Accept"] == "text/event-stream"

    asyncio.run(run_test())
