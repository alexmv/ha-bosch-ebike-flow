"""Shared utility functions for the Bosch eBike Flow integration."""

from __future__ import annotations


def extract_bike_name(bike: dict) -> str:
    """Extract a human-readable bike name from a profile dict."""
    for key in ("nickname", "bikeName", "name"):
        val = bike.get(key)
        if val:
            return str(val)
    brand = bike.get("brandName", "")
    product_line = ""
    drive_unit = bike.get("driveUnit")
    if isinstance(drive_unit, dict):
        product_line = drive_unit.get("productLine", "")
    if brand or product_line:
        return f"{brand} {product_line}".strip()
    bike_id: str = bike.get("id", "")
    return bike_id[:8] or "eBike"
