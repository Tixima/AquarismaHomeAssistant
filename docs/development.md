# Developing the Home Assistant integration

The component lives in `custom_components/aquarisma` next to this file's parent, which is the root the Marketplace reads after this folder is copied into the integration repository. Home Assistant is not imported by `client.py`, `plan.py`, or `oauth.py`, so those modules can be tested on their own.

```bash
python3 tests/test_contract.py
```

From the Aquarisma application repository that path is `python3 integrations/home-assistant/tests/test_contract.py`.

That suite checks:

- snapshot ETag and HTTP 304
- HTTP 429 and HTTP 401
- an unsupported schema
- calendar query encoding
- idempotency keys
- stable unique ids when an aquarium is renamed
- no `state_class: measurement` unless the reading is realtime
- no entity for a parameter that has no value
- the confirm button only when one feeding slot is open
- permission loss removing water entities and leaving feeding entities
- server errors and incomplete snapshots removing nothing
- a complete empty snapshot removing devices
- team-wide food stock staying off the aquarium
- URL normalization, PKCE, token expiry, and poll backoff
- which connection owns an overlapping aquarium
- English and German translations covering the same keys, with an icon for every entity

A failure here is fixed before a core pytest run. The core run still has to be added in the Home Assistant repository. This environment does not install `homeassistant`, so a green contract test is not a hassfest result.

## Rules that are easy to break

- Do not log `Authorization`, `access_token`, `refresh_token`, or the token JSON.
- Do not delete a device unless the snapshot status is 200 and `complete` is true.
- Do not set `state_class` from a manual reading. Trust `realtime` on the payload. The API sets that flag only for origin `sensor`.
- Keep unique ids stable. New presentation belongs in a translation key.
- Two connections must not both create `(aquarisma, aquarium id)`. `owned_aquarium_ids` chooses the smallest connection id.
- Register actions in `async_setup`, not in `async_setup_entry`.
- Keep `PARALLEL_UPDATES = 0` on every platform.

## Local install

Copy `custom_components/aquarisma` into a Home Assistant config, restart, and add the integration. Point it at the Aquarisma site. For a private lab, HTTP is limited to loopback and private hosts. The return address should stay on My Home Assistant unless the instance has an external URL.

The demo account and the local password are described in `docs/cloud-environment.md`. Do not put that password into the integration, a fixture, or a log.
