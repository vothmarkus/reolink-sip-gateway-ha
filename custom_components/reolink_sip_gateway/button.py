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
from .const import (
    CAPABILITY_HANGUP,
    CAPABILITY_ROUTE_TEST_CALLS,
    CAPABILITY_TEST_CALL,
    DOMAIN,
)
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
    if CAPABILITY_ROUTE_TEST_CALLS in coordinator.info.capabilities:
        known_route_ids: set[str] = set()

        def add_route_buttons() -> None:
            new_routes = [
                route for route in coordinator.data.routes if route.id not in known_route_ids
            ]
            if not new_routes:
                return
            known_route_ids.update(route.id for route in new_routes)
            async_add_entities(
                [
                    GatewayRouteTestCallButton(coordinator, route.id, route.name)
                    for route in new_routes
                ]
            )

        add_route_buttons()
        entry.async_on_unload(coordinator.async_add_listener(add_route_buttons))
    elif CAPABILITY_TEST_CALL in coordinator.info.capabilities:
        entities.append(GatewayTestCallButton(coordinator))
    if CAPABILITY_HANGUP in coordinator.info.capabilities:
        entities.append(GatewayHangupButton(coordinator))
    async_add_entities(entities)


class GatewayButton(GatewayEntity, ButtonEntity):
    """Base class that turns API errors into localized UI errors."""

    async def _async_run_command(self, command: str, route_id: str | None = None) -> None:
        try:
            if command == "test_call":
                await self.coordinator.api.async_start_test_call(route_id)
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
                "route_not_found": "route_not_found",
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


class GatewayRouteTestCallButton(GatewayButton):
    """Start an outgoing call for exactly one configured route."""

    _attr_translation_key = "route_test_call"
    _attr_icon = "mdi:phone-outgoing"

    def __init__(self, coordinator: GatewayCoordinator, route_id: str, route_name: str) -> None:
        super().__init__(coordinator, f"test_call_{route_id}")
        self.route_id = route_id
        self._attr_translation_placeholders = {"route_name": route_name}

    @property
    def available(self) -> bool:
        route = self.coordinator.data.route(self.route_id)
        return super().available and route is not None and route.test_call_available

    async def async_press(self) -> None:
        await self._async_run_command("test_call", self.route_id)


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
