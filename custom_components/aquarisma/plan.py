"""Turn a snapshot into the entity set Home Assistant should hold.

Unique ids stay on the aquarium id. Display names are translation keys, so a
rename or a language change does not rewrite automations.
"""

from __future__ import annotations

from typing import Any

READ_CAPABILITIES = {
    "water": "water.read",
    "feeding": "feeding.plans",
    "care": "care.read",
    "livestock": "livestock.read",
    "inventory": "feeding.stock",
}

# Keys that have their own translated name. Anything else uses {parameter}.
KNOWN_PARAMETERS = {
    "temperature",
    "ph",
    "gh",
    "kh",
    "ammonia_nh3",
    "ammonium_nh4",
    "tan",
    "nitrite",
    "nitrate",
    "nitrate_n",
    "phosphate",
    "phosphate_p",
    "oxygen",
    "co2",
    "conductivity",
    "tds",
    "chlorine",
    "silicate",
    "iron",
    "potassium",
    "salinity",
    "specific_gravity",
    "alkalinity",
    "calcium",
    "magnesium",
    "orp",
    "copper",
}

PRECISION = {
    "temperature": 1,
    "ph": 2,
    "gh": 1,
    "kh": 1,
    "ammonia_nh3": 3,
    "ammonium_nh4": 2,
    "tan": 2,
    "nitrite": 2,
    "nitrate": 1,
    "nitrate_n": 2,
    "phosphate": 2,
    "phosphate_p": 3,
    "oxygen": 1,
    "co2": 1,
    "conductivity": 0,
    "tds": 0,
    "chlorine": 2,
    "silicate": 2,
    "iron": 2,
    "potassium": 1,
    "salinity": 1,
    "specific_gravity": 3,
    "alkalinity": 1,
    "calcium": 0,
    "magnesium": 0,
    "orp": 0,
    "copper": 2,
}

# Home Assistant unit strings. Missing codes fall back to the API symbol.
UNIT_BY_CODE = {
    "celsius": "°C",
    "fahrenheit": "°F",
    "liter": "L",
    "food_liter": "L",
    "milliliter": "mL",
    "us_gallon": "gal",
    "imperial_gallon": "imp gal",
    "mg_l": "mg/L",
    "concentration_ppm": "ppm",
    "hardness_ppm": "ppm",
    "alkalinity_ppm": "ppm",
    "tds_ppm": "ppm",
    "dh": "°dH",
    "dkh": "°dKH",
    "meq_l": "meq/L",
    "us_cm": "µS/cm",
    "ms_cm": "mS/cm",
    "psu": "PSU",
    "ppt": "ppt",
    "mv": "mV",
    "ph": None,
    "sg": None,
}

WATER_STATUS = ("unknown", "target", "watch", "uncertain", "warn", "critical")


def removal_allowed(status: int | None, complete: bool | None) -> bool:
    """Devices disappear only after a successful, complete snapshot."""

    return status == 200 and complete is True


def reconcile(
    existing: set[str],
    specs: list[dict[str, Any]] | None,
    status: int | None,
    complete: bool | None,
) -> tuple[set[str], set[str]]:
    """Return the ids to keep and the ids that may be removed.

    A failed or incomplete snapshot may add nothing destructive. New ids from a
    partial snapshot are kept, and nothing is removed until a complete snapshot
    says they are gone.
    """

    if specs is None or status != 200:
        return set(existing), set()
    desired = {spec["unique_id"] for spec in specs}
    if removal_allowed(status, complete):
        return desired, set(existing) - desired
    return set(existing) | desired, set()


def device_reconcile(
    existing: set[str],
    snapshot: dict[str, Any] | None,
    status: int | None,
    complete: bool | None,
) -> tuple[set[str], set[str]]:
    """Same removal rule as entities, applied to aquarium device ids."""

    if not isinstance(snapshot, dict) or status != 200:
        return set(existing), set()
    desired = device_ids(snapshot)
    if removal_allowed(status, complete):
        return desired, set(existing) - desired
    return set(existing) | desired, set()


def owning_entry(candidates: list[tuple[str, str]]) -> str | None:
    """Pick the config entry that owns one aquarium.

    Candidates are `(connection_id, entry_id)`. The lexicographically smallest
    connection id wins, so two connections never create the same device.
    Callers should pass the entry id when the connection id is still empty.
    """

    if not candidates:
        return None
    return sorted(candidates)[0][1]


def owned_aquarium_ids(
    entry_id: str,
    connection_id: str,
    mine: set[str],
    others: list[tuple[str, str, set[str]]],
) -> set[str]:
    """Aquariums this entry may create. `others` are complete claims of the rest."""

    owned: set[str] = set()
    label = connection_id or entry_id
    for aquarium_id in mine:
        candidates = [(label, entry_id)]
        for other_entry, other_connection, ids in others:
            if aquarium_id in ids:
                candidates.append((other_connection or other_entry, other_entry))
        if owning_entry(candidates) == entry_id:
            owned.add(aquarium_id)
    return owned


def entity_specs(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for aquarium in snapshot.get("aquariums") or []:
        if not isinstance(aquarium, dict) or not aquarium.get("id"):
            continue
        capabilities = set(aquarium.get("capabilities") or [])
        aquarium_id = str(aquarium["id"])
        specs.extend(_water(aquarium_id, aquarium, capabilities))
        specs.extend(_feeding(aquarium_id, aquarium, capabilities))
        specs.extend(_care(aquarium_id, aquarium, capabilities))
        specs.extend(_livestock(aquarium_id, aquarium, capabilities))
        specs.extend(_inventory(aquarium_id, aquarium, capabilities))
        specs.append({
            "unique_id": f"{aquarium_id}:aquarium:volume",
            "aquarium_id": aquarium_id,
            "domain": "sensor",
            "key": "volume",
            "translation_key": "volume",
            "value": aquarium.get("volume_liters"),
            "unit": "L",
            "device_class": "volume_storage",
            "enabled_default": True,
            "category": None,
        })
        specs.append({
            "unique_id": f"{aquarium_id}:calendar",
            "aquarium_id": aquarium_id,
            "domain": "calendar",
            "key": "calendar",
            "translation_key": "calendar",
            "enabled_default": True,
            "category": None,
        })
    return specs


def device_ids(snapshot: dict[str, Any]) -> set[str]:
    return {
        str(row["id"])
        for row in snapshot.get("aquariums") or []
        if isinstance(row, dict) and row.get("id")
    }


def _water(aquarium_id: str, aquarium: dict[str, Any], capabilities: set[str]) -> list[dict[str, Any]]:
    if READ_CAPABILITIES["water"] not in capabilities:
        return []
    water = aquarium.get("water") if isinstance(aquarium.get("water"), dict) else {}
    if water.get("available") is False:
        return []
    specs: list[dict[str, Any]] = []
    parameters = water.get("parameters") if isinstance(water.get("parameters"), dict) else {}
    for key in sorted(parameters):
        row = parameters[key] if isinstance(parameters[key], dict) else {}
        if "value" not in row:
            continue
        specs.append(_parameter(aquarium_id, key, row))
    specs.append(_binary(
        aquarium_id,
        "water:critical",
        "water_critical",
        (water.get("critical_count") or 0) > 0,
        True,
        binary_device_class="problem",
    ))
    specs.append({
        "unique_id": f"{aquarium_id}:water:status",
        "aquarium_id": aquarium_id,
        "domain": "sensor",
        "key": "water_status",
        "translation_key": "water_status",
        "value": water.get("status"),
        "enabled_default": True,
        "category": None,
        "options": list(WATER_STATUS),
    })
    if "warning_count" in water:
        specs.append(_count(aquarium_id, "water:warnings", "water_warnings", water.get("warning_count"), enabled=False))
    if "open_incidents" in water:
        specs.append(_count(aquarium_id, "water:incidents", "water_incidents", water.get("open_incidents"), enabled=False))
    if "last_measured_at" in water:
        specs.append({
            "unique_id": f"{aquarium_id}:water:last_measured",
            "aquarium_id": aquarium_id,
            "domain": "sensor",
            "key": "last_measured",
            "translation_key": "last_measured",
            "value": water.get("last_measured_at"),
            "device_class": "timestamp",
            "enabled_default": True,
            "category": None,
        })
    return specs


def _parameter(aquarium_id: str, key: str, row: dict[str, Any]) -> dict[str, Any]:
    unit = _unit(row)
    device_class = None
    if key == "temperature" and unit in {"°C", "°F"}:
        device_class = "temperature"
    elif key == "ph":
        device_class = "ph"
        unit = None
    known = key in KNOWN_PARAMETERS
    spec: dict[str, Any] = {
        "unique_id": f"{aquarium_id}:water:{key}",
        "aquarium_id": aquarium_id,
        "domain": "sensor",
        "key": key,
        "translation_key": key if known else "water_value",
        "value": row.get("value"),
        "unit": unit,
        "device_class": device_class,
        "state_class": "measurement" if row.get("realtime") else None,
        "enabled_default": True,
        "category": None,
        "attributes": {
            "measured_at": row.get("measured_at"),
            "freshness": row.get("freshness"),
            "origin": row.get("origin"),
            "realtime": bool(row.get("realtime")),
            "status": row.get("status"),
            "ranges": row.get("ranges"),
        },
    }
    if not known:
        spec["translation_placeholders"] = {"parameter": key}
    if key in PRECISION:
        spec["precision"] = PRECISION[key]
    return spec


def _unit(row: dict[str, Any]) -> str | None:
    code = row.get("unit_code")
    if isinstance(code, str) and code in UNIT_BY_CODE:
        mapped = UNIT_BY_CODE[code]
        return mapped
    unit = row.get("unit")
    if unit in (None, "", "pH", "ph"):
        return None
    return str(unit)


def _feeding(aquarium_id: str, aquarium: dict[str, Any], capabilities: set[str]) -> list[dict[str, Any]]:
    if "feeding.plans" not in capabilities and "feeding.logs" not in capabilities:
        return []
    feeding = aquarium.get("feeding") if isinstance(aquarium.get("feeding"), dict) else {}
    if feeding.get("available") is False:
        return []
    specs: list[dict[str, Any]] = []
    if "feeding.plans" in capabilities:
        specs.extend([
            _count(aquarium_id, "feeding:planned", "feeding_planned", feeding.get("planned_today")),
            _count(aquarium_id, "feeding:completed", "feeding_completed", feeding.get("completed_today")),
            _count(aquarium_id, "feeding:open", "feeding_open", feeding.get("open_today")),
            _count(aquarium_id, "feeding:overdue", "feeding_overdue", feeding.get("overdue")),
            _binary(aquarium_id, "feeding:due", "feeding_due", bool(feeding.get("due_now")), True, "problem"),
            _binary(aquarium_id, "feeding:fast", "feeding_fast", bool(feeding.get("fasting_today")), False, None),
        ])
        nxt = feeding.get("next") if isinstance(feeding.get("next"), dict) else None
        specs.append({
            "unique_id": f"{aquarium_id}:feeding:next",
            "aquarium_id": aquarium_id,
            "domain": "sensor",
            "key": "next_feeding",
            "translation_key": "next_feeding",
            "value": None if not nxt else nxt.get("at"),
            "device_class": "timestamp",
            "enabled_default": True,
            "category": None,
            "attributes": nxt or {},
        })
        if (
            "feeding.write" in capabilities
            and nxt
            and nxt.get("plan_id")
            and nxt.get("slot_id")
            and feeding.get("open_today") == 1
        ):
            specs.append({
                "unique_id": f"{aquarium_id}:feeding:confirm",
                "aquarium_id": aquarium_id,
                "domain": "button",
                "key": "confirm_feeding",
                "translation_key": "confirm_feeding",
                "action": "feeding.confirm",
                "parameters": {
                    "plan_id": nxt.get("plan_id"),
                    "slot_id": nxt.get("slot_id"),
                    "date": nxt.get("date"),
                },
                "enabled_default": True,
            })
    return specs


def _care(aquarium_id: str, aquarium: dict[str, Any], capabilities: set[str]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if "care.read" in capabilities:
        care = aquarium.get("care") if isinstance(aquarium.get("care"), dict) else {}
        specs.extend([
            _count(aquarium_id, "care:open", "care_open", care.get("open")),
            _count(aquarium_id, "care:overdue", "care_overdue", care.get("overdue")),
            _count(aquarium_id, "care:due_today", "care_due_today", care.get("due_today")),
            _binary(aquarium_id, "care:due", "care_due", bool(care.get("due_now")), True, "problem"),
        ])
        nxt = care.get("next") if isinstance(care.get("next"), dict) else None
        specs.append({
            "unique_id": f"{aquarium_id}:care:next",
            "aquarium_id": aquarium_id,
            "domain": "sensor",
            "key": "next_care",
            "translation_key": "next_care",
            "value": None if not nxt else nxt.get("due_at"),
            "device_class": "timestamp",
            "enabled_default": True,
            "category": None,
            "attributes": nxt or {},
        })
        if "care.write" in capabilities and nxt and nxt.get("id") and care.get("open") == 1:
            specs.append({
                "unique_id": f"{aquarium_id}:care:complete",
                "aquarium_id": aquarium_id,
                "domain": "button",
                "key": "complete_care",
                "translation_key": "complete_care",
                "action": "care.complete",
                "parameters": {"occurrence_id": nxt.get("id")},
                "enabled_default": False,
            })
    if "care.water_changes" in capabilities:
        change: dict[str, Any] = {}
        care = aquarium.get("care") if isinstance(aquarium.get("care"), dict) else {}
        if isinstance(care.get("water_change"), dict):
            change = care["water_change"]
        specs.append(_binary(
            aquarium_id,
            "care:water_change_due",
            "water_change_due",
            bool(change.get("due")),
            True,
            "problem",
        ))
        specs.append({
            "unique_id": f"{aquarium_id}:care:last_water_change",
            "aquarium_id": aquarium_id,
            "domain": "sensor",
            "key": "last_water_change",
            "translation_key": "last_water_change",
            "value": change.get("last_at"),
            "device_class": "timestamp",
            "enabled_default": True,
            "category": None,
            "attributes": {"liters": change.get("last_liters"), "days_since": change.get("days_since")},
        })
    return specs


def _livestock(aquarium_id: str, aquarium: dict[str, Any], capabilities: set[str]) -> list[dict[str, Any]]:
    if "livestock.read" not in capabilities or not isinstance(aquarium.get("livestock"), dict):
        return []
    stock = aquarium["livestock"]
    return [
        _count(aquarium_id, "livestock:fish", "livestock_fish", stock.get("fish")),
        _count(aquarium_id, "livestock:invertebrates", "livestock_invertebrates", stock.get("invertebrates")),
        _count(aquarium_id, "livestock:plants", "livestock_plants", stock.get("plants"), enabled=False),
        _count(aquarium_id, "livestock:animals", "livestock_animals", stock.get("animals")),
        _count(aquarium_id, "livestock:species", "livestock_species", stock.get("species"), enabled=False),
    ]


def _inventory(aquarium_id: str, aquarium: dict[str, Any], capabilities: set[str]) -> list[dict[str, Any]]:
    if "feeding.stock" not in capabilities or not isinstance(aquarium.get("inventory"), dict):
        return []
    if aquarium["inventory"].get("scope") != "assigned":
        return []
    stock = aquarium["inventory"]
    return [
        _count(aquarium_id, "inventory:low", "inventory_low", stock.get("low"), enabled=False),
        _count(aquarium_id, "inventory:expiring", "inventory_expiring", stock.get("expiring"), enabled=False),
        _count(aquarium_id, "inventory:expired", "inventory_expired", stock.get("expired"), enabled=False),
    ]


def _count(
    aquarium_id: str,
    suffix: str,
    translation_key: str,
    value: Any,
    enabled: bool = True,
) -> dict[str, Any]:
    return {
        "unique_id": f"{aquarium_id}:{suffix}",
        "aquarium_id": aquarium_id,
        "domain": "sensor",
        "key": translation_key,
        "translation_key": translation_key,
        "value": value,
        "enabled_default": enabled,
        "category": None if enabled else "diagnostic",
    }


def _binary(
    aquarium_id: str,
    suffix: str,
    translation_key: str,
    value: bool,
    enabled: bool,
    binary_device_class: str | None,
) -> dict[str, Any]:
    return {
        "unique_id": f"{aquarium_id}:{suffix}",
        "aquarium_id": aquarium_id,
        "domain": "binary_sensor",
        "key": translation_key,
        "translation_key": translation_key,
        "value": value,
        "binary_device_class": binary_device_class,
        "enabled_default": enabled,
        "category": None,
    }
