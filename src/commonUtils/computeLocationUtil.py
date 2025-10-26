from typing import Optional


def compute_location(address: Optional[dict]) -> Optional[dict]:
    if not address:
        return None
    lat = address.get("latitude")
    lon = address.get("longitude")
    if lat is not None and lon is not None:
        return {"type": "Point", "coordinates": [lon, lat]}
    return None
