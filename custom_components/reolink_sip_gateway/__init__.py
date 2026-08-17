"""Reolink SIP Gateway integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    GatewayAPIClient,
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayForbiddenError,
    GatewayProtocolError,
)
from .const import CONF_API_URL, CONF_TOKEN, REQUIRED_CAPABILITIES
from .coordinator import GatewayCoordinator

PLATFORMS = (Platform.SENSOR, Platform.BUTTON)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Reolink SIP Gateway from a config entry."""
    api = GatewayAPIClient(
        async_get_clientsession(hass),
        entry.data[CONF_API_URL],
        entry.data[CONF_TOKEN],
    )
    try:
        info = await api.async_get_info()
    except GatewayAuthenticationError as err:
        raise ConfigEntryAuthFailed("gateway token was rejected") from err
    except GatewayConnectionError as err:
        raise ConfigEntryNotReady("gateway is not reachable") from err
    except GatewayForbiddenError as err:
        raise ConfigEntryError("gateway rejected the source network") from err
    except GatewayProtocolError as err:
        raise ConfigEntryError("gateway API is incompatible") from err

    if entry.unique_id and entry.unique_id != info.instance_id:
        raise ConfigEntryError("configured gateway identity has changed")
    if not entry.unique_id:
        hass.config_entries.async_update_entry(entry, unique_id=info.instance_id)

    missing = REQUIRED_CAPABILITIES - info.capabilities
    if missing:
        raise ConfigEntryError(
            f"gateway is missing required capabilities: {', '.join(sorted(missing))}"
        )

    coordinator = GatewayCoordinator(hass, entry, api, info)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start_event_stream()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Reolink SIP Gateway config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_stop()
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after URL or token reconfiguration."""
    await hass.config_entries.async_reload(entry.entry_id)
