"""Constants for the Bosch eBike Flow integration."""

from datetime import timedelta

DOMAIN = "bosch_ebike"

# Coordinator update intervals
DATA_UPDATE_INTERVAL = timedelta(minutes=5)
LOCATION_UPDATE_INTERVAL = timedelta(minutes=30)
