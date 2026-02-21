"""Configuration and device auto-detection for EastLight.

Handles loading/saving user preferences from ~/.config/eastlight/config.yaml
and scanning mounted volumes for ROLAND/ directory structures.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_CONFIG_DIR = Path.home() / ".config" / "eastlight"
_CONFIG_FILE = _CONFIG_DIR / "config.yaml"


@dataclass
class Config:
    """User configuration."""

    roland_dir: str | None = None  # Default ROLAND/ path
    backup: bool = True  # Auto-backup before writes
    recent: list[str] = field(default_factory=list)  # Recently used ROLAND/ paths


def load_config(path: Path | None = None) -> Config:
    """Load config from YAML file, or return defaults if not found."""
    path = path or _CONFIG_FILE
    if not path.exists():
        return Config()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return Config(
        roland_dir=raw.get("roland_dir"),
        backup=raw.get("backup", True),
        recent=raw.get("recent", []),
    )


def save_config(config: Config, path: Path | None = None) -> Path:
    """Save config to YAML file."""
    path = path or _CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "backup": config.backup,
    }
    if config.roland_dir:
        data["roland_dir"] = config.roland_dir
    if config.recent:
        data["recent"] = config.recent

    with open(path, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)

    return path


def resolve_roland_dir(
    explicit: str | None = None, config_path: Path | None = None
) -> Path:
    """Resolve ROLAND/ directory from explicit path, config, or auto-detection.

    Resolution order:
      1. Explicit path (CLI argument or option)
      2. Config ``roland_dir`` setting
      3. Single auto-detected device

    Raises:
        ValueError: If no directory can be resolved, or multiple devices
            are detected without a configured default.
    """
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise ValueError(f"Directory not found: {path}")
        return path

    cfg = load_config(config_path)
    if cfg.roland_dir:
        path = Path(cfg.roland_dir)
        if path.exists():
            return path

    devices = detect_device()
    if len(devices) == 1:
        return devices[0]
    elif len(devices) > 1:
        lines = [f"  {i}. {p}" for i, p in enumerate(devices, 1)]
        raise ValueError(
            "Multiple RC-505 MK2 devices found:\n"
            + "\n".join(lines)
            + "\n\nSet a default: eastlight config --set-dir <path>"
        )

    raise ValueError(
        "No ROLAND/ directory found. Provide one with -d/--dir, "
        "or set a default: eastlight config --set-dir <path>"
    )


def _is_roland_dir(path: Path) -> bool:
    """Check if a path looks like a valid RC-505 MK2 ROLAND/ directory."""
    return (
        path.is_dir()
        and (path / "DATA").is_dir()
        and any((path / "DATA").glob("MEMORY*A.RC0"))
    )


def detect_device() -> list[Path]:
    """Scan common mount points for connected RC-505 MK2 devices.

    Returns a list of paths to ROLAND/ directories found on mounted volumes.
    """
    candidates: list[Path] = []
    system = platform.system()

    if system == "Linux":
        # Standard mount points for removable media
        for base in [Path("/media"), Path("/mnt"), Path("/run/media")]:
            if base.exists():
                # /media/USER/VOLUME/ROLAND or /media/VOLUME/ROLAND
                for child in _safe_iterdir(base):
                    if child.is_dir():
                        _scan_for_roland(child, candidates, depth=2)

    elif system == "Darwin":
        volumes = Path("/Volumes")
        if volumes.exists():
            for child in _safe_iterdir(volumes):
                _scan_for_roland(child, candidates, depth=1)

    elif system == "Windows":
        # Scan drive letters D: through Z:
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:\\")
            if drive.exists():
                _scan_for_roland(drive, candidates, depth=1)

    return candidates


def _safe_iterdir(path: Path) -> list[Path]:
    """List directory contents, returning empty list on permission errors."""
    try:
        return list(path.iterdir())
    except PermissionError:
        return []


def _scan_for_roland(base: Path, results: list[Path], depth: int) -> None:
    """Recursively scan for ROLAND/ directories up to a given depth."""
    roland = base / "ROLAND"
    if _is_roland_dir(roland):
        results.append(roland)
        return

    if depth > 0:
        for child in _safe_iterdir(base):
            if child.is_dir() and not child.name.startswith("."):
                _scan_for_roland(child, results, depth - 1)
