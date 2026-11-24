"""OAuth account linking for Aquarisma."""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .client import AquarismaClient, AquarismaError
from .const import (
    CLIENT_VERSION,
    CONF_ALLOW_WRITE,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CONNECTION_ID,
    CONF_POLL,
    CONF_REDIRECT_URI,
    CONF_TOKEN,
    CONF_USE_MY,
    DEFAULT_BASE_URL,
    DEFAULT_POLL,
    DOMAIN,
    MAX_POLL,
    MIN_POLL,
    MY_REDIRECT,
    READ_SCOPES,
    WRITE_SCOPES,
)
from .coordinator import AiohttpTransport
from .oauth import InvalidAquarismaUrl, authorize_url, code_verifier, normalize_base_url, stamp_token

_LOGGER = logging.getLogger(__name__)


class AquarismaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Link an Aquarisma account with PKCE. No client secret is stored."""

    VERSION = 1

    def __init__(self) -> None:
        self._base = ""
        self._redirect = ""
        self._client_id = ""
        self._verifier = ""
        self._allow_write = False
        self._reauth = False
        self._reconfigure = False

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._prepare(user_input)
            if not errors:
                return await self._start_oauth()
        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        self._reauth = True
        self._base = entry_data[CONF_BASE_URL]
        self._redirect = entry_data[CONF_REDIRECT_URI]
        self._client_id = entry_data[CONF_CLIENT_ID]
        self._allow_write = bool(entry_data.get(CONF_ALLOW_WRITE))
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self._start_oauth()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reconfigure_entry()
        self._reconfigure = True
        self._base = str(entry.data.get(CONF_BASE_URL) or DEFAULT_BASE_URL)
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._prepare(user_input)
            if not errors:
                return await self._start_oauth()
        redirect = entry.data.get(CONF_REDIRECT_URI, MY_REDIRECT)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(
                use_my=redirect == MY_REDIRECT,
                allow_write=bool(entry.data.get(CONF_ALLOW_WRITE, False)),
            ),
            errors=errors,
        )

    async def _prepare(self, user_input: dict[str, Any]) -> dict[str, str]:
        raw = user_input.get(CONF_BASE_URL)
        if not isinstance(raw, str) or not raw.strip():
            raw = self._base or DEFAULT_BASE_URL
        try:
            self._base = normalize_base_url(raw)
        except InvalidAquarismaUrl:
            return {"base": "invalid_url"}
        self._allow_write = bool(user_input.get(CONF_ALLOW_WRITE))
        use_my = bool(user_input.get(CONF_USE_MY, True))
        if use_my:
            self._redirect = MY_REDIRECT
        else:
            try:
                external = get_url(self.hass, allow_internal=False).rstrip("/")
            except NoURLAvailableError:
                return {"base": "no_external_url"}
            self._redirect = f"{external}/auth/external/callback"
        try:
            client = self._client()
            self._client_id = await client.register(self._redirect)
        except AquarismaError as error:
            _LOGGER.debug("Aquarisma registration failed with status %s (%s)", error.status, error.code)
            return {"base": "cannot_connect"}
        except aiohttp.ClientError:
            _LOGGER.debug("Aquarisma registration could not reach the host")
            return {"base": "cannot_connect"}
        return {}

    async def _start_oauth(self):
        self._verifier = code_verifier()
        scopes = READ_SCOPES + (WRITE_SCOPES if self._allow_write else [])
        url = authorize_url(
            self._base,
            client_id=self._client_id,
            redirect_uri=self._redirect,
            state=self.flow_id,
            verifier=self._verifier,
            scopes=scopes,
        )
        return self.async_external_step(step_id="auth", url=url)

    async def async_step_auth(self, user_input: dict[str, Any] | None = None):
        if not user_input or user_input.get("error"):
            return self.async_abort(reason="oauth_rejected")
        if user_input.get("state") and user_input.get("state") != self.flow_id:
            return self.async_abort(reason="oauth_state")
        code = user_input.get("code")
        if not isinstance(code, str) or not code:
            return self.async_abort(reason="oauth_rejected")
        try:
            client = self._client()
            token = await client.exchange(self._client_id, self._redirect, code, self._verifier)
            access = token.get("access_token")
            if not isinstance(access, str) or not access:
                return self.async_abort(reason="oauth_token")
            client.token = access
            identity = await client.me()
        except (AquarismaError, aiohttp.ClientError):
            _LOGGER.debug("Aquarisma token exchange failed")
            return self.async_abort(reason="oauth_token")
        connection_id = identity.get("connection_id")
        if not isinstance(connection_id, str) or not connection_id:
            return self.async_abort(reason="oauth_token")
        await self.async_set_unique_id(connection_id)
        data = {
            CONF_BASE_URL: self._base,
            CONF_CLIENT_ID: self._client_id,
            CONF_REDIRECT_URI: self._redirect,
            CONF_TOKEN: stamp_token(token, time.time()),
            CONF_CONNECTION_ID: connection_id,
            CONF_ALLOW_WRITE: self._allow_write,
        }
        title = identity.get("display_name") if isinstance(identity.get("display_name"), str) else None
        if self._reauth:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
        if self._reconfigure:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data_updates=data,
                reason="reconfigure_successful",
            )
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=title or "Aquarisma", data=data)

    def _client(self) -> AquarismaClient:
        return AquarismaClient(self._base, AiohttpTransport(async_get_clientsession(self.hass)), "", CLIENT_VERSION)

    @staticmethod
    def _schema(
        use_my: bool = True,
        allow_write: bool = False,
    ) -> vol.Schema:
        return vol.Schema({
            vol.Required(CONF_USE_MY, default=use_my): bool,
            vol.Required(CONF_ALLOW_WRITE, default=allow_write): bool,
        })

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return AquarismaOptionsFlow()


class AquarismaOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            interval = min(MAX_POLL, max(MIN_POLL, int(user_input[CONF_POLL])))
            return self.async_create_entry(data={CONF_POLL: interval})
        current = self.config_entry.options.get(CONF_POLL, DEFAULT_POLL) if self.config_entry else DEFAULT_POLL
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_POLL, default=current): vol.All(vol.Coerce(int), vol.Range(min=MIN_POLL, max=MAX_POLL)),
            }),
        )
