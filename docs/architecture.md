# Architecture

This document explains how Artemis Monitor works internally, how data flows through the system, and how each component fits together.

## Overview

Artemis Monitor is a full-screen terminal dashboard that polls two NASA data sources on a loop, parses the responses, and renders them using Rich. The DSN XML feed is parsed by a Rust extension for performance.

```
                         ┌─────────────────────────┐
                         │      main.py (run)       │
                         │   async event loop       │
                         └────────┬────────────────-┘
                                  │
                        asyncio.gather (concurrent)
                       ┌──────────┼──────────────┐
                       │          │              │
                       v          v              v
                  fetch_dsn   fetch_solar    fetch_geo
                       │      _flares       _storms
                       │          │              │
                       v          └──────┬───────┘
               dsn_parser.parse_dsn      │
               (Rust / PyO3)       space_weather.py
                       │           (_fetch_data)
                       │                 │
                       v                 v
              NASA DSN XML feed    NASA DONKI REST API
              eyes.nasa.gov        api.nasa.gov/DONKI
                       │                 │
                       └────────┬────────┘
                                │
                                v
                         ┌─────────────┐
                         │   ui.py     │
                         │ build_layout│
                         └──────┬──────┘
                                │
                                v
                         Rich Live display
                         (full-screen TUI)
```

## Module Breakdown

### `artemis/main.py` -- Entrypoint & Fetch Loop

This is the core of the application. It does three things:

1. **`fetch_dsn()`** -- GETs the DSN XML feed and passes the raw XML string to the Rust parser.
2. **`fetch_all()`** -- Runs `fetch_dsn()`, `fetch_solar_flares()`, and `fetch_geomagnetic_storms()` concurrently using `asyncio.gather`. All three HTTP requests happen in parallel.
3. **`run()`** -- The main loop. Opens a `Rich.Live` context in full-screen mode and loops forever:
   - Calls `fetch_all()` to get fresh data
   - On error, preserves the last good data and sets an error message
   - Passes everything to `build_layout()` and updates the display
   - Sleeps for `REFRESH_INTERVAL` seconds

`main()` wraps `asyncio.run()` and catches `KeyboardInterrupt` for clean exit.

**Error handling strategy:** The `except` block in the loop catches HTTP errors, timeouts, and unexpected exceptions separately. On failure, the dashboard keeps showing the last successful data and displays the error in the footer bar. It never crashes from a transient network issue.

### `artemis/config.py` -- Configuration

Loads environment variables from `.env` using `python-dotenv`. Three settings:

| Variable | Type | Default | Used By |
|---|---|---|---|
| `NASA_API_KEY` | `str` | `DEMO_KEY` | `space_weather.py` |
| `REFRESH_INTERVAL` | `int` | `10` | `main.py` (sleep between fetches) |
| `LAUNCH_DATE` | `datetime` | `2026-06-01T00:00:00+00:00` | `ui.py` (countdown timer) |

`load_dotenv()` runs at import time, so any module importing from `config` gets the values already resolved.

### `artemis/space_weather.py` -- NASA DONKI Client

Talks to NASA's [DONKI API](https://api.nasa.gov/) (Space Weather Database of Notifications, Knowledge, Information).

**Internal helper:**

```python
async def _fetch_data(endpoint: str, days: int) -> list[dict]
```

Builds a date range (`today - days` to `today`), makes an async GET to `https://api.nasa.gov/DONKI/{endpoint}`, and returns the JSON response as a list of dicts.

**Public functions:**

- `fetch_solar_flares()` -- Calls `_fetch_data("FLR", days=1)`. Returns solar flare events from the last 24 hours.
- `fetch_geomagnetic_storms()` -- Calls `_fetch_data("GST", days=7)`. Returns geomagnetic storm events from the last 7 days.

Both use the API key from `config.NASA_API_KEY`. The `DEMO_KEY` works but is rate-limited to ~30 requests/hour.

### `artemis/ui.py` -- Terminal UI

Builds the Rich layout. Pure rendering logic, no I/O.

**Layout structure:**

```
┌──────────────────────────────────────────────────┐
│ header (size=3)                                  │
│   Countdown timer or "MISSION ACTIVE"            │
├────────────────────────┬─────────────────────────┤
│ dsn (flexible)         │ weather (flexible)      │
│   Antenna table        │   Flare/storm summary   │
├────────────────────────┴─────────────────────────┤
│ footer (size=1)                                  │
│   Last update timestamp or error message         │
└──────────────────────────────────────────────────┘
```

**Functions:**

- `build_countdown()` -- Computes `LAUNCH_DATE - now`. If positive, shows `Xd Xh Xm Xs`. If zero or negative, shows "MISSION ACTIVE".
- `build_dsn_panel(dishes)` -- Renders a table of DSN antennas. Each row shows antenna name, target spacecraft, azimuth, and elevation. Shows "No data" if the list is empty.
- `build_weather_panel(flares, storms)` -- Two-row summary. Shows count + warning icon if events exist, or "Clear"/"None" with a checkmark if quiet.
- `build_layout(dishes, flares, storms, error=None)` -- Assembles the three panels into a `Layout`. If `error` is set, the footer shows the error instead of the timestamp.

### `crates/dsn_parser/` -- Rust XML Parser

A Python extension module written in Rust using [PyO3](https://pyo3.rs/) and [quick-xml](https://docs.rs/quick-xml/).

**Why Rust?** NASA's DSN feed is XML. Parsing XML in Python is slow relative to the rest of the app. The Rust parser handles it in microseconds.

**How it works:**

1. `parse_dsn_xml(xml: &str) -> Vec<DishStatus>` -- Internal Rust function. Iterates XML events using `quick-xml::Reader`:
   - On `<dish>` start tag: extracts `name`, `azimuthAngle`, `elevationAngle` from attributes
   - On `<target>` inside a dish: extracts `name` attribute, filters out empty and `"none"` values
   - On `</dish>` end tag: pushes the completed `DishStatus` into the result vector

2. `parse_dsn(py, xml: &str) -> PyResult<PyList>` -- The `#[pyfunction]` exposed to Python. Calls `parse_dsn_xml`, then converts each `DishStatus` struct into a Python dict:

```python
# What Python sees:
[
    {
        "name": "DSS-14",        # antenna name
        "azimuth": 245.3,        # degrees
        "elevation": 36.7,       # degrees
        "targets": ["Voyager 1"] # list of spacecraft names
    },
    ...
]
```

**Build system:** Uses [maturin](https://www.maturin.rs/) to compile the Rust code into a `.so` and install it as a Python package. Registered as a uv workspace member so `uv sync` handles it automatically.

## Data Flow: One Refresh Cycle

1. `run()` calls `fetch_all()`
2. `asyncio.gather` fires three async HTTP requests in parallel:
   - `GET https://eyes.nasa.gov/dsn/data/dsn.xml` (DSN feed)
   - `GET https://api.nasa.gov/DONKI/FLR?startDate=...&endDate=...&api_key=...`
   - `GET https://api.nasa.gov/DONKI/GST?startDate=...&endDate=...&api_key=...`
3. DSN XML response goes to `dsn_parser.parse_dsn()` (Rust) which returns a list of dicts
4. DONKI JSON responses are returned as-is (already `list[dict]`)
5. All three results are passed to `build_layout()` which constructs the Rich layout tree
6. `live.update()` renders the layout to the terminal
7. `asyncio.sleep(REFRESH_INTERVAL)` waits before the next cycle

If any request fails, the error is caught, the last successful data is preserved, and the error message replaces the footer timestamp.

## Workspace Structure

The project uses a uv workspace with two members:

```toml
# root pyproject.toml
[tool.uv.workspace]
members = ["crates/dsn_parser"]

[tool.uv.sources]
dsn-parser = { workspace = true }
```

- **Root package (`artemis-monitor`)** -- The Python application. Built with hatchling. Declares `dsn-parser` as a dependency.
- **Workspace member (`dsn-parser`)** -- The Rust extension. Built with maturin. Has its own `pyproject.toml` and `Cargo.toml`.

`uv sync` builds and installs both. For development on the Rust side, use `maturin develop` inside `crates/dsn_parser/` to rebuild without a full sync.

## Type Checking

The Rust extension has no Python source, so type checkers (basedpyright) can't see its exports. The `typings/dsn_parser/__init__.pyi` stub file provides the type signature:

```python
def parse_dsn(xml: str) -> list[dict[str, object]]: ...
```

This is configured via `pyrightconfig.json` with `"stubPath": "typings"`.
