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
    normalize_api_url,
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


def test_get_info_uses_bearer_token(info_payload):
    async def run_test() -> None:
        session = FakeSession(FakeResponse(200, info_payload))
        client = GatewayAPIClient(session, "http://ha.local:18099", "secret")
        info = await client.async_get_info()
        assert info.gateway_version == "0.9.0"
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


def test_sse_status_event(status_payload):
    async def run_test() -> None:
        data = json.dumps(status_payload, separators=(",", ":")).encode()
        session = FakeSession(
            FakeResponse(
                200,
                lines=[
                    b": keepalive\n",
                    b"event: status\n",
                    b"id: 7\n",
                    b"data: " + data + b"\n",
                    b"\n",
                ],
            )
        )
        client = GatewayAPIClient(session, "http://ha.local:18099", "secret")
        stream = client.async_stream_status()
        snapshot = await anext(stream)
        await stream.aclose()
        assert snapshot.revision == 7
        assert snapshot.call.last_caller_number == "+4912345"
        assert session.calls[0][2]["headers"]["Accept"] == "text/event-stream"

    asyncio.run(run_test())
