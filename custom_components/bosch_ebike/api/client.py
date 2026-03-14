"""Trimmed Bosch eBike API client for Home Assistant."""

from .activity import ActivityService
from .antitheft import TheftDetectionService
from .bike import BikeProfileService


class BoschEBikeClient:
    """Client aggregating only the services needed for HA."""

    def __init__(self, session):
        self._session = session
        self.bike_profile = BikeProfileService(session)
        self.activity = ActivityService(session)
        self.theft_detection = TheftDetectionService(session)
