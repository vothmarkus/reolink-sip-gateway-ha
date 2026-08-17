"""Sensors for Reolink SIP Gateway."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, ClassVar

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import STATUS_OPTIONS
from .coordinator import GatewayCoordinator
from .entity import GatewayEntity
from .model import localized_direction


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up both agreed gateway sensors."""
    coordinator: GatewayCoordinator = entry.runtime_data
    async_add_entities(
        (
            GatewayStatusSensor(coordinator),
            GatewayCallerNumberSensor(coordinator),
        )
    )


class GatewayStatusSensor(GatewayEntity, SensorEntity):
    """Compact, automation-friendly gateway/call state."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = list(STATUS_OPTIONS)

    def __init__(self, coordinator: GatewayCoordinator) -> None:
        super().__init__(coordinator, "status")

    @property
    def native_value(self) -> str:
        """Return the agreed five-state presentation."""
        return self.coordinator.data.presentation_status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose useful call details without creating extra entities."""
        data = self.coordinator.data
        call = data.call
        attributes: dict[str, Any] = {
            "sip_registered": data.sip.registered,
            "direction": localized_direction(call.direction or call.last_direction),
            "duration_seconds": call.duration_seconds(),
            "codec": call.codec,
            "last_incoming_number": call.last_caller_number,
        }
        if data.gateway.last_error:
            attributes["last_error"] = data.gateway.last_error
        if data.sip.last_registration_error:
            attributes["last_registration_error"] = data.sip.last_registration_error
        return {key: value for key, value in attributes.items() if value is not None}

    async def async_added_to_hass(self) -> None:
        """Refresh the duration attribute once per second during calls."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._async_refresh_duration,
                timedelta(seconds=1),
            )
        )

    @callback
    def _async_refresh_duration(self, _now: Any) -> None:
        call = self.coordinator.data.call
        if call.active or call.state != "idle":
            self.async_write_ha_state()


class GatewayCallerNumberSensor(GatewayEntity, SensorEntity):
    """Keep the last accepted incoming caller visible after hang-up."""

    _attr_translation_key = "caller_number"

    def __init__(self, coordinator: GatewayCoordinator) -> None:
        super().__init__(coordinator, "caller_number")

    @property
    def native_value(self) -> str | None:
        """Return current caller first, otherwise the persisted last caller."""
        return self.coordinator.data.caller_number

    @property
    def icon(self) -> str:
        """Show whether the number belongs to the current call."""
        if self.coordinator.data.call.caller_number:
            return "mdi:phone-in-talk"
        return "mdi:phone-incoming"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        call = self.coordinator.data.call
        return {
            "current": call.caller_number is not None,
            "last_call_ended_at": call.ended_at,
        }
