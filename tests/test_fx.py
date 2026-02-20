"""Tests for FX schema, suffix matching, and CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from eastlight.cli.main import cli
from eastlight.core.parser import parse_memory_file
from eastlight.core.schema import FXTypeEnum, SchemaRegistry, load_fx_types


# --- FX-specific RC0 fixture ---

# Minimal RC0 content with IFX and TFX elements containing:
# - SETUP section (current_slot selector)
# - Group A parent section
# - Subslot AA header (sw=1, fx_type=35 → DELAY)
# - AA_DELAY effect section (time=211, feedback=20, ...)
# - Subslot AB header (sw=0, fx_type=0 → LPF)
# - AB_LPF effect section
_FX_RC0 = '''\
<?xml version="1.0" encoding="utf-8"?>
<database name="RC-505MK2" revision="0">
<mem id="0">
<NAME>
<A>70</A>
<B>88</B>
<C>32</C>
<D>80</D>
<E>97</E>
<F>116</F>
<G>99</G>
<H>104</H>
<I>32</I>
<J>32</J>
<K>32</K>
<L>32</L>
</NAME>
<TRACK1>
<A>0</A>
<B>0</B>
<C>50</C>
<D>100</D>
<E>0</E>
<F>0</F>
<G>0</G>
<H>0</H>
<I>0</I>
<J>5</J>
<K>0</K>
<L>1</L>
<M>0</M>
<N>1</N>
<O>1</O>
<P>0</P>
<Q>127</Q>
<R>0</R>
<S>8</S>
<T>0</T>
<U>700</U>
<V>151200</V>
<W>1</W>
<X>1209600</X>
<Y>1</Y>
</TRACK1>
<MASTER>
<A>100</A>
<B>0</B>
</MASTER>
</mem>
<ifx id="0">
<SETUP>
<A>0</A>
</SETUP>
<AA>
<A>1</A>
<B>0</B>
<C>35</C>
<D>0</D>
</AA>
<AA_DELAY>
<A>211</A>
<B>20</B>
<C>100</C>
<D>0</D>
<E>29</E>
<F>50</F>
</AA_DELAY>
<AA_LPF>
<A>3</A>
<B>50</B>
<C>50</C>
<D>50</D>
<E>0</E>
</AA_LPF>
<AB>
<A>0</A>
<B>0</B>
<C>0</C>
<D>0</D>
</AB>
<AB_LPF>
<A>3</A>
<B>50</B>
<C>50</C>
<D>50</D>
<E>0</E>
</AB_LPF>
</ifx>
<tfx id="0">
<SETUP>
<A>0</A>
</SETUP>
<AA>
<A>1</A>
<B>0</B>
<C>48</C>
<D>0</D>
</AA>
<AA_REVERB>
<A>30</A>
<B>0</B>
<C>4</C>
<D>0</D>
<E>29</E>
<F>100</F>
<G>50</G>
</AA_REVERB>
<AA_BEAT_SCATTER>
<A>0</A>
<B>3</B>
</AA_BEAT_SCATTER>
</tfx>
</database>
<count>0013</count>
'''


@pytest.fixture
def fx_roland_dir(tmp_path: Path) -> Path:
    """ROLAND/ directory with FX-populated memory files."""
    root = tmp_path / "ROLAND"
    data = root / "DATA"
    wave = root / "WAVE"
    data.mkdir(parents=True)
    wave.mkdir(parents=True)
    (data / "MEMORY001A.RC0").write_text(_FX_RC0, encoding="utf-8")
    return root


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# --- Schema registry tests ---


class TestFXSchemaRegistry:
    def test_fx_effect_schemas_loaded(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        assert len(r.fx_effect_names) == 70

    def test_suffix_match_basic(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        schema = r.get("AA_LPF")
        assert schema is not None
        assert schema.section == "LPF"
        assert "rate" in schema.field_names

    def test_suffix_match_any_subslot(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        for prefix in ["AA", "AB", "BA", "CD", "DD"]:
            schema = r.get(f"{prefix}_DELAY")
            assert schema is not None
            assert schema.section == "DELAY"

    def test_suffix_match_seq_variants(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        schema = r.get("AA_LPF_SEQ")
        assert schema is not None
        assert schema.section == "LPF_SEQ"
        assert len(schema.fields) == 22

    def test_suffix_match_tfx_exclusive(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        schema = r.get("AA_BEAT_SCATTER")
        assert schema is not None
        assert schema.section == "BEAT_SCATTER"

    def test_suffix_no_false_positives(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        # "NAME" has no underscore prefix, should not match as FX
        schema = r.get("NAME")
        assert schema is not None
        assert schema.section == "NAME"

        # Non-existent effect
        assert r.get("AA_NONEXISTENT") is None

    def test_existing_schemas_still_work(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        # Direct lookups should still work
        assert r.get("TRACK1") is not None
        assert r.get("MASTER") is not None
        # Subslot header
        assert r.get("AA") is not None
        assert r.get("AA").section == "FX_SUBSLOT"


class TestFXTypeEnum:
    def test_ifx_types_loaded(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        assert len(r.fx_types.ifx_types) == 66

    def test_tfx_types_loaded(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        assert len(r.fx_types.tfx_types) == 70

    def test_ifx_name_lookup(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        assert r.fx_types.ifx_name(0) == "LPF"
        assert r.fx_types.ifx_name(35) == "DELAY"
        assert r.fx_types.ifx_name(48) == "REVERB"

    def test_tfx_exclusive_types(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        assert r.fx_types.tfx_name(66) == "BEAT_SCATTER"
        assert r.fx_types.tfx_name(67) == "BEAT_REPEAT"
        assert r.fx_types.tfx_name(68) == "BEAT_SHIFT"
        assert r.fx_types.tfx_name(69) == "VINYL_FLICK"
        # These should NOT be in IFX
        assert r.fx_types.ifx_name(66) is None

    def test_reverse_lookup(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        assert r.fx_types.ifx_index("LPF") == 0
        assert r.fx_types.ifx_index("DELAY") == 35
        assert r.fx_types.tfx_index("BEAT_SCATTER") == 66

    def test_case_insensitive_reverse(self) -> None:
        r = SchemaRegistry()
        r.load_all()
        assert r.fx_types.ifx_index("lpf") == 0
        assert r.fx_types.ifx_index("Delay") == 35


# --- FX CLI tests ---


class TestFXShowCommand:
    def test_fx_show_ifx(self, runner: CliRunner, fx_roland_dir: Path) -> None:
        result = runner.invoke(cli, ["fx-show", str(fx_roland_dir), "1", "ifx"])
        assert result.exit_code == 0
        assert "DELAY" in result.output
        assert "AA" in result.output

    def test_fx_show_tfx(self, runner: CliRunner, fx_roland_dir: Path) -> None:
        result = runner.invoke(cli, ["fx-show", str(fx_roland_dir), "1", "tfx"])
        assert result.exit_code == 0
        assert "REVERB" in result.output

    def test_fx_show_group_filter(self, runner: CliRunner, fx_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["fx-show", str(fx_roland_dir), "1", "ifx", "-g", "A"]
        )
        assert result.exit_code == 0
        assert "AA" in result.output
        assert "AB" in result.output

    def test_fx_show_slot_filter(self, runner: CliRunner, fx_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["fx-show", str(fx_roland_dir), "1", "ifx", "-s", "AA"]
        )
        assert result.exit_code == 0
        assert "DELAY" in result.output
        # Should show resolved parameter names
        assert "Time" in result.output or "time" in result.output.lower()

    def test_fx_show_raw_mode(self, runner: CliRunner, fx_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["fx-show", str(fx_roland_dir), "1", "ifx", "-s", "AA", "--raw"]
        )
        assert result.exit_code == 0
        # Should show raw tag names (A, B, C, etc.)

    def test_fx_show_displays_on_off(self, runner: CliRunner, fx_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["fx-show", str(fx_roland_dir), "1", "ifx", "-s", "AA"]
        )
        assert result.exit_code == 0
        assert "ON" in result.output  # AA has sw=1

        result = runner.invoke(
            cli, ["fx-show", str(fx_roland_dir), "1", "ifx", "-s", "AB"]
        )
        assert result.exit_code == 0
        assert "OFF" in result.output  # AB has sw=0


class TestFXSetCommand:
    def test_fx_set_effect_param_by_name(
        self, runner: CliRunner, fx_roland_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["fx-set", str(fx_roland_dir), "1", "ifx", "AA", "feedback", "30"]
        )
        assert result.exit_code == 0
        assert "Set" in result.output
        assert "20" in result.output  # old value
        assert "30" in result.output  # new value

        # Verify written to file
        rc0 = parse_memory_file(fx_roland_dir / "DATA" / "MEMORY001A.RC0")
        assert rc0.ifx.sections["AA_DELAY"]["B"] == 30

    def test_fx_set_effect_param_by_tag(
        self, runner: CliRunner, fx_roland_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["fx-set", str(fx_roland_dir), "1", "ifx", "AA", "B", "25"]
        )
        assert result.exit_code == 0
        assert "Set" in result.output

        rc0 = parse_memory_file(fx_roland_dir / "DATA" / "MEMORY001A.RC0")
        assert rc0.ifx.sections["AA_DELAY"]["B"] == 25

    def test_fx_set_header_sw(
        self, runner: CliRunner, fx_roland_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["fx-set", str(fx_roland_dir), "1", "ifx", "AB", "sw", "1"]
        )
        assert result.exit_code == 0
        assert "Set" in result.output

        rc0 = parse_memory_file(fx_roland_dir / "DATA" / "MEMORY001A.RC0")
        assert rc0.ifx.sections["AB"]["A"] == 1  # sw tag = A

    def test_fx_set_header_fx_type(
        self, runner: CliRunner, fx_roland_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["fx-set", str(fx_roland_dir), "1", "ifx", "AA", "fx_type", "48"]
        )
        assert result.exit_code == 0
        assert "DELAY" in result.output  # old type name
        assert "REVERB" in result.output  # new type name

        rc0 = parse_memory_file(fx_roland_dir / "DATA" / "MEMORY001A.RC0")
        assert rc0.ifx.sections["AA"]["C"] == 48

    def test_fx_set_invalid_subslot(
        self, runner: CliRunner, fx_roland_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["fx-set", str(fx_roland_dir), "1", "ifx", "ZZ", "feedback", "30"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_fx_set_invalid_param(
        self, runner: CliRunner, fx_roland_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["fx-set", str(fx_roland_dir), "1", "ifx", "AA", "nonexistent", "30"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output


class TestFXShowWithResolvedSchemas:
    """Verify that FX effect parameters are resolved via suffix matching."""

    def test_delay_params_resolved(self, runner: CliRunner, fx_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["fx-show", str(fx_roland_dir), "1", "ifx", "-s", "AA"]
        )
        assert result.exit_code == 0
        # DELAY schema should resolve tags to parameter names
        output_lower = result.output.lower()
        assert "time" in output_lower
        assert "feedback" in output_lower

    def test_reverb_params_resolved(self, runner: CliRunner, fx_roland_dir: Path) -> None:
        result = runner.invoke(
            cli, ["fx-show", str(fx_roland_dir), "1", "tfx", "-s", "AA"]
        )
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "reverb" in output_lower
