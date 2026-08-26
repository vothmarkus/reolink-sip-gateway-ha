"""Shared payload builders for unit tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest


@pytest.fixture
def info_payload() -> dict[str, Any]:
    """Return a valid /info response."""
    return {
        "api_version": 1,
        "gateway_version": "1.2.0",
        "instance_id": "12345678-1234-5678-9234-567812345678",
        "name": "Reolink SIP Gateway",
        "capabilities": [
            "call_status",
            "caller_number",
            "dtmf_events",
            "events",
            "hangup",
            "route_test_calls",
            "test_call",
        ],
    }


@pytest.fixture
def status_payload() -> dict[str, Any]:
    """Return a valid idle /status response."""
    return {
        "api_version": 1,
        "revision": 7,
        "updated_at": "2026-08-17T10:30:00Z",
        "gateway": {
            "version": "1.2.0",
            "state": "idle",
            "started_at": "2026-08-17T09:00:00Z",
            "home_assistant_connected": True,
            "dry_run": False,
            "last_visitor_event": "2026-08-17T10:00:00Z",
        },
        "sip": {"registered": True},
        "call": {
            "active": False,
            "state": "idle",
            "last_direction": "incoming",
            "last_caller_number": "+4912345",
            "started_at": "2026-08-17T10:20:00Z",
            "ended_at": "2026-08-17T10:21:05Z",
            "codec": "pcma",
            "last_route_id": "wohnung_1",
            "last_route_name": "Wohnung 1",
        },
        "media": {
            "configured_reolink_mode": "nvr",
            "active_reolink_mode": "nvr",
            "profile": "Baichuan/Baichuan (sub)",
            "receive_mode": "baichuan",
            "talkback_mode": "nvr",
            "echo_cancellation": "active",
            "calibrated_delay_ms": 1399,
            "current_delay_ms": 1399,
            "calibration_status": "calibrated",
        },
        "controls": {
            "test_call_available": True,
            "hangup_available": False,
        },
        "routes": [
            {"id": "wohnung_1", "name": "Wohnung 1", "test_call_available": True},
            {"id": "wohnung_2", "name": "Wohnung 2", "test_call_available": False},
        ],
    }


@pytest.fixture
def dtmf_payload() -> dict[str, Any]:
    """Return a valid transient DTMF SSE payload."""
    return {
        "api_version": 1,
        "digit": "#",
        "duration_ms": 120,
        "call_direction": "incoming",
        "remote_number": "**620",
        "call_id": "call-123@example.org",
        "received_at": "2026-08-17T10:30:01Z",
        "instance_id": "12345678-1234-5678-9234-567812345678",
    }


@pytest.fixture
def copy_payload():
    """Return a helper that safely mutates fixture payloads."""
    return deepcopy
