# EastLight

**Alpha — not ready for production use.**

This project is under active development. The file format parser achieves byte-for-byte round-trip fidelity and ~98% schema coverage, but the CLI interface, error handling, and edge cases are still maturing. Back up your SD card before using EastLight on real data.

## What it is

Open-source editor/librarian for the **Roland RC-505 MK2** loop station.

EastLight reads and writes the RC-505 MK2's SD card backup format (ROLAND/ directory), giving you full control over memory patches, audio tracks, effects, and system settings from the command line.

## Install

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

### Organize memories

```
eastlight copy 1 50
eastlight swap 1 50
eastlight diff 1 50
```

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
eastlight fx-set 1 ifx AA fx_type 35
```

70 effect types fully mapped: filters, modulation, delay, reverb, dynamics, pitch, vocoder, slicer, and 4 TFX-exclusive beat effects.

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

## Safety

EastLight automatically backs up files before any write operation. Backups are timestamped and stored in `~/.config/eastlight/backups/` (outside the device filesystem). To disable:

```
eastlight config --no-backup
```

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
    main.py        Click-based CLI (15 commands)
```

## Schema coverage

~98% of the RC-505 MK2's file format is mapped:

- All memory-level sections (track, master, EQ, mixer, routing, assign, ...)
- All 70 FX effect types (66 shared + 4 TFX-exclusive)
- FX type index enum with reverse lookup
- System settings (SETUP, PREF)

Remaining gaps: CTL FUNC display names (200+ entries), 13 internal SETUP fields.

## Development

```
pip install -e ".[dev]"
pytest
```

## License

GPL-3.0-or-later
