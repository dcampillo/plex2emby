"""Command-line entry point."""

import os
from collections import Counter
from pathlib import Path
from typing import Annotated

import httpx
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from plex2emby.emby import EmbyClient, UnknownUser
from plex2emby.migrate import run_migration
from plex2emby.models import ResumePolicy
from plex2emby.plex import PlexClient, UnknownLibrary
from plex2emby.report import FAILED, ReportRow, write_report

REQUIRED_SETTINGS = ("PLEX_URL", "PLEX_TOKEN", "EMBY_URL", "EMBY_API_KEY", "EMBY_USER")
EXIT_FAILED_WRITES = 1
EXIT_CANNOT_START = 2

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


def make_http_client(base_url: str, headers: dict[str, str]) -> httpx.Client:
    return httpx.Client(base_url=base_url, headers=headers, timeout=120)


def _stop(message: str) -> typer.Exit:
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(EXIT_CANNOT_START)


def _settings() -> dict[str, str]:
    load_dotenv(Path.cwd() / ".env")
    missing = [name for name in REQUIRED_SETTINGS if not os.environ.get(name)]
    if missing:
        raise _stop(f"missing settings: {', '.join(missing)}. Set them in .env.")
    return {name: os.environ[name] for name in REQUIRED_SETTINGS}


def _connect_plex(settings: dict[str, str], library: list[str] | None) -> tuple[PlexClient, list]:
    headers = {"X-Plex-Token": settings["PLEX_TOKEN"], "Accept": "application/json"}
    plex = PlexClient(make_http_client(settings["PLEX_URL"], headers))
    try:
        return plex, plex.libraries(library)
    except UnknownLibrary as error:
        raise _stop(f"no movie or TV library on Plex named: {error}") from error
    except httpx.HTTPError as error:
        raise _stop(f"cannot reach Plex: {error}") from error


def _connect_emby(settings: dict[str, str]) -> EmbyClient:
    headers = {"X-Emby-Token": settings["EMBY_API_KEY"], "Accept": "application/json"}
    emby = EmbyClient(make_http_client(settings["EMBY_URL"], headers))
    try:
        emby.log_in(settings["EMBY_USER"])
    except UnknownUser as error:
        raise _stop(f"no Emby user named: {error}") from error
    except httpx.HTTPError as error:
        raise _stop(f"cannot reach Emby: {error}") from error
    return emby


def _print_summary(rows: list[ReportRow], report: Path) -> None:
    table = Table("Result", "Items")
    for status, count in sorted(Counter(row.status for row in rows).items()):
        table.add_row(status, str(count))
    console.print(table)
    console.print(f"Report: {report}", markup=False, soft_wrap=True)


@app.callback()
def main() -> None:
    """Migrate viewing history from Plex to Emby."""


@app.command()
def migrate(
    library: Annotated[
        list[str] | None,
        typer.Option("--library", help="Plex library to include. Repeatable. Default: all."),
    ] = None,
    resume_position: Annotated[
        ResumePolicy,
        typer.Option(help="How to settle resume positions that differ."),
    ] = ResumePolicy.FURTHEST,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Write to Emby. Without this, nothing is changed."),
    ] = False,
) -> None:
    """Copy Watch State to Emby. Previews the changes unless --apply is given."""
    settings = _settings()
    plex, libraries = _connect_plex(settings, library)
    emby = _connect_emby(settings)

    try:
        sources = plex.source_items(libraries)
        targets = emby.target_items()
    except httpx.HTTPError as error:
        raise _stop(f"could not read the libraries: {error}") from error

    with console.status("Writing to Emby..." if apply else "Comparing..."):
        rows = run_migration(sources, targets, resume_position, emby, apply)
    _print_summary(rows, write_report(rows, Path("reports")))
    if not apply:
        console.print("Dry Run: nothing was written. Add --apply to write these changes.")
    if any(row.status == FAILED for row in rows):
        raise typer.Exit(EXIT_FAILED_WRITES)
