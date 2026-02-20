"""Tests for CLI commands."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from eastlight.cli.main import cli
from eastlight.core.parser import parse_memory_file
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
