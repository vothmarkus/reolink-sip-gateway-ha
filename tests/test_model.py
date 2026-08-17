"""Tests for API payload validation and entity presentation."""

from datetime import UTC, datetime

import pytest

from custom_components.reolink_sip_gateway.const import (
    STATUS_CONNECTED,
    STATUS_ERROR,
    STATUS_INCOMING,
    STATUS_OUTGOING,
    STATUS_READY,
)
from custom_components.reolink_sip_gateway.model import (
    GatewayDTMFEvent,
    GatewayInfo,
    GatewayStatus,
    InvalidPayloadError,
)


def test_info_validation(info_payload):
    info = GatewayInfo.from_payload(info_payload)
    assert info.gateway_version == "1.0.0"
    assert info.instance_id == "12345678-1234-5678-9234-567812345678"
    assert "events" in info.capabilities
    assert "dtmf_events" in info.capabilities


def test_dtmf_event_validation_and_home_assistant_contract(dtmf_payload):
    event = GatewayDTMFEvent.from_payload(dtmf_payload)
    assert event.digit == "#"
    assert event.duration_ms == 120
    assert event.home_assistant_event_data() == {
        "digit": "#",
        "duration_ms": 120,
        "call_direction": "incoming",
        "caller_number": "**620",
        "received_at": "2026-08-17T10:30:01+00:00",
        "instance_id": "12345678-1234-5678-9234-567812345678",
    }


def test_outgoing_dtmf_event_allows_empty_caller_number(dtmf_payload):
    dtmf_payload["call_direction"] = "outgoing"
    dtmf_payload["caller_number"] = ""
    assert GatewayDTMFEvent.from_payload(dtmf_payload).caller_number == ""


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("digit", "16"),
        ("digit", "a"),
        ("duration_ms", -1),
        ("duration_ms", 8193),
        ("call_direction", "idle"),
        ("caller_number", None),
        ("received_at", "2026-08-17T10:30:01"),
    ],
)
def test_dtmf_event_rejects_invalid_payload(dtmf_payload, copy_payload, field, value):
    payload = copy_payload(dtmf_payload)
    payload[field] = value
    with pytest.raises(InvalidPayloadError):
        GatewayDTMFEvent.from_payload(payload)


@pytest.mark.parametrize("field", ["api_version", "instance_id", "capabilities"])
def test_info_rejects_missing_required_fields(info_payload, copy_payload, field):
    payload = copy_payload(info_payload)
    payload.pop(field)
    with pytest.raises(InvalidPayloadError):
        GatewayInfo.from_payload(payload)


def test_idle_status_and_retained_caller(status_payload):
    status = GatewayStatus.from_payload(status_payload)
    assert status.presentation_status == STATUS_READY
    assert status.caller_number == "+4912345"
    assert status.call.duration_seconds() == 65


@pytest.mark.parametrize(
    ("gateway_state", "registered", "dry_run", "call_state", "direction", "expected"),
    [
        ("error", True, False, "idle", None, STATUS_ERROR),
        ("idle", False, False, "idle", None, STATUS_ERROR),
        ("idle", False, True, "idle", None, STATUS_READY),
        ("dialing", True, False, "dialing", "outgoing", STATUS_OUTGOING),
        (
            "connecting_media",
            True,
            False,
            "connecting_media",
            "incoming",
            STATUS_INCOMING,
        ),
        ("active", True, False, "active", "outgoing", STATUS_CONNECTED),
    ],
)
def test_status_mapping(
    status_payload,
    copy_payload,
    gateway_state,
    registered,
    dry_run,
    call_state,
    direction,
    expected,
):
    payload = copy_payload(status_payload)
    payload["gateway"]["state"] = gateway_state
    payload["gateway"]["dry_run"] = dry_run
    payload["sip"]["registered"] = registered
    payload["call"]["state"] = call_state
    payload["call"]["active"] = call_state != "idle"
    if direction is None:
        payload["call"].pop("direction", None)
    else:
        payload["call"]["direction"] = direction

    assert GatewayStatus.from_payload(payload).presentation_status == expected


def test_active_call_duration_uses_current_time(status_payload, copy_payload):
    payload = copy_payload(status_payload)
    payload["call"].update(
        {
            "active": True,
            "state": "active",
            "direction": "incoming",
            "caller_number": "**620",
            "started_at": "2026-08-17T10:20:00Z",
        }
    )
    payload["call"].pop("ended_at", None)
    call = GatewayStatus.from_payload(payload).call
    now = datetime(2026, 8, 17, 10, 20, 42, tzinfo=UTC)
    assert call.duration_seconds(now) == 42


def test_status_rejects_naive_timestamp(status_payload, copy_payload):
    payload = copy_payload(status_payload)
    payload["updated_at"] = "2026-08-17T10:30:00"
    with pytest.raises(InvalidPayloadError):
        GatewayStatus.from_payload(payload)


def test_idle_call_without_end_has_no_growing_duration(status_payload, copy_payload):
    payload = copy_payload(status_payload)
    payload["call"].pop("ended_at")
    assert GatewayStatus.from_payload(payload).call.duration_seconds() is None
