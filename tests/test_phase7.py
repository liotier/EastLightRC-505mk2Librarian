"""Tests for Phase 7: clear, backup management, batch operations, validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from eastlight.cli.main import cli, _parse_memory_range
from eastlight.core.library import RC505Library
from eastlight.core.parser import parse_memory_file


@pytest.fixture
def roland_dir(tmp_path: Path, sample_rc0_content: str) -> Path:
    """ROLAND/ directory with memories 1 and 2 plus WAV on track 1."""
    root = tmp_path / "ROLAND"
    data = root / "DATA"
    wave = root / "WAVE"
    data.mkdir(parents=True)
    wave.mkdir(parents=True)

    (data / "MEMORY001A.RC0").write_text(sample_rc0_content, encoding="utf-8")
    (data / "MEMORY001B.RC0").write_text(sample_rc0_content, encoding="utf-8")

    content_002 = sample_rc0_content.replace(
        '<mem id="0">', '<mem id="1">'
    ).replace(
        '<ifx id="0">', '<ifx id="1">'
    ).replace(
        '<tfx id="0">', '<tfx id="1">'
    )
    (data / "MEMORY002A.RC0").write_text(content_002, encoding="utf-8")

    wav_dir = wave / "001_1"
    wav_dir.mkdir()
    (wav_dir / "001_1.WAV").write_bytes(b"\x00" * 100)

    return root


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# --- Library: clear_memory ---


class TestClearMemory:
    def test_clear_removes_rc0(self, roland_dir: Path) -> None:
        lib = RC505Library(roland_dir, backup=False)
        lib.clear_memory(1)
        assert not (roland_dir / "DATA" / "MEMORY001A.RC0").exists()
        assert not (roland_dir / "DATA" / "MEMORY001B.RC0").exists()

    def test_clear_removes_wav(self, roland_dir: Path) -> None:
        lib = RC505Library(roland_dir, backup=False)
        lib.clear_memory(1)
        assert not (roland_dir / "WAVE" / "001_1" / "001_1.WAV").exists()

    def test_clear_removes_empty_wav_dir(self, roland_dir: Path) -> None:
        lib = RC505Library(roland_dir, backup=False)
        lib.clear_memory(1)
        assert not (roland_dir / "WAVE" / "001_1").exists()

    def test_clear_backs_up_first(self, roland_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        lib = RC505Library(roland_dir, backup=True, backup_dir=backup_dir)
        lib.clear_memory(1)
        assert backup_dir.exists()
        ts_dirs = list(backup_dir.iterdir())
        assert len(ts_dirs) >= 1
        # Should have backed up the RC0 files
        backup_files = list(ts_dirs[0].rglob("*.RC0"))
        assert len(backup_files) >= 1

    def test_clear_invalid_number(self, roland_dir: Path) -> None:
        lib = RC505Library(roland_dir, backup=False)
        with pytest.raises(ValueError, match="1-99"):
            lib.clear_memory(0)
        with pytest.raises(ValueError, match="1-99"):
            lib.clear_memory(100)

    def test_clear_nonexistent_slot_safe(self, roland_dir: Path) -> None:
        """Clearing a slot that has no files shouldn't error."""
        lib = RC505Library(roland_dir, backup=False)
        lib.clear_memory(50)  # no files for slot 50


# --- Library: backup management ---


class TestBackupManagement:
    def test_list_backups_empty(self, roland_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        lib = RC505Library(roland_dir, backup=True, backup_dir=backup_dir)
        assert lib.list_backups() == []

    def test_list_backups_after_save(self, roland_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        lib = RC505Library(roland_dir, backup=True, backup_dir=backup_dir)
        rc0 = lib.parse_memory(1)
        lib.save_memory(1, rc0)

        snapshots = lib.list_backups()
        assert len(snapshots) == 1
        ts, files = snapshots[0]
        assert len(files) >= 1

    def test_restore_backup(self, roland_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        lib = RC505Library(roland_dir, backup=True, backup_dir=backup_dir)

        # Read original
        original = (roland_dir / "DATA" / "MEMORY001A.RC0").read_text()

        # Modify and save (creates backup of original)
        rc0 = lib.parse_memory(1)
        rc0.mem["MASTER"]["A"] = 80
        lib.save_memory(1, rc0)

        # Verify modified
        assert (roland_dir / "DATA" / "MEMORY001A.RC0").read_text() != original

        # Restore from backup
        snapshots = lib.list_backups()
        ts = snapshots[0][0]
        restored = lib.restore_backup(ts)
        assert len(restored) >= 1

        # Should have original content back
        assert (roland_dir / "DATA" / "MEMORY001A.RC0").read_text() == original

    def test_restore_nonexistent(self, roland_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        lib = RC505Library(roland_dir, backup=True, backup_dir=backup_dir)
        with pytest.raises(FileNotFoundError, match="not found"):
            lib.restore_backup("20250101T000000Z")

    def test_prune_backups(self, roland_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        lib = RC505Library(roland_dir, backup=True, backup_dir=backup_dir)

        # Manually create multiple timestamp directories to simulate backups
        import shutil
        src_file = roland_dir / "DATA" / "MEMORY001A.RC0"
        for ts in ["20260101T000000Z", "20260102T000000Z", "20260103T000000Z"]:
            ts_dir = backup_dir / ts / "DATA"
            ts_dir.mkdir(parents=True)
            shutil.copy2(src_file, ts_dir / "MEMORY001A.RC0")

        snapshots = lib.list_backups()
        assert len(snapshots) == 3

        deleted = lib.prune_backups(keep=1)
        assert deleted == 2
        remaining = lib.list_backups()
        assert len(remaining) == 1

    def test_prune_nothing_to_delete(self, roland_dir: Path, tmp_path: Path) -> None:
        backup_dir = tmp_path / "backups"
        lib = RC505Library(roland_dir, backup=True, backup_dir=backup_dir)
        assert lib.prune_backups(keep=5) == 0


# --- CLI: clear command ---


class TestClearCommand:
    def test_clear_with_force(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["clear", "1", "-d", str(roland_dir), "--force"]
        )
        assert result.exit_code == 0
        assert "Cleared" in result.output
        assert not (roland_dir / "DATA" / "MEMORY001A.RC0").exists()

    def test_clear_prompts_without_force(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["clear", "1", "-d", str(roland_dir)], input="n\n"
        )
        assert result.exit_code != 0 or "Aborted" in result.output
        # File should still exist
        assert (roland_dir / "DATA" / "MEMORY001A.RC0").exists()

    def test_clear_confirm_yes(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["clear", "1", "-d", str(roland_dir)], input="y\n"
        )
        assert result.exit_code == 0
        assert "Cleared" in result.output

    def test_clear_nonexistent(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["clear", "99", "-d", str(roland_dir), "--force"]
        )
        assert result.exit_code != 0
        assert "does not exist" in result.output


# --- CLI: backup commands ---


class TestBackupCommands:
    def test_backup_list_empty(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(cli, ["backup", "list", "-d", str(roland_dir)])
        assert result.exit_code == 0
        assert "No backups" in result.output

    def test_backup_list_after_operations(
        self, runner: CliRunner, roland_dir: Path
    ) -> None:
        # Perform a write to trigger backup
        runner.invoke(
            cli, ["set", "1", "MASTER", "A", "80", "-d", str(roland_dir)]
        )
        result = runner.invoke(cli, ["backup", "list", "-d", str(roland_dir)])
        assert result.exit_code == 0
        # Should show at least one snapshot
        assert "snapshot" in result.output.lower() or "Snapshot" in result.output

    def test_backup_prune(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["backup", "prune", "-d", str(roland_dir), "--keep", "5"]
        )
        assert result.exit_code == 0

    def test_backup_restore_not_found(
        self, runner: CliRunner, roland_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["backup", "restore", "20250101T000000Z", "-d", str(roland_dir), "--force"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output


# --- CLI: template commands ---


class TestTemplateExport:
    def test_export_all_sections(
        self, runner: CliRunner, roland_dir: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "template.yaml"
        result = runner.invoke(
            cli, ["template-export", "1", str(out), "-d", str(roland_dir)]
        )
        assert result.exit_code == 0
        assert "Exported" in result.output
        assert out.exists()

        data = yaml.safe_load(out.read_text())
        assert "_sections" in data
        assert "TRACK1" in data["_sections"]

    def test_export_specific_sections(
        self, runner: CliRunner, roland_dir: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "partial.yaml"
        result = runner.invoke(
            cli,
            ["template-export", "1", str(out), "-d", str(roland_dir),
             "-s", "MASTER", "-s", "TRACK1"],
        )
        assert result.exit_code == 0
        data = yaml.safe_load(out.read_text())
        assert set(data["_sections"].keys()) == {"MASTER", "TRACK1"}


class TestTemplateApply:
    def test_apply_template_single(
        self, runner: CliRunner, roland_dir: Path, tmp_path: Path
    ) -> None:
        # Export from memory 1
        tmpl = tmp_path / "t.yaml"
        runner.invoke(
            cli, ["template-export", "1", str(tmpl), "-d", str(roland_dir)]
        )

        # Modify memory 2, then apply template from 1
        runner.invoke(
            cli, ["set", "2", "MASTER", "A", "80", "-d", str(roland_dir)]
        )
        result = runner.invoke(
            cli, ["template-apply", str(tmpl), "2", "-d", str(roland_dir)]
        )
        assert result.exit_code == 0
        assert "Applied" in result.output

        # Verify MASTER.A was restored from template
        rc0 = parse_memory_file(roland_dir / "DATA" / "MEMORY002A.RC0")
        assert rc0.mem["MASTER"]["A"] == 100  # original value from template

    def test_apply_template_range(
        self, runner: CliRunner, roland_dir: Path, tmp_path: Path
    ) -> None:
        tmpl = tmp_path / "t.yaml"
        runner.invoke(
            cli, ["template-export", "1", str(tmpl), "-d", str(roland_dir)]
        )
        result = runner.invoke(
            cli, ["template-apply", str(tmpl), "1-2", "-d", str(roland_dir)]
        )
        assert result.exit_code == 0
        assert "Applied" in result.output

    def test_apply_template_section_filter(
        self, runner: CliRunner, roland_dir: Path, tmp_path: Path
    ) -> None:
        tmpl = tmp_path / "t.yaml"
        runner.invoke(
            cli, ["template-export", "1", str(tmpl), "-d", str(roland_dir)]
        )
        result = runner.invoke(
            cli,
            ["template-apply", str(tmpl), "2", "-d", str(roland_dir), "-s", "MASTER"],
        )
        assert result.exit_code == 0
        assert "1 section" in result.output

    def test_apply_template_skips_missing(
        self, runner: CliRunner, roland_dir: Path, tmp_path: Path
    ) -> None:
        tmpl = tmp_path / "t.yaml"
        runner.invoke(
            cli, ["template-export", "1", str(tmpl), "-d", str(roland_dir)]
        )
        # Apply to range that includes non-existent slots
        result = runner.invoke(
            cli, ["template-apply", str(tmpl), "1,50,99", "-d", str(roland_dir)]
        )
        assert result.exit_code == 0
        assert "Warning" in result.output  # warns about missing slots


# --- CLI: bulk-set command ---


class TestBulkSet:
    def test_bulk_set_range(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["bulk-set", "1-2", "MASTER", "A", "80", "-d", str(roland_dir)]
        )
        assert result.exit_code == 0
        assert "Set" in result.output
        assert "2 memory slot" in result.output

        # Verify both were updated
        rc0_1 = parse_memory_file(roland_dir / "DATA" / "MEMORY001A.RC0")
        rc0_2 = parse_memory_file(roland_dir / "DATA" / "MEMORY002A.RC0")
        assert rc0_1.mem["MASTER"]["A"] == 80
        assert rc0_2.mem["MASTER"]["A"] == 80

    def test_bulk_set_comma_list(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["bulk-set", "1,2", "MASTER", "A", "90", "-d", str(roland_dir)]
        )
        assert result.exit_code == 0
        assert "2 memory slot" in result.output

    def test_bulk_set_skips_empty(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["bulk-set", "1,50", "MASTER", "A", "70", "-d", str(roland_dir)]
        )
        assert result.exit_code == 0
        assert "1 memory slot" in result.output


# --- Validation warnings ---


class TestValidationWarnings:
    def test_set_warns_out_of_range(
        self, runner: CliRunner, roland_dir: Path
    ) -> None:
        # pan has range [0, 100] in track schema
        result = runner.invoke(
            cli, ["set", "1", "TRACK1", "pan", "999", "-d", str(roland_dir)]
        )
        # set_by_name raises ValueError for out-of-range
        assert result.exit_code != 0 or "Warning" in result.output

    def test_set_warns_invalid_choice(
        self, runner: CliRunner, roland_dir: Path
    ) -> None:
        # reverse (tag A) is enum with choices {0: OFF, 1: ON}
        result = runner.invoke(
            cli, ["set", "1", "TRACK1", "reverse", "5", "-d", str(roland_dir)]
        )
        # Either warning or error depending on validation path
        assert "Warning" in result.output or result.exit_code != 0


# --- _parse_memory_range ---


class TestParseMemoryRange:
    def test_single(self) -> None:
        assert _parse_memory_range("5") == [5]

    def test_range(self) -> None:
        assert _parse_memory_range("1-5") == [1, 2, 3, 4, 5]

    def test_comma_list(self) -> None:
        assert _parse_memory_range("1,3,5") == [1, 3, 5]

    def test_mixed(self) -> None:
        assert _parse_memory_range("1-3,7,10-12") == [1, 2, 3, 7, 10, 11, 12]

    def test_dedup(self) -> None:
        assert _parse_memory_range("1-3,2-4") == [1, 2, 3, 4]

    def test_invalid_range(self) -> None:
        with pytest.raises(Exception):
            _parse_memory_range("0")

    def test_invalid_high(self) -> None:
        with pytest.raises(Exception):
            _parse_memory_range("100")
