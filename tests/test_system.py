"""Tests for system settings: sys-show, sys-set, save_system."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from eastlight.cli.main import cli
from eastlight.core.library import RC505Library
from eastlight.core.parser import parse_system_file
from eastlight.core.schema import SchemaRegistry


# Minimal system RC0 with SETUP, PREF, COLOR, USB, MIDI sections
_SYS_RC0 = '''\
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
<PREF>
<A>1</A>
<B>1</B>
<C>1</C>
<D>1</D>
<E>1</E>
<F>1</F>
<G>1</G>
<H>1</H>
<I>1</I>
<J>1</J>
<K>1</K>
<L>1</L>
<M>1</M>
<N>1</N>
<O>1</O>
<P>1</P>
<Q>1</Q>
<R>1</R>
<S>1</S>
<T>1</T>
</PREF>
<COLOR>
<A>0</A>
<B>0</B>
<C>0</C>
<D>0</D>
<E>0</E>
</COLOR>
<USB>
<A>0</A>
<B>0</B>
<C>0</C>
<D>0</D>
<E>0</E>
</USB>
<MIDI>
<A>0</A>
<B>0</B>
<C>0</C>
<D>1</D>
<E>0</E>
<F>0</F>
<G>0</G>
<H>0</H>
<I>0</I>
<J>0</J>
</MIDI>
</sys>
</database>
<count>0001</count>
'''


@pytest.fixture
def sys_roland_dir(tmp_path: Path) -> Path:
    """ROLAND/ directory with SYSTEM1.RC0."""
    root = tmp_path / "ROLAND"
    data = root / "DATA"
    wave = root / "WAVE"
    data.mkdir(parents=True)
    wave.mkdir(parents=True)
    (data / "SYSTEM1.RC0").write_text(_SYS_RC0, encoding="utf-8")
    return root


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# --- Library tests ---


class TestSaveSystem:
    def test_save_system_roundtrip(self, sys_roland_dir: Path) -> None:
        lib = RC505Library(sys_roland_dir, backup=False)
        rc0 = lib.parse_system(1)
        setup = rc0.sys["SETUP"]
        assert setup["D"] == 6  # contrast

        setup["D"] = 8
        lib.save_system(rc0, 1)

        rc0_back = lib.parse_system(1)
        assert rc0_back.sys["SETUP"]["D"] == 8

    def test_save_system_creates_backup(self, tmp_path: Path) -> None:
        root = tmp_path / "ROLAND"
        data = root / "DATA"
        wave = root / "WAVE"
        data.mkdir(parents=True)
        wave.mkdir(parents=True)
        (data / "SYSTEM1.RC0").write_text(_SYS_RC0, encoding="utf-8")
        original = (data / "SYSTEM1.RC0").read_text()

        backup_dir = tmp_path / "backups"
        lib = RC505Library(root, backup=True, backup_dir=backup_dir)
        rc0 = lib.parse_system(1)
        rc0.sys["SETUP"]["D"] = 10
        lib.save_system(rc0, 1)

        assert backup_dir.exists()
        ts_dirs = list(backup_dir.iterdir())
        assert len(ts_dirs) == 1
        backup_file = ts_dirs[0] / "DATA" / "SYSTEM1.RC0"
        assert backup_file.exists()
        assert backup_file.read_text() == original

    def test_save_system_invalid_variant(self, sys_roland_dir: Path) -> None:
        lib = RC505Library(sys_roland_dir, backup=False)
        rc0 = lib.parse_system(1)
        with pytest.raises(ValueError, match="1 or 2"):
            lib.save_system(rc0, 3)


# --- Schema tests ---


class TestPrefSchemaComplete:
    def test_pref_has_20_fields(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        schema = r.get("PREF")
        assert schema is not None
        assert len(schema.fields) == 20

    def test_pref_known_fields(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        schema = r.get("PREF")
        assert schema.name_to_tag("pref_main") == "A"
        assert schema.name_to_tag("pref_track") == "N"

    def test_system_sections_all_covered(self) -> None:
        """All sections in our fixture should have schemas."""
        r = SchemaRegistry()
        r.load_all()
        for sec in ["SETUP", "PREF", "COLOR", "USB", "MIDI"]:
            assert r.get(sec) is not None, f"Missing schema for {sec}"


# --- CLI tests ---


class TestSysShowCommand:
    def test_sys_show_default(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(cli, ["sys-show", "-d", str(sys_roland_dir)])
        assert result.exit_code == 0
        assert "System Settings" in result.output
        assert "SETUP" in result.output
        assert "PREF" in result.output

    def test_sys_show_section(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-show", "-d", str(sys_roland_dir), "-s", "SETUP"]
        )
        assert result.exit_code == 0
        assert "SETUP" in result.output
        # Should show resolved parameter names
        assert "Contrast" in result.output or "contrast" in result.output.lower()

    def test_sys_show_pref_resolves(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-show", "-d", str(sys_roland_dir), "-s", "PREF"]
        )
        assert result.exit_code == 0
        assert "MEMORY" in result.output  # All prefs are set to 1 = MEMORY

    def test_sys_show_raw(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-show", "-d", str(sys_roland_dir), "-s", "SETUP", "--raw"]
        )
        assert result.exit_code == 0
        # Raw mode should show tag letters, not resolved names
        # "D" tag should appear as parameter name
        assert result.output.count("D") >= 1

    def test_sys_show_all(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-show", "-d", str(sys_roland_dir), "--all"]
        )
        assert result.exit_code == 0
        assert "MIDI" in result.output
        assert "USB" in result.output
        assert "COLOR" in result.output

    def test_sys_show_invalid_section(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-show", "-d", str(sys_roland_dir), "-s", "NONEXISTENT"]
        )
        assert result.exit_code == 0  # No error, just no output for that section


class TestSysSetCommand:
    def test_sys_set_by_name(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-set", "SETUP", "contrast", "8", "-d", str(sys_roland_dir)]
        )
        assert result.exit_code == 0
        assert "Set" in result.output
        assert "6" in result.output  # old value
        assert "8" in result.output  # new value

        # Verify written
        rc0 = parse_system_file(sys_roland_dir / "DATA" / "SYSTEM1.RC0")
        assert rc0.sys["SETUP"]["D"] == 8

    def test_sys_set_by_tag(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-set", "SETUP", "D", "9", "-d", str(sys_roland_dir)]
        )
        assert result.exit_code == 0
        assert "Set" in result.output

        rc0 = parse_system_file(sys_roland_dir / "DATA" / "SYSTEM1.RC0")
        assert rc0.sys["SETUP"]["D"] == 9

    def test_sys_set_pref(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-set", "PREF", "pref_eq", "0", "-d", str(sys_roland_dir)]
        )
        assert result.exit_code == 0
        assert "Set" in result.output

        rc0 = parse_system_file(sys_roland_dir / "DATA" / "SYSTEM1.RC0")
        assert rc0.sys["PREF"]["K"] == 0  # pref_eq = tag K

    def test_sys_set_invalid_section(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-set", "NONEXISTENT", "foo", "1", "-d", str(sys_roland_dir)]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_sys_set_invalid_param(self, runner: CliRunner, sys_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["sys-set", "SETUP", "nonexistent_param", "1", "-d", str(sys_roland_dir)]
        )
        assert result.exit_code != 0
        assert "not found" in result.output
