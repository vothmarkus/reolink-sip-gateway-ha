"""Async client for the Reolink SIP Gateway integration API."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Mapping
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import GATEWAY_API_PATH, GATEWAY_API_PORT
from .model import GatewayInfo, GatewayStatus, InvalidPayloadError

REQUEST_TIMEOUT = ClientTimeout(total=10)
STREAM_TIMEOUT = ClientTimeout(total=None, connect=10, sock_connect=10, sock_read=90)
MAX_SSE_LINE_BYTES = 1024 * 1024
_HOST_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


class GatewayAPIError(Exception):
    """Base exception for gateway API errors."""


class GatewayConnectionError(GatewayAPIError):
    """Raised when the local gateway cannot be reached."""


class GatewayAuthenticationError(GatewayAPIError):
    """Raised when the bearer token is rejected."""


class GatewayForbiddenError(GatewayAPIError):
    """Raised when the gateway rejects the source network."""


class GatewayProtocolError(GatewayAPIError):
    """Raised for incompatible or malformed API responses."""


class GatewayCommandError(GatewayAPIError):
    """Raised when a call-control command is rejected."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class GatewayAPIClient:
    """Small dependency-free client around Home Assistant's shared session."""

    def __init__(self, session: ClientSession, api_url: str, token: str) -> None:
        self._session = session
        self.api_url = normalize_api_url(api_url)
        self._token = token.strip()
        if not self._token:
            raise ValueError("token must not be empty")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    async def async_get_info(self) -> GatewayInfo:
        """Read and validate API identity and capabilities."""
        try:
            payload = await self._async_request_json("GET", "/info", {200})
        except GatewayCommandError as err:
            raise GatewayProtocolError(str(err)) from err
        try:
            return GatewayInfo.from_payload(payload)
        except InvalidPayloadError as err:
            raise GatewayProtocolError(str(err)) from err

    async def async_get_status(self) -> GatewayStatus:
        """Read and validate the latest complete status snapshot."""
        try:
            payload = await self._async_request_json("GET", "/status", {200})
        except GatewayCommandError as err:
            raise GatewayProtocolError(str(err)) from err
        return self._parse_status(payload)

    async def async_start_test_call(self) -> None:
        """Start a call to the destination configured in the app."""
        await self._async_request_json("POST", "/calls/test", {202})

    async def async_hangup(self) -> None:
        """End the active call; the endpoint is idempotent."""
        await self._async_request_json("POST", "/calls/hangup", {202, 204})

    async def async_stream_status(self) -> AsyncIterator[GatewayStatus]:
        """Yield complete status snapshots from the SSE endpoint."""
        headers = {**self._headers, "Accept": "text/event-stream"}
        try:
            async with self._session.get(
                self._url("/events"), headers=headers, timeout=STREAM_TIMEOUT
            ) as response:
                if response.status != 200:
                    await self._raise_for_status(response)

                event_type: str | None = None
                data_lines: list[str] = []
                while True:
                    raw_line = await response.content.readline()
                    if not raw_line:
                        raise GatewayConnectionError("event stream closed")
                    if len(raw_line) > MAX_SSE_LINE_BYTES:
                        raise GatewayProtocolError("event stream line is too large")
                    try:
                        line = raw_line.decode("utf-8").rstrip("\r\n")
                    except UnicodeDecodeError as err:
                        raise GatewayProtocolError("event stream is not valid UTF-8") from err

                    if not line:
                        if data_lines and event_type in (None, "status"):
                            yield self._parse_sse_data("\n".join(data_lines))
                        event_type = None
                        data_lines.clear()
                        continue
                    if line.startswith(":"):
                        continue

                    field, separator, value = line.partition(":")
                    if separator and value.startswith(" "):
                        value = value[1:]
                    if field == "event":
                        event_type = value
                    elif field == "data":
                        data_lines.append(value)
        except GatewayCommandError as err:
            raise GatewayProtocolError(str(err)) from err
        except (GatewayAPIError, asyncio.CancelledError):
            raise
        except (TimeoutError, ClientError) as err:
            raise GatewayConnectionError("cannot read gateway event stream") from err

    async def _async_request_json(
        self, method: str, path: str, expected_statuses: set[int]
    ) -> Mapping[str, Any]:
        try:
            async with self._session.request(
                method,
                self._url(path),
                headers=self._headers,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status not in expected_statuses:
                    await self._raise_for_status(response)
                if response.status == 204:
                    return {}
                try:
                    payload = await response.json(content_type=None)
                except (json.JSONDecodeError, ValueError) as err:
                    raise GatewayProtocolError("gateway returned invalid JSON") from err
        except (GatewayAPIError, asyncio.CancelledError):
            raise
        except (TimeoutError, ClientError) as err:
            raise GatewayConnectionError("cannot connect to gateway") from err

        if not isinstance(payload, Mapping):
            raise GatewayProtocolError("gateway response must be a JSON object")
        return payload

    async def _raise_for_status(self, response: Any) -> None:
        status = response.status
        code = "http_error"
        message = f"gateway returned HTTP {status}"
        try:
            payload = await response.json(content_type=None)
            error = payload.get("error") if isinstance(payload, Mapping) else None
            if isinstance(error, Mapping):
                raw_code = error.get("code")
                raw_message = error.get("message")
                if isinstance(raw_code, str) and raw_code:
                    code = raw_code
                if isinstance(raw_message, str) and raw_message:
                    message = raw_message
        except (json.JSONDecodeError, ValueError, ClientError):
            pass

        if status == 401:
            raise GatewayAuthenticationError(message)
        if status == 403:
            raise GatewayForbiddenError(message)
        raise GatewayCommandError(code, message, status)

    def _parse_sse_data(self, data: str) -> GatewayStatus:
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as err:
            raise GatewayProtocolError("event stream returned invalid JSON") from err
        if not isinstance(payload, Mapping):
            raise GatewayProtocolError("event data must be a JSON object")
        return self._parse_status(payload)

    @staticmethod
    def _parse_status(payload: Mapping[str, Any]) -> GatewayStatus:
        try:
            return GatewayStatus.from_payload(payload)
        except InvalidPayloadError as err:
            raise GatewayProtocolError(str(err)) from err

    def _url(self, path: str) -> str:
        return f"{self.api_url}{path}"


def normalize_api_url(value: str) -> str:
    """Normalize a stored/internal URL to the versioned API root."""
    raw = value.strip()
    if not raw:
        raise ValueError("API URL must not be empty")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("API URL must be an absolute HTTP or HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API URL must not contain credentials, query, or fragment")

    path = parsed.path.rstrip("/")
    for endpoint in ("/info", "/status", "/events"):
        if path.endswith(f"/api/v1{endpoint}"):
            path = path[: -len(endpoint)]
            break
    if path in {"", "/"}:
        path = "/api/v1"
    if not path.endswith("/api/v1"):
        raise ValueError("API URL must end in /api/v1")

    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, "", ""))


def normalize_gateway_host(value: str) -> str:
    """Validate and normalize a hostname entered in the config flow."""
    host = value.strip().lower().rstrip(".")
    if not host or len(host) > 253:
        raise ValueError("gateway hostname is empty or too long")
    if any(character in host for character in ":/?#@") or any(
        character.isspace() for character in host
    ):
        raise ValueError("enter a hostname without scheme, port, or path")
    if not all(_HOST_LABEL.fullmatch(label) for label in host.split(".")):
        raise ValueError("gateway hostname is invalid")
    return host


def api_url_from_host(value: str) -> str:
    """Build the fixed local API root from an add-on hostname."""
    host = normalize_gateway_host(value)
    return f"http://{host}:{GATEWAY_API_PORT}{GATEWAY_API_PATH}"


def gateway_host_from_api_url(value: str) -> str:
    """Extract a hostname from a stored v0.1.0 API URL."""
    parsed = urlsplit(normalize_api_url(value))
    if parsed.hostname is None:
        raise ValueError("stored API URL has no hostname")
    return normalize_gateway_host(parsed.hostname)
