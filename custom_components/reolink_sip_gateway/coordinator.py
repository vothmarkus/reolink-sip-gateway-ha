"""Data coordination for Reolink SIP Gateway."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    GatewayAPIClient,
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayForbiddenError,
    GatewayProtocolError,
)
from .const import DOMAIN, EVENT_DTMF, POLL_INTERVAL
from .model import GatewayDTMFEvent, GatewayInfo, GatewayStatus

_LOGGER = logging.getLogger(__name__)
_RECONNECT_DELAYS = (1, 2, 5, 10, 30)


class GatewayCoordinator(DataUpdateCoordinator[GatewayStatus]):
    """Combine immediate SSE updates with a conservative polling fallback."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: GatewayAPIClient,
        info: GatewayInfo,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=POLL_INTERVAL,
            always_update=False,
        )
        self.api = api
        self.info = info
        self._event_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def _async_update_data(self) -> GatewayStatus:
        try:
            return await self.api.async_get_status()
        except GatewayAuthenticationError as err:
            raise ConfigEntryAuthFailed("gateway token was rejected") from err
        except (GatewayConnectionError, GatewayForbiddenError, GatewayProtocolError) as err:
            raise UpdateFailed(str(err)) from err

    def start_event_stream(self) -> None:
        """Start the event listener once platform setup is complete."""
        if self._event_task is None or self._event_task.done():
            self._stop_event.clear()
            self._event_task = self.hass.async_create_task(self._event_loop())

    async def async_stop(self) -> None:
        """Stop the background event listener."""
        self._stop_event.set()
        if self._event_task is None:
            return
        self._event_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._event_task
        self._event_task = None

    async def _event_loop(self) -> None:
        failures = 0
        while not self._stop_event.is_set():
            try:
                async for event in self.api.async_stream_events():
                    failures = 0
                    if self._stop_event.is_set():
                        return
                    if isinstance(event, GatewayDTMFEvent):
                        self._fire_dtmf_event(event)
                        continue
                    snapshot = event
                    if (
                        self.data is not None
                        and snapshot.gateway.started_at == self.data.gateway.started_at
                        and snapshot.revision < self.data.revision
                    ):
                        continue
                    self.async_set_updated_data(snapshot)
            except asyncio.CancelledError:
                raise
            except GatewayAuthenticationError:
                _LOGGER.warning("Gateway event stream rejected the configured token")
                await self.async_refresh()
                failures += 1
            except GatewayForbiddenError:
                _LOGGER.warning("Gateway event stream rejected the source network")
                failures += 1
            except (GatewayConnectionError, GatewayProtocolError) as err:
                failures += 1
                if failures == 1:
                    _LOGGER.debug("Gateway event stream disconnected: %s", err)

            delay = _RECONNECT_DELAYS[min(failures - 1, len(_RECONNECT_DELAYS) - 1)]
            with suppress(TimeoutError):
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)

    def _fire_dtmf_event(self, event: GatewayDTMFEvent) -> None:
        """Validate gateway identity and fire the public Home Assistant event."""
        if event.instance_id != self.info.instance_id:
            raise GatewayProtocolError("gateway event identity changed")
        self.hass.bus.async_fire(EVENT_DTMF, event.home_assistant_event_data())
