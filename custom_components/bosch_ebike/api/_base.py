"""Base service class for Bosch eBike API services."""

import logging
import uuid

_LOGGER = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "Accept": "application/json",
}


def _check_response(resp):
    """Log response body on error, then raise."""
    if not resp.ok:
        _LOGGER.warning(
            "API error %s %s — body: %s",
            resp.status_code,
            resp.url,
            resp.text[:1000],
        )
    resp.raise_for_status()


class BaseService:
    """Base class providing HTTP methods with automatic URL construction."""

    BASE_URL: str = ""

    def __init__(self, session):
        self._session = session

    def _url(self, path):
        return self.BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    def _headers(self, extra=None):
        """Build headers: defaults + X-Request-ID + any extras."""
        h = {**_DEFAULT_HEADERS, "X-Request-ID": str(uuid.uuid4())}
        if extra:
            h.update(extra)
        return h

    def _get(self, path, params=None, headers=None, **kwargs):
        resp = self._session.get(
            self._url(path), params=params, headers=self._headers(headers), **kwargs
        )
        _check_response(resp)
        return resp

    def _post(self, path, json=None, data=None, params=None, headers=None, **kwargs):
        resp = self._session.post(
            self._url(path),
            json=json,
            data=data,
            params=params,
            headers=self._headers(headers),
            **kwargs,
        )
        _check_response(resp)
        return resp

    def _put(self, path, json=None, data=None, params=None, headers=None, **kwargs):
        resp = self._session.put(
            self._url(path),
            json=json,
            data=data,
            params=params,
            headers=self._headers(headers),
            **kwargs,
        )
        _check_response(resp)
        return resp

    def _patch(self, path, json=None, headers=None, **kwargs):
        resp = self._session.patch(
            self._url(path), json=json, headers=self._headers(headers), **kwargs
        )
        _check_response(resp)
        return resp

    def _delete(self, path, params=None, json=None, headers=None, **kwargs):
        resp = self._session.delete(
            self._url(path), params=params, json=json, headers=self._headers(headers), **kwargs
        )
        _check_response(resp)
        return resp
