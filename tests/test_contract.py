"""Tests for the Aquarisma client and entity plan. They do not boot Home Assistant."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "aquarisma"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


client = load("client")
plan = load("plan")
oauth = load("oauth")


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def request(self, method, url, headers, json_body):
        self.calls.append((method, url, headers, json_body))
        status, response_headers, body = self.responses.pop(0)
        return client.HttpResult(status, response_headers, body)


def snapshot(**overrides):
    body = {
        "schema_version": 1,
        "complete": True,
        "aquariums": [
            {
                "id": "B1",
                "name": "Rio",
                "capabilities": ["aquarium.read", "water.read", "feeding.plans", "feeding.write", "care.read"],
                "water": {
                    "status": "target",
                    "critical_count": 0,
                    "parameters": {
                        "temperature": {
                            "value": 25.4,
                            "unit": "°C",
                            "realtime": False,
                            "freshness": "current",
                            "origin": "measured",
                            "status": "target",
                        },
                        "future_parameter": {"ranges": {"target": {"min": 1, "max": 2}}},
                    },
                },
                "feeding": {
                    "available": True,
                    "planned_today": 1,
                    "completed_today": 0,
                    "open_today": 1,
                    "overdue": 0,
                    "due_now": False,
                    "fasting_today": False,
                    "next": {"at": "2026-11-24T18:00:00+00:00", "plan_id": "P1", "slot_id": 4, "date": "2026-11-24"},
                },
                "care": {"open": 2, "overdue": 0, "due_today": 1, "due_now": False, "next": {"id": "O1", "due_at": "2026-11-24T12:00:00+00:00"}},
            }
        ],
    }
    body.update(overrides)
    return body


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_snapshot_etag_and_not_modified(self):
        transport = FakeTransport([
            (200, {"etag": '"abc"'}, b'{"schema_version":1,"complete":true,"aquariums":[]}'),
            (304, {"etag": '"abc"'}, b""),
        ])
        api = client.AquarismaClient("https://aquarisma.test", transport, "token", "1.0.0")
        first = await api.snapshot()
        self.assertFalse(first.not_modified)
        self.assertEqual(first.etag, '"abc"')
        second = await api.snapshot('"abc"')
        self.assertTrue(second.not_modified)
        self.assertEqual(transport.calls[1][2]["If-None-Match"], '"abc"')
        self.assertEqual(transport.calls[0][2]["Authorization"], "Bearer token")

    async def test_rate_limit_exposes_retry_after(self):
        transport = FakeTransport([(429, {"retry-after": "30"}, b'{"code":"rate_limited","detail":"wait"}')])
        api = client.AquarismaClient("https://aquarisma.test", transport, "token", "1.0.0")
        with self.assertRaises(client.AquarismaError) as caught:
            await api.snapshot()
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(caught.exception.retry_after, 30)

    async def test_unsupported_schema_does_not_look_like_success(self):
        transport = FakeTransport([(200, {}, b'{"schema_version":99,"complete":true,"aquariums":[]}')])
        api = client.AquarismaClient("https://aquarisma.test", transport, "token", "1.0.0")
        with self.assertRaises(client.UnsupportedSchema):
            await api.snapshot()

    async def test_unauthorized(self):
        transport = FakeTransport([(401, {}, b'{"code":"unauthorized","detail":"no"}')])
        api = client.AquarismaClient("https://aquarisma.test", transport, "token", "1.0.0")
        with self.assertRaises(client.AquarismaError) as caught:
            await api.snapshot()
        self.assertEqual(caught.exception.status, 401)


class PlanTests(unittest.TestCase):
    def test_manual_reading_has_no_measurement_state_class(self):
        specs = {row["unique_id"]: row for row in plan.entity_specs(snapshot())}
        self.assertIsNone(specs["B1:water:temperature"]["state_class"])
        self.assertNotIn("B1:water:future_parameter", specs)
        self.assertIn("B1:feeding:confirm", specs)

    def test_rename_keeps_unique_id(self):
        renamed = snapshot()
        renamed["aquariums"][0]["name"] = "Neuer Name"
        before = {row["unique_id"] for row in plan.entity_specs(snapshot())}
        after = {row["unique_id"] for row in plan.entity_specs(renamed)}
        self.assertEqual(before, after)

    def test_lost_water_permission_removes_only_water_entities(self):
        full = plan.entity_specs(snapshot())
        limited = snapshot()
        limited["aquariums"][0]["capabilities"] = ["aquarium.read", "feeding.plans"]
        limited["aquariums"][0].pop("water")
        next_specs = plan.entity_specs(limited)
        existing = {row["unique_id"] for row in full}
        desired, removed = plan.reconcile(existing, next_specs, 200, True)
        self.assertIn("B1:water:temperature", removed)
        self.assertIn("B1:feeding:planned", desired)
        self.assertNotIn("B1:feeding:planned", removed)

    def test_server_error_and_incomplete_snapshot_do_not_remove(self):
        existing = {"B1:water:temperature", "B1:feeding:planned"}
        self.assertEqual(plan.reconcile(existing, None, 500, None), (existing, set()))
        partial = plan.entity_specs(snapshot(complete=False, aquariums=[]))
        desired, removed = plan.reconcile(existing, partial, 200, False)
        self.assertEqual(removed, set())
        self.assertTrue(existing.issubset(desired))

    def test_empty_complete_snapshot_removes_devices(self):
        existing = {"B1:water:temperature"}
        desired, removed = plan.reconcile(existing, plan.entity_specs(snapshot(aquariums=[])), 200, True)
        self.assertEqual(desired, set())
        self.assertEqual(removed, existing)

    def test_new_aquarium_is_added(self):
        body = snapshot()
        body["aquariums"].append({"id": "B2", "name": "Nano", "capabilities": ["aquarium.read"], "volume_liters": 60})
        specs = plan.entity_specs(body)
        desired, removed = plan.reconcile(set(), specs, 200, True)
        self.assertIn("B2:aquarium:volume", desired)
        self.assertEqual(removed, set())

    def test_unknown_capability_is_ignored(self):
        body = snapshot()
        body["aquariums"][0]["capabilities"].append("future.magic")
        specs = plan.entity_specs(body)
        self.assertFalse(any("magic" in row["unique_id"] for row in specs))

    def test_button_requires_a_single_open_feeding(self):
        body = snapshot()
        body["aquariums"][0]["feeding"]["open_today"] = 2
        specs = plan.entity_specs(body)
        self.assertNotIn("B1:feeding:confirm", {row["unique_id"] for row in specs})

    def test_realtime_measurement_translation_and_units(self):
        body = snapshot()
        water = body["aquariums"][0]["water"]
        water["parameters"]["temperature"].update({"realtime": True, "origin": "sensor", "unit_code": "celsius"})
        water["parameters"]["ph"] = {"value": 7.2, "unit": "pH", "unit_code": "ph", "realtime": False}
        water["parameters"]["custom:extra"] = {"value": 1.5, "unit": "mg/l", "realtime": False}
        water["last_measured_at"] = "2026-11-24T08:00:00+00:00"
        specs = {row["unique_id"]: row for row in plan.entity_specs(body)}
        self.assertEqual(specs["B1:water:temperature"]["state_class"], "measurement")
        self.assertEqual(specs["B1:water:temperature"]["device_class"], "temperature")
        self.assertEqual(specs["B1:water:temperature"]["unit"], "°C")
        self.assertEqual(specs["B1:water:temperature"]["translation_key"], "temperature")
        self.assertNotIn("name", specs["B1:water:temperature"])
        self.assertIsNone(specs["B1:water:ph"]["unit"])
        self.assertEqual(specs["B1:water:ph"]["device_class"], "ph")
        self.assertEqual(specs["B1:water:ph"]["precision"], 2)
        self.assertIsNone(specs["B1:water:ph"]["state_class"])
        custom = specs["B1:water:custom:extra"]
        self.assertEqual(custom["translation_key"], "water_value")
        self.assertEqual(custom["translation_placeholders"]["parameter"], "custom:extra")
        self.assertEqual(specs["B1:water:last_measured"]["device_class"], "timestamp")
        self.assertIn("B1:calendar", specs)

    def test_sensor_origin_without_realtime_flag_is_not_a_measurement(self):
        body = snapshot()
        body["aquariums"][0]["water"]["parameters"]["temperature"]["origin"] = "sensor"
        specs = {row["unique_id"]: row for row in plan.entity_specs(body)}
        self.assertIsNone(specs["B1:water:temperature"]["state_class"])

    def test_team_stock_is_ignored_and_assigned_stock_is_diagnostic(self):
        body = snapshot()
        body["aquariums"][0]["capabilities"].append("feeding.stock")
        body["aquariums"][0]["inventory"] = {"scope": "tenant", "low": 4}
        hidden = plan.entity_specs(body)
        self.assertFalse(any(row["unique_id"].endswith(":inventory:low") for row in hidden))
        body["aquariums"][0]["inventory"] = {"scope": "assigned", "low": 4}
        specs = {row["unique_id"]: row for row in plan.entity_specs(body)}
        self.assertEqual(specs["B1:inventory:low"]["category"], "diagnostic")
        self.assertFalse(specs["B1:inventory:low"]["enabled_default"])

    def test_device_removal_follows_the_snapshot_rule(self):
        existing = {"B1", "B2"}
        self.assertEqual(plan.device_reconcile(existing, None, 500, None), (existing, set()))
        kept, removed = plan.device_reconcile(existing, {"aquariums": [{"id": "B1"}]}, 200, False)
        self.assertEqual(removed, set())
        self.assertEqual(kept, {"B1", "B2"})
        kept, removed = plan.device_reconcile(existing, {"aquariums": []}, 200, True)
        self.assertEqual(kept, set())
        self.assertEqual(removed, existing)

    def test_smaller_connection_id_owns_the_aquarium(self):
        self.assertEqual(plan.owning_entry([("b", "entry-b"), ("a", "entry-a")]), "entry-a")
        owned = plan.owned_aquarium_ids("entry-b", "b", {"X", "Y"}, [("entry-a", "a", {"X"})])
        self.assertEqual(owned, {"Y"})
        self.assertEqual(plan.owning_entry([]), None)


class ClientBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_calendar_query_is_encoded(self):
        transport = FakeTransport([(200, {}, b'{"events":[]}')])
        api = client.AquarismaClient("https://aquarisma.test", transport, "token", "1.0.0")
        await api.calendar("2026-11-24T00:00:00+01:00", "2026-11-25T00:00:00+01:00")
        url = transport.calls[0][1]
        self.assertIn("start=2026-11-24T00%3A00%3A00%2B01%3A00", url)
        self.assertNotIn(" ", url)
        self.assertNotIn("+", url.split("?", 1)[1])

    def test_idempotency_key_shape(self):
        self.assertTrue(client.valid_idempotency_key("feed-rio-2026"))
        self.assertTrue(client.valid_idempotency_key("a" * 8))
        self.assertTrue(client.valid_idempotency_key("a" * 80))
        self.assertFalse(client.valid_idempotency_key("short"))
        self.assertFalse(client.valid_idempotency_key("a" * 81))
        self.assertFalse(client.valid_idempotency_key("has space"))
        self.assertFalse(client.valid_idempotency_key(None))


class OauthTests(unittest.TestCase):
    def test_public_https_and_private_http(self):
        self.assertEqual(oauth.normalize_base_url("https://Aquarisma.Example:8443/"), "https://aquarisma.example:8443")
        self.assertEqual(oauth.normalize_base_url("http://127.0.0.1:8000"), "http://127.0.0.1:8000")
        self.assertEqual(oauth.normalize_base_url("http://[::1]:8000/"), "http://[::1]:8000")
        self.assertEqual(oauth.normalize_base_url("http://192.168.1.20"), "http://192.168.1.20")
        for raw in [
            "http://aquarisma.example",
            "https://aquarisma.example/api",
            "https://user:secret@aquarisma.example",
            "https://aquarisma.example?token=1",
            "https://aquarisma.example#frag",
            "ftp://aquarisma.example",
            "",
            " https://aquarisma.example/api ",
        ]:
            with self.assertRaises(oauth.InvalidAquarismaUrl, msg=raw):
                oauth.normalize_base_url(raw)

    def test_pkce_and_authorize_url_hide_the_verifier(self):
        import base64
        import hashlib

        challenge = oauth.code_challenge("abc")
        expected = base64.urlsafe_b64encode(hashlib.sha256(b"abc").digest()).decode().rstrip("=")
        self.assertEqual(challenge, expected)
        self.assertNotIn("=", challenge)
        url = oauth.authorize_url(
            "https://aquarisma.test",
            client_id="client",
            redirect_uri="https://my.home-assistant.io/redirect/oauth",
            state="flow",
            verifier="abc",
            scopes=["aquariums:read", "water.measurements:read"],
        )
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("resource=https%3A%2F%2Faquarisma.test%2Fapi%2Fv1", url)
        self.assertIn("integration_type=home_assistant", url)
        self.assertNotIn("client_secret", url)
        self.assertNotIn("verifier=abc", url)
        self.assertNotIn("=abc&", url)

    def test_token_expiry_and_backoff(self):
        stamped = oauth.stamp_token({"access_token": "a", "refresh_token": "r", "expires_in": 900}, 1_000)
        self.assertEqual(stamped["expires_at"], 1_900)
        self.assertEqual(stamped["access_token"], "a")
        self.assertFalse(oauth.access_token_expired(stamped, 1_900 - 61))
        self.assertTrue(oauth.access_token_expired(stamped, 1_900 - 60))
        self.assertFalse(oauth.access_token_expired({"access_token": "a"}, 99_999))
        self.assertEqual(oauth.next_poll_interval(60, failures=0, retry_after=None, minimum=30, maximum=300), 60)
        self.assertEqual(oauth.next_poll_interval(60, failures=3, retry_after=None, minimum=30, maximum=300), 300)
        self.assertEqual(oauth.next_poll_interval(60, failures=1, retry_after=10, minimum=30, maximum=300), 30)
        self.assertEqual(oauth.next_poll_interval(60, failures=1, retry_after=120, minimum=30, maximum=300), 120)
        self.assertEqual(oauth.next_poll_interval(60, failures=1, retry_after=1000, minimum=30, maximum=300), 300)


class MarketplaceTests(unittest.TestCase):
    def test_repository_layout_matches_the_marketplace(self):
        repo = Path(__file__).resolve().parents[1]
        hacs = json.loads((repo / "hacs.json").read_text())
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(hacs["name"], "Aquarisma")
        self.assertEqual(hacs["homeassistant"], "2026.11.0")
        self.assertFalse(hacs.get("content_in_root", False))
        self.assertNotIn("render_readme", hacs)
        self.assertNotIn("filename", hacs)
        self.assertEqual(manifest["version"], "1.2.0")
        self.assertEqual(manifest["domain"], "aquarisma")
        self.assertEqual(manifest["categories"][0], "pets")
        self.assertLessEqual(len(manifest["categories"]), 3)
        self.assertTrue((ROOT / "brand" / "icon.png").is_file())
        self.assertTrue((ROOT / "translations" / "en.json").is_file())
        self.assertEqual((repo / "custom_components" / "aquarisma").resolve(), ROOT.resolve())


class TranslationTests(unittest.TestCase):
    def test_english_and_german_cover_the_same_keys(self):
        strings = json.loads((ROOT / "strings.json").read_text())
        english = json.loads((ROOT / "translations" / "en.json").read_text())
        german = json.loads((ROOT / "translations" / "de.json").read_text())
        icons = json.loads((ROOT / "icons.json").read_text())
        self.assertEqual(english, strings)
        self.assertEqual(_paths(german), _paths(strings))
        for domain, entries in strings["entity"].items():
            for key in entries:
                self.assertIn(key, icons["entity"][domain], msg=f"{domain}.{key}")
                self.assertTrue(icons["entity"][domain][key]["default"].startswith("mdi:"))
        for service in strings["services"]:
            self.assertIn(service, icons["services"])


def _paths(value, prefix=""):
    found = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found |= _paths(child, f"{prefix}.{key}" if prefix else key)
        return found
    return {prefix}


if __name__ == "__main__":
    unittest.main()
