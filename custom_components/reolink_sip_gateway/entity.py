"""Shared entity base for Reolink SIP Gateway."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import GatewayCoordinator


class GatewayEntity(CoordinatorEntity[GatewayCoordinator]):
    """Attach all entities to one stable gateway device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: GatewayCoordinator, entity_key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.info.instance_id}_{entity_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.info.instance_id)},
            name=NAME,
            manufacturer="Reolink SIP Gateway Community",
            model="Home Assistant SIP gateway",
            sw_version=coordinator.info.gateway_version,
        )
