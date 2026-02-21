"""Tests for WAV file handling."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from eastlight.core.wav import (
    DEVICE_CHANNELS,
    DEVICE_SAMPLE_RATE,
    DEVICE_SUBTYPE,
    ExportFormat,
    import_audio,
    wav_export,
    wav_info,
    wav_overview,
    wav_read,
    wav_write_device,
)


@pytest.fixture
def device_wav(tmp_path: Path) -> Path:
    """Create a valid 32-bit float stereo WAV at 44.1kHz."""
    path = tmp_path / "test.WAV"
    frames = 44100  # 1 second
    data = np.random.default_rng(42).uniform(-0.5, 0.5, (frames, 2)).astype(np.float32)
    sf.write(str(path), data, DEVICE_SAMPLE_RATE, subtype=DEVICE_SUBTYPE)
    return path


@pytest.fixture
def mono_wav(tmp_path: Path) -> Path:
    """Create a mono 16-bit PCM WAV at 44.1kHz."""
    path = tmp_path / "mono.wav"
    frames = 22050  # 0.5 seconds
    data = np.random.default_rng(7).uniform(-0.5, 0.5, frames).astype(np.float32)
    sf.write(str(path), data, DEVICE_SAMPLE_RATE, subtype="PCM_16")
    return path


class TestWavInfo:
    def test_reads_metadata(self, device_wav: Path) -> None:
        info = wav_info(device_wav)
        assert info.sample_rate == DEVICE_SAMPLE_RATE
        assert info.channels == DEVICE_CHANNELS
        assert info.frames == 44100
        assert abs(info.duration - 1.0) < 0.01
        assert info.subtype == "FLOAT"
        assert info.format == "WAV"
        assert info.is_float32

    def test_mono_file(self, mono_wav: Path) -> None:
        info = wav_info(mono_wav)
        assert info.channels == 1
        assert not info.is_float32


class TestWavRead:
    def test_reads_float32(self, device_wav: Path) -> None:
        data, sr = wav_read(device_wav)
        assert sr == DEVICE_SAMPLE_RATE
        assert data.dtype == np.float32
        assert data.shape == (44100, 2)


class TestWavWriteDevice:
    def test_writes_native_format(self, tmp_path: Path) -> None:
        path = tmp_path / "output.WAV"
        data = np.zeros((1000, 2), dtype=np.float32)
        wav_write_device(path, data)

        info = wav_info(path)
        assert info.sample_rate == DEVICE_SAMPLE_RATE
        assert info.channels == 2
        assert info.subtype == "FLOAT"
        assert info.frames == 1000


class TestWavExport:
    def test_export_float32(self, tmp_path: Path) -> None:
        path = tmp_path / "export.wav"
        data = np.zeros((1000, 2), dtype=np.float32)
        wav_export(path, data, DEVICE_SAMPLE_RATE, ExportFormat.FLOAT_32)
        info = wav_info(path)
        assert info.subtype == "FLOAT"

    def test_export_pcm24(self, tmp_path: Path) -> None:
        path = tmp_path / "export.wav"
        data = np.zeros((1000, 2), dtype=np.float32)
        wav_export(path, data, DEVICE_SAMPLE_RATE, ExportFormat.PCM_24)
        info = wav_info(path)
        assert info.subtype == "PCM_24"

    def test_export_pcm16(self, tmp_path: Path) -> None:
        path = tmp_path / "export.wav"
        data = np.zeros((1000, 2), dtype=np.float32)
        wav_export(path, data, DEVICE_SAMPLE_RATE, ExportFormat.PCM_16)
        info = wav_info(path)
        assert info.subtype == "PCM_16"


class TestImportAudio:
    def test_import_stereo(self, device_wav: Path) -> None:
        data, sr = import_audio(device_wav)
        assert sr == DEVICE_SAMPLE_RATE
        assert data.dtype == np.float32
        assert data.shape[1] == 2

    def test_mono_to_stereo(self, mono_wav: Path) -> None:
        data, sr = import_audio(mono_wav)
        assert data.shape[1] == 2
        # Both channels should be identical (duplicated mono)
        np.testing.assert_array_equal(data[:, 0], data[:, 1])

    def test_multi_channel_truncated(self, tmp_path: Path) -> None:
        """Multi-channel (>2) input should be truncated to first 2 channels."""
        path = tmp_path / "multi.wav"
        data = np.zeros((1000, 4), dtype=np.float32)
        data[:, 2] = 0.5  # channel 3 has distinctive value
        sf.write(str(path), data, DEVICE_SAMPLE_RATE, subtype="FLOAT")

        imported, _ = import_audio(path)
        assert imported.shape[1] == 2
        # Channel 3 should be discarded
        assert imported[:, 0].max() == 0.0


class TestWavOverview:
    def test_overview_shape(self, device_wav: Path) -> None:
        overview = wav_overview(device_wav, num_points=100)
        assert overview.shape == (100, 2)
        assert overview.dtype == np.float32

    def test_overview_min_max(self, device_wav: Path) -> None:
        overview = wav_overview(device_wav, num_points=50)
        # Min should be <= 0 and max >= 0 for random audio
        assert overview[:, 0].min() < 0  # min column
        assert overview[:, 1].max() > 0  # max column


class TestRoundtrip:
    def test_read_write_roundtrip(self, device_wav: Path, tmp_path: Path) -> None:
        """Read a device WAV, write it back, verify identical."""
        data, sr = wav_read(device_wav)
        out_path = tmp_path / "roundtrip.WAV"
        wav_write_device(out_path, data, sr)

        data2, sr2 = wav_read(out_path)
        assert sr == sr2
        np.testing.assert_array_equal(data, data2)
