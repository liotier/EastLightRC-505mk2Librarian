"""Tests for backup, config, and device detection."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from eastlight.cli.main import cli
from eastlight.core.config import (
    Config,
    _is_roland_dir,
    detect_device,
    load_config,
    save_config,
)
from eastlight.core.library import RC505Library
from eastlight.core.parser import parse_memory_file


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# --- Backup tests ---


class TestAutoBackup:
    def test_save_memory_creates_backup(
        self, tmp_path: Path, sample_rc0_content: str
    ) -> None:
        root = tmp_path / "ROLAND"
        data = root / "DATA"
        wave = root / "WAVE"
        data.mkdir(parents=True)
        wave.mkdir(parents=True)
        rc0_path = data / "MEMORY001A.RC0"
        rc0_path.write_text(sample_rc0_content, encoding="utf-8")
        original_content = rc0_path.read_text()

        lib = RC505Library(root, backup=True)
        rc0 = lib.parse_memory(1)
        # Modify something so the save is meaningful
        rc0.mem["MASTER"]["A"] = 80
        lib.save_memory(1, rc0)

        # Backup directory should exist
        backup_dir = root / ".eastlight_backup"
        assert backup_dir.exists()

        # Should have exactly one timestamped subdirectory
        ts_dirs = list(backup_dir.iterdir())
        assert len(ts_dirs) == 1

        # Backup file should contain the original content
        backup_file = ts_dirs[0] / "DATA" / "MEMORY001A.RC0"
        assert backup_file.exists()
        assert backup_file.read_text() == original_content

    def test_backup_disabled(
        self, tmp_path: Path, sample_rc0_content: str
    ) -> None:
        root = tmp_path / "ROLAND"
        data = root / "DATA"
        wave = root / "WAVE"
        data.mkdir(parents=True)
        wave.mkdir(parents=True)
        (data / "MEMORY001A.RC0").write_text(sample_rc0_content, encoding="utf-8")

        lib = RC505Library(root, backup=False)
        rc0 = lib.parse_memory(1)
        lib.save_memory(1, rc0)

        # No backup directory should be created
        assert not (root / ".eastlight_backup").exists()

    def test_backup_skipped_for_new_file(
        self, tmp_path: Path, sample_rc0_content: str
    ) -> None:
        root = tmp_path / "ROLAND"
        data = root / "DATA"
        wave = root / "WAVE"
        data.mkdir(parents=True)
        wave.mkdir(parents=True)
        (data / "MEMORY001A.RC0").write_text(sample_rc0_content, encoding="utf-8")

        lib = RC505Library(root, backup=True)
        rc0 = lib.parse_memory(1)
        # Save to a new slot (050) — no existing file to backup
        for elem in rc0.elements:
            if elem.id is not None:
                elem.id = 49
        lib.save_memory(50, rc0)

        # Backup dir should not exist (nothing to back up)
        assert not (root / ".eastlight_backup").exists()


# --- Config tests ---


class TestConfig:
    def test_load_default_config(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.roland_dir is None
        assert cfg.backup is True
        assert cfg.recent == []

    def test_save_and_load_config(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        cfg = Config(
            roland_dir="/media/user/RC505/ROLAND",
            backup=False,
            recent=["/media/user/RC505/ROLAND", "/mnt/sd/ROLAND"],
        )
        save_config(cfg, path)

        loaded = load_config(path)
        assert loaded.roland_dir == "/media/user/RC505/ROLAND"
        assert loaded.backup is False
        assert len(loaded.recent) == 2

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "config.yaml"
        save_config(Config(), path)
        assert path.exists()

    def test_save_minimal_config(self, tmp_path: Path) -> None:
        path = tmp_path / "config.yaml"
        save_config(Config(), path)
        loaded = load_config(path)
        assert loaded.roland_dir is None
        assert loaded.backup is True


# --- Device detection tests ---


class TestDeviceDetection:
    def test_is_roland_dir(self, tmp_path: Path, sample_rc0_content: str) -> None:
        root = tmp_path / "ROLAND"
        data = root / "DATA"
        data.mkdir(parents=True)
        (data / "MEMORY001A.RC0").write_text(sample_rc0_content)
        assert _is_roland_dir(root)

    def test_is_not_roland_dir_missing_data(self, tmp_path: Path) -> None:
        root = tmp_path / "ROLAND"
        root.mkdir()
        assert not _is_roland_dir(root)

    def test_is_not_roland_dir_no_rc0(self, tmp_path: Path) -> None:
        root = tmp_path / "ROLAND"
        (root / "DATA").mkdir(parents=True)
        assert not _is_roland_dir(root)

    def test_detect_returns_empty_on_no_devices(self) -> None:
        # Just verify it doesn't crash; result depends on host system
        result = detect_device()
        assert isinstance(result, list)


# --- CLI config/detect command tests ---


class TestConfigCommand:
    def test_config_show(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["config", "--show"])
        assert result.exit_code == 0
        assert "Configuration" in result.output

    def test_config_set_dir(self, runner: CliRunner, tmp_path: Path) -> None:
        # Create a valid ROLAND dir
        root = tmp_path / "ROLAND"
        data = root / "DATA"
        data.mkdir(parents=True)

        result = runner.invoke(cli, ["config", "--set-dir", str(root)])
        assert result.exit_code == 0
        assert "Saved" in result.output


class TestDetectCommand:
    def test_detect_runs(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["detect"])
        assert result.exit_code == 0
        assert "Scanning" in result.output
