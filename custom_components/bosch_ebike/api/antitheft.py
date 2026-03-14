"""Anti-theft / theft detection services."""

from ._base import BaseService

THEFT_DETECTION_URL = "https://theft-detection.prod.connected-biking.cloud"


class TheftDetectionService(BaseService):
    """Theft detection, BCM registration, and location tracking."""

    BASE_URL = THEFT_DETECTION_URL

    def get_registrations(self, bike_id):
        """Get BCM registrations for a bike."""
        return self._get("v0/registrations", params={"bikeId": bike_id}).json()

    def get_latest_locations(self, bike_id):
        """Get the latest known locations of a bike."""
        return self._get("v0/latest-locations", params={"bikeId": bike_id}).json()
