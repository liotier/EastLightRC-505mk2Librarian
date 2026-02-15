"""WAV file handling for RC-505 MK2 32-bit IEEE Float audio files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass
class WavInfo:
    """Metadata for a WAV file."""

    path: Path
    sample_rate: int  # Always 44100 for RC-505 MK2
    channels: int  # Always 2 (stereo)
    frames: int  # Total sample frames
    duration: float  # Duration in seconds
    subtype: str  # e.g., "FLOAT" for 32-bit IEEE float
    format: str  # e.g., "WAV"

    @property
    def is_float32(self) -> bool:
        return self.subtype == "FLOAT"


def wav_info(path: str | Path) -> WavInfo:
    """Read WAV file metadata without loading audio data.

    Args:
        path: Path to the WAV file.

    Returns:
        WavInfo with file metadata.
    """
    path = Path(path)
    info = sf.info(str(path))
    return WavInfo(
        path=path,
        sample_rate=info.samplerate,
        channels=info.channels,
        frames=info.frames,
        duration=info.duration,
        subtype=info.subtype,
        format=info.format,
    )


def wav_read(path: str | Path) -> tuple[np.ndarray, int]:
    """Read a WAV file and return audio data as float32 numpy array.

    Args:
        path: Path to the WAV file.

    Returns:
        Tuple of (data, sample_rate). Data shape is (frames, channels).
    """
    data, sr = sf.read(str(path), dtype="float32")
    return data, sr


def wav_write(
    path: str | Path,
    data: np.ndarray,
    sample_rate: int = 44100,
) -> None:
    """Write audio data to a 32-bit float WAV file.

    Args:
        path: Output path.
        data: Audio data as float32 numpy array, shape (frames, channels).
        sample_rate: Sample rate (default 44100).
    """
    sf.write(str(path), data, sample_rate, subtype="FLOAT")


def wav_overview(path: str | Path, num_points: int = 1000) -> np.ndarray:
    """Generate a waveform overview by downsampling.

    Reads the file in chunks and computes min/max per segment for
    efficient waveform display.

    Args:
        path: Path to the WAV file.
        num_points: Number of overview points (default 1000).

    Returns:
        Array of shape (num_points, 2) with [min, max] per segment,
        computed from the first channel (or mono mix if mono).
    """
    info = sf.info(str(path))
    frames_per_point = max(1, info.frames // num_points)
    overview = np.zeros((num_points, 2), dtype=np.float32)

    with sf.SoundFile(str(path)) as f:
        for i in range(num_points):
            chunk = f.read(frames_per_point, dtype="float32")
            if len(chunk) == 0:
                break
            # Use first channel for overview
            if chunk.ndim > 1:
                mono = chunk[:, 0]
            else:
                mono = chunk
            overview[i, 0] = mono.min()
            overview[i, 1] = mono.max()

    return overview
