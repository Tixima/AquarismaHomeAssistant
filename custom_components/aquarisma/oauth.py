"""OAuth helpers that do not import Home Assistant.

The config flow uses these checks before it opens a browser or stores a token.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import secrets
from urllib.parse import urlencode, urlparse

LOCAL_HTTP_HOSTS = {"localhost", "127.0.0.1", "::1"}


class InvalidAquarismaUrl(ValueError):
    """The address is not a usable Aquarisma base URL."""


def normalize_base_url(value: str) -> str:
    """Return a canonical base URL or raise InvalidAquarismaUrl.

    HTTPS is required for public hosts. HTTP is limited to loopback and
    private addresses so a lab instance can be linked without opening the
    redirect policy to the whole internet.
    """

    raw = value.strip()
    if not raw or any(char.isspace() for char in raw):
        raise InvalidAquarismaUrl
    parsed = urlparse(raw)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise InvalidAquarismaUrl
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise InvalidAquarismaUrl
    if parsed.path not in {"", "/"}:
        raise InvalidAquarismaUrl
    host = parsed.hostname.lower()
    if parsed.scheme == "http" and host not in LOCAL_HTTP_HOSTS and not _private_host(host):
        raise InvalidAquarismaUrl
    port = f":{parsed.port}" if parsed.port else ""
    display = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{display}{port}"


def code_verifier() -> str:
    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def authorize_url(
    base_url: str,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    verifier: str,
    scopes: list[str],
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
            "state": state,
            "resource": f"{base_url}/api/v1",
            "scope": " ".join(scopes),
            "integration_type": "home_assistant",
        }
    )
    return f"{base_url}/oauth/authorize?{query}"


def stamp_token(token: dict, now: float) -> dict:
    """Remember when the access token expires. The secret itself is unchanged."""

    stamped = dict(token)
    expires_in = stamped.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        stamped["expires_at"] = now + float(expires_in)
    return stamped


def access_token_expired(token: dict, now: float, skew: float = 60) -> bool:
    expires_at = token.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        return False
    return now >= float(expires_at) - skew


def next_poll_interval(
    preferred: int,
    *,
    failures: int,
    retry_after: int | None,
    minimum: int,
    maximum: int,
) -> int:
    """Clamp a poll interval and back off after errors without dropping below the server minimum."""

    if retry_after is not None and retry_after > 0:
        return min(maximum, max(minimum, retry_after))
    if failures <= 0:
        return min(maximum, max(minimum, preferred))
    grown = preferred * (2 ** min(failures, 4))
    return min(maximum, max(minimum, grown))


def _private_host(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith(".local") or host.endswith(".home.arpa")
    return address.is_private or address.is_loopback or address.is_link_local
