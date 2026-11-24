"""Translated errors for actions. Details never include a token."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError

from .client import AquarismaError, valid_idempotency_key
from .const import DOMAIN


def require_idempotency_key(value: object) -> str:
    if not valid_idempotency_key(value):
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="invalid_idempotency_key")
    return str(value)


def placeholder(value: object) -> str:
    """Keep user text from breaking a translation string."""

    return str(value).replace("{", "(").replace("}", ")").replace("\n", " ")[:180]


def action_failed(error: AquarismaError) -> HomeAssistantError:
    if error.status in (401, 403):
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="action_not_allowed")
    if error.status == 409:
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="idempotency_conflict")
    if error.status == 422:
        return HomeAssistantError(translation_domain=DOMAIN, translation_key="action_rejected")
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="api_error",
        translation_placeholders={"detail": placeholder(error.detail)},
    )
