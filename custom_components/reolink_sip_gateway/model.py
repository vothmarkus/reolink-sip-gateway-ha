"""Validated models for the Reolink SIP Gateway API."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .const import (
    API_VERSION,
    STATUS_CONNECTED,
    STATUS_ERROR,
    STATUS_INCOMING,
    STATUS_OUTGOING,
    STATUS_READY,
)


class InvalidPayloadError(ValueError):
    """Raised when the gateway returned an invalid API payload."""


@dataclass(frozen=True, slots=True)
class GatewayInfo:
    """Stable gateway identity returned by /info."""

    api_version: int
    gateway_version: str
    instance_id: str
    name: str
    capabilities: frozenset[str]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> GatewayInfo:
        """Build and validate gateway information."""
        api_version = _required_int(payload, "api_version")
        if api_version != API_VERSION:
            raise InvalidPayloadError(f"unsupported API version {api_version}")

        instance_id = _required_str(payload, "instance_id")
        try:
            instance_id = str(UUID(instance_id))
        except ValueError as err:
            raise InvalidPayloadError("instance_id is not a UUID") from err

        raw_capabilities = payload.get("capabilities")
        if not isinstance(raw_capabilities, Sequence) or isinstance(raw_capabilities, (str, bytes)):
            raise InvalidPayloadError("capabilities must be an array")
        capabilities = frozenset(_array_string(value, "capabilities") for value in raw_capabilities)

        return cls(
            api_version=api_version,
            gateway_version=_required_str(payload, "gateway_version"),
            instance_id=instance_id,
            name=_required_str(payload, "name"),
            capabilities=capabilities,
        )


@dataclass(frozen=True, slots=True)
class GatewayDTMFEvent:
    """One transient completed RFC 4733 keypress from the SIP peer."""

    api_version: int
    digit: str
    duration_ms: int
    call_direction: str
    remote_number: str
    call_id: str
    received_at: datetime
    instance_id: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> GatewayDTMFEvent:
        """Build and validate a DTMF event from the SSE data object."""
        api_version = _required_int(payload, "api_version")
        if api_version != API_VERSION:
            raise InvalidPayloadError(f"unsupported API version {api_version}")

        digit = _required_str(payload, "digit")
        if digit not in frozenset("0123456789*#ABCD"):
            raise InvalidPayloadError("digit must be one RFC 4733 DTMF key")

        duration_ms = _required_non_negative_int(payload, "duration_ms")
        if duration_ms > 8192:
            raise InvalidPayloadError("duration_ms exceeds the RFC 4733 8 kHz limit")
        call_direction = _required_str(payload, "call_direction")
        if call_direction not in {"incoming", "outgoing"}:
            raise InvalidPayloadError("call_direction must be incoming or outgoing")

        call_id = _required_str(payload, "call_id")
        if len(call_id) > 256:
            raise InvalidPayloadError("call_id must not exceed 256 characters")

        instance_id = _required_str(payload, "instance_id")
        try:
            instance_id = str(UUID(instance_id))
        except ValueError as err:
            raise InvalidPayloadError("instance_id is not a UUID") from err

        return cls(
            api_version=api_version,
            digit=digit,
            duration_ms=duration_ms,
            call_direction=call_direction,
            remote_number=_required_str(payload, "remote_number"),
            call_id=call_id,
            received_at=_required_datetime(payload, "received_at"),
            instance_id=instance_id,
        )

    def home_assistant_event_data(self) -> dict[str, str | int]:
        """Return the deliberately small public Home Assistant event contract."""
        return {
            "digit": self.digit,
            "duration_ms": self.duration_ms,
            "call_direction": self.call_direction,
            "remote_number": self.remote_number,
            "call_id": self.call_id,
            "received_at": self.received_at.isoformat(),
            "instance_id": self.instance_id,
        }


@dataclass(frozen=True, slots=True)
class GatewayState:
    """Gateway process status."""

    version: str
    state: str
    started_at: datetime
    home_assistant_connected: bool
    dry_run: bool
    last_visitor_event: datetime | None
    last_error: str | None


@dataclass(frozen=True, slots=True)
class SIPState:
    """SIP registration status."""

    registered: bool
    last_registration_error: str | None


@dataclass(frozen=True, slots=True)
class CallState:
    """Current and most recent call status."""

    active: bool
    state: str
    direction: str | None
    last_direction: str | None
    caller_number: str | None
    last_caller_number: str | None
    started_at: datetime | None
    ended_at: datetime | None
    codec: str | None
    route_id: str | None
    route_name: str | None
    last_route_id: str | None
    last_route_name: str | None

    def duration_seconds(self, now: datetime | None = None) -> int | None:
        """Return current or most recently completed call duration."""
        if self.started_at is None:
            return None
        end = self.ended_at
        if self.active or self.state != "idle":
            end = now or datetime.now(UTC)
        elif end is None:
            return None
        return max(0, int((end - self.started_at).total_seconds()))


@dataclass(frozen=True, slots=True)
class MediaState:
    """Active Reolink media status."""

    configured_reolink_mode: str
    active_reolink_mode: str | None
    profile: str | None
    receive_mode: str | None
    receive_details: str | None
    talkback_mode: str | None
    talkback_details: str | None
    echo_cancellation: str | None
    calibrated_delay_ms: int
    current_delay_ms: int
    calibration_status: str | None
    last_calibration: datetime | None


@dataclass(frozen=True, slots=True)
class Controls:
    """Availability of gateway commands."""

    test_call_available: bool
    hangup_available: bool


@dataclass(frozen=True, slots=True)
class RouteState:
    """One configured call route exposed by gateway v1.2 or newer."""

    id: str
    name: str
    test_call_available: bool


@dataclass(frozen=True, slots=True)
class GatewayStatus:
    """Complete immutable status snapshot."""

    api_version: int
    revision: int
    updated_at: datetime
    gateway: GatewayState
    sip: SIPState
    call: CallState
    media: MediaState
    controls: Controls
    routes: tuple[RouteState, ...]

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> GatewayStatus:
        """Build and validate a complete gateway status snapshot."""
        api_version = _required_int(payload, "api_version")
        if api_version != API_VERSION:
            raise InvalidPayloadError(f"unsupported API version {api_version}")
        revision = _required_int(payload, "revision")
        if revision < 1:
            raise InvalidPayloadError("revision must be at least 1")

        gateway = _required_mapping(payload, "gateway")
        sip = _required_mapping(payload, "sip")
        call = _required_mapping(payload, "call")
        media = _required_mapping(payload, "media")
        controls = _required_mapping(payload, "controls")

        return cls(
            api_version=api_version,
            revision=revision,
            updated_at=_required_datetime(payload, "updated_at"),
            gateway=GatewayState(
                version=_required_str(gateway, "version"),
                state=_required_str(gateway, "state"),
                started_at=_required_datetime(gateway, "started_at"),
                home_assistant_connected=_required_bool(gateway, "home_assistant_connected"),
                dry_run=_required_bool(gateway, "dry_run"),
                last_visitor_event=_optional_datetime(gateway, "last_visitor_event"),
                last_error=_optional_str(gateway, "last_error"),
            ),
            sip=SIPState(
                registered=_required_bool(sip, "registered"),
                last_registration_error=_optional_str(sip, "last_registration_error"),
            ),
            call=CallState(
                active=_required_bool(call, "active"),
                state=_required_str(call, "state"),
                direction=_optional_str(call, "direction"),
                last_direction=_optional_str(call, "last_direction"),
                caller_number=_optional_str(call, "caller_number"),
                last_caller_number=_optional_str(call, "last_caller_number"),
                started_at=_optional_datetime(call, "started_at"),
                ended_at=_optional_datetime(call, "ended_at"),
                codec=_optional_str(call, "codec"),
                route_id=_optional_str(call, "route_id"),
                route_name=_optional_str(call, "route_name"),
                last_route_id=_optional_str(call, "last_route_id"),
                last_route_name=_optional_str(call, "last_route_name"),
            ),
            media=MediaState(
                configured_reolink_mode=_required_str(media, "configured_reolink_mode"),
                active_reolink_mode=_optional_str(media, "active_reolink_mode"),
                profile=_optional_str(media, "profile"),
                receive_mode=_optional_str(media, "receive_mode"),
                receive_details=_optional_str(media, "receive_details"),
                talkback_mode=_optional_str(media, "talkback_mode"),
                talkback_details=_optional_str(media, "talkback_details"),
                echo_cancellation=_optional_str(media, "echo_cancellation"),
                calibrated_delay_ms=_required_non_negative_int(media, "calibrated_delay_ms"),
                current_delay_ms=_required_non_negative_int(media, "current_delay_ms"),
                calibration_status=_optional_str(media, "calibration_status"),
                last_calibration=_optional_datetime(media, "last_calibration"),
            ),
            controls=Controls(
                test_call_available=_required_bool(controls, "test_call_available"),
                hangup_available=_required_bool(controls, "hangup_available"),
            ),
            routes=_route_states(payload),
        )

    @property
    def presentation_status(self) -> str:
        """Map detailed API state to the agreed Home Assistant status values."""
        if self.gateway.state == "error":
            return STATUS_ERROR
        if self.gateway.state == "idle" and not self.gateway.dry_run and not self.sip.registered:
            return STATUS_ERROR
        if self.call.state == "active":
            return STATUS_CONNECTED

        call_in_progress = self.call.active or self.call.state != "idle"
        if call_in_progress:
            if self.call.direction == "incoming":
                return STATUS_INCOMING
            if self.call.direction == "outgoing":
                return STATUS_OUTGOING
        return STATUS_READY

    @property
    def caller_number(self) -> str | None:
        """Return the current caller or retain the last incoming caller."""
        return self.call.caller_number or self.call.last_caller_number

    def route(self, route_id: str) -> RouteState | None:
        """Return the latest status for one stable route ID."""
        return next((route for route in self.routes if route.id == route_id), None)


def localized_direction(direction: str | None) -> str | None:
    """Return a stable German presentation value for call direction."""
    if direction == "incoming":
        return STATUS_INCOMING
    if direction == "outgoing":
        return STATUS_OUTGOING
    return None


_ROUTE_ID = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _route_states(payload: Mapping[str, Any]) -> tuple[RouteState, ...]:
    raw_routes = payload.get("routes", ())
    if not isinstance(raw_routes, Sequence) or isinstance(raw_routes, (str, bytes)):
        raise InvalidPayloadError("routes must be an array")
    routes: list[RouteState] = []
    seen: set[str] = set()
    for index, raw_route in enumerate(raw_routes):
        if not isinstance(raw_route, Mapping):
            raise InvalidPayloadError(f"routes[{index}] must be an object")
        route_id = _required_str(raw_route, "id")
        if not _ROUTE_ID.fullmatch(route_id):
            raise InvalidPayloadError(f"routes[{index}].id is invalid")
        if route_id in seen:
            raise InvalidPayloadError(f"routes contains duplicate id {route_id}")
        seen.add(route_id)
        name = _required_str(raw_route, "name")
        if len(name) > 64:
            raise InvalidPayloadError(f"routes[{index}].name is too long")
        routes.append(
            RouteState(
                id=route_id,
                name=name,
                test_call_available=_required_bool(raw_route, "test_call_available"),
            )
        )
    return tuple(routes)


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise InvalidPayloadError(f"{key} must be an object")
    return value


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise InvalidPayloadError(f"{key} must be a non-empty string")
    return value


def _optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidPayloadError(f"{key} must be a string")
    return value or None


def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise InvalidPayloadError(f"{key} must be a boolean")
    return value


def _required_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise InvalidPayloadError(f"{key} must be an integer")
    return value


def _required_non_negative_int(payload: Mapping[str, Any], key: str) -> int:
    value = _required_int(payload, key)
    if value < 0:
        raise InvalidPayloadError(f"{key} must not be negative")
    return value


def _required_datetime(payload: Mapping[str, Any], key: str) -> datetime:
    value = _optional_datetime(payload, key)
    if value is None:
        raise InvalidPayloadError(f"{key} must be a date-time")
    return value


def _optional_datetime(payload: Mapping[str, Any], key: str) -> datetime | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidPayloadError(f"{key} must be a date-time string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise InvalidPayloadError(f"{key} is not a valid date-time") from err
    if parsed.tzinfo is None:
        raise InvalidPayloadError(f"{key} must include a timezone")
    return parsed


def _array_string(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidPayloadError(f"{key} must contain non-empty strings")
    return value
