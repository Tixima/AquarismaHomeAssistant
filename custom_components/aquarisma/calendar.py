"""One calendar per aquarium. Events are loaded for the visible range only."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .client import AquarismaError
from .entity import AquarismaEntity
from .errors import action_failed
from .platform import async_setup_platform_entities

PARALLEL_UPDATES = 0
_MAX_RANGE = timedelta(days=62)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    await async_setup_platform_entities(hass, entry, async_add_entities, "calendar", AquarismaCalendar)


class AquarismaCalendar(AquarismaEntity, CalendarEntity):
    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        if end_date - start_date > _MAX_RANGE:
            end_date = start_date + _MAX_RANGE
        try:
            payload = await self.coordinator.client.calendar(start_date.isoformat(), end_date.isoformat())
        except AquarismaError as error:
            raise action_failed(error) from error
        events: list[CalendarEvent] = []
        for row in payload.get("events") or []:
            if not isinstance(row, dict) or row.get("aquarium_id") != self.spec["aquarium_id"]:
                continue
            start = dt_util.parse_datetime(str(row.get("start") or ""))
            end = dt_util.parse_datetime(str(row.get("end") or ""))
            if start is None or end is None or end < start:
                continue
            events.append(CalendarEvent(
                start=start,
                end=end,
                summary=str(row.get("summary") or ""),
                description=row.get("description") if isinstance(row.get("description"), str) else None,
                uid=row.get("uid") if isinstance(row.get("uid"), str) else None,
            ))
        return events
