import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import dsn_parser
import httpx
from rich.live import Live

from artemis import config
from artemis.space_weather import fetch_geomagnetic_storms, fetch_solar_flares
from artemis.ui import build_layout

DSN_URL = "https://eyes.nasa.gov/dsn/data/dsn.xml"
MAX_RETRIES = 3


async def fetch_with_retry(
    coro_func: Callable[[], Coroutine[Any, Any, list[dict[str, Any]]]],
    retries: int = MAX_RETRIES,
) -> list[dict[str, Any]]:
    for attempt in range(retries):
        try:
            return await coro_func()
        except (httpx.HTTPStatusError, httpx.TimeoutException):
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2**attempt)
    return []


async def fetch_dsn() -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        r = await client.get(DSN_URL, timeout=10)
        r.raise_for_status()
        return dsn_parser.parse_dsn(r.text)


def format_error(source: str, exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{source}: HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return f"{source}: Timeout"
    return f"{source}: {type(exc).__name__}"


async def run() -> None:
    dishes: list[dict[str, Any]] = []
    flares: list[dict[str, Any]] = []
    storms: list[dict[str, Any]] = []

    with Live(
        build_layout(dishes, flares, storms), refresh_per_second=1, screen=True
    ) as live:
        while True:
            errors: list[str] = []

            results = await asyncio.gather(
                fetch_with_retry(fetch_dsn),
                fetch_with_retry(fetch_solar_flares),
                fetch_with_retry(fetch_geomagnetic_storms),
                return_exceptions=True,
            )

            if isinstance(results[0], BaseException):
                errors.append(format_error("DSN", results[0]))
            else:
                dishes = results[0]

            if isinstance(results[1], BaseException):
                errors.append(format_error("Flares", results[1]))
            else:
                flares = results[1]

            if isinstance(results[2], BaseException):
                errors.append(format_error("Storms", results[2]))
            else:
                storms = results[2]

            error_msg = " | ".join(errors) if errors else None
            live.update(build_layout(dishes, flares, storms, error=error_msg))
            await asyncio.sleep(config.REFRESH_INTERVAL)


def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
