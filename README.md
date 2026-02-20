# EastLight — RC-505 MK2 Librarian

Open-source editor and librarian for the **Roland RC-505 MK2** loop station.

## Overview

EastLight reads and writes the RC-505 MK2's `.RC0` file format — per-memory XML files with single-letter positional tags — and exposes a clean Python API, a CLI for scripting, and a PyQt6 GUI for musicians.

The format is fully decoded: track parameters, FX architecture, WAV layout, tempo/sample relationships, file naming conventions, and system structure are all understood and covered by YAML schemas.

## Features

- **Schema-driven parser** — YAML mapping tables define the positional tag → parameter name correspondence; the generic parser handles the rest
- **Byte-exact roundtrip** — read → write produces an identical file
- **CLI** (`eastlight`) for scripting and power users
- **PyQt6 GUI** for interactive patch management (in progress)
- **Audio import/export** — native 32-bit float WAV for lossless roundtrips

## Installation

```bash
pip install eastlight          # CLI + library
pip install eastlight[gui]     # add PyQt6 GUI
```

### From source

```bash
git clone https://github.com/liotier/EastLightRC-505mk2Librarian
cd EastLightRC-505mk2Librarian
pip install -e ".[dev]"
```

## Quick start

```bash
# Dump a memory file as JSON
eastlight dump MEMORY001A.RC0

# Copy patch 1 to slot 5 within the same file
eastlight copy MEMORY001A.RC0 --from 1 --to 5

# Export track 1 audio
eastlight export MEMORY001A.RC0 --track 1 --out loop.wav
```

## Project status

Pre-alpha — format reverse engineering is complete; CLI and GUI are under active development.

See [`rc505-mk2-feasibility.md`](rc505-mk2-feasibility.md) for the full format analysis.

## License

GNU General Public License v3.0 — see [`LICENSE`](LICENSE).
