"""WAV file handling for RC-505 MK2 32-bit IEEE Float audio files.

The RC-505 MK2 stores audio as 32-bit IEEE Float, stereo, 44.1kHz WAV.

Import: accepts WAV/FLAC/OGG (anything soundfile/libsndfile supports),
    converts to the device's required format.
Export: default is 24-bit PCM WAV for universal compatibility; native
    32-bit float and 16-bit PCM also available.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import soundfile as sf

# Device constants
DEVICE_SAMPLE_RATE = 44100
DEVICE_CHANNELS = 2
DEVICE_SUBTYPE = "FLOAT"  # 32-bit IEEE float


class ExportFormat(Enum):
    """Audio export format options."""

    PCM_24 = "PCM_24"  # 24-bit PCM WAV — universal compatibility (default)
    FLOAT_32 = "FLOAT"  # 32-bit float WAV — native device format
    PCM_16 = "PCM_16"  # 16-bit PCM WAV — maximum compatibility, smallest files


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


def wav_write_device(
    path: str | Path,
    data: np.ndarray,
    sample_rate: int = DEVICE_SAMPLE_RATE,
) -> None:
    """Write audio data in the RC-505 MK2's native format (32-bit float WAV).

    Used when importing audio into the device's ROLAND/WAVE/ directory.

    Args:
        path: Output path.
        data: Audio data as float32 numpy array, shape (frames, channels).
        sample_rate: Sample rate (default 44100).
    """
    sf.write(str(path), data, sample_rate, subtype=DEVICE_SUBTYPE)


def wav_export(
    path: str | Path,
    data: np.ndarray,
    sample_rate: int = DEVICE_SAMPLE_RATE,
    fmt: ExportFormat = ExportFormat.PCM_24,
) -> None:
    """Export audio data to WAV in the user's chosen format.

    Default is 24-bit PCM for universal compatibility (all DAWs including
    Logic Pro, all media players, all hardware). No quality loss for audio
    at or below 0 dBFS.

    Args:
        path: Output path.
        data: Audio data as numpy array.
        sample_rate: Sample rate.
        fmt: Export format (default: 24-bit PCM).
    """
    sf.write(str(path), data, sample_rate, subtype=fmt.value)


def import_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Import audio from any soundfile-supported format and prepare for device.

    Reads WAV, FLAC, OGG (and other libsndfile-supported formats),
    converts to float32, and ensures stereo. Does NOT resample — caller
    should check sample rate and resample if needed.

    Args:
        path: Path to the source audio file.

    Returns:
        Tuple of (data, sample_rate). Data is float32, shape (frames, 2).
    """
    data, sr = sf.read(str(path), dtype="float32")

    # Ensure stereo
    if data.ndim == 1:
        # Mono → duplicate to stereo
        data = np.column_stack([data, data])
    elif data.shape[1] > 2:
        # Multi-channel → take first two
        data = data[:, :2]

    return data, sr


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
