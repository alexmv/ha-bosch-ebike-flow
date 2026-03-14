"""Bike profile and state-of-charge services."""

from ._base import BaseService

RIDER_PROFILE_URL = "https://obc-rider-profile.prod.connected-biking.cloud"


class BikeProfileService(BaseService):
    """Manage bike profiles."""

    BASE_URL = RIDER_PROFILE_URL

    def get_all(self):
        """Get all bike profiles for the authenticated rider."""
        return self._get("v2/bike-profile/").json()

    def get(self, bike_id):
        """Get a specific bike profile."""
        return self._get(f"v2/bike-profile/{bike_id}").json()

    def get_state_of_charge(self, bike_id):
        """Get battery state of charge for a bike."""
        return self._get(f"v1/state-of-charge/{bike_id}").json()
