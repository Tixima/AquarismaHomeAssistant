# Submitting Aquarisma to Home Assistant

This tree is prepared for a core review. It is not part of Home Assistant yet, and it is not in the Marketplace catalog. Publishing those is a separate pull request in another repository.

The page to copy is [aquarisma.markdown](aquarisma.markdown). The German product note lives in `docs/integrations/home-assistant.md` and is not the page Home Assistant publishes.

## What is ready

- Config flow with PKCE, address checks, reauthentication, and reconfigure.
- One coordinator per connection, ETag, backoff, and refresh-token rotation without logging the token.
- Devices, dynamic entities, translations in English and German, icons, repairs, and redacted diagnostics.
- Entities disappear only after a complete HTTP 200 snapshot.
- A manual reading does not get `state_class: measurement`.
- Contract tests in `integrations/home-assistant/tests/test_contract.py` cover the client, the plan, ownership, and the URL rules. They do not boot Home Assistant.

`quality_scale.yaml` is the honest score. The manifest does not claim bronze, silver, gold, or platinum.

## Before the core pull request

1. Diff `quality_scale.yaml` against `homeassistant/components/quality_scale.py` in the core version you target. Add any rule that file has gained. Do not mark a rule done unless the code and the core test both satisfy it.
2. Open a pull request in [home-assistant/brands](https://github.com/home-assistant/brands) with `core_integrations/aquarisma/icon.png` and `logo.png`. Follow that repository's size and padding rules. Until it is merged, `brands` stays `todo`.
3. Copy `aquarisma.markdown` to `home-assistant.io` as `source/_integrations/aquarisma.markdown`. Set `ha_release` to the release that will contain the integration. Add `ha_quality_scale` only after the manifest claims the same scale.
4. Move `custom_components/aquarisma` to `homeassistant/components/aquarisma`. Drop `manifest.json` keys that core does not use (`version` is a custom-component field). Keep `codeowners` as the GitHub account that will review issues. Replace `@Tixima` if someone else will own the integration.
5. Add the core pytest suite. The minimum that the scale asks for is a config-flow test (success, invalid URL, cannot connect, already configured, reauth, reconfigure) and a coordinator test (200, 304, 401 refresh, 401 reauth, 429, unsupported schema, incomplete snapshot does not delete). Use `aiohttp` mocks. Do not put a live token in the tests.
6. Run hassfest, the core pytest file, and the quality scale check. Then set `quality_scale` in `manifest.json` to the highest tier whose rules are all `done` or `exempt`.
7. Request a review from the Home Assistant core team. The integration type is `hub`, the IoT class is `cloud_polling`, and there is no YAML setup.

## What this repository must not claim

- A merged core integration.
- A published home-assistant.io page. The documentation URL in the manifest points at this file on GitHub until that page exists.
- A listing in the Marketplace catalog (`hacs/default`).
- A brand icon inside Home Assistant.
- A platinum or gold badge.

## Marketplace, until core exists

Home Assistant 2026.11 ships the Marketplace. It is HACS inside Home Assistant. The old HACS custom integration does not install on that version. `hacs.json` is still the repository manifest, and the catalog is still `hacs/default`.

This application repository can be added as a custom integration repository because `hacs.json` is in the root and the component is `custom_components/aquarisma`. The minimum version in `hacs.json` is `2026.11.0`. That check applies once a GitHub release exists. The manifest `version` must match the release tag.

`bash integrations/home-assistant/scripts/package.sh` only copies a tree into `dist/`. It does not publish a release.

`.github/workflows/home-assistant.yml` runs hassfest. `hacs/action` only validates public repositories, and this application repository is private, so that action is not part of the workflow. Run it after the integration has its own public repository.
