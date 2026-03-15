"""Bosch eBike Flow OAuth2 PKCE authentication helpers for Home Assistant.

No file I/O — tokens are managed by HA's config entry system.
"""

import requests
from authlib.common.security import generate_token
from authlib.integrations.requests_client import OAuth2Session

CLIENT_ID = "one-bike-app"
AUTH_BASE = "https://p9.authz.bosch.com/auth/realms/obc/protocol/openid-connect"
TOKEN_URL = f"{AUTH_BASE}/token"
AUTH_URL = f"{AUTH_BASE}/auth"
REDIRECT_URI = "onebikeapp-android://com.bosch.ebike.flow/login"


def generate_auth_url() -> tuple[str, str]:
    """Generate an OAuth2 PKCE authorization URL.

    After login, the Bosch server redirects to onebikeapp-android://...?code=XXX.
    Browsers can't handle the custom scheme, so the user must extract the code
    from the redirect URL via the browser's Network tab.

    Returns (auth_url, code_verifier) tuple.
    """
    client = OAuth2Session(
        client_id=CLIENT_ID,
        scope="openid",
        redirect_uri=REDIRECT_URI,
        code_challenge_method="S256",
    )
    code_verifier = generate_token(48)
    url, _state = client.create_authorization_url(
        url=AUTH_URL,
        code_verifier=code_verifier,
        kc_idp_hint="skid",
    )
    return url, code_verifier


def exchange_code(code: str, code_verifier: str) -> dict:
    """Exchange an authorization code for tokens.

    Returns the full token dict (access_token, refresh_token, expires_at, etc.).
    """
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        },
    )
    resp.raise_for_status()
    token: dict = resp.json()
    return token


def create_session(token: dict) -> OAuth2Session:
    """Create an authenticated OAuth2Session from an existing token dict."""
    return OAuth2Session(client_id=CLIENT_ID, token=token)


def refresh_session_token(token: dict) -> tuple[OAuth2Session, dict]:
    """Refresh the access token using the refresh token.

    Returns (session, new_token_dict) tuple.
    """
    client = OAuth2Session(client_id=CLIENT_ID, token={})
    new_token = client.refresh_token(TOKEN_URL, refresh_token=token["refresh_token"])
    return client, dict(new_token)
