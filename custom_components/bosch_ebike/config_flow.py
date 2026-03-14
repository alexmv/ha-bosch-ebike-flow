"""Config flow for Bosch eBike Flow integration."""

from __future__ import annotations

import hashlib
import logging
from urllib.parse import parse_qs, urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .api.auth import create_session, exchange_code, generate_auth_url
from .api.client import BoschEBikeClient
from .const import DOMAIN
from .helpers import extract_bike_name

_LOGGER = logging.getLogger(__name__)


def _extract_code(user_input: str) -> str | None:
    """Extract the authorization code from user input.

    Accepts either:
    - A bare authorization code string
    - A full redirect URL containing ?code=... or &code=...
    """
    text = user_input.strip()
    if not text:
        return None
    # If it looks like a URL, parse the code parameter out.
    if "://" in text or text.startswith("onebikeapp"):
        parsed = urlparse(text)
        params = parse_qs(parsed.query) or parse_qs(parsed.fragment)
        codes = params.get("code", [])
        return codes[0] if codes else None
    # Otherwise treat the whole input as the code.
    return text


class BoschEBikeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Bosch eBike Flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._auth_url: str | None = None
        self._code_verifier: str | None = None

    async def async_step_user(self, user_input: dict[str, str] | None = None) -> ConfigFlowResult:
        """Step 1: Generate auth URL and show login instructions."""
        if self._auth_url is None:
            self._auth_url, self._code_verifier = await self.hass.async_add_executor_job(
                generate_auth_url
            )

        if user_input is not None:
            return await self.async_step_code()

        assert self._auth_url is not None
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={"auth_url": self._auth_url},
        )

    async def async_step_code(self, user_input: dict[str, str] | None = None) -> ConfigFlowResult:
        """Step 2: Accept the authorization code and complete setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = _extract_code(user_input.get("code", ""))

            if not code:
                errors["code"] = "invalid_code"
            else:
                assert self._code_verifier is not None
                try:
                    token = await self.hass.async_add_executor_job(
                        exchange_code, code, self._code_verifier
                    )
                except Exception:
                    _LOGGER.exception("Token exchange failed")
                    errors["base"] = "token_exchange_failed"
                else:
                    try:
                        session = create_session(token)
                        client = BoschEBikeClient(session)
                        bikes = await self.hass.async_add_executor_job(client.bike_profile.get_all)
                    except Exception:
                        _LOGGER.exception("API validation failed")
                        errors["base"] = "api_error"
                    else:
                        # Derive a stable unique ID from the set of bike IDs owned
                        # by this account.  This prevents adding the same account
                        # twice.
                        bike_ids = sorted(b["id"] for b in bikes)
                        unique_id = hashlib.sha256(",".join(bike_ids).encode()).hexdigest()[:16]
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        names = [extract_bike_name(b) for b in bikes]
                        title = f"Bosch eBike ({', '.join(names)})"
                        return self.async_create_entry(title=title, data={"token": token})

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
        )
