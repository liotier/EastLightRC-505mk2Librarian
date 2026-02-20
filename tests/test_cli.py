"""Tests for CLI commands."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from click.testing import CliRunner

from eastlight.cli.main import cli
from eastlight.core.parser import parse_memory_file
from eastlight.core.wav import DEVICE_SAMPLE_RATE, DEVICE_SUBTYPE
from eastlight.core.writer import write_rc0


@pytest.fixture
def roland_dir(tmp_path: Path, sample_rc0_content: str) -> Path:
    """Create a minimal ROLAND/ backup structure for CLI testing."""
    root = tmp_path / "ROLAND"
    data = root / "DATA"
    wave = root / "WAVE"
    data.mkdir(parents=True)
    wave.mkdir(parents=True)

    # Write memory 001 (A variant)
    (data / "MEMORY001A.RC0").write_text(sample_rc0_content, encoding="utf-8")

    # Write memory 002 with a different name
    content_002 = sample_rc0_content.replace(
        '<mem id="0">', '<mem id="1">'
    ).replace(
        '<ifx id="0">', '<ifx id="1">'
    ).replace(
        '<tfx id="0">', '<tfx id="1">'
    )
    # Change name chars to "Loop 2" (76, 111, 111, 112, 32, 50)
    content_002 = (
        content_002
        .replace("<A>77</A>\n<B>101</B>", "<A>76</A>\n<B>111</B>")
        .replace("<C>109</C>\n<D>111</D>", "<C>111</C>\n<D>112</D>")
        .replace("<E>114</E>\n<F>121</F>", "<E>32</E>\n<F>50</F>")
        .replace("<G>32</G>\n<H>49</H>", "<G>32</G>\n<H>32</H>")
    )
    (data / "MEMORY002A.RC0").write_text(content_002, encoding="utf-8")

    # Create a WAV file for memory 001 track 1
    wav_dir = wave / "001_1"
    wav_dir.mkdir()
    (wav_dir / "001_1.WAV").write_bytes(b"\x00" * 44)  # minimal placeholder

    return root


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestListCommand:
    def test_list_shows_memories(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["list", str(roland_dir)])
        assert result.exit_code == 0
        assert "Memory 1" in result.output
        assert "Loop 2" in result.output

    def test_list_nonexistent_dir(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["list", "/nonexistent/path"])
        assert result.exit_code != 0


class TestShowCommand:
    def test_show_memory(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["show", str(roland_dir), "1"])
        assert result.exit_code == 0
        assert "Memory 001" in result.output
        assert "Memory 1" in result.output

    def test_show_specific_section(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["show", str(roland_dir), "1", "-s", "TRACK1"])
        assert result.exit_code == 0
        assert "TRACK1" in result.output

    def test_show_raw_mode(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["show", str(roland_dir), "1", "--raw"])
        assert result.exit_code == 0


class TestParseCommand:
    def test_parse_file(self, runner: CliRunner, roland_dir: Path) -> None:
        rc0_path = roland_dir / "DATA" / "MEMORY001A.RC0"
        result = runner.invoke(cli, ["parse", str(rc0_path)])
        assert result.exit_code == 0
        assert "RC-505MK2" in result.output
        assert "mem" in result.output.lower()


class TestSetCommand:
    def test_set_by_name(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["set", str(roland_dir), "1", "TRACK1", "pan", "75"]
        )
        assert result.exit_code == 0
        assert "Set" in result.output
        assert "50" in result.output  # old value
        assert "75" in result.output  # new value

        # Verify the file was actually modified
        rc0 = parse_memory_file(roland_dir / "DATA" / "MEMORY001A.RC0")
        track1 = rc0.mem["TRACK1"]
        assert track1["C"] == 75  # C = pan tag

    def test_set_by_tag(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["set", str(roland_dir), "1", "TRACK1", "C", "60"]
        )
        assert result.exit_code == 0
        assert "Set" in result.output

        rc0 = parse_memory_file(roland_dir / "DATA" / "MEMORY001A.RC0")
        assert rc0.mem["TRACK1"]["C"] == 60

    def test_set_invalid_section(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["set", str(roland_dir), "1", "NONEXISTENT", "pan", "50"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_set_invalid_param(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["set", str(roland_dir), "1", "TRACK1", "zzz_fake", "50"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output


class TestNameCommand:
    def test_rename_memory(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["name", str(roland_dir), "1", "New Name"])
        assert result.exit_code == 0
        assert "Renamed" in result.output
        assert "Memory 1" in result.output  # old name
        assert "New Name" in result.output  # new name

        # Verify the file was actually modified
        rc0 = parse_memory_file(roland_dir / "DATA" / "MEMORY001A.RC0")
        name_section = rc0.mem["NAME"]
        chars = []
        for tag in "ABCDEFGHIJKL":
            code = name_section.get(tag)
            if code == 0:
                break
            chars.append(chr(code))
        assert "".join(chars).rstrip() == "New Name"

    def test_rename_truncates_long_name(
        self, runner: CliRunner, roland_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["name", str(roland_dir), "1", "This Is A Very Long Name"]
        )
        assert result.exit_code == 0
        assert "Renamed" in result.output


class TestCopyCommand:
    def test_copy_to_empty_slot(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["copy", str(roland_dir), "1", "50"])
        assert result.exit_code == 0
        assert "Copied" in result.output
        assert "001" in result.output
        assert "050" in result.output

        # Verify destination RC0 exists
        dst_path = roland_dir / "DATA" / "MEMORY050A.RC0"
        assert dst_path.exists()

        # Verify element ID was updated
        rc0 = parse_memory_file(dst_path)
        assert rc0.mem.id == 49  # 0-indexed: slot 50 → id 49

    def test_copy_preserves_audio(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["copy", str(roland_dir), "1", "50"])
        assert result.exit_code == 0

        # WAV should be copied
        dst_wav = roland_dir / "WAVE" / "050_1" / "050_1.WAV"
        assert dst_wav.exists()

    def test_copy_overwrite_prompts(self, runner: CliRunner, roland_dir: Path) -> None:
        # Copy to slot 2 which already exists — decline
        result = runner.invoke(cli, ["copy", str(roland_dir), "1", "2"], input="n\n")
        assert result.exit_code != 0 or "Aborted" in result.output

    def test_copy_overwrite_force(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["copy", str(roland_dir), "1", "2", "--force"]
        )
        assert result.exit_code == 0
        assert "Copied" in result.output

    def test_copy_nonexistent_source(
        self, runner: CliRunner, roland_dir: Path
    ) -> None:
        result = runner.invoke(cli, ["copy", str(roland_dir), "99", "50"])
        assert result.exit_code != 0
        assert "does not exist" in result.output


class TestSwapCommand:
    def test_swap_memories(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["swap", str(roland_dir), "1", "2"])
        assert result.exit_code == 0
        assert "Swapped" in result.output

        # Verify names were swapped
        rc0_1 = parse_memory_file(roland_dir / "DATA" / "MEMORY001A.RC0")
        rc0_2 = parse_memory_file(roland_dir / "DATA" / "MEMORY002A.RC0")

        # Memory 1 should now have Loop 2's name (L=76)
        assert rc0_1.mem["NAME"]["A"] == 76

        # Memory 2 should now have Memory 1's name (M=77)
        assert rc0_2.mem["NAME"]["A"] == 77

        # Element IDs should be updated
        assert rc0_1.mem.id == 0  # slot 1 → id 0
        assert rc0_2.mem.id == 1  # slot 2 → id 1

    def test_swap_preserves_audio(self, runner: CliRunner, roland_dir: Path) -> None:
        # Memory 1 has audio at 001_1, memory 2 has none
        result = runner.invoke(cli, ["swap", str(roland_dir), "1", "2"])
        assert result.exit_code == 0

        # Audio should move from 001_1 to 002_1
        assert (roland_dir / "WAVE" / "002_1" / "002_1.WAV").exists()

    def test_swap_nonexistent(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["swap", str(roland_dir), "1", "99"])
        assert result.exit_code != 0
        assert "does not exist" in result.output


class TestDiffCommand:
    def test_diff_identical(self, runner: CliRunner, roland_dir: Path) -> None:
        # Copy memory 1 to slot 3, then diff — should be identical (except IDs)
        runner.invoke(cli, ["copy", str(roland_dir), "1", "3"])
        result = runner.invoke(cli, ["diff", str(roland_dir), "1", "3"])
        assert result.exit_code == 0
        # NAME section will differ (same bytes since copy preserves name)
        # but other sections should be identical

    def test_diff_different(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["diff", str(roland_dir), "1", "2"])
        assert result.exit_code == 0
        assert "difference" in result.output.lower()

    def test_diff_section_filter(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["diff", str(roland_dir), "1", "2", "-s", "NAME"]
        )
        assert result.exit_code == 0

    def test_diff_shows_param_names(self, runner: CliRunner, roland_dir: Path) -> None:
        # Modify a known param in memory 1 then diff
        runner.invoke(cli, ["set", str(roland_dir), "1", "TRACK1", "pan", "75"])
        result = runner.invoke(cli, ["diff", str(roland_dir), "1", "2"])
        assert result.exit_code == 0
        # Should show difference in pan (tag C)


# --- WAV command helpers ---


def _make_device_wav(path: Path, frames: int = 44100) -> None:
    """Write a valid 32-bit float stereo WAV at 44.1kHz."""
    data = np.random.default_rng(42).uniform(-0.5, 0.5, (frames, 2)).astype(np.float32)
    sf.write(str(path), data, DEVICE_SAMPLE_RATE, subtype=DEVICE_SUBTYPE)


@pytest.fixture
def roland_dir_wav(tmp_path: Path, sample_rc0_content: str) -> Path:
    """ROLAND/ directory with a valid WAV file on memory 001 track 1."""
    root = tmp_path / "ROLAND"
    data = root / "DATA"
    wave = root / "WAVE"
    data.mkdir(parents=True)
    wave.mkdir(parents=True)

    (data / "MEMORY001A.RC0").write_text(sample_rc0_content, encoding="utf-8")

    # Second memory for multi-slot tests
    content_002 = sample_rc0_content.replace(
        '<mem id="0">', '<mem id="1">'
    ).replace(
        '<ifx id="0">', '<ifx id="1">'
    ).replace(
        '<tfx id="0">', '<tfx id="1">'
    )
    (data / "MEMORY002A.RC0").write_text(content_002, encoding="utf-8")

    # Valid WAV for track 1
    wav_dir = wave / "001_1"
    wav_dir.mkdir()
    _make_device_wav(wav_dir / "001_1.WAV", frames=44100)

    return root


# --- WAV CLI tests ---


class TestWavInfoCommand:
    def test_wav_info_shows_tracks(
        self, runner: CliRunner, roland_dir_wav: Path
    ) -> None:
        result = runner.invoke(cli, ["wav-info", str(roland_dir_wav), "1"])
        assert result.exit_code == 0
        assert "audio" in result.output
        assert "44100" in result.output

    def test_wav_info_specific_track(
        self, runner: CliRunner, roland_dir_wav: Path
    ) -> None:
        result = runner.invoke(
            cli, ["wav-info", str(roland_dir_wav), "1", "-t", "1"]
        )
        assert result.exit_code == 0
        assert "audio" in result.output

    def test_wav_info_empty_track(
        self, runner: CliRunner, roland_dir_wav: Path
    ) -> None:
        result = runner.invoke(
            cli, ["wav-info", str(roland_dir_wav), "1", "-t", "2"]
        )
        assert result.exit_code == 0
        assert "empty" in result.output

    def test_wav_info_nonexistent_memory(
        self, runner: CliRunner, roland_dir_wav: Path
    ) -> None:
        result = runner.invoke(cli, ["wav-info", str(roland_dir_wav), "99"])
        assert result.exit_code != 0
        assert "does not exist" in result.output


class TestWavExportCommand:
    def test_export_default_float32(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "export.wav"
        result = runner.invoke(
            cli, ["wav-export", str(roland_dir_wav), "1", "1", str(out)]
        )
        assert result.exit_code == 0
        assert "Exported" in result.output
        assert out.exists()

        from eastlight.core.wav import wav_info

        info = wav_info(out)
        assert info.subtype == "FLOAT"
        assert info.frames == 44100

    def test_export_pcm24(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "export24.wav"
        result = runner.invoke(
            cli,
            ["wav-export", str(roland_dir_wav), "1", "1", str(out), "--format", "pcm24"],
        )
        assert result.exit_code == 0

        from eastlight.core.wav import wav_info

        info = wav_info(out)
        assert info.subtype == "PCM_24"

    def test_export_pcm16(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "export16.wav"
        result = runner.invoke(
            cli,
            ["wav-export", str(roland_dir_wav), "1", "1", str(out), "--format", "pcm16"],
        )
        assert result.exit_code == 0

        from eastlight.core.wav import wav_info

        info = wav_info(out)
        assert info.subtype == "PCM_16"

    def test_export_empty_track(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "nope.wav"
        result = runner.invoke(
            cli, ["wav-export", str(roland_dir_wav), "1", "2", str(out)]
        )
        assert result.exit_code != 0
        assert "no audio" in result.output

    def test_export_nonexistent_memory(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "nope.wav"
        result = runner.invoke(
            cli, ["wav-export", str(roland_dir_wav), "99", "1", str(out)]
        )
        assert result.exit_code != 0


class TestWavImportCommand:
    def test_import_wav(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        # Create a source WAV to import
        src = tmp_path / "source.wav"
        data = np.zeros((22050, 2), dtype=np.float32)
        sf.write(str(src), data, DEVICE_SAMPLE_RATE, subtype="FLOAT")

        # Import into track 2 (empty)
        result = runner.invoke(
            cli, ["wav-import", str(roland_dir_wav), "1", "2", str(src)]
        )
        assert result.exit_code == 0
        assert "Imported" in result.output

        # Verify WAV was written to device location
        dst = roland_dir_wav / "WAVE" / "001_2" / "001_2.WAV"
        assert dst.exists()

        from eastlight.core.wav import wav_info

        info = wav_info(dst)
        assert info.subtype == "FLOAT"
        assert info.frames == 22050

    def test_import_mono_converts_to_stereo(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "mono.wav"
        data = np.zeros(11025, dtype=np.float32)
        sf.write(str(src), data, DEVICE_SAMPLE_RATE, subtype="PCM_16")

        result = runner.invoke(
            cli, ["wav-import", str(roland_dir_wav), "1", "3", str(src)]
        )
        assert result.exit_code == 0

        dst = roland_dir_wav / "WAVE" / "001_3" / "001_3.WAV"
        assert dst.exists()

        from eastlight.core.wav import wav_info

        info = wav_info(dst)
        assert info.channels == 2  # mono was converted to stereo

    def test_import_overwrite_prompts(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "source.wav"
        data = np.zeros((1000, 2), dtype=np.float32)
        sf.write(str(src), data, DEVICE_SAMPLE_RATE, subtype="FLOAT")

        # Track 1 already has audio — decline overwrite
        result = runner.invoke(
            cli, ["wav-import", str(roland_dir_wav), "1", "1", str(src)], input="n\n"
        )
        assert result.exit_code != 0 or "Aborted" in result.output

    def test_import_overwrite_force(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "source.wav"
        data = np.zeros((1000, 2), dtype=np.float32)
        sf.write(str(src), data, DEVICE_SAMPLE_RATE, subtype="FLOAT")

        result = runner.invoke(
            cli,
            ["wav-import", str(roland_dir_wav), "1", "1", str(src), "--force"],
        )
        assert result.exit_code == 0
        assert "Imported" in result.output

    def test_import_wrong_sample_rate(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "48k.wav"
        data = np.zeros((1000, 2), dtype=np.float32)
        sf.write(str(src), data, 48000, subtype="FLOAT")

        result = runner.invoke(
            cli, ["wav-import", str(roland_dir_wav), "1", "2", str(src)]
        )
        assert result.exit_code != 0
        assert "sample rate" in result.output.lower()

    def test_import_updates_rc0_metadata(
        self, runner: CliRunner, roland_dir_wav: Path, tmp_path: Path
    ) -> None:
        src = tmp_path / "source.wav"
        frames = 22050
        data = np.zeros((frames, 2), dtype=np.float32)
        sf.write(str(src), data, DEVICE_SAMPLE_RATE, subtype="FLOAT")

        result = runner.invoke(
            cli, ["wav-import", str(roland_dir_wav), "1", "2", str(src)]
        )
        assert result.exit_code == 0

        # Verify RC0 metadata was updated
        rc0 = parse_memory_file(roland_dir_wav / "DATA" / "MEMORY001A.RC0")
        track2 = rc0.mem["TRACK2"]
        assert track2["W"] == 1  # has_audio
        assert track2["X"] == frames  # total_samples
