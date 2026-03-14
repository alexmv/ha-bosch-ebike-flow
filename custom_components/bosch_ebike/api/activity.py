"""Activity tracking and ride summary services."""

from ._base import BaseService

ACTIVITY_URL = "https://obc-rider-activity.prod.connected-biking.cloud"


class ActivityService(BaseService):
    """Query ride activity summaries."""

    BASE_URL = ACTIVITY_URL

    def get_summaries(self, page=0, size=20):
        """Get paginated activity summaries, newest first.

        The APK uses sort=-startTime (dash prefix for descending),
        NOT sort=startTime,desc (Spring Data style).
        """
        return self._get(
            "v1/activity",
            params={
                "page": page,
                "size": size,
                "sort": "-startTime",
                "include-polyline": "false",
            },
        ).json()
