"""Tests for the config flow: _extract_code helper and end-to-end HA flow."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.bosch_ebike.config_flow import _extract_code
from custom_components.bosch_ebike.const import DOMAIN

from .conftest import BIKE_ID

FAKE_TOKEN = {
    "access_token": "at",
    "refresh_token": "rt",
    "expires_at": 9999999999,
}

FAKE_BIKES = [
    {
        "id": BIKE_ID,
        "brandName": "Riese & Müller",
        "driveUnit": {"productLine": "Cargo Line"},
    }
]


# --- Unit tests for _extract_code ---


class TestExtractCode:
    def test_bare_code(self):
        assert _extract_code("abc123-def456") == "abc123-def456"

    def test_full_redirect_url(self):
        url = "onebikeapp-android://com.bosch.ebike.flow/login?code=THE_CODE&state=xyz"
        assert _extract_code(url) == "THE_CODE"

    def test_empty_input(self):
        assert _extract_code("") is None
        assert _extract_code("   ") is None

    def test_url_without_code_param(self):
        assert _extract_code("onebikeapp-android://login?state=xyz") is None

    def test_whitespace_stripped(self):
        assert _extract_code("  abc123  ") == "abc123"


# --- HA integration tests ---


def _patch_happy_flow():
    """Patch auth + API for a successful config flow."""

    class FakeClient:
        def __init__(self, session):
            self.bike_profile = type("bp", (), {"get_all": lambda self: FAKE_BIKES})()

    return (
        patch.multiple(
            "custom_components.bosch_ebike.config_flow",
            generate_auth_url=lambda: ("https://auth.example.com/login", "verifier123"),
            exchange_code=lambda code, verifier: FAKE_TOKEN,
            create_session=lambda token: None,
        ),
        patch("custom_components.bosch_ebike.config_flow.BoschEBikeClient", FakeClient),
    )


class TestConfigFlowHappy:
    @pytest.mark.asyncio
    async def test_full_flow(self, hass: HomeAssistant) -> None:
        auth_patch, client_patch = _patch_happy_flow()
        with auth_patch, client_patch:
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            assert result["type"] is FlowResultType.FORM
            assert result["step_id"] == "user"

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={}
            )
            assert result["step_id"] == "code"

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={"code": "the-auth-code"}
            )
            assert result["type"] is FlowResultType.CREATE_ENTRY
            assert result["title"] == "Bosch eBike (Riese & Müller Cargo Line)"
            assert result["data"]["token"] == FAKE_TOKEN


class TestConfigFlowErrors:
    @pytest.mark.asyncio
    async def test_empty_code(self, hass: HomeAssistant) -> None:
        auth_patch, _ = _patch_happy_flow()
        with auth_patch:
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={"code": ""}
            )
            assert result["errors"] == {"code": "invalid_code"}

    @pytest.mark.asyncio
    async def test_token_exchange_failure(self, hass: HomeAssistant) -> None:
        with (
            patch(
                "custom_components.bosch_ebike.config_flow.generate_auth_url",
                return_value=("https://auth.example.com", "v"),
            ),
            patch(
                "custom_components.bosch_ebike.config_flow.exchange_code",
                side_effect=Exception("network"),
            ),
        ):
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={"code": "bad-code"}
            )
            assert result["errors"] == {"base": "token_exchange_failed"}

    @pytest.mark.asyncio
    async def test_api_validation_failure(self, hass: HomeAssistant) -> None:
        class FailingClient:
            def __init__(self, session):
                class FailingBikeProfile:
                    def get_all(self):
                        raise Exception("api down")

                self.bike_profile = FailingBikeProfile()

        with (
            patch(
                "custom_components.bosch_ebike.config_flow.generate_auth_url",
                return_value=("https://auth.example.com", "v"),
            ),
            patch(
                "custom_components.bosch_ebike.config_flow.exchange_code",
                return_value=FAKE_TOKEN,
            ),
            patch("custom_components.bosch_ebike.config_flow.create_session", return_value=None),
            patch("custom_components.bosch_ebike.config_flow.BoschEBikeClient", FailingClient),
        ):
            result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], user_input={"code": "good-code"}
            )
            assert result["errors"] == {"base": "api_error"}

    @pytest.mark.asyncio
    async def test_duplicate_account_aborts(self, hass: HomeAssistant) -> None:
        auth_patch, client_patch = _patch_happy_flow()
        with auth_patch, client_patch:
            # First setup.
            r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            r = await hass.config_entries.flow.async_configure(r["flow_id"], user_input={})
            r = await hass.config_entries.flow.async_configure(
                r["flow_id"], user_input={"code": "c1"}
            )
            assert r["type"] is FlowResultType.CREATE_ENTRY

            # Second setup — same bikes → abort.
            r2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
            r2 = await hass.config_entries.flow.async_configure(r2["flow_id"], user_input={})
            r2 = await hass.config_entries.flow.async_configure(
                r2["flow_id"], user_input={"code": "c2"}
            )
            assert r2["type"] is FlowResultType.ABORT
            assert r2["reason"] == "already_configured"
