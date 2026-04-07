# Artemis Monitor

A terminal-based dashboard for tracking NASA's Deep Space Network (DSN) activity and space weather conditions in real time.

Artemis Monitor fetches live data from NASA's public feeds, parses DSN dish status using a high-performance Rust extension, and renders everything in a rich terminal UI.

## Features

- **DSN Tracking** -- Monitor which dishes are active, what spacecraft they're communicating with, and signal strength in real time
- **Space Weather** -- Solar flare and geomagnetic storm alerts from NASA's DONKI API
- **Artemis II Countdown** -- Live countdown to launch (or mission active indicator post-launch)
- **Fast XML Parsing** -- DSN data is parsed via `dsn_parser`, a native Rust module built with PyO3 and quick-xml for speed
- **Terminal UI** -- Full-screen live dashboard powered by Rich

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- Rust toolchain (for building the `dsn_parser` extension)

## Installation

```bash
git clone https://github.com/roberjacobo/artemis-monitor.git
cd artemis-monitor
uv sync
```

This installs all Python dependencies and builds the Rust extension automatically via the uv workspace.

## Configuration

Copy the example environment file and edit it with your values:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `NASA_API_KEY` | `DEMO_KEY` | API key from [api.nasa.gov](https://api.nasa.gov) |
| `REFRESH_INTERVAL` | `10` | Dashboard refresh interval in seconds |
| `LAUNCH_DATE` | `2026-06-01T00:00:00+00:00` | Artemis II launch date (ISO 8601) |

The `DEMO_KEY` works but is rate-limited. Get a free key at [api.nasa.gov](https://api.nasa.gov).

## Usage

```bash
uv run artemis-monitor
```

Press `Ctrl+C` to exit.

## Project Structure

```
artemis-monitor/
├── artemis/                # Python package
│   ├── __init__.py
│   ├── main.py             # CLI entrypoint & async fetch loop
│   ├── config.py           # Environment-based configuration
│   ├── space_weather.py    # NASA DONKI API client
│   └── ui.py               # Rich terminal UI layout
├── crates/
│   └── dsn_parser/         # Rust extension (uv workspace member)
│       ├── Cargo.toml
│       └── src/
│           └── lib.rs      # DSN XML parsing with PyO3 + quick-xml
├── typings/
│   └── dsn_parser/
│       └── __init__.pyi    # Type stubs for the Rust extension
├── pyproject.toml           # Project config & workspace definition
└── uv.lock
```

## Development

Install dev dependencies:

```bash
uv sync --group dev
```

Run tests:

```bash
uv run pytest
```

Rebuild the Rust extension after changes:

```bash
cd crates/dsn_parser && uv run maturin develop
```

## License

MIT -- see [LICENSE](LICENSE) for details.
