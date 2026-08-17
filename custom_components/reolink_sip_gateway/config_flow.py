"""Config flow for Reolink SIP Gateway."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    GatewayAPIClient,
    GatewayAuthenticationError,
    GatewayConnectionError,
    GatewayForbiddenError,
    GatewayProtocolError,
    normalize_api_url,
)
from .const import (
    CONF_API_URL,
    CONF_TOKEN,
    DEFAULT_API_URL,
    DOMAIN,
    REQUIRED_CAPABILITIES,
)
from .model import GatewayInfo

_LOGGER = logging.getLogger(__name__)


class ReolinkSIPGatewayConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the integration's setup and credential flows."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure a gateway from the address and Ingress token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data, info = await self._async_validate(user_input)
            except ValueError:
                errors["base"] = "invalid_url"
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayForbiddenError:
                errors["base"] = "forbidden"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except GatewayProtocolError:
                errors["base"] = "unsupported_api"
            except Exception:
                _LOGGER.exception("Unexpected error while validating the gateway")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info.instance_id)
                self._abort_if_unique_id_configured(updates={CONF_API_URL: data[CONF_API_URL]})
                return self.async_create_entry(title=info.name, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_setup_schema(user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the API address or token."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data, info = await self._async_validate(user_input)
            except ValueError:
                errors["base"] = "invalid_url"
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayForbiddenError:
                errors["base"] = "forbidden"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except GatewayProtocolError:
                errors["base"] = "unsupported_api"
            except Exception:
                _LOGGER.exception("Unexpected error while reconfiguring the gateway")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info.instance_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=data,
                )

        defaults = user_input or dict(entry.data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_setup_schema(defaults),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after a rejected token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store a replacement token."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {
                CONF_API_URL: entry.data[CONF_API_URL],
                CONF_TOKEN: user_input[CONF_TOKEN],
            }
            try:
                data, info = await self._async_validate(candidate)
            except GatewayAuthenticationError:
                errors["base"] = "invalid_auth"
            except GatewayForbiddenError:
                errors["base"] = "forbidden"
            except GatewayConnectionError:
                errors["base"] = "cannot_connect"
            except (GatewayProtocolError, ValueError):
                errors["base"] = "unsupported_api"
            except Exception:
                _LOGGER.exception("Unexpected error while reauthenticating the gateway")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info.instance_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_TOKEN: data[CONF_TOKEN]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): _token_selector()}),
            errors=errors,
        )

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, str], GatewayInfo]:
        api_url = normalize_api_url(str(user_input[CONF_API_URL]))
        token = str(user_input[CONF_TOKEN]).strip()
        if not token:
            raise GatewayAuthenticationError("token is empty")
        api = GatewayAPIClient(async_get_clientsession(self.hass), api_url, token)
        info = await api.async_get_info()
        if REQUIRED_CAPABILITIES - info.capabilities:
            raise GatewayProtocolError("required capabilities are missing")
        return {CONF_API_URL: api_url, CONF_TOKEN: token}, info


def _setup_schema(defaults: dict[str, Any] | None) -> vol.Schema:
    values = defaults or {}
    api_url = values.get(CONF_API_URL, DEFAULT_API_URL)
    schema: dict[vol.Marker, Any] = {
        vol.Required(CONF_API_URL, default=api_url): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        )
    }
    token = values.get(CONF_TOKEN)
    if token:
        schema[vol.Required(CONF_TOKEN, default=token)] = _token_selector()
    else:
        schema[vol.Required(CONF_TOKEN)] = _token_selector()
    return vol.Schema(schema)


def _token_selector() -> selector.TextSelector:
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )
