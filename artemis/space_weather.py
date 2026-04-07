from datetime import datetime, timedelta, timezone

import httpx

from artemis import config

DONKI_BASE = "https://api.nasa.gov/DONKI"


async def _fetch_data(endpoint: str, days: int) -> list[dict]:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{DONKI_BASE}/{endpoint}",
            params={"startDate": start, "endDate": end, "api_key": config.NASA_API_KEY},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()


async def fetch_solar_flares() -> list[dict]:
    return await _fetch_data("FLR", days=1)


async def fetch_geomagnetic_storms() -> list[dict]:
    return await _fetch_data("GST", days=7)
