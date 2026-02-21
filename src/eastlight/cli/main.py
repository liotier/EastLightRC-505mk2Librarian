"""CLI interface for EastLight RC-505 MK2 editor."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from eastlight.core.config import detect_device, load_config, resolve_roland_dir, save_config
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


def _resolve_dir(roland_dir: str | None) -> str:
    """Resolve ROLAND directory, raising ClickException on failure."""
    try:
        return str(resolve_roland_dir(roland_dir))
    except ValueError as e:
        raise click.ClickException(str(e))


def _open_memory(roland_dir: str, memory_num: int) -> tuple[RC505Library, Memory, SchemaRegistry]:
    """Parse a memory and return (library, memory, registry) for reuse."""
    lib = RC505Library(roland_dir)
    registry = _load_registry()
    rc0 = lib.parse_memory(memory_num)
    return lib, Memory(rc0, registry), registry


@click.group()
@click.version_option(package_name="eastlight")
def cli() -> None:
    """EastLight — RC-505 MK2 editor/librarian."""


@cli.command("list")
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
def list_cmd(roland_dir: str | None) -> None:
    """List all memories in a ROLAND/ backup directory."""
    roland_dir = _resolve_dir(roland_dir)
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
@click.argument("memory_num", type=int)
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
@click.option("--section", "-s", help="Show only this section (e.g., TRACK1, MASTER)")
@click.option("--raw", is_flag=True, help="Show raw tag names instead of resolved names")
def show(memory_num: int, roland_dir: str | None, section: str | None, raw: bool) -> None:
    """Show parameters for a memory slot."""
    roland_dir = _resolve_dir(roland_dir)
    _, mem, _ = _open_memory(roland_dir, memory_num)

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
@click.argument("memory_num", type=int)
@click.argument("section_name")
@click.argument("param_name")
@click.argument("value", type=int)
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
def set_cmd(
    memory_num: int,
    section_name: str,
    param_name: str,
    value: int,
    roland_dir: str | None,
) -> None:
    """Set a parameter value in a memory.

    Example: eastlight set 1 MASTER tempo_x10 800
    """
    roland_dir = _resolve_dir(roland_dir)
    lib, mem, _ = _open_memory(roland_dir, memory_num)
    resolved = mem.section(section_name)
    if resolved is None:
        raise click.ClickException(
            f"Section '{section_name}' not found in memory {memory_num:03d}. "
            f"Use 'eastlight show {memory_num}' to see available sections."
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
@click.argument("memory_num", type=int)
@click.argument("new_name")
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
def name(memory_num: int, new_name: str, roland_dir: str | None) -> None:
    """Rename a memory slot.

    Example: eastlight name 1 "My Loop"
    """
    roland_dir = _resolve_dir(roland_dir)
    lib, mem, _ = _open_memory(roland_dir, memory_num)
    old_name = mem.name
    mem.set_name(new_name)
    lib.save_memory(memory_num, mem.rc0)
    console.print(
        f"[green]Renamed[/green] memory {memory_num:03d}: "
        f"'{old_name}' → '{mem.name}'"
    )


@cli.command()
@click.argument("src", type=int)
@click.argument("dst", type=int)
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
@click.option("--force", is_flag=True, help="Overwrite destination without prompting")
def copy(src: int, dst: int, roland_dir: str | None, force: bool) -> None:
    """Copy a memory slot to another slot (RC0 + WAV).

    Example: eastlight copy 1 50
    """
    roland_dir = _resolve_dir(roland_dir)
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
@click.argument("mem_a", type=int)
@click.argument("mem_b", type=int)
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
def swap(mem_a: int, mem_b: int, roland_dir: str | None) -> None:
    """Swap two memory slots (RC0 + WAV).

    Example: eastlight swap 1 50
    """
    roland_dir = _resolve_dir(roland_dir)
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
@click.argument("mem_a", type=int)
@click.argument("mem_b", type=int)
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
@click.option("--section", "-s", help="Compare only this section")
def diff(mem_a: int, mem_b: int, roland_dir: str | None, section: str | None) -> None:
    """Show differences between two memories.

    Example: eastlight diff 1 3
    """
    roland_dir = _resolve_dir(roland_dir)
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
@click.argument("memory_num", type=int)
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
@click.option("--track", "-t", type=int, default=None, help="Show only this track (1-5)")
def wav_info_cmd(memory_num: int, roland_dir: str | None, track: int | None) -> None:
    """Show WAV audio info for a memory's tracks.

    Example: eastlight wav-info 1
    """
    roland_dir = _resolve_dir(roland_dir)
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
@click.argument("memory_num", type=int)
@click.argument("track_num", type=int)
@click.argument("output", type=click.Path(dir_okay=False))
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["float32", "pcm24", "pcm16"]),
    default="float32",
    help="Export format (default: float32 — native lossless)",
)
def wav_export_cmd(
    memory_num: int, track_num: int, output: str, roland_dir: str | None, fmt: str
) -> None:
    """Export a track's audio to a WAV file.

    Default format is 32-bit float (native, lossless). Use --format pcm24
    for DAW compatibility, or pcm16 for maximum compatibility.

    Example: eastlight wav-export 1 1 my_loop.wav
    """
    roland_dir = _resolve_dir(roland_dir)
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
@click.argument("memory_num", type=int)
@click.argument("track_num", type=int)
@click.argument("input_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
@click.option("--force", is_flag=True, help="Overwrite existing track audio without prompting")
def wav_import_cmd(
    memory_num: int,
    track_num: int,
    input_file: str,
    roland_dir: str | None,
    force: bool,
) -> None:
    """Import an audio file into a memory track.

    Accepts WAV, FLAC, OGG, and other formats supported by libsndfile.
    Audio is converted to 32-bit float stereo at 44.1kHz (the device's
    native format). Mono files are duplicated to stereo.

    Example: eastlight wav-import 1 1 my_recording.wav
    """
    roland_dir = _resolve_dir(roland_dir)
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


# --- FX commands ---


_FX_CHAINS = {"ifx": "Input FX", "tfx": "Track FX"}
_FX_GROUPS = ["A", "B", "C", "D"]
_FX_SLOTS = ["A", "B", "C", "D"]


@cli.command("fx-show")
@click.argument("memory_num", type=int)
@click.argument("chain", type=click.Choice(["ifx", "tfx"]))
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
@click.option("--group", "-g", type=click.Choice(_FX_GROUPS), help="Show only this group (A-D)")
@click.option("--slot", "-s", help="Show only this subslot (e.g., AA, AB, CD)")
@click.option("--raw", is_flag=True, help="Show raw tag names instead of resolved names")
def fx_show(
    memory_num: int,
    chain: str,
    roland_dir: str | None,
    group: str | None,
    slot: str | None,
    raw: bool,
) -> None:
    """Show FX chain parameters for a memory.

    CHAIN is 'ifx' (input FX) or 'tfx' (track FX).

    Examples:

    \b
      eastlight fx-show 1 ifx
      eastlight fx-show 1 tfx -g A
      eastlight fx-show 1 ifx -s AA
    """
    roland_dir = _resolve_dir(roland_dir)
    lib, mem, registry = _open_memory(roland_dir, memory_num)
    rc0 = mem.rc0

    fx_element = rc0.ifx if chain == "ifx" else rc0.tfx
    if fx_element is None:
        raise click.ClickException(f"No <{chain}> element in memory {memory_num:03d}.")

    chain_label = _FX_CHAINS[chain]
    console.print(
        f"[bold]Memory {memory_num:03d}[/bold] — {chain_label}"
    )
    console.print()

    fx_type_map = registry.fx_types.ifx_types if chain == "ifx" else registry.fx_types.tfx_types

    # Determine which subslots to display
    if slot:
        subslots = [slot.upper()]
    elif group:
        subslots = [f"{group.upper()}{s}" for s in _FX_SLOTS]
    else:
        subslots = [f"{g}{s}" for g in _FX_GROUPS for s in _FX_SLOTS]

    for ss in subslots:
        # Show subslot header (switch + active FX type)
        header_section = fx_element.sections.get(ss)
        if header_section is None:
            continue

        sw = header_section.get("A", 0)
        fx_type_idx = header_section.get("C", 0)
        fx_name = fx_type_map.get(fx_type_idx, f"UNKNOWN({fx_type_idx})")
        sw_str = "[green]ON[/green]" if sw else "[dim]OFF[/dim]"

        console.print(
            f"  [bold cyan]{ss}[/bold cyan]: {sw_str}  "
            f"[yellow]{fx_name}[/yellow] (type {fx_type_idx})"
        )

        # Show the active effect's parameters
        active_section_name = f"{ss}_{fx_name}"
        section = fx_element.sections.get(active_section_name)
        if section is None:
            console.print(f"    [dim](no section '{active_section_name}')[/dim]")
            console.print()
            continue

        schema = registry.get(active_section_name)

        table = Table(show_header=True, padding=(0, 1))
        table.add_column("Tag", style="dim", width=4)
        table.add_column("Parameter", style="cyan", min_width=16)
        table.add_column("Value", justify="right")

        for tag, value in section.fields.items():
            if raw or schema is None:
                param_name = tag
            else:
                fd = schema.fields.get(tag)
                param_name = (fd.display or fd.name) if fd else tag

            table.add_row(tag, param_name, str(value))

        console.print(table)
        console.print()


@cli.command("fx-set")
@click.argument("memory_num", type=int)
@click.argument("chain", type=click.Choice(["ifx", "tfx"]))
@click.argument("subslot")
@click.argument("param_name")
@click.argument("value", type=int)
@click.option("--dir", "-d", "roland_dir", type=click.Path(file_okay=False),
              default=None, help="ROLAND/ directory (default: config or auto-detect)")
def fx_set(
    memory_num: int,
    chain: str,
    subslot: str,
    param_name: str,
    value: int,
    roland_dir: str | None,
) -> None:
    """Set an FX parameter value.

    SUBSLOT identifies the FX slot (e.g., AA, AB, CD).
    PARAM_NAME can be a schema name (e.g., 'feedback') or raw tag (e.g., 'B').

    Special param names for the subslot header:
      sw        — enable/disable the slot (0 or 1)
      fx_type   — change the active effect type index

    Examples:

    \b
      eastlight fx-set 1 ifx AA feedback 30
      eastlight fx-set 1 tfx AA sw 1
      eastlight fx-set 1 ifx AA fx_type 35
    """
    roland_dir = _resolve_dir(roland_dir)
    lib, mem, registry = _open_memory(roland_dir, memory_num)
    rc0 = mem.rc0

    fx_element = rc0.ifx if chain == "ifx" else rc0.tfx
    if fx_element is None:
        raise click.ClickException(f"No <{chain}> element in memory {memory_num:03d}.")

    subslot = subslot.upper()
    fx_type_map = registry.fx_types.ifx_types if chain == "ifx" else registry.fx_types.tfx_types

    # Check if setting a header field (sw, fx_type)
    header_section = fx_element.sections.get(subslot)
    if header_section is None:
        raise click.ClickException(
            f"Subslot '{subslot}' not found in {chain} of memory {memory_num:03d}."
        )

    header_schema = registry.get(subslot)

    # Try header field first (sw, fx_type, etc.)
    if header_schema:
        header_tag = header_schema.name_to_tag(param_name)
        if header_tag is not None:
            old_value = header_section.get(header_tag)
            header_section[header_tag] = value
            lib.save_memory(memory_num, rc0)
            display = param_name
            if param_name == "fx_type":
                old_name = fx_type_map.get(old_value, str(old_value))
                new_name = fx_type_map.get(value, str(value))
                display = f"fx_type ({old_name} → {new_name})"
            console.print(
                f"[green]Set[/green] {chain}.{subslot}.{display}: "
                f"{old_value} → {value}"
            )
            return

    # Otherwise, set a parameter on the active effect
    fx_type_idx = header_section.get("C", 0)
    fx_name = fx_type_map.get(fx_type_idx, f"UNKNOWN({fx_type_idx})")
    effect_section_name = f"{subslot}_{fx_name}"
    effect_section = fx_element.sections.get(effect_section_name)

    if effect_section is None:
        raise click.ClickException(
            f"Effect section '{effect_section_name}' not found."
        )

    effect_schema = registry.get(effect_section_name)

    # Try schema name first
    tag = None
    if effect_schema:
        tag = effect_schema.name_to_tag(param_name)

    if tag is None:
        # Try raw tag
        if param_name in effect_section.fields:
            tag = param_name
        else:
            raise click.ClickException(
                f"Parameter '{param_name}' not found in {effect_section_name}."
            )

    old_value = effect_section.get(tag)
    effect_section[tag] = value
    lib.save_memory(memory_num, rc0)

    display_name = param_name
    if effect_schema and tag != param_name:
        display_name = f"{param_name} ({tag})"

    console.print(
        f"[green]Set[/green] {chain}.{subslot}.{fx_name}.{display_name}: "
        f"{old_value} → {value}"
    )


# --- Device & config commands ---


@cli.command()
def detect() -> None:
    """Auto-detect connected RC-505 MK2 devices.

    Scans mounted volumes for ROLAND/ directories containing RC0 files.
    """
    console.print("[bold]Scanning for RC-505 MK2 devices...[/bold]")
    devices = detect_device()

    if not devices:
        console.print("[dim]No devices found.[/dim]")
        console.print(
            "\nMake sure your RC-505 MK2 is connected via USB "
            "and the SD card is mounted."
        )
        return

    for i, path in enumerate(devices, 1):
        console.print(f"  {i}. [green]{path}[/green]")

    if len(devices) == 1:
        console.print(
            f"\nTo set as default: [bold]eastlight config --set-dir {devices[0]}[/bold]"
        )
    else:
        console.print(
            "\nSet one as default: [bold]eastlight config --set-dir <path>[/bold]"
        )


@cli.command()
@click.option("--set-dir", type=click.Path(exists=True, file_okay=False),
              help="Set default ROLAND/ directory path")
@click.option("--backup/--no-backup", default=None,
              help="Enable/disable automatic backup before writes")
@click.option("--show", is_flag=True, help="Show current configuration")
def config(set_dir: str | None, backup: bool | None, show: bool) -> None:
    """View or modify EastLight configuration.

    Configuration is stored in ~/.config/eastlight/config.yaml.

    Examples:

    \b
      eastlight config --show
      eastlight config --set-dir /media/user/RC505/ROLAND
      eastlight config --no-backup
    """
    cfg = load_config()

    if set_dir is not None:
        cfg.roland_dir = set_dir
        # Add to recent list
        if set_dir not in cfg.recent:
            cfg.recent.insert(0, set_dir)
            cfg.recent = cfg.recent[:10]  # Keep last 10
        path = save_config(cfg)
        console.print(f"[green]Saved[/green] default directory: {set_dir}")
        console.print(f"[dim]Config: {path}[/dim]")
        return

    if backup is not None:
        cfg.backup = backup
        path = save_config(cfg)
        state = "enabled" if backup else "disabled"
        console.print(f"[green]Saved[/green] backup: {state}")
        return

    # Default: show config
    console.print("[bold]EastLight Configuration[/bold]")
    console.print(f"  ROLAND dir: {cfg.roland_dir or '[dim](not set)[/dim]'}")
    console.print(f"  Backup:     {'[green]enabled[/green]' if cfg.backup else '[red]disabled[/red]'}")
    if cfg.recent:
        console.print("  Recent:")
        for r in cfg.recent:
            console.print(f"    {r}")


if __name__ == "__main__":
    cli()
