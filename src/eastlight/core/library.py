"""Library manager for ROLAND/ backup directory operations.

Handles discovery and organization of RC0 files and WAV directories
within a Roland RC-505 MK2 backup directory structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .parser import RC0File, parse_memory_file, parse_system_file


@dataclass
class MemorySlot:
    """A memory slot (1-99) with its A/B file paths and WAV track paths."""

    number: int  # 1-99
    a_path: Path | None  # MEMORY001A.RC0
    b_path: Path | None  # MEMORY001B.RC0
    wav_paths: dict[int, Path]  # track_num (1-5) → WAV file path

    @property
    def exists(self) -> bool:
        return self.a_path is not None and self.a_path.exists()

    @property
    def has_backup(self) -> bool:
        return self.b_path is not None and self.b_path.exists()

    def track_wav(self, track: int) -> Path | None:
        """Get WAV path for a track (1-5), or None if no audio."""
        return self.wav_paths.get(track)


class RC505Library:
    """Manager for a ROLAND/ backup directory."""

    def __init__(self, roland_dir: str | Path) -> None:
        """Initialize library from a ROLAND/ directory path.

        Args:
            roland_dir: Path to the ROLAND/ directory (containing DATA/ and WAVE/).
        """
        self.root = Path(roland_dir)
        self.data_dir = self.root / "DATA"
        self.wave_dir = self.root / "WAVE"

        if not self.data_dir.exists():
            raise FileNotFoundError(f"DATA directory not found: {self.data_dir}")

    def memory_slot(self, number: int) -> MemorySlot:
        """Get a memory slot by number (1-99)."""
        if not 1 <= number <= 99:
            raise ValueError(f"Memory number must be 1-99, got {number}")

        prefix = f"MEMORY{number:03d}"
        a_path = self.data_dir / f"{prefix}A.RC0"
        b_path = self.data_dir / f"{prefix}B.RC0"

        wav_paths = {}
        for track in range(1, 6):
            wav_dir = self.wave_dir / f"{number:03d}_{track}"
            wav_file = wav_dir / f"{number:03d}_{track}.WAV"
            if wav_file.exists():
                wav_paths[track] = wav_file

        return MemorySlot(
            number=number,
            a_path=a_path if a_path.exists() else None,
            b_path=b_path if b_path.exists() else None,
            wav_paths=wav_paths,
        )

    def list_memories(self) -> list[MemorySlot]:
        """List all 99 memory slots."""
        return [self.memory_slot(n) for n in range(1, 100)]

    def parse_memory(self, number: int, variant: str = "A") -> RC0File:
        """Parse a memory file.

        Args:
            number: Memory number (1-99).
            variant: "A" for live state, "B" for backup.

        Returns:
            Parsed RC0File.
        """
        if variant not in ("A", "B"):
            raise ValueError(f"Variant must be 'A' or 'B', got '{variant}'")
        path = self.data_dir / f"MEMORY{number:03d}{variant}.RC0"
        return parse_memory_file(path)

    def parse_system(self, variant: int = 1) -> RC0File:
        """Parse a system file.

        Args:
            variant: 1 for live state, 2 for backup.

        Returns:
            Parsed RC0File.
        """
        if variant not in (1, 2):
            raise ValueError(f"System variant must be 1 or 2, got {variant}")
        path = self.data_dir / f"SYSTEM{variant}.RC0"
        return parse_system_file(path)

    def memory_name(self, number: int) -> str:
        """Read the display name of a memory slot.

        Decodes the NAME section's A-L fields as ASCII character codes.
        """
        rc0 = self.parse_memory(number)
        mem = rc0.mem
        if mem is None or "NAME" not in mem:
            return ""

        name_section = mem["NAME"]
        chars = []
        for tag in "ABCDEFGHIJKL":
            code = name_section.get(tag, 32)  # 32 = space
            if code == 0:
                break
            chars.append(chr(code))

        return "".join(chars).rstrip()
