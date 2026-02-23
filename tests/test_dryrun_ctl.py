"""Tests for dry-run mode, controller CLI, and PyPI packaging."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from eastlight.cli.main import cli
from eastlight.core.parser import parse_memory_file


# Minimal system RC0 with SETUP + ICTL + ECTL sections
_SYS_WITH_CTL = '''\
<?xml version="1.0" encoding="utf-8"?>
<database name="RC-505MK2" revision="0">
<sys>
<SETUP>
<A>0</A>
<B>0</B>
<C>98</C>
<D>6</D>
<E>0</E>
<F>2</F>
<G>0</G>
<H>2</H>
<I>0</I>
<J>0</J>
<K>0</K>
<L>0</L>
<M>0</M>
<N>0</N>
<O>0</O>
<P>0</P>
<Q>0</Q>
<R>0</R>
<S>0</S>
<T>0</T>
<U>0</U>
<V>1</V>
</SETUP>
<ICTL1_TRACK1_FX>
<A>42</A>
<B>0</B>
<C>1</C>
</ICTL1_TRACK1_FX>
<ICTL1_PEDAL1>
<A>10</A>
<B>5</B>
<C>0</C>
</ICTL1_PEDAL1>
<ECTL_CTL1>
<A>20</A>
<B>0</B>
<C>0</C>
<D>127</D>
</ECTL_CTL1>
<ECTL_EXP1>
<A>30</A>
<B>0</B>
<C>0</C>
<D>64</D>
</ECTL_EXP1>
</sys>
</database>
<count>0001</count>
'''


@pytest.fixture
def roland_dir(tmp_path: Path, sample_rc0_content: str) -> Path:
    """ROLAND/ with memories 1-2 for dry-run tests."""
    root = tmp_path / "ROLAND"
    data = root / "DATA"
    wave = root / "WAVE"
    data.mkdir(parents=True)
    wave.mkdir(parents=True)
    (data / "MEMORY001A.RC0").write_text(sample_rc0_content, encoding="utf-8")

    content_002 = sample_rc0_content.replace(
        '<mem id="0">', '<mem id="1">'
    ).replace(
        '<ifx id="0">', '<ifx id="1">'
    ).replace(
        '<tfx id="0">', '<tfx id="1">'
    )
    (data / "MEMORY002A.RC0").write_text(content_002, encoding="utf-8")
    return root


@pytest.fixture
def ctl_roland_dir(tmp_path: Path, sample_rc0_content: str) -> Path:
    """ROLAND/ with system file containing ICTL/ECTL sections."""
    root = tmp_path / "ROLAND"
    data = root / "DATA"
    wave = root / "WAVE"
    data.mkdir(parents=True)
    wave.mkdir(parents=True)
    (data / "SYSTEM1.RC0").write_text(_SYS_WITH_CTL, encoding="utf-8")
    (data / "MEMORY001A.RC0").write_text(sample_rc0_content, encoding="utf-8")
    return root


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# --- Dry-run: set ---


class TestDryRunSet:
    def test_set_dry_run_no_write(self, runner: CliRunner, roland_dir: Path) -> None:
        original = (roland_dir / "DATA" / "MEMORY001A.RC0").read_text()
        result = runner.invoke(
            cli, ["set", "1", "MASTER", "A", "80", "-d", str(roland_dir), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "(dry-run)" in result.output
        assert "80" in result.output
        # File should be unchanged
        assert (roland_dir / "DATA" / "MEMORY001A.RC0").read_text() == original

    def test_set_dry_run_short_flag(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["set", "1", "MASTER", "A", "80", "-d", str(roland_dir), "-n"]
        )
        assert result.exit_code == 0
        assert "(dry-run)" in result.output


# --- Dry-run: clear ---


class TestDryRunClear:
    def test_clear_dry_run_no_delete(self, runner: CliRunner, roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["clear", "1", "-d", str(roland_dir), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "(dry-run)" in result.output
        assert "delete" in result.output
        # File should still exist
        assert (roland_dir / "DATA" / "MEMORY001A.RC0").exists()


# --- Dry-run: sys-set ---


class TestDryRunSysSet:
    def test_sys_set_dry_run(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["sys-set", "SETUP", "D", "10", "-d", str(ctl_roland_dir), "--dry-run"],
        )
        assert result.exit_code == 0
        assert "(dry-run)" in result.output
        assert "6" in result.output  # old value
        assert "10" in result.output  # new value


# --- Dry-run: bulk-set ---


class TestDryRunBulkSet:
    def test_bulk_set_dry_run(self, runner: CliRunner, roland_dir: Path) -> None:
        original_1 = (roland_dir / "DATA" / "MEMORY001A.RC0").read_text()
        original_2 = (roland_dir / "DATA" / "MEMORY002A.RC0").read_text()

        result = runner.invoke(
            cli, ["bulk-set", "1-2", "MASTER", "A", "80", "-d", str(roland_dir), "-n"]
        )
        assert result.exit_code == 0
        assert "(dry-run)" in result.output
        assert "2 memory slot" in result.output

        # Files unchanged
        assert (roland_dir / "DATA" / "MEMORY001A.RC0").read_text() == original_1
        assert (roland_dir / "DATA" / "MEMORY002A.RC0").read_text() == original_2


# --- Dry-run: template-apply ---


class TestDryRunTemplateApply:
    def test_template_apply_dry_run(
        self, runner: CliRunner, roland_dir: Path, tmp_path: Path
    ) -> None:
        # Export template
        tmpl = tmp_path / "t.yaml"
        runner.invoke(
            cli, ["template-export", "1", str(tmpl), "-d", str(roland_dir)]
        )

        # Modify memory 2
        runner.invoke(
            cli, ["set", "2", "MASTER", "A", "80", "-d", str(roland_dir)]
        )
        modified = (roland_dir / "DATA" / "MEMORY002A.RC0").read_text()

        # Apply with dry-run — should NOT write
        result = runner.invoke(
            cli, ["template-apply", str(tmpl), "2", "-d", str(roland_dir), "-n"]
        )
        assert result.exit_code == 0
        assert "(dry-run)" in result.output

        # File should be unchanged from the modified version
        assert (roland_dir / "DATA" / "MEMORY002A.RC0").read_text() == modified


# --- ctl-show ---


class TestCtlShow:
    def test_ctl_show_all(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["ctl-show", "-d", str(ctl_roland_dir)]
        )
        assert result.exit_code == 0
        assert "Internal Controllers" in result.output
        assert "External Controllers" in result.output
        assert "ICTL1_TRACK1_FX" in result.output
        assert "ECTL_CTL1" in result.output

    def test_ctl_show_ictl_only(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["ctl-show", "-d", str(ctl_roland_dir), "--type", "ictl"]
        )
        assert result.exit_code == 0
        assert "Internal Controllers" in result.output
        assert "ICTL1_TRACK1_FX" in result.output
        assert "External Controllers" not in result.output

    def test_ctl_show_ectl_only(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["ctl-show", "-d", str(ctl_roland_dir), "--type", "ectl"]
        )
        assert result.exit_code == 0
        assert "External Controllers" in result.output
        assert "ECTL_CTL1" in result.output
        assert "Internal Controllers" not in result.output

    def test_ctl_show_raw(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["ctl-show", "-d", str(ctl_roland_dir), "--raw"]
        )
        assert result.exit_code == 0


# --- ctl-set ---


class TestCtlSet:
    def test_ctl_set_ictl_by_name(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["ctl-set", "ICTL1_TRACK1_FX", "ctl_func", "99", "-d", str(ctl_roland_dir)],
        )
        assert result.exit_code == 0
        assert "Set" in result.output
        assert "42" in result.output  # old
        assert "99" in result.output  # new

    def test_ctl_set_ictl_by_tag(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["ctl-set", "ICTL1_PEDAL1", "A", "55", "-d", str(ctl_roland_dir)],
        )
        assert result.exit_code == 0
        assert "55" in result.output

    def test_ctl_set_ectl(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["ctl-set", "ECTL_CTL1", "ctl_func", "15", "-d", str(ctl_roland_dir)],
        )
        assert result.exit_code == 0
        assert "15" in result.output

    def test_ctl_set_ectl_range(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["ctl-set", "ECTL_EXP1", "ctl_range", "100", "-d", str(ctl_roland_dir)],
        )
        assert result.exit_code == 0
        assert "100" in result.output

    def test_ctl_set_dry_run(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["ctl-set", "ECTL_CTL1", "ctl_func", "50", "-d", str(ctl_roland_dir), "-n"],
        )
        assert result.exit_code == 0
        assert "(dry-run)" in result.output

    def test_ctl_set_invalid_section(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["ctl-set", "NONEXISTENT", "A", "0", "-d", str(ctl_roland_dir)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_ctl_set_invalid_param(self, runner: CliRunner, ctl_roland_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["ctl-set", "ECTL_CTL1", "nonexistent", "0", "-d", str(ctl_roland_dir)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output


# --- PyPI packaging ---


class TestPackaging:
    def test_entry_point_available(self) -> None:
        """Verify the eastlight CLI entry point is registered."""
        import importlib.metadata
        eps = importlib.metadata.entry_points()
        console_scripts = eps.select(group="console_scripts")
        names = [ep.name for ep in console_scripts]
        assert "eastlight" in names

    def test_version_is_set(self) -> None:
        import importlib.metadata
        version = importlib.metadata.version("eastlight")
        assert version == "0.1.0"

    def test_schema_files_included(self) -> None:
        """Schema YAML files should be included in the package."""
        from eastlight.core.schema import SchemaRegistry
        registry = SchemaRegistry()
        registry.load_all()
        # Verify at least the key schemas exist
        assert registry.get("TRACK") is not None
        assert registry.get("MASTER") is not None
        assert registry.get("ICTL") is not None
        assert registry.get("ECTL") is not None
