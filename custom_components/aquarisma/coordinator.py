"""One snapshot per Aquarisma connection."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import random
import time

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import AquarismaClient, AquarismaError, HttpResult, UnsupportedSchema
from .const import (
    CLIENT_VERSION,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CONNECTION_ID,
    CONF_POLL,
    CONF_TOKEN,
    DEFAULT_POLL,
    DOMAIN,
    MAX_POLL,
    MIN_POLL,
    TOKEN_REFRESH_SKEW,
)
from .oauth import access_token_expired, next_poll_interval, stamp_token

_LOGGER = logging.getLogger(__name__)


class AiohttpTransport:
    """Uses the shared Home Assistant session. Headers are never logged."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict | None,
    ) -> HttpResult:
        try:
            async with self.session.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                return HttpResult(
                    response.status,
                    {key.lower(): value for key, value in response.headers.items()},
                    await response.read(),
                )
        except TimeoutError as error:
            raise AquarismaError(0, "timeout", "Aquarisma did not answer in time") from error
        except aiohttp.ClientError as error:
            raise AquarismaError(0, "cannot_connect", "Aquarisma could not be reached") from error


class AquarismaCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._preferred = _preferred_interval(entry)
        self._failures = 0
        self._lock = asyncio.Lock()
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=_spaced(self._preferred),
            config_entry=entry,
        )
        token = entry.data.get(CONF_TOKEN) or {}
        self.client = AquarismaClient(
            entry.data[CONF_BASE_URL],
            AiohttpTransport(async_get_clientsession(hass)),
            str(token.get("access_token") or ""),
            CLIENT_VERSION,
        )
        self.etag: str | None = None
        self.last_status: int | None = None
        self.connection_id = entry.data.get(CONF_CONNECTION_ID)
        self.unsupported_schema: object | None = None

    async def _async_update_data(self) -> dict:
        await self._ensure_token()
        try:
            payload = await self._snapshot()
        except AquarismaError as error:
            if error.status != 401:
                raise self._failed(error) from error
            refreshed = await self._ensure_token(force=True)
            if not refreshed:
                raise ConfigEntryAuthFailed("Aquarisma rejected the access token") from error
            try:
                payload = await self._snapshot()
            except AquarismaError as second:
                if second.status == 401:
                    raise ConfigEntryAuthFailed("Aquarisma rejected the refreshed token") from second
                raise self._failed(second) from second
        self._failures = 0
        self.unsupported_schema = None
        self.update_interval = _spaced(self._interval_for(payload))
        return payload

    async def _snapshot(self) -> dict:
        try:
            result = await self.client.snapshot(self.etag)
        except UnsupportedSchema as error:
            self.last_status = None
            self.unsupported_schema = error.schema
            _LOGGER.warning("Aquarisma snapshot schema %s is not supported by this integration", error.schema)
            raise UpdateFailed(f"Unsupported snapshot schema {error.schema}") from error
        self.last_status = result.status
        _LOGGER.debug("Aquarisma snapshot for %s returned status %s", self.entry.entry_id, result.status)
        if result.not_modified and isinstance(self.data, dict):
            return self.data
        self.etag = result.etag
        payload = result.payload or {}
        if payload.get("connection_id"):
            self.connection_id = payload["connection_id"]
        return payload

    def _failed(self, error: AquarismaError) -> UpdateFailed:
        self.last_status = error.status
        self._failures += 1
        retry = error.retry_after
        self.update_interval = _spaced(
            next_poll_interval(
                self._preferred,
                failures=self._failures,
                retry_after=retry,
                minimum=MIN_POLL,
                maximum=MAX_POLL,
            )
        )
        return UpdateFailed(f"Aquarisma snapshot failed ({error.code})")

    def _interval_for(self, payload: dict) -> int:
        minimum = MIN_POLL
        maximum = MAX_POLL
        if isinstance(payload.get("min_poll_interval"), int):
            minimum = max(MIN_POLL, payload["min_poll_interval"])
        if isinstance(payload.get("max_poll_interval"), int):
            maximum = min(MAX_POLL, payload["max_poll_interval"])
        recommended = payload.get("recommended_poll_interval")
        preferred = self._preferred
        if CONF_POLL not in self.entry.options and isinstance(recommended, int):
            preferred = recommended
        return next_poll_interval(preferred, failures=0, retry_after=None, minimum=minimum, maximum=maximum)

    async def _ensure_token(self, force: bool = False) -> bool:
        """Refresh the access token when it is due. The token is not logged."""

        async with self._lock:
            token = dict(self.entry.data.get(CONF_TOKEN) or {})
            access = token.get("access_token")
            if not force and not access_token_expired(token, time.time(), TOKEN_REFRESH_SKEW):
                if isinstance(access, str) and access:
                    self.client.token = access
                    return True
                return False
            refresh = token.get("refresh_token")
            client_id = self.entry.data.get(CONF_CLIENT_ID)
            if not isinstance(refresh, str) or not refresh or not client_id:
                return False
            try:
                fresh = await self.client.refresh(str(client_id), refresh)
            except AquarismaError as error:
                if error.status in (400, 401):
                    raise ConfigEntryAuthFailed("Aquarisma rejected the refresh token") from error
                raise UpdateFailed(f"Aquarisma token refresh failed ({error.code})") from error
            if not isinstance(fresh, dict) or not fresh.get("access_token"):
                raise ConfigEntryAuthFailed("Aquarisma returned no access token")
            if "refresh_token" not in fresh:
                fresh["refresh_token"] = refresh
            stamped = stamp_token(fresh, time.time())
            self.client.token = str(stamped["access_token"])
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={**self.entry.data, CONF_TOKEN: stamped},
            )
            _LOGGER.debug("Aquarisma access token refreshed for %s", self.entry.entry_id)
            return True


def _preferred_interval(entry: ConfigEntry) -> int:
    raw = entry.options.get(CONF_POLL, DEFAULT_POLL)
    try:
        interval = int(raw)
    except (TypeError, ValueError):
        interval = DEFAULT_POLL
    return min(MAX_POLL, max(MIN_POLL, interval))


def _spaced(seconds: int) -> timedelta:
    jitter = random.uniform(0, min(15, max(seconds, 1) / 4))
    return timedelta(seconds=seconds + jitter)
