from datetime import datetime, timezone

from rich import box
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from artemis.config import LAUNCH_DATE


def build_countdown() -> Text:
    now = datetime.now(timezone.utc)
    delta = LAUNCH_DATE - now
    if delta.total_seconds() <= 0:
        return Text("🚀 MISSION ACTIVE", style="bold green")
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    t = Text()
    t.append("🚀 ARTEMIS II — Launch in: ", style="bold white")
    t.append(f"{days}d {hours}h {minutes}m {seconds}s", style="bold cyan")
    return t


def build_dsn_panel(dishes: list[dict]) -> Panel:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta")
    table.add_column("Antenna", style="cyan")
    table.add_column("Target(s)", style="green")
    table.add_column("Az°", justify="right")
    table.add_column("El°", justify="right")

    if not dishes:
        table.add_row("No data", "—", "—", "—")
    else:
        for dish in dishes:
            targets = ", ".join(dish["targets"]) if dish["targets"] else "idle"
            table.add_row(
                dish["name"],
                targets,
                f"{dish['azimuth']:.1f}",
                f"{dish['elevation']:.1f}",
            )

    return Panel(table, title="[bold]🛰️  DSN STATUS[/bold]", border_style="blue")


def build_weather_panel(flares: list[dict], storms: list[dict]) -> Panel:
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Event", style="bold")
    table.add_column("Status")

    flare_count = len(flares)
    flare_status = (
        Text(f"{flare_count} detected ⚠️", style="yellow")
        if flare_count
        else Text("Clear ✅", style="green")
    )
    table.add_row("Solar Flares (24h)", flare_status)

    storm_count = len(storms)
    storm_status = (
        Text(f"{storm_count} active ⚠️", style="yellow")
        if storm_count
        else Text("None ✅", style="green")
    )
    table.add_row("Geomagnetic Storms (7d)", storm_status)

    return Panel(table, title="[bold]☀️  SPACE WEATHER[/bold]", border_style="yellow")


def build_layout(
    dishes: list[dict], flares: list[dict], storms: list[dict], error: str | None = None
) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=1),
    )
    layout["main"].split_row(
        Layout(name="dsn"),
        Layout(name="weather"),
    )

    layout["header"].update(Panel(build_countdown(), border_style="bright_black"))
    layout["dsn"].update(build_dsn_panel(dishes))
    layout["weather"].update(build_weather_panel(flares, storms))
    layout["footer"].update(
        Text(
            f"  Last update: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC",
            style="dim",
        )
    )

    if error:
        layout["footer"].update(Text(f"  ⚠️ {error}", style="bold yellow"))
    else:
        layout["footer"].update(
            Text(
                f"  Last update: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC",
                style="dim",
            )
        )

    return layout
