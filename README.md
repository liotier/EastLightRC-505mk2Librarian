# EastLight

**Alpha — not ready for production use.** See the [feasibility study](rc505-mk2-feasibility.md) for context.

This project is under active development. The file format parser achieves byte-for-byte round-trip fidelity and ~98% schema coverage, but the CLI interface, error handling, and edge cases are still maturing. Back up your SD card before using EastLight on real data.

## What it is

Open-source editor/librarian for the **Roland RC-505 MK2** loop station.

EastLight reads and writes the RC-505 MK2's SD card backup format (ROLAND/ directory), giving you full control over memory patches, audio tracks, effects, and system settings from the command line.

## Install

```
pip install eastlight
```

Or from source:

```
pip install -e .
```

Requires Python 3.11+ and libsndfile (for WAV/FLAC/OGG audio support).

## Quick start

### Find your device

Connect your RC-505 MK2 via USB and mount the SD card, then:

```
eastlight detect
eastlight config --set-dir /media/user/RC505/ROLAND
```

Once a default directory is set, all commands use it automatically. You can always override with `-d/--dir`.

### Browse memories

```
eastlight list
eastlight list -d /media/user/RC505/ROLAND
```

Shows all 99 memory slots with names, track indicators, tempo, and backup status.

### Inspect a memory

```
eastlight show 1
eastlight show 1 -s TRACK1
eastlight show 1 --raw
```

### Edit parameters

```
eastlight set 1 MASTER pan 75
eastlight name 1 "My Loop"
```

Set commands warn when values are outside schema-defined ranges or invalid for boolean/enum fields. Use `--dry-run` / `-n` to preview changes without writing.

### Organize memories

```
eastlight copy 1 50
eastlight swap 1 50
eastlight clear 5
eastlight clear 5 --dry-run
eastlight diff 1 50
```

`clear` removes a memory slot's RC0 data and WAV audio (with automatic backup first).

### Batch operations

```
eastlight bulk-set 1-10 MASTER play_level 100
eastlight bulk-set 1,3,5 TRACK1 pan 50 --dry-run
eastlight template-export 1 my_settings.yaml
eastlight template-export 1 fx_only.yaml -s TRACK1 -s MASTER
eastlight template-apply my_settings.yaml 5
eastlight template-apply settings.yaml 1-10 --dry-run
```

- `bulk-set` applies the same parameter change across multiple memories at once
- `template-export` saves a memory's parameters as YAML (no audio)
- `template-apply` applies a YAML template to one or more memories

Memory ranges support commas and dashes: `1-5`, `1,3,5`, `1-3,7,10-12`.

### Audio import/export

```
eastlight wav-info 1
eastlight wav-export 1 1 my_loop.wav
eastlight wav-export 1 1 my_loop.wav --format pcm24
eastlight wav-import 1 2 recording.wav
```

Supported import formats: WAV, FLAC, OGG (anything libsndfile supports).
Audio is converted to 32-bit float stereo at 44.1 kHz (the device's native format).
Mono files are automatically duplicated to stereo.

### Effects

```
eastlight fx-show 1 ifx
eastlight fx-show 1 tfx -g A
eastlight fx-show 1 ifx -s AA

eastlight fx-set 1 ifx AA feedback 30
eastlight fx-set 1 ifx AA sw 1
eastlight fx-set 1 ifx AA fx_type 35 --dry-run
```

70 effect types fully mapped: filters, modulation, delay, reverb, dynamics, pitch, vocoder, slicer, and 4 TFX-exclusive beat effects.

### System settings

```
eastlight sys-show
eastlight sys-show -s SETUP
eastlight sys-show --all
eastlight sys-set SETUP contrast 8
eastlight sys-set PREF pref_eq 0 --dry-run
```

### MIDI controller assignments

```
eastlight ctl-show
eastlight ctl-show --type ictl
eastlight ctl-show --type ectl
eastlight ctl-set ICTL1_TRACK1_FX ctl_func 42
eastlight ctl-set ECTL_CTL1 ctl_func 10
eastlight ctl-set ECTL_EXP1 ctl_range 64
eastlight ctl-set ICTL1_PEDAL1 ctl_mode 0
```

Internal controllers (ICTL): 47 panel button and pedal assignments across 3 banks.
External controllers (ECTL): 6 MIDI CC inputs (CTL1-4, EXP1-2).

### Backup management

```
eastlight backup list
eastlight backup show 20260101T120000Z
eastlight backup restore 20260101T120000Z
eastlight backup prune --keep 3
```

Backups are timestamped snapshots created automatically before every write.

### Configuration

```
eastlight config --show
eastlight config --set-dir /media/user/RC505/ROLAND
eastlight config --no-backup
```

Configuration is stored in `~/.config/eastlight/config.yaml`.

### ROLAND directory resolution

Commands find the ROLAND/ directory in this order:

1. Explicit `-d/--dir` option
2. Default from `eastlight config --set-dir`
3. Single auto-detected device (USB mount scan)

If multiple devices are detected and no default is set, EastLight lists them and asks you to pick one with `config --set-dir`.

### Dry-run mode

All write commands support `--dry-run` / `-n` to preview what would change without touching any files:

```
eastlight set 1 MASTER pan 75 --dry-run
eastlight clear 5 -n
eastlight bulk-set 1-10 MASTER play_level 100 -n
eastlight sys-set SETUP contrast 8 -n
eastlight fx-set 1 ifx AA feedback 30 -n
eastlight ctl-set ECTL_CTL1 ctl_func 10 -n
eastlight template-apply settings.yaml 1-10 --dry-run
```

## Safety

EastLight automatically backs up files before any write operation. Backups are timestamped and stored in `~/.config/eastlight/backups/` (outside the device filesystem). To disable:

```
eastlight config --no-backup
```

Use `eastlight backup list` to see snapshots and `eastlight backup restore` to roll back.

## Architecture

```
src/eastlight/
  core/
    parser.py      Regex-based RC0 reader (handles Roland's non-standard XML)
    writer.py      RC0 serializer (byte-for-byte roundtrip fidelity)
    model.py       Typed data model with undo/redo and change observers
    schema.py      YAML-driven parameter mapping with FX suffix matching
    library.py     ROLAND/ directory operations with auto-backup
    wav.py         32-bit float WAV import/export via libsndfile
    config.py      User config, device auto-detection, dir resolution
  schema/
    *.yaml         24 section schemas (track, master, assign, routing, ...)
    effects/       70 FX effect type schemas
    fx_types.yaml  FX type index enum (IFX 0-65, TFX 0-69)
  cli/
    main.py        Click-based CLI (25 commands)
```

## Schema coverage

~98% of the RC-505 MK2's file format is mapped:

- All memory-level sections (track, master, EQ, mixer, routing, assign, ...)
- All 70 FX effect types (66 shared + 4 TFX-exclusive)
- FX type index enum with reverse lookup
- System settings (SETUP, PREF, COLOR, USB, MIDI)
- All 53 ICTL + 6 ECTL controller mapping sections

Remaining gaps: CTL FUNC display names (200+ entries), 13 internal SETUP fields.

## Development

```
pip install -e ".[dev]"
pytest
```

## License

GPL-3.0-or-later
