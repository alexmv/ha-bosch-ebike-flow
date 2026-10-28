"""Tests for the OAuth helpers."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from custom_components.bosch_ebike.api.auth import CLIENT_ID, REDIRECT_URI, generate_auth_url


class TestGenerateAuthUrl:
    def test_requests_offline_access(self):
        url, verifier = generate_auth_url()
        params = parse_qs(urlparse(url).query)
        assert params["scope"] == ["openid offline_access"]
        assert params["client_id"] == [CLIENT_ID]
        assert params["redirect_uri"] == [REDIRECT_URI]
        assert params["code_challenge_method"] == ["S256"]
        assert verifier
