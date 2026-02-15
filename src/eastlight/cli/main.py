"""CLI interface for EastLight RC-505 MK2 editor."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from eastlight.core.library import RC505Library
from eastlight.core.model import Memory
from eastlight.core.parser import parse_memory_file
from eastlight.core.schema import SchemaRegistry

console = Console()


def _load_registry() -> SchemaRegistry:
    """Load the built-in schema registry."""
    registry = SchemaRegistry()
    registry.load_all()
    return registry


@click.group()
@click.version_option(package_name="eastlight")
def cli() -> None:
    """EastLight — RC-505 MK2 editor/librarian."""


@cli.command()
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
def list(roland_dir: str) -> None:
    """List all memories in a ROLAND/ backup directory."""
    lib = RC505Library(roland_dir)
    registry = _load_registry()

    table = Table(title="RC-505 MK2 Memories")
    table.add_column("#", style="cyan", justify="right", width=4)
    table.add_column("Name", style="bold", min_width=14)
    table.add_column("Tracks", justify="center")
    table.add_column("Tempo", justify="right")
    table.add_column("Backup", justify="center")

    for slot in lib.list_memories():
        if not slot.exists:
            continue

        rc0 = lib.parse_memory(slot.number)
        mem = Memory(rc0, registry)
        name = mem.name or "(unnamed)"

        # Count tracks with audio
        track_indicators = []
        tempo_str = ""
        for t in range(1, 6):
            track = mem.track(t)
            if track and track.get_by_tag("W") == 1:
                track_indicators.append(f"[green]{t}[/green]")
                if not tempo_str:
                    tempo_x10 = track.get_by_tag("U")
                    if tempo_x10:
                        tempo_str = f"{tempo_x10 / 10:.1f}"
            else:
                track_indicators.append(f"[dim]{t}[/dim]")

        tracks_str = " ".join(track_indicators)
        backup = "[green]Y[/green]" if slot.has_backup else "[red]N[/red]"

        table.add_row(
            str(slot.number),
            name,
            tracks_str,
            tempo_str or "[dim]-[/dim]",
            backup,
        )

    console.print(table)


@cli.command()
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("memory_num", type=int)
@click.option("--section", "-s", help="Show only this section (e.g., TRACK1, MASTER)")
@click.option("--raw", is_flag=True, help="Show raw tag names instead of resolved names")
def show(roland_dir: str, memory_num: int, section: str | None, raw: bool) -> None:
    """Show parameters for a memory slot."""
    lib = RC505Library(roland_dir)
    registry = _load_registry()
    rc0 = lib.parse_memory(memory_num)
    mem = Memory(rc0, registry)

    console.print(f"[bold]Memory {memory_num:03d}[/bold]: {mem.name or '(unnamed)'}")
    console.print()

    sections_to_show = [section] if section else mem.section_names

    for sec_name in sections_to_show:
        resolved = mem.section(sec_name)
        if resolved is None:
            continue

        # Skip sections with no fields
        if not resolved.raw.fields:
            continue

        table = Table(title=sec_name, show_header=True)
        table.add_column("Tag", style="dim", width=4)
        table.add_column("Parameter", style="cyan", min_width=20)
        table.add_column("Value", justify="right")
        table.add_column("Display", style="green")

        for tag, value in resolved.raw.fields.items():
            if raw or resolved.schema is None:
                param_name = tag
                display_val = str(value)
            else:
                fd = resolved.schema.fields.get(tag)
                if fd:
                    param_name = fd.display or fd.name
                    if fd.choices and value in fd.choices:
                        display_val = fd.choices[value]
                    elif fd.unit:
                        display_val = f"{value} {fd.unit}"
                    else:
                        display_val = str(value)
                else:
                    param_name = tag
                    display_val = str(value)

            table.add_row(tag, param_name, str(value), display_val)

        console.print(table)
        console.print()


@cli.command()
@click.argument("rc0_file", type=click.Path(exists=True, dir_okay=False))
def parse(rc0_file: str) -> None:
    """Parse and display raw structure of an RC0 file."""
    rc0 = parse_memory_file(rc0_file)

    console.print(f"[bold]File[/bold]: {rc0.path.name}")
    console.print(f"[bold]Device[/bold]: {rc0.device_name}")
    console.print(f"[bold]Revision[/bold]: {rc0.revision}")
    console.print(f"[bold]Count[/bold]: {rc0.count}")
    console.print()

    for element in rc0.elements:
        id_str = f' id="{element.id}"' if element.id is not None else ""
        console.print(f"[bold cyan]<{element.element}{id_str}>[/bold cyan]")
        console.print(f"  Sections: {len(element.sections)}")
        for sec_name, section in element.sections.items():
            console.print(f"  [dim]{sec_name}[/dim]: {len(section.fields)} fields")


if __name__ == "__main__":
    cli()
