"""Call-control buttons for Reolink SIP Gateway."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import (
    GatewayAuthenticationError,
    GatewayCommandError,
    GatewayConnectionError,
    GatewayForbiddenError,
    GatewayProtocolError,
)
from .const import CAPABILITY_HANGUP, CAPABILITY_TEST_CALL, DOMAIN
from .coordinator import GatewayCoordinator
from .entity import GatewayEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the supported gateway controls."""
    coordinator: GatewayCoordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    if CAPABILITY_TEST_CALL in coordinator.info.capabilities:
        entities.append(GatewayTestCallButton(coordinator))
    if CAPABILITY_HANGUP in coordinator.info.capabilities:
        entities.append(GatewayHangupButton(coordinator))
    async_add_entities(entities)


class GatewayButton(GatewayEntity, ButtonEntity):
    """Base class that turns API errors into localized UI errors."""

    async def _async_run_command(self, command: str) -> None:
        try:
            if command == "test_call":
                await self.coordinator.api.async_start_test_call()
            else:
                await self.coordinator.api.async_hangup()
        except GatewayAuthenticationError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_auth",
            ) from err
        except GatewayForbiddenError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="forbidden",
            ) from err
        except GatewayConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
            ) from err
        except GatewayProtocolError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_response",
            ) from err
        except GatewayCommandError as err:
            translation_key = {
                "call_busy": "call_busy",
                "sip_unavailable": "sip_unavailable",
                "gateway_unavailable": "gateway_unavailable",
            }.get(err.code, "command_failed")
            placeholders = {"message": str(err)} if translation_key == "command_failed" else None
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=translation_key,
                translation_placeholders=placeholders,
            ) from err
        await self.coordinator.async_request_refresh()


class GatewayTestCallButton(GatewayButton):
    """Start an outgoing call to the app's configured destination."""

    _attr_translation_key = "test_call"
    _attr_icon = "mdi:phone-outgoing"

    def __init__(self, coordinator: GatewayCoordinator) -> None:
        super().__init__(coordinator, "test_call")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.controls.test_call_available

    async def async_press(self) -> None:
        await self._async_run_command("test_call")


class GatewayHangupButton(GatewayButton):
    """End the current incoming or outgoing call."""

    _attr_translation_key = "hangup"
    _attr_icon = "mdi:phone-hangup"

    def __init__(self, coordinator: GatewayCoordinator) -> None:
        super().__init__(coordinator, "hangup")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.controls.hangup_available

    async def async_press(self) -> None:
        await self._async_run_command("hangup")
