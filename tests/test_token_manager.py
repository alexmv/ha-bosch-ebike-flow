"""Tests for TokenManager expiry logic."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.bosch_ebike.coordinator import _TOKEN_REFRESH_MARGIN, TokenManager


@pytest.fixture()
def mock_hass():
    """Lightweight mock hass (not the full HA fixture — just enough for TokenManager)."""
    h = MagicMock()
    h.async_add_executor_job = AsyncMock()
    return h


@pytest.fixture()
def mock_entry():
    return MagicMock()


class TestTokenManager:
    @pytest.mark.asyncio
    async def test_skips_refresh_when_token_is_fresh(self, mock_hass, mock_entry):
        mock_entry.data = {
            "token": {
                "access_token": "good",
                "refresh_token": "rt",
                "expires_at": time.time() + 3600,
            }
        }
        manager = TokenManager(mock_hass, mock_entry)

        with patch("custom_components.bosch_ebike.coordinator.create_session") as mock_create:
            mock_create.return_value = MagicMock()
            await manager.get_client()

        mock_hass.async_add_executor_job.assert_not_called()
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_refreshes_when_token_is_expired(self, mock_hass, mock_entry):
        mock_entry.data = {
            "token": {
                "access_token": "old",
                "refresh_token": "rt",
                "expires_at": time.time() - 100,
            }
        }
        new_token = {"access_token": "new", "refresh_token": "rt2", "expires_at": 9999999999}
        mock_hass.async_add_executor_job.return_value = (MagicMock(), new_token)

        manager = TokenManager(mock_hass, mock_entry)
        await manager.get_client()

        mock_hass.async_add_executor_job.assert_called_once()
        mock_hass.config_entries.async_update_entry.assert_called_once()

    @pytest.mark.asyncio
    async def test_refreshes_when_within_margin(self, mock_hass, mock_entry):
        mock_entry.data = {
            "token": {
                "access_token": "almost",
                "refresh_token": "rt",
                "expires_at": time.time() + _TOKEN_REFRESH_MARGIN - 10,
            }
        }
        new_token = {"access_token": "new", "refresh_token": "rt2", "expires_at": 9999999999}
        mock_hass.async_add_executor_job.return_value = (MagicMock(), new_token)

        manager = TokenManager(mock_hass, mock_entry)
        await manager.get_client()

        mock_hass.async_add_executor_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_on_refresh_failure(self, mock_hass, mock_entry):
        mock_entry.data = {
            "token": {
                "access_token": "stale",
                "refresh_token": "rt",
                "expires_at": time.time() - 100,
            }
        }
        mock_hass.async_add_executor_job.side_effect = Exception("network error")

        manager = TokenManager(mock_hass, mock_entry)

        with patch("custom_components.bosch_ebike.coordinator.create_session") as mock_create:
            mock_create.return_value = MagicMock()
            await manager.get_client()

        mock_create.assert_called_once()
        mock_hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_expires_at_triggers_refresh(self, mock_hass, mock_entry):
        mock_entry.data = {"token": {"access_token": "no_expiry", "refresh_token": "rt"}}
        new_token = {"access_token": "new", "refresh_token": "rt2", "expires_at": 9999999999}
        mock_hass.async_add_executor_job.return_value = (MagicMock(), new_token)

        manager = TokenManager(mock_hass, mock_entry)
        await manager.get_client()

        mock_hass.async_add_executor_job.assert_called_once()
