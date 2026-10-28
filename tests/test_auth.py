"""Tests for the OAuth helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from custom_components.bosch_ebike.api._base import REQUEST_TIMEOUT
from custom_components.bosch_ebike.api.auth import (
    CLIENT_ID,
    REDIRECT_URI,
    create_session,
    exchange_code,
    generate_auth_url,
)


class TestGenerateAuthUrl:
    def test_requests_offline_access(self):
        url, verifier = generate_auth_url()
        params = parse_qs(urlparse(url).query)
        assert params["scope"] == ["openid offline_access"]
        assert params["client_id"] == [CLIENT_ID]
        assert params["redirect_uri"] == [REDIRECT_URI]
        assert params["code_challenge_method"] == ["S256"]
        assert verifier


class TestTimeouts:
    def test_exchange_code_has_timeout(self):
        with patch("custom_components.bosch_ebike.api.auth.requests.post") as mock_post:
            mock_post.return_value = MagicMock(json=MagicMock(return_value={}))
            exchange_code("code", "verifier")
        assert mock_post.call_args.kwargs["timeout"] == REQUEST_TIMEOUT

    def test_session_has_default_timeout(self):
        session = create_session({"access_token": "at", "token_type": "Bearer"})
        assert session.default_timeout == REQUEST_TIMEOUT
