"""Tests for translating gateway stream items to Home Assistant events."""

from types import SimpleNamespace

import pytest

from custom_components.reolink_sip_gateway.api import GatewayProtocolError
from custom_components.reolink_sip_gateway.const import EVENT_DTMF
from custom_components.reolink_sip_gateway.coordinator import GatewayCoordinator
from custom_components.reolink_sip_gateway.model import GatewayDTMFEvent, GatewayInfo


class FakeBus:
    """Record fired Home Assistant events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, str | int]]] = []

    def async_fire(self, event_type: str, event_data: dict[str, str | int]) -> None:
        self.events.append((event_type, event_data))


def test_coordinator_fires_only_public_dtmf_event(info_payload, dtmf_payload):
    bus = FakeBus()
    coordinator = object.__new__(GatewayCoordinator)
    coordinator.hass = SimpleNamespace(bus=bus)
    coordinator.info = GatewayInfo.from_payload(info_payload)

    coordinator._fire_dtmf_event(GatewayDTMFEvent.from_payload(dtmf_payload))

    assert bus.events == [
        (
            EVENT_DTMF,
            {
                "digit": "#",
                "duration_ms": 120,
                "call_direction": "incoming",
                "remote_number": "**620",
                "call_id": "call-123@example.org",
                "received_at": "2026-08-17T10:30:01+00:00",
                "instance_id": "12345678-1234-5678-9234-567812345678",
            },
        )
    ]


def test_coordinator_rejects_dtmf_from_changed_gateway(info_payload, dtmf_payload):
    coordinator = object.__new__(GatewayCoordinator)
    coordinator.hass = SimpleNamespace(bus=FakeBus())
    coordinator.info = GatewayInfo.from_payload(info_payload)
    dtmf_payload["instance_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    with pytest.raises(GatewayProtocolError, match="identity changed"):
        coordinator._fire_dtmf_event(GatewayDTMFEvent.from_payload(dtmf_payload))
