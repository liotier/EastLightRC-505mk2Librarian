"""Library manager for ROLAND/ backup directory operations.

Handles discovery and organization of RC0 files and WAV directories
within a Roland RC-505 MK2 backup directory structure.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .parser import RC0File, parse_memory_file, parse_system_file
from .writer import write_rc0

_BACKUP_BASE = Path.home() / ".config" / "eastlight" / "backups"


def backup_dir_for(roland_dir: Path) -> Path:
    """Compute backup directory for a given ROLAND directory.

    Backups are stored under ~/.config/eastlight/backups/<hash>/
    where <hash> is derived from the resolved ROLAND directory path.
    This keeps backups outside the device filesystem.
    """
    path_hash = hashlib.sha256(str(roland_dir.resolve()).encode()).hexdigest()[:12]
    return _BACKUP_BASE / path_hash


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

    @property
    def has_audio(self) -> bool:
        return len(self.wav_paths) > 0

    def track_wav(self, track: int) -> Path | None:
        """Get WAV path for a track (1-5), or None if no audio."""
        return self.wav_paths.get(track)


class RC505Library:
    """Manager for a ROLAND/ backup directory.

    Args:
        roland_dir: Path to the ROLAND/ directory.
        backup: If True, automatically create timestamped backups before
            any write operation. Backups are stored under
            ~/.config/eastlight/backups/ (outside the device filesystem).
            Default True.
        backup_dir: Override backup directory (for testing). If None,
            computed from the ROLAND directory path.
    """

    def __init__(
        self,
        roland_dir: str | Path,
        *,
        backup: bool = True,
        backup_dir: Path | None = None,
    ) -> None:
        self.root = Path(roland_dir)
        self.data_dir = self.root / "DATA"
        self.wave_dir = self.root / "WAVE"
        self._backup = backup
        self._backup_dir = backup_dir or backup_dir_for(self.root)

        if not self.data_dir.exists():
            raise FileNotFoundError(f"DATA directory not found: {self.data_dir}")

    def _backup_file(self, path: Path) -> Path | None:
        """Create a timestamped backup of a file before overwriting it.

        Returns the backup path, or None if backup is disabled or file doesn't exist.
        """
        if not self._backup or not path.exists():
            return None

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rel = path.relative_to(self.root)
        backup_path = self._backup_dir / ts / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        return backup_path

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
        """Parse a memory file."""
        if variant not in ("A", "B"):
            raise ValueError(f"Variant must be 'A' or 'B', got '{variant}'")
        path = self.data_dir / f"MEMORY{number:03d}{variant}.RC0"
        return parse_memory_file(path)

    def save_memory(self, number: int, rc0: RC0File, variant: str = "A") -> Path:
        """Write a memory RC0 file back to disk.

        Automatically backs up the existing file before overwriting.
        """
        if variant not in ("A", "B"):
            raise ValueError(f"Variant must be 'A' or 'B', got '{variant}'")
        path = self.data_dir / f"MEMORY{number:03d}{variant}.RC0"
        self._backup_file(path)
        write_rc0(rc0, path)
        return path

    def copy_memory(self, src: int, dst: int) -> None:
        """Copy a memory slot to another slot (RC0 data + WAV audio).

        Updates the element IDs in the copied RC0 to match the destination.
        """
        if not 1 <= src <= 99:
            raise ValueError(f"Source must be 1-99, got {src}")
        if not 1 <= dst <= 99:
            raise ValueError(f"Destination must be 1-99, got {dst}")

        dst_id = dst - 1  # element IDs are 0-indexed

        # Copy A variant
        src_rc0 = self.parse_memory(src)
        for element in src_rc0.elements:
            if element.id is not None:
                element.id = dst_id
        self.save_memory(dst, src_rc0)

        # Copy B variant if it exists
        src_b = self.data_dir / f"MEMORY{src:03d}B.RC0"
        if src_b.exists():
            src_b_rc0 = self.parse_memory(src, variant="B")
            for element in src_b_rc0.elements:
                if element.id is not None:
                    element.id = dst_id
            self.save_memory(dst, src_b_rc0, variant="B")

        # Copy WAV files
        for track in range(1, 6):
            src_wav = self.wave_dir / f"{src:03d}_{track}" / f"{src:03d}_{track}.WAV"
            if src_wav.exists():
                dst_wav_dir = self.wave_dir / f"{dst:03d}_{track}"
                dst_wav_dir.mkdir(parents=True, exist_ok=True)
                dst_wav = dst_wav_dir / f"{dst:03d}_{track}.WAV"
                self._backup_file(dst_wav)
                shutil.copy2(src_wav, dst_wav)

    def swap_memories(self, a: int, b: int) -> None:
        """Swap two memory slots (RC0 data + WAV audio)."""
        if not 1 <= a <= 99:
            raise ValueError(f"Memory A must be 1-99, got {a}")
        if not 1 <= b <= 99:
            raise ValueError(f"Memory B must be 1-99, got {b}")

        id_a, id_b = a - 1, b - 1

        # Parse both
        rc0_a = self.parse_memory(a)
        rc0_b = self.parse_memory(b)

        # Swap element IDs and write to opposite slots
        for element in rc0_a.elements:
            if element.id is not None:
                element.id = id_b
        for element in rc0_b.elements:
            if element.id is not None:
                element.id = id_a
        self.save_memory(b, rc0_a)
        self.save_memory(a, rc0_b)

        # Swap WAV files via temp directory
        tmp_dir = self.wave_dir / "__swap_tmp"
        try:
            for track in range(1, 6):
                wav_a = self.wave_dir / f"{a:03d}_{track}" / f"{a:03d}_{track}.WAV"
                wav_b = self.wave_dir / f"{b:03d}_{track}" / f"{b:03d}_{track}.WAV"
                a_exists = wav_a.exists()
                b_exists = wav_b.exists()

                # Backup before swap
                if a_exists:
                    self._backup_file(wav_a)
                if b_exists:
                    self._backup_file(wav_b)

                if not a_exists and not b_exists:
                    continue

                if a_exists:
                    tmp_track = tmp_dir / f"_{track}"
                    tmp_track.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(wav_a), str(tmp_track / "tmp.WAV"))

                if b_exists:
                    dst_dir_a = self.wave_dir / f"{a:03d}_{track}"
                    dst_dir_a.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(wav_b), str(dst_dir_a / f"{a:03d}_{track}.WAV"))

                if a_exists:
                    dst_dir_b = self.wave_dir / f"{b:03d}_{track}"
                    dst_dir_b.mkdir(parents=True, exist_ok=True)
                    shutil.move(
                        str(tmp_dir / f"_{track}" / "tmp.WAV"),
                        str(dst_dir_b / f"{b:03d}_{track}.WAV"),
                    )
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)

    def parse_system(self, variant: int = 1) -> RC0File:
        """Parse a system file."""
        if variant not in (1, 2):
            raise ValueError(f"System variant must be 1 or 2, got {variant}")
        path = self.data_dir / f"SYSTEM{variant}.RC0"
        return parse_system_file(path)

    def save_system(self, rc0: RC0File, variant: int = 1) -> Path:
        """Write a system RC0 file back to disk.

        Automatically backs up the existing file before overwriting.
        """
        if variant not in (1, 2):
            raise ValueError(f"System variant must be 1 or 2, got {variant}")
        path = self.data_dir / f"SYSTEM{variant}.RC0"
        self._backup_file(path)
        write_rc0(rc0, path)
        return path

    def clear_memory(self, number: int) -> None:
        """Clear a memory slot: back up then remove RC0 files and WAV audio.

        After clearing, the device will show the slot as empty.
        """
        if not 1 <= number <= 99:
            raise ValueError(f"Memory number must be 1-99, got {number}")

        prefix = f"MEMORY{number:03d}"

        # Backup and remove RC0 files
        for variant in ("A", "B"):
            path = self.data_dir / f"{prefix}{variant}.RC0"
            if path.exists():
                self._backup_file(path)
                path.unlink()

        # Backup and remove WAV files/directories
        for track in range(1, 6):
            wav_dir = self.wave_dir / f"{number:03d}_{track}"
            wav_file = wav_dir / f"{number:03d}_{track}.WAV"
            if wav_file.exists():
                self._backup_file(wav_file)
                wav_file.unlink()
            # Remove empty track dir
            if wav_dir.exists() and not any(wav_dir.iterdir()):
                wav_dir.rmdir()

    def list_backups(self) -> list[tuple[str, list[Path]]]:
        """List all backup snapshots as (timestamp, [relative_paths]).

        Returns a list sorted newest-first.
        """
        if not self._backup_dir.exists():
            return []

        result = []
        for ts_dir in sorted(self._backup_dir.iterdir(), reverse=True):
            if not ts_dir.is_dir():
                continue
            files = sorted(
                p.relative_to(ts_dir) for p in ts_dir.rglob("*") if p.is_file()
            )
            result.append((ts_dir.name, files))
        return result

    def restore_backup(self, timestamp: str) -> list[Path]:
        """Restore all files from a backup snapshot.

        Returns the list of restored file paths (relative to ROLAND/).
        """
        ts_dir = self._backup_dir / timestamp
        if not ts_dir.exists():
            raise FileNotFoundError(f"Backup '{timestamp}' not found")

        restored = []
        for backup_file in ts_dir.rglob("*"):
            if not backup_file.is_file():
                continue
            rel = backup_file.relative_to(ts_dir)
            dest = self.root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, dest)
            restored.append(rel)
        return restored

    def prune_backups(self, keep: int = 5) -> int:
        """Delete old backup snapshots, keeping the most recent N.

        Returns the number of snapshots deleted.
        """
        if not self._backup_dir.exists():
            return 0

        snapshots = sorted(
            (d for d in self._backup_dir.iterdir() if d.is_dir()),
            reverse=True,
        )
        to_delete = snapshots[keep:]
        for d in to_delete:
            shutil.rmtree(d)
        return len(to_delete)

    def memory_name(self, number: int) -> str:
        """Read the display name of a memory slot."""
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
