# Aquarisma for Home Assistant

Custom integration for [Aquarisma](https://github.com/Tixima/AquaVault). Home Assistant polls the Aquarisma integration API. There is no MQTT broker, no local bridge, and no client secret in this code.

Home Assistant 2026.11 or newer includes the Marketplace. That is the current Home Assistant Community Store. The separate HACS custom integration is not installed on that version.

This application repository is the source. Aquarisma is not in the default catalog yet, and it is not part of Home Assistant core. The submission steps are in [docs/submission.md](docs/submission.md). The page intended for home-assistant.io is [docs/aquarisma.markdown](docs/aquarisma.markdown).

## Install from the Marketplace

1. Open **Settings → Marketplace**. Connect GitHub when Home Assistant asks for it.
2. Add `https://github.com/Tixima/AquarismaHomeAssistant` as a custom repository. The category is integration.
3. Install Aquarisma and restart Home Assistant. Version 2026.11.0 or newer is required.
4. Go to **Settings → Devices & services → Add integration** and search for **Aquarisma**.
5. Enter the site address, for example `https://app.example.com`.
6. Keep **My Home Assistant** enabled unless this instance has its own public URL.
7. Sign in, choose the aquariums or teams, and confirm.

The Marketplace installs `custom_components/aquarisma` from that repository. `hacs.json` in its root tells it the minimum Home Assistant version. A repository that only contains this README, `docs`, `scripts`, and `tests` cannot be installed.

Reading is requested by default. Writing is requested only when the switch in the form is on. The password stays in the browser.

The team that owns the aquariums needs the Expert plan or higher. Personal, Hobby, and Pro do not include external integrations.

On Home Assistant 2026.10 or older, the separate HACS integration can still install the same `hacs.json`. This release asks for 2026.11.0 once it is published as a GitHub release, so older installations are not offered that release.

## What you get

- One device per aquarium, with sensors for water, feeding, care, livestock, and assigned food.
- A calendar per aquarium.
- Buttons only when a single feeding or a single care task can be identified.
- Repairs when the snapshot schema is newer than this integration, when no aquarium is shared, or when another connection already owns the device.
- English and German names. The entity id is chosen from the language that was active when the entity was created.

A manual water test is not a live sensor. Automations that switch hardware must require `realtime`, `freshness: current`, and `origin: sensor`, and they must turn the output off when the entity becomes `unavailable`.

## Develop

```bash
python3 integrations/home-assistant/tests/test_contract.py
bash integrations/home-assistant/scripts/package.sh
```

The package script copies a Marketplace tree into `dist/`. It does not publish a release.
