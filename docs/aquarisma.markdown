---
title: Aquarisma
description: Monitor aquariums shared from Aquarisma and record feeding, care, water changes and manual tests.
ha_category:
  - Calendar
  - Sensor
ha_iot_class: Cloud Polling
ha_config_flow: true
ha_codeowners:
  - '@Tixima'
ha_domain: aquarisma
ha_platforms:
  - binary_sensor
  - button
  - calendar
  - sensor
ha_integration_type: hub
---

Aquarisma is a hosted aquarium journal. This integration connects one Aquarisma account link to Home Assistant and creates a device for every aquarium that link is allowed to see.

Home Assistant talks to your Aquarisma site over HTTPS. It does not use MQTT, a local bridge, or a client secret. The password is entered in the browser and is not stored.

## Prerequisites

- An Aquarisma site you can sign in to.
- A team on the Expert, Business, or Enterprise plan. External integrations are not included in Personal, Hobby, or Pro.
- The aquariums, teams, or whole account explicitly shared with the Home Assistant connection inside Aquarisma. Sharing a team does not share aquariums that the signed-in person cannot open.

## Configuration

{% details "To add the integration" %}

1. Go to {% my integrations title="Settings > Devices & services" %}.
2. Select **Add integration** and search for **Aquarisma**.
3. Leave **Use My Home Assistant for the return address** on unless this Home Assistant instance has its own public address.
4. Leave write access off if Home Assistant should only read. Turn it on to record a feeding, a care task, a water change, or a manual test.
5. Sign in on the Aquarisma page, choose what the connection may see, and confirm.

The integration always uses `https://aquarisma.com`. The dialog does not ask for an address and does not offer one in the options.

{% enddetails %}

The connection is one config entry. Adding the same Aquarisma connection twice is refused. Use **Reconfigure** to change the write permission, and the reauthentication prompt if the sign-in expires.

### Options

The update interval is 30 to 300 seconds. The default is 60. Aquarisma also enforces its own minimum and maximum. A shorter interval does not turn a manual test into a live sensor.

## Supported functionality

Each aquarium is a device. The identifier is `(aquarisma, <aquarium id>)`. The device name follows the name in Aquarisma. Entity names are translated and do not repeat the aquarium name.

The entity id is built from those names in the language Home Assistant was using when the entity was created. An aquarium named Rio gets `sensor.rio_temperature` in English and `sensor.rio_temperatur` in German. Copy the id from the UI. Do not guess it.

### Water

One sensor per parameter that has a reading slot in the aquarium profile. Known parameters have their own translated name. A parameter this version does not know yet is still created, and its name is the parameter key.

| Sensor | Device class | Notes |
| --- | --- | --- |
| Temperature | Temperature | `state_class: measurement` only when Aquarisma marks the reading `realtime: true`. |
| pH | pH | No unit. |
| Other parameters | none | Unit comes from the snapshot, for example mg/L, µS/cm, or °dH. |
| Water status | none | `unknown`, `target`, `watch`, `uncertain`, `warn`, or `critical`. |
| Last measured | Timestamp | Present when Aquarisma sends a last-reading time. |
| Volume | Volume storage | Liters. |
| Critical water reading | Problem | On when at least one parameter is critical. |
| Water warnings, open incidents | none | Diagnostic, disabled by default. |

Every water sensor has attributes:

- `measured_at`, when that sample was taken
- `freshness`: `current`, `aging`, `stale`, or `unknown`
- `origin`: where the value came from
- `realtime`: whether Aquarisma considers it a live sensor
- `status`: where the value sits against the target range
- `ranges`: the target and warning ranges, when the connection may see them

A manual test is `realtime: false`. Do not use it as the process value of a controller. A failed poll makes the entity `unavailable`. It does not repeat the last number as if it had just been measured.

### Feeding, care, livestock, and food

| Entity | Meaning |
| --- | --- |
| Feedings planned, completed, open, overdue | Counts for today in the aquarium's time zone. |
| Feeding due | Problem, on when a feeding is due now. |
| Fasting day | On when today is a fasting day. |
| Next feeding | Timestamp of the next planned slot. |
| Confirm next feeding | Button. Shown only when write access is granted and exactly one slot is still open. |
| Care tasks open, overdue, care due today | Counts. |
| Care due | Problem, on when a task is due now. |
| Next care task | Timestamp. |
| Complete next care task | Button. Disabled by default, and only created when exactly one task is open. |
| Water change due | Problem. Requires the water-change permission. |
| Last water change | Timestamp. |
| Calendar | Feeding and care inside the visible calendar range, at most 62 days per request. |
| Fish, invertebrates, animals | Counts. Shrimp and snails are invertebrates. Aquarisma does not split them further. |
| Plants, species | Diagnostic, disabled by default. |
| Food running low, expiring, expired | Diagnostic, disabled by default. Only food assigned to that aquarium. A team-wide stock is not shown as an aquarium sensor. |

### Actions

Actions run on the connection that owns the device. If two connections can see the same aquarium, the connection with the lexicographically smallest connection id owns it.

| Action | Purpose |
| --- | --- |
| `aquarisma.refresh` | Fetch a snapshot for every connection. |
| `aquarisma.confirm_feeding` | Confirm one planned feeding. Requires `aquarium_id`, `plan_id`, `slot_id`, and `date` (`YYYY-MM-DD` in the aquarium time zone). |
| `aquarisma.complete_care` | Complete one care occurrence. |
| `aquarisma.record_water_change` | Record a water change. `liters` is required. There is no default volume. |
| `aquarisma.record_measurement` | Record one manual reading. It is stored as a manual reading. |

`idempotency_key` is optional. Use 8 to 80 characters from letters, numbers, `.`, `_`, `:`, and `-`. Repeating the same key retries the same action. Reusing it for a different payload is rejected.

The buttons generate their own key per press. An automation that must not double-record should call the action with a stable key.

## Data updates

Home Assistant polls one snapshot per connection. Aquarisma returns an ETag. The next request sends `If-None-Match`. HTTP 304 keeps the current entities and deletes nothing.

The snapshot says whether it is `complete`. A timeout, HTTP 429, HTTP 500, or `complete: false` marks the entities unavailable or leaves them as they are. Devices are removed only after HTTP 200 with `complete: true` that no longer lists the aquarium.

On HTTP 429 the next poll waits at least the `Retry-After` value, still inside 30 to 300 seconds. Repeated failures back off up to the maximum. A little jitter keeps several connections from polling in the same second.

The access token is refreshed about a minute before it expires, and once after an HTTP 401. The refresh token is stored on the config entry. It is not written to the log. If the refresh token is rejected, Home Assistant asks you to sign in again. Devices stay until a new complete snapshot says otherwise.

## Examples

A critical reading is a reason to look at the aquarium, not a reason to dose it. This automation only notifies.

```yaml
alias: Aquarisma critical water reading
triggers:
  - trigger: state
    entity_id: binary_sensor.rio_critical_water_reading
    to: "on"
conditions:
  - condition: template
    value_template: "{{ state_attr('sensor.rio_temperature', 'freshness') != 'stale' }}"
actions:
  - action: notify.notify
    data:
      message: "A water reading in Rio is critical. Check it before changing anything."
```

A controller may follow temperature only when the sample is a live sensor and still fresh. If Aquarisma becomes unavailable, the output must turn off.

```yaml
alias: Fan on a fresh temperature sensor
triggers:
  - trigger: numeric_state
    entity_id: sensor.rio_temperature
    above: 28
conditions:
  - condition: template
    value_template: >
      {{ state_attr('sensor.rio_temperature', 'realtime')
         and state_attr('sensor.rio_temperature', 'freshness') == 'current'
         and state_attr('sensor.rio_temperature', 'origin') == 'sensor' }}
actions:
  - action: switch.turn_on
    target:
      entity_id: switch.aquarium_fan
```

```yaml
alias: Fan off when Aquarisma is unavailable
triggers:
  - trigger: state
    entity_id: sensor.rio_temperature
    to: unavailable
    for: "00:10:00"
actions:
  - action: switch.turn_off
    target:
      entity_id: switch.aquarium_fan
```

```yaml
alias: Confirm one Rio feeding
actions:
  - action: aquarisma.confirm_feeding
    data:
      aquarium_id: BDEMO450
      plan_id: PDEMO
      slot_id: 2
      date: "2026-11-24"
      idempotency_key: feed-rio-2026-11-24-slot-2
```

## Known limitations

- There is no local push. Updates arrive on the poll interval.
- A manual or imported reading is not a live sensor, even if it was typed in a minute ago.
- The confirm button exists only when one feeding slot is open. Several open slots need `aquarisma.confirm_feeding` with the plan, slot, and date.
- Two connections that can see the same aquarium do not create two devices. The older connection id keeps the device. The other connection raises a repair.
- An empty snapshot is a valid grant with no aquariums. It is not a connection failure. Home Assistant removes the devices that this connection used to own.
- Deleting the config entry does not delete Home Assistant history, statistics, or backups. Revoking the connection in Aquarisma stops new reads. It does not erase values Home Assistant already stored.
- Anyone who can open this Home Assistant instance can see the imported values. That is separate from the permissions inside Aquarisma.
- Discovery is not available. Every connection uses `https://aquarisma.com`.

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| "aquarisma.com could not be reached" | Check DNS and that this Home Assistant host can open HTTPS to aquarisma.com. |
| Sign-in returns to the wrong place | Keep My Home Assistant enabled, or set the external URL of Home Assistant and allow the exact path `/auth/external/callback`. |
| A repair says the snapshot schema is unsupported | Update the integration. Devices are left in place until a supported snapshot arrives. |
| A repair says no aquariums were returned | In Aquarisma, open the connection and share a team or an aquarium. Also confirm the team plan includes external integrations. |
| A repair says another connection manages the aquarium | Keep one connection, or accept that only the first connection id creates the device. |
| Entities are `unavailable` | The last poll failed or was rate limited. Nothing was deleted. The log names the error code and not the token. |
| A button is missing | Write access is off, more than one slot is open, or the connection may not see plans. |
| Reauthentication appears | The refresh token was rejected. Sign in again. The devices stay. |

Diagnostics are under the config entry menu. Tokens, refresh tokens, and expiry timestamps are removed before the download is built.

## Removing the integration

1. Go to {% my integrations title="Settings > Devices & services" %} and open **Aquarisma**.
2. Delete the connection. Devices that only this connection created are removed. History already recorded by Home Assistant stays until you delete it there.
3. In Aquarisma, revoke the Home Assistant connection so the refresh token can no longer be used.

## Privacy

Home Assistant stores the site address, the public client id, the redirect URI, the access token, the refresh token, and the token expiry on the config entry. Snapshots are kept in memory for the coordinator and are written to the recorder like any other entity state.

The integration sends the bearer token only to the configured site. It does not send the password. Diagnostics and logs omit the tokens.
