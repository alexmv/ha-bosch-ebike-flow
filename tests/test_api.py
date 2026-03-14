"""Tests for the API client layer."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from custom_components.bosch_ebike.api._base import BaseService, _check_response
from custom_components.bosch_ebike.api.activity import ActivityService
from custom_components.bosch_ebike.api.antitheft import TheftDetectionService
from custom_components.bosch_ebike.api.bike import BikeProfileService
from custom_components.bosch_ebike.api.client import BoschEBikeClient

from .conftest import BIKE_ID


class TestBaseService:
    def test_url_construction(self):
        svc = BaseService(session=None)
        svc.BASE_URL = "https://example.com"
        assert svc._url("v1/test") == "https://example.com/v1/test"
        assert svc._url("/v1/test") == "https://example.com/v1/test"

    def test_url_strips_trailing_slash(self):
        svc = BaseService(session=None)
        svc.BASE_URL = "https://example.com/"
        assert svc._url("v1/test") == "https://example.com/v1/test"

    def test_headers_include_accept_and_request_id(self):
        svc = BaseService(session=None)
        headers = svc._headers()
        assert headers["Accept"] == "application/json"
        assert "X-Request-ID" in headers

    def test_headers_merge_extras(self):
        svc = BaseService(session=None)
        headers = svc._headers({"Custom": "value"})
        assert headers["Custom"] == "value"
        assert headers["Accept"] == "application/json"


class TestCheckResponse:
    def test_ok_response_passes(self):
        resp = MagicMock()
        resp.ok = True
        _check_response(resp)
        resp.raise_for_status.assert_called_once()

    def test_error_response_logs_body(self, caplog):
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 500
        resp.url = "https://example.com/test"
        resp.text = '{"errors": ["something went wrong"]}'
        resp.raise_for_status.side_effect = Exception("500")

        with pytest.raises(Exception, match="500"), caplog.at_level(logging.WARNING):
            _check_response(resp)

        assert "500" in caplog.text
        assert "something went wrong" in caplog.text


class TestBoschEBikeClient:
    def test_creates_all_services(self):
        client = BoschEBikeClient(MagicMock())
        assert isinstance(client.bike_profile, BikeProfileService)
        assert isinstance(client.activity, ActivityService)
        assert isinstance(client.theft_detection, TheftDetectionService)


class TestActivityService:
    def test_get_summaries_url_and_params(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"data": [], "meta": {}, "links": {}}
        mock_session.get.return_value = mock_resp

        result = ActivityService(mock_session).get_summaries()

        call_args = mock_session.get.call_args
        params = call_args[1]["params"]
        assert params["sort"] == "-startTime"
        assert params["include-polyline"] == "false"
        assert result == {"data": [], "meta": {}, "links": {}}


class TestBikeProfileService:
    def _mock_service(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_session.get.return_value = mock_resp
        return BikeProfileService(mock_session), mock_session, mock_resp

    def test_get_all_url(self):
        svc, session, resp = self._mock_service()
        resp.json.return_value = []
        svc.get_all()
        assert session.get.call_args[0][0].endswith("/v2/bike-profile/")

    def test_get_state_of_charge_url(self):
        svc, session, resp = self._mock_service()
        resp.json.return_value = {"stateOfCharge": 80}
        svc.get_state_of_charge(BIKE_ID)
        url = session.get.call_args[0][0]
        assert BIKE_ID in url
        assert "state-of-charge" in url


class TestTheftDetectionService:
    def _mock_service(self):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_session.get.return_value = mock_resp
        return TheftDetectionService(mock_session), mock_session, mock_resp

    def test_get_registrations_passes_bike_id(self):
        svc, session, resp = self._mock_service()
        resp.json.return_value = {"registrations": []}
        svc.get_registrations(BIKE_ID)
        assert session.get.call_args[1]["params"]["bikeId"] == BIKE_ID

    def test_get_latest_locations_passes_bike_id(self):
        svc, session, resp = self._mock_service()
        resp.json.return_value = {"locations": []}
        svc.get_latest_locations(BIKE_ID)
        assert session.get.call_args[1]["params"]["bikeId"] == BIKE_ID
