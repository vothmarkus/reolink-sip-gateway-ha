"""Regression tests for the event stream using Home Assistant's task lifecycle."""

from __future__ import annotations

import asyncio
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant, callback

from custom_components.reolink_sip_gateway import async_unload_entry
from custom_components.reolink_sip_gateway.api import GatewayConnectionError
from custom_components.reolink_sip_gateway.const import DOMAIN, EVENT_DTMF
from custom_components.reolink_sip_gateway.coordinator import GatewayCoordinator
from custom_components.reolink_sip_gateway.model import GatewayDTMFEvent, GatewayInfo, GatewayStatus


class EventAPI:
    """Keep a stream open until an event, disconnect, or cancellation arrives."""

    def __init__(self) -> None:
        self.events: asyncio.Queue[GatewayStatus | GatewayDTMFEvent | Exception] = asyncio.Queue()
        self.opened = asyncio.Event()
        self.closed = asyncio.Event()
        self.connections = 0

    async def async_stream_events(self):
        self.connections += 1
        self.closed.clear()
        try:
            self.opened.set()
            while True:
                event = await self.events.get()
                if isinstance(event, Exception):
                    raise event
                yield event
        finally:
            self.closed.set()


@pytest.fixture
def make_runtime(tmp_path, info_payload):
    """Construct real HA task tracking inside each test's event loop."""

    def create():
        hass = HomeAssistant(str(tmp_path))
        entry = ConfigEntry(
            version=1,
            minor_version=1,
            domain=DOMAIN,
            title="Gateway",
            source="user",
            data={},
            options={},
            unique_id=info_payload["instance_id"],
            discovery_keys=MappingProxyType({}),
            subentries_data=None,
        )
        api = EventAPI()
        coordinator = GatewayCoordinator(hass, entry, api, GatewayInfo.from_payload(info_payload))
        entry.runtime_data = coordinator
        return hass, entry, api, coordinator

    return create


@pytest.mark.parametrize("disconnected", [False, True])
def test_event_stream_does_not_block_home_assistant_start(
    make_runtime, monkeypatch, caplog, disconnected
):
    """Reproduce the reported startup phase with an idle or reconnecting stream."""
    monkeypatch.setattr("homeassistant.core.TIMEOUT_EVENT_START", 0.05)

    async def run_test() -> None:
        hass, _, api, coordinator = make_runtime()
        if disconnected:
            api.events.put_nowait(GatewayConnectionError("connection lost"))
        coordinator.start_event_stream()
        try:
            await asyncio.wait_for(api.opened.wait(), timeout=1)
            await asyncio.wait_for(hass.async_start(), timeout=1)
            assert hass.state is CoreState.running
            assert "Something is blocking Home Assistant" not in caplog.text
            await asyncio.wait_for(hass.async_block_till_done(), timeout=1)
            assert coordinator._event_task is not None
            assert not coordinator._event_task.done()
        finally:
            await coordinator.async_stop()
            await hass.async_stop(force=True)

    asyncio.run(run_test())


def test_event_stream_starts_once_and_can_restart_after_stop(make_runtime):
    async def run_test() -> None:
        hass, _, api, coordinator = make_runtime()
        try:
            for expected_connections in (1, 2):
                api.opened.clear()
                coordinator.start_event_stream()
                coordinator.start_event_stream()
                await asyncio.wait_for(api.opened.wait(), timeout=1)
                assert api.connections == expected_connections
                await asyncio.wait_for(coordinator.async_stop(), timeout=1)
                assert api.closed.is_set()
                assert coordinator._event_task is None
                await coordinator.async_stop()
        finally:
            await coordinator.async_stop()
            await hass.async_stop(force=True)

    asyncio.run(run_test())


def test_config_entry_cleanup_cancels_stream(make_runtime):
    """HA must own the stream even when the normal unload path is skipped."""

    async def run_test() -> None:
        hass, entry, api, coordinator = make_runtime()
        coordinator.start_event_stream()
        try:
            await asyncio.wait_for(api.opened.wait(), timeout=1)
            await asyncio.wait_for(entry._async_process_on_unload(hass), timeout=1)
            assert api.closed.is_set()
            assert coordinator._event_task.cancelled()
        finally:
            await coordinator.async_stop()
            await hass.async_stop(force=True)

    asyncio.run(run_test())


def test_home_assistant_shutdown_cancels_stream(make_runtime):
    async def run_test() -> None:
        hass, _, api, coordinator = make_runtime()
        coordinator.start_event_stream()
        try:
            await asyncio.wait_for(api.opened.wait(), timeout=1)
            await asyncio.wait_for(hass.async_stop(force=True), timeout=1)
            assert api.closed.is_set()
            assert coordinator._event_task.cancelled()
        finally:
            await coordinator.async_stop()
            await hass.async_stop(force=True)

    asyncio.run(run_test())


@pytest.mark.parametrize("unloaded", [False, True])
def test_integration_stops_stream_only_after_platforms_unload(make_runtime, unloaded):
    async def run_test() -> None:
        hass, entry, api, coordinator = make_runtime()
        hass.config_entries = SimpleNamespace(
            async_unload_platforms=AsyncMock(return_value=unloaded)
        )
        coordinator.start_event_stream()
        try:
            await asyncio.wait_for(api.opened.wait(), timeout=1)
            assert await async_unload_entry(hass, entry) is unloaded
            assert api.closed.is_set() is unloaded
            if not unloaded:
                assert not coordinator._event_task.done()
        finally:
            await coordinator.async_stop()
            await hass.async_stop(force=True)

    asyncio.run(run_test())


def test_background_stream_delivers_status_and_dtmf(make_runtime, status_payload, dtmf_payload):
    async def run_test() -> None:
        hass, _, api, coordinator = make_runtime()
        events = []

        @callback
        def record_event(event):
            events.append(event.data)

        unsubscribe = hass.bus.async_listen(EVENT_DTMF, record_event)
        status = GatewayStatus.from_payload(status_payload)
        dtmf = GatewayDTMFEvent.from_payload(dtmf_payload)
        api.events.put_nowait(status)
        api.events.put_nowait(dtmf)
        coordinator.start_event_stream()
        try:
            await asyncio.wait_for(api.opened.wait(), timeout=1)
            await asyncio.wait_for(hass.async_block_till_done(), timeout=1)
            assert coordinator.data == status
            assert events == [dtmf.home_assistant_event_data()]
        finally:
            unsubscribe()
            await coordinator.async_stop()
            await hass.async_stop(force=True)

    asyncio.run(run_test())
