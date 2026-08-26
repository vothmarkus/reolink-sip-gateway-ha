"""Tests for route-specific Home Assistant call controls."""

from __future__ import annotations

import asyncio

from custom_components.reolink_sip_gateway.button import (
    GatewayHangupButton,
    GatewayRouteTestCallButton,
    GatewayTestCallButton,
    async_setup_entry,
)
from custom_components.reolink_sip_gateway.model import GatewayInfo, GatewayStatus


class FakeAPI:
    """Record route-specific test-call commands."""

    def __init__(self) -> None:
        self.routes: list[str | None] = []

    async def async_start_test_call(self, route_id: str | None = None) -> None:
        self.routes.append(route_id)


class FakeCoordinator:
    """Provide the small coordinator surface used by button entities."""

    def __init__(self, info: GatewayInfo, data: GatewayStatus) -> None:
        self.info = info
        self.data = data
        self.api = FakeAPI()
        self.last_update_success = True
        self.listeners = []
        self.refreshes = 0

    def async_add_listener(self, listener):
        self.listeners.append(listener)
        return lambda: None

    async def async_request_refresh(self) -> None:
        self.refreshes += 1


class FakeEntry:
    """Capture platform unload callbacks."""

    def __init__(self, coordinator: FakeCoordinator) -> None:
        self.runtime_data = coordinator
        self.unload_callbacks = []

    def async_on_unload(self, callback) -> None:
        self.unload_callbacks.append(callback)


def test_route_catalog_creates_one_test_call_button_per_route(info_payload, status_payload):
    async def run_test() -> None:
        coordinator = FakeCoordinator(
            GatewayInfo.from_payload(info_payload), GatewayStatus.from_payload(status_payload)
        )
        entry = FakeEntry(coordinator)
        entities = []

        await async_setup_entry(None, entry, lambda new: entities.extend(new))

        route_buttons = [
            entity for entity in entities if isinstance(entity, GatewayRouteTestCallButton)
        ]
        assert [button.route_id for button in route_buttons] == ["wohnung_1", "wohnung_2"]
        assert len([entity for entity in entities if isinstance(entity, GatewayHangupButton)]) == 1
        assert route_buttons[0].available is True
        assert route_buttons[1].available is False

        await route_buttons[0].async_press()
        assert coordinator.api.routes == ["wohnung_1"]
        assert coordinator.refreshes == 1

    asyncio.run(run_test())


def test_new_route_is_added_after_status_catalog_update(info_payload, status_payload, copy_payload):
    async def run_test() -> None:
        coordinator = FakeCoordinator(
            GatewayInfo.from_payload(info_payload), GatewayStatus.from_payload(status_payload)
        )
        entry = FakeEntry(coordinator)
        entities = []
        await async_setup_entry(None, entry, lambda new: entities.extend(new))

        updated = copy_payload(status_payload)
        updated["routes"].append(
            {"id": "wohnung_3", "name": "Wohnung 3", "test_call_available": True}
        )
        coordinator.data = GatewayStatus.from_payload(updated)
        coordinator.listeners[0]()

        route_buttons = [
            entity for entity in entities if isinstance(entity, GatewayRouteTestCallButton)
        ]
        assert [button.route_id for button in route_buttons] == [
            "wohnung_1",
            "wohnung_2",
            "wohnung_3",
        ]

    asyncio.run(run_test())


def test_removed_route_button_becomes_unavailable(info_payload, status_payload, copy_payload):
    async def run_test() -> None:
        coordinator = FakeCoordinator(
            GatewayInfo.from_payload(info_payload), GatewayStatus.from_payload(status_payload)
        )
        entry = FakeEntry(coordinator)
        entities = []
        await async_setup_entry(None, entry, lambda new: entities.extend(new))
        route_button = next(
            entity
            for entity in entities
            if isinstance(entity, GatewayRouteTestCallButton) and entity.route_id == "wohnung_1"
        )
        assert route_button.available is True

        updated = copy_payload(status_payload)
        updated["routes"] = updated["routes"][1:]
        coordinator.data = GatewayStatus.from_payload(updated)
        assert route_button.available is False

    asyncio.run(run_test())


def test_legacy_gateway_keeps_single_test_call_button(info_payload, status_payload, copy_payload):
    async def run_test() -> None:
        info = copy_payload(info_payload)
        info["capabilities"].remove("route_test_calls")
        status = copy_payload(status_payload)
        status.pop("routes")
        coordinator = FakeCoordinator(
            GatewayInfo.from_payload(info), GatewayStatus.from_payload(status)
        )
        entry = FakeEntry(coordinator)
        entities = []
        await async_setup_entry(None, entry, lambda new: entities.extend(new))

        legacy_buttons = [
            entity for entity in entities if isinstance(entity, GatewayTestCallButton)
        ]
        assert len(legacy_buttons) == 1
        await legacy_buttons[0].async_press()
        assert coordinator.api.routes == [None]

    asyncio.run(run_test())
