"""HTTP client for the Aquarisma integration API.

The transport is injected so the client can be tested without Home Assistant
or a network stack. A later SDK can publish this module on its own.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,80}$")


class AquarismaError(Exception):
    def __init__(self, status: int, code: str, detail: str, retry_after: int | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.retry_after = retry_after


class UnsupportedSchema(AquarismaError):
    def __init__(self, schema: object) -> None:
        super().__init__(200, "unsupported_schema", f"Unsupported snapshot schema {schema}")
        self.schema = schema


def valid_idempotency_key(value: object) -> bool:
    """Aquarisma accepts 8 to 80 characters from a fixed set. Spaces are rejected."""

    return isinstance(value, str) and _IDEMPOTENCY_KEY.fullmatch(value) is not None


@dataclass
class HttpResult:
    status: int
    headers: dict[str, str]
    body: bytes


class Transport(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None,
    ) -> HttpResult: ...


@dataclass
class SnapshotResult:
    status: int
    etag: str | None
    payload: dict[str, Any] | None
    not_modified: bool
    retry_after: int | None = None


class AquarismaClient:
    def __init__(self, base_url: str, transport: Transport, token: str, client_version: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.token = token
        self.client_version = client_version

    async def snapshot(self, etag: str | None = None, schema_version: int = 1) -> SnapshotResult:
        result = await self._request("GET", "/api/v1/integrations/home-assistant/snapshot", etag=etag)
        if result.status == 304:
            return SnapshotResult(304, result.headers.get("etag"), None, True)
        payload = self._json(result)
        if result.status != 200:
            raise self._error(result, payload)
        schema = payload.get("schema_version")
        if schema != schema_version:
            raise UnsupportedSchema(schema)
        return SnapshotResult(200, result.headers.get("etag"), payload, False)

    async def calendar(self, start: str, end: str) -> dict[str, Any]:
        query = urlencode({"start": start, "end": end})
        result = await self._request("GET", f"/api/v1/integrations/home-assistant/calendar?{query}")
        payload = self._json(result)
        if result.status != 200:
            raise self._error(result, payload)
        return payload

    async def action(self, action: str, aquarium_id: str, parameters: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        result = await self._request(
            "POST",
            "/api/v1/integrations/home-assistant/actions",
            json_body={
                "action": action,
                "aquarium_id": aquarium_id,
                "idempotency_key": idempotency_key,
                "parameters": parameters,
            },
        )
        payload = self._json(result)
        if result.status not in (200, 201):
            raise self._error(result, payload)
        return payload

    async def me(self) -> dict[str, Any]:
        result = await self._request("GET", "/api/v1/integrations/me")
        payload = self._json(result)
        if result.status != 200:
            raise self._error(result, payload)
        return payload

    async def exchange(self, client_id: str, redirect_uri: str, code: str, verifier: str) -> dict[str, Any]:
        result = await self.transport.request(
            "POST",
            f"{self.base_url}/oauth/token",
            {"Accept": "application/json", "Content-Type": "application/json"},
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code": code,
                "code_verifier": verifier,
                "resource": f"{self.base_url}/api/v1",
            },
        )
        payload = self._json(result)
        if result.status != 200:
            raise self._error(result, payload)
        return payload

    async def refresh(self, client_id: str, refresh_token: str) -> dict[str, Any]:
        result = await self.transport.request(
            "POST",
            f"{self.base_url}/oauth/token",
            {"Accept": "application/json", "Content-Type": "application/json"},
            {
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
                "resource": f"{self.base_url}/api/v1",
            },
        )
        payload = self._json(result)
        if result.status != 200:
            raise self._error(result, payload)
        return payload

    async def register(self, redirect_uri: str) -> str:
        result = await self.transport.request(
            "POST",
            f"{self.base_url}/oauth/register",
            {"Accept": "application/json", "Content-Type": "application/json"},
            {
                "client_name": "Home Assistant",
                "redirect_uris": [redirect_uri],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        payload = self._json(result)
        if result.status not in (200, 201) or not payload.get("client_id"):
            raise self._error(result, payload)
        return str(payload["client_id"])

    async def _request(
        self,
        method: str,
        path: str,
        etag: str | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> HttpResult:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.token}",
            "X-Aquarisma-Client": self.client_version,
        }
        if etag:
            headers["If-None-Match"] = etag
        return await self.transport.request(method, f"{self.base_url}{path}", headers, json_body)

    def _json(self, result: HttpResult) -> dict[str, Any]:
        if not result.body:
            return {}
        try:
            parsed = json.loads(result.body.decode())
        except json.JSONDecodeError as error:
            raise AquarismaError(result.status, "invalid_json", "Response was not JSON") from error
        return parsed if isinstance(parsed, dict) else {}

    def _error(self, result: HttpResult, payload: dict[str, Any]) -> AquarismaError:
        retry = result.headers.get("retry-after")
        return AquarismaError(
            result.status,
            str(payload.get("code") or payload.get("error") or "http_error"),
            str(payload.get("detail") or payload.get("title") or "Request failed"),
            int(retry) if retry and str(retry).isdigit() else None,
        )
