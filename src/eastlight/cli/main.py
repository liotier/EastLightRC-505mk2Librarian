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
from eastlight.core.wav import (
    DEVICE_SAMPLE_RATE,
    ExportFormat,
    import_audio,
    wav_export,
    wav_info,
    wav_write_device,
)
from eastlight.core.writer import write_rc0

console = Console()


def _load_registry() -> SchemaRegistry:
    """Load the built-in schema registry."""
    registry = SchemaRegistry()
    registry.load_all()
    return registry


def _open_memory(roland_dir: str, memory_num: int) -> tuple[RC505Library, Memory]:
    """Parse a memory and return (library, memory) for reuse."""
    lib = RC505Library(roland_dir)
    registry = _load_registry()
    rc0 = lib.parse_memory(memory_num)
    return lib, Memory(rc0, registry)


@click.group()
@click.version_option(package_name="eastlight")
def cli() -> None:
    """EastLight — RC-505 MK2 editor/librarian."""


@cli.command("list")
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
def list_cmd(roland_dir: str) -> None:
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
    _, mem = _open_memory(roland_dir, memory_num)

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


# --- New commands: set, name, copy, diff, swap ---


@cli.command("set")
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("memory_num", type=int)
@click.argument("section_name")
@click.argument("param_name")
@click.argument("value", type=int)
def set_cmd(
    roland_dir: str,
    memory_num: int,
    section_name: str,
    param_name: str,
    value: int,
) -> None:
    """Set a parameter value in a memory.

    Example: eastlight set ROLAND 1 MASTER tempo_x10 800
    """
    lib, mem = _open_memory(roland_dir, memory_num)
    resolved = mem.section(section_name)
    if resolved is None:
        raise click.ClickException(
            f"Section '{section_name}' not found in memory {memory_num:03d}. "
            f"Use 'eastlight show {roland_dir} {memory_num}' to see available sections."
        )

    old_value = resolved.get_by_name(param_name)
    if old_value is None:
        # Try raw tag access
        if param_name not in resolved.raw.fields:
            raise click.ClickException(
                f"Parameter '{param_name}' not found in {section_name}."
            )
        old_value = resolved.get_by_tag(param_name)
        resolved.set_by_tag(param_name, value)
        tag = param_name
    else:
        resolved.set_by_name(param_name, value)
        tag = resolved.schema.name_to_tag(param_name) if resolved.schema else param_name

    lib.save_memory(memory_num, mem.rc0)
    console.print(
        f"[green]Set[/green] {section_name}.{param_name} "
        f"({tag}): {old_value} → {value}"
    )


@cli.command()
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("memory_num", type=int)
@click.argument("new_name")
def name(roland_dir: str, memory_num: int, new_name: str) -> None:
    """Rename a memory slot.

    Example: eastlight name ROLAND 1 "My Loop"
    """
    lib, mem = _open_memory(roland_dir, memory_num)
    old_name = mem.name
    mem.set_name(new_name)
    lib.save_memory(memory_num, mem.rc0)
    console.print(
        f"[green]Renamed[/green] memory {memory_num:03d}: "
        f"'{old_name}' → '{mem.name}'"
    )


@cli.command()
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("src", type=int)
@click.argument("dst", type=int)
@click.option("--force", is_flag=True, help="Overwrite destination without prompting")
def copy(roland_dir: str, src: int, dst: int, force: bool) -> None:
    """Copy a memory slot to another slot (RC0 + WAV).

    Example: eastlight copy ROLAND 1 50
    """
    lib = RC505Library(roland_dir)

    src_slot = lib.memory_slot(src)
    if not src_slot.exists:
        raise click.ClickException(f"Source memory {src:03d} does not exist.")

    dst_slot = lib.memory_slot(dst)
    if dst_slot.exists and not force:
        dst_name = lib.memory_name(dst) or "(unnamed)"
        if not click.confirm(
            f"Destination {dst:03d} ('{dst_name}') already exists. Overwrite?"
        ):
            raise click.Abort()

    lib.copy_memory(src, dst)

    src_name = lib.memory_name(src) or "(unnamed)"
    console.print(
        f"[green]Copied[/green] memory {src:03d} ('{src_name}') → {dst:03d}"
    )


@cli.command()
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("mem_a", type=int)
@click.argument("mem_b", type=int)
def swap(roland_dir: str, mem_a: int, mem_b: int) -> None:
    """Swap two memory slots (RC0 + WAV).

    Example: eastlight swap ROLAND 1 50
    """
    lib = RC505Library(roland_dir)

    slot_a = lib.memory_slot(mem_a)
    slot_b = lib.memory_slot(mem_b)
    if not slot_a.exists:
        raise click.ClickException(f"Memory {mem_a:03d} does not exist.")
    if not slot_b.exists:
        raise click.ClickException(f"Memory {mem_b:03d} does not exist.")

    name_a = lib.memory_name(mem_a) or "(unnamed)"
    name_b = lib.memory_name(mem_b) or "(unnamed)"

    lib.swap_memories(mem_a, mem_b)
    console.print(
        f"[green]Swapped[/green] {mem_a:03d} ('{name_a}') ↔ {mem_b:03d} ('{name_b}')"
    )


@cli.command()
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("mem_a", type=int)
@click.argument("mem_b", type=int)
@click.option("--section", "-s", help="Compare only this section")
def diff(roland_dir: str, mem_a: int, mem_b: int, section: str | None) -> None:
    """Show differences between two memories.

    Example: eastlight diff ROLAND 1 3
    """
    registry = _load_registry()
    lib = RC505Library(roland_dir)
    rc0_a = lib.parse_memory(mem_a)
    rc0_b = lib.parse_memory(mem_b)
    ma = Memory(rc0_a, registry)
    mb = Memory(rc0_b, registry)

    name_a = ma.name or "(unnamed)"
    name_b = mb.name or "(unnamed)"
    console.print(
        f"[bold]Diff[/bold]: {mem_a:03d} ('{name_a}') vs {mem_b:03d} ('{name_b}')"
    )
    console.print()

    sections_to_check = [section] if section else ma.section_names
    total_diffs = 0

    for sec_name in sections_to_check:
        sa = ma.section(sec_name)
        sb = mb.section(sec_name)
        if sa is None or sb is None:
            continue

        diffs = []
        all_tags = set(sa.raw.fields.keys()) | set(sb.raw.fields.keys())
        for tag in sorted(all_tags):
            val_a = sa.raw.fields.get(tag)
            val_b = sb.raw.fields.get(tag)
            if val_a != val_b:
                # Resolve parameter name from schema
                param = tag
                if sa.schema:
                    fd = sa.schema.fields.get(tag)
                    if fd:
                        param = fd.display or fd.name
                diffs.append((tag, param, val_a, val_b))

        if diffs:
            table = Table(title=sec_name, show_header=True)
            table.add_column("Tag", style="dim", width=4)
            table.add_column("Parameter", style="cyan", min_width=20)
            table.add_column(f"{mem_a:03d}", justify="right", style="red")
            table.add_column(f"{mem_b:03d}", justify="right", style="green")

            for tag, param, va, vb in diffs:
                table.add_row(
                    tag,
                    param,
                    str(va) if va is not None else "-",
                    str(vb) if vb is not None else "-",
                )

            console.print(table)
            console.print()
            total_diffs += len(diffs)

    if total_diffs == 0:
        console.print("[dim]No differences found.[/dim]")
    else:
        console.print(f"[bold]{total_diffs}[/bold] difference(s) found.")


# --- WAV commands ---


@cli.command("wav-info")
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("memory_num", type=int)
@click.option("--track", "-t", type=int, default=None, help="Show only this track (1-5)")
def wav_info_cmd(roland_dir: str, memory_num: int, track: int | None) -> None:
    """Show WAV audio info for a memory's tracks.

    Example: eastlight wav-info ROLAND 1
    """
    lib = RC505Library(roland_dir)
    slot = lib.memory_slot(memory_num)

    if not slot.exists:
        raise click.ClickException(f"Memory {memory_num:03d} does not exist.")

    tracks = [track] if track else range(1, 6)

    table = Table(title=f"Memory {memory_num:03d} — Audio Tracks")
    table.add_column("Track", style="cyan", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Sample Rate", justify="right")
    table.add_column("Channels", justify="right")
    table.add_column("Format", style="dim")

    found = False
    for t in tracks:
        wav_path = slot.track_wav(t)
        if wav_path is None:
            table.add_row(str(t), "[dim]empty[/dim]", "-", "-", "-", "-")
            continue

        found = True
        info = wav_info(wav_path)
        minutes = int(info.duration // 60)
        seconds = info.duration % 60
        dur_str = f"{minutes}:{seconds:05.2f}" if minutes else f"{seconds:.2f}s"

        table.add_row(
            str(t),
            "[green]audio[/green]",
            dur_str,
            f"{info.sample_rate} Hz",
            str(info.channels),
            f"{info.subtype} {info.format}",
        )

    console.print(table)

    if not found and track:
        console.print(f"[dim]Track {track} has no audio.[/dim]")


@cli.command("wav-export")
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("memory_num", type=int)
@click.argument("track_num", type=int)
@click.argument("output", type=click.Path(dir_okay=False))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["float32", "pcm24", "pcm16"]),
    default="float32",
    help="Export format (default: float32 — native lossless)",
)
def wav_export_cmd(
    roland_dir: str, memory_num: int, track_num: int, output: str, fmt: str
) -> None:
    """Export a track's audio to a WAV file.

    Default format is 32-bit float (native, lossless). Use --format pcm24
    for DAW compatibility, or pcm16 for maximum compatibility.

    Example: eastlight wav-export ROLAND 1 1 my_loop.wav
    """
    lib = RC505Library(roland_dir)
    slot = lib.memory_slot(memory_num)

    if not slot.exists:
        raise click.ClickException(f"Memory {memory_num:03d} does not exist.")

    wav_path = slot.track_wav(track_num)
    if wav_path is None:
        raise click.ClickException(
            f"Track {track_num} of memory {memory_num:03d} has no audio."
        )

    format_map = {
        "float32": ExportFormat.FLOAT_32,
        "pcm24": ExportFormat.PCM_24,
        "pcm16": ExportFormat.PCM_16,
    }
    export_fmt = format_map[fmt]

    from eastlight.core.wav import wav_read

    data, sr = wav_read(wav_path)
    out_path = Path(output)
    wav_export(out_path, data, sr, export_fmt)

    info = wav_info(out_path)
    console.print(
        f"[green]Exported[/green] memory {memory_num:03d} track {track_num} → {out_path.name} "
        f"({info.subtype}, {info.duration:.2f}s)"
    )


@cli.command("wav-import")
@click.argument("roland_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("memory_num", type=int)
@click.argument("track_num", type=int)
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--force", is_flag=True, help="Overwrite existing track audio without prompting")
def wav_import_cmd(
    roland_dir: str,
    memory_num: int,
    track_num: int,
    input_file: str,
    force: bool,
) -> None:
    """Import an audio file into a memory track.

    Accepts WAV, FLAC, OGG, and other formats supported by libsndfile.
    Audio is converted to 32-bit float stereo at 44.1kHz (the device's
    native format). Mono files are duplicated to stereo.

    Example: eastlight wav-import ROLAND 1 1 my_recording.wav
    """
    lib = RC505Library(roland_dir)
    slot = lib.memory_slot(memory_num)

    if not slot.exists:
        raise click.ClickException(f"Memory {memory_num:03d} does not exist.")

    if not 1 <= track_num <= 5:
        raise click.ClickException(f"Track number must be 1-5, got {track_num}.")

    # Check for existing audio
    existing = slot.track_wav(track_num)
    if existing is not None and not force:
        if not click.confirm(
            f"Track {track_num} already has audio. Overwrite?"
        ):
            raise click.Abort()

    # Import and convert audio
    data, sr = import_audio(input_file)

    if sr != DEVICE_SAMPLE_RATE:
        raise click.ClickException(
            f"Sample rate mismatch: source is {sr} Hz, device requires {DEVICE_SAMPLE_RATE} Hz. "
            f"Please resample your audio to {DEVICE_SAMPLE_RATE} Hz before importing."
        )

    # Write to device WAV location
    wav_dir = lib.wave_dir / f"{memory_num:03d}_{track_num}"
    wav_dir.mkdir(parents=True, exist_ok=True)
    dst_path = wav_dir / f"{memory_num:03d}_{track_num}.WAV"
    wav_write_device(dst_path, data, sr)

    # Update track metadata in the RC0 file
    registry = _load_registry()
    rc0 = lib.parse_memory(memory_num)
    mem = Memory(rc0, registry)
    track = mem.track(track_num)
    if track is not None:
        total_samples = data.shape[0]
        track.set_by_tag("W", 1)  # has_audio = true
        track.set_by_tag("X", total_samples)  # total_samples
        # Compute samples_per_measure from tempo if available
        tempo_x10 = track.get_by_tag("U")
        if tempo_x10 and tempo_x10 > 0:
            bpm = tempo_x10 / 10.0
            samples_per_beat = DEVICE_SAMPLE_RATE * 60.0 / bpm
            samples_per_measure = int(samples_per_beat * 4)
            track.set_by_tag("V", samples_per_measure)
            # Compute loop length in measures
            if samples_per_measure > 0:
                measures = round(total_samples / samples_per_measure)
                track.set_by_tag("S", max(1, measures))
        lib.save_memory(memory_num, rc0)

    dur = data.shape[0] / sr
    console.print(
        f"[green]Imported[/green] {Path(input_file).name} → "
        f"memory {memory_num:03d} track {track_num} "
        f"({dur:.2f}s, {data.shape[0]} samples)"
    )


if __name__ == "__main__":
    cli()
