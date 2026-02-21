# EastLight

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
```

Or point directly at the ROLAND/ directory on your SD card.

### Browse memories

```
eastlight list /media/user/RC505/ROLAND
```

Shows all 99 memory slots with names, track indicators, tempo, and backup status.

### Inspect a memory

```
eastlight show ROLAND 1
eastlight show ROLAND 1 -s TRACK1
eastlight show ROLAND 1 --raw
```

### Edit parameters

```
eastlight set ROLAND 1 TRACK1 pan 75
eastlight name ROLAND 1 "My Loop"
```

### Organize memories

```
eastlight copy ROLAND 1 50
eastlight swap ROLAND 1 50
eastlight diff ROLAND 1 50
```

### Audio import/export

```
eastlight wav-info ROLAND 1
eastlight wav-export ROLAND 1 1 my_loop.wav
eastlight wav-export ROLAND 1 1 my_loop.wav --format pcm24
eastlight wav-import ROLAND 1 2 recording.wav
```

Supported import formats: WAV, FLAC, OGG (anything libsndfile supports).
Audio is converted to 32-bit float stereo at 44.1 kHz (the device's native format).
Mono files are automatically duplicated to stereo.

### Effects

```
eastlight fx-show ROLAND 1 ifx
eastlight fx-show ROLAND 1 tfx -g A
eastlight fx-show ROLAND 1 ifx -s AA

eastlight fx-set ROLAND 1 ifx AA feedback 30
eastlight fx-set ROLAND 1 ifx AA sw 1
eastlight fx-set ROLAND 1 ifx AA fx_type 35
```

70 effect types fully mapped: filters, modulation, delay, reverb, dynamics, pitch, vocoder, slicer, and 4 TFX-exclusive beat effects.

### Configuration

```
eastlight config --show
eastlight config --set-dir /media/user/RC505/ROLAND
eastlight config --no-backup
```

Configuration is stored in `~/.config/eastlight/config.yaml`.

## Safety

EastLight automatically backs up files before any write operation. Backups are timestamped and stored in `.eastlight_backup/` within your ROLAND/ directory. To disable:

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
    config.py      User config and device auto-detection
  schema/
    *.yaml         24 section schemas (track, master, assign, routing, ...)
    effects/       70 FX effect type schemas
    fx_types.yaml  FX type index enum (IFX 0-65, TFX 0-69)
  cli/
    main.py        Click-based CLI (13 commands)
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
