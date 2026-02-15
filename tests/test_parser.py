"""Tests for the RC0 parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from eastlight.core.parser import parse_memory_file, parse_rc0


class TestParseRC0:
    def test_parse_database_header(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        assert rc0.device_name == "RC-505MK2"
        assert rc0.revision == 0

    def test_parse_count_footer(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        assert rc0.count == 13

    def test_parse_top_level_elements(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        assert len(rc0.elements) == 3
        assert rc0.mem is not None
        assert rc0.ifx is not None
        assert rc0.tfx is not None

    def test_parse_element_ids(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        assert rc0.mem.id == 0
        assert rc0.ifx.id == 0
        assert rc0.tfx.id == 0

    def test_parse_sections(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        mem = rc0.mem
        assert "NAME" in mem
        assert "TRACK1" in mem
        assert "TRACK2" in mem
        assert "MASTER" in mem

    def test_parse_name_fields(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        name = rc0.mem["NAME"]
        # "Memory 1" = 77, 101, 109, 111, 114, 121, 32, 49
        assert name["A"] == 77  # M
        assert name["B"] == 101  # e
        assert name["C"] == 109  # m
        assert name["D"] == 111  # o
        assert name["E"] == 114  # r
        assert name["F"] == 121  # y

    def test_parse_track_fields(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        track1 = rc0.mem["TRACK1"]
        assert track1["C"] == 50  # pan = center
        assert track1["D"] == 100  # play level
        assert track1["U"] == 700  # tempo = 70.0 BPM
        assert track1["V"] == 151200  # samples per measure
        assert track1["W"] == 1  # has audio
        assert track1["X"] == 1209600  # total samples
        assert track1["S"] == 8  # loop length = 8 measures

    def test_track_tempo_math(self, sample_rc0_path: Path) -> None:
        """Verify S = X / V (loop measures = total samples / samples per measure)."""
        rc0 = parse_rc0(sample_rc0_path)
        track1 = rc0.mem["TRACK1"]
        s = track1["S"]  # loop length in measures
        v = track1["V"]  # samples per measure
        x = track1["X"]  # total samples
        assert s == x // v

    def test_empty_track(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        track2 = rc0.mem["TRACK2"]
        assert track2["W"] == 0  # no audio
        assert track2["X"] == 0  # no samples
        assert track2["H"] == 1  # factory empty
        assert track2["Y"] == 2  # empty state

    def test_parse_ifx_setup(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        setup = rc0.ifx["SETUP"]
        assert setup["A"] == 0


class TestParseMemoryFile:
    def test_validates_mem_element(self, sample_rc0_path: Path) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        assert rc0.mem is not None

    def test_rejects_missing_elements(self, tmp_path: Path) -> None:
        # File with only sys element (not a memory file)
        content = '''<?xml version="1.0" encoding="utf-8"?>
<database name="RC-505MK2" revision="0">
<sys>
<SETUP>
<A>0</A>
</SETUP>
</sys>
</database>
<count>0001</count>
'''
        path = tmp_path / "bad.RC0"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match="missing <mem>"):
            parse_memory_file(path)


class TestParseRealFiles:
    """Tests against real device dump files (skipped if not available)."""

    @pytest.fixture
    def dump_dir(self) -> Path:
        d = Path("/tmp/rc505-dump/ROLAND/DATA")
        if not d.exists():
            pytest.skip("Device dump not available")
        return d

    def test_parse_memory001a(self, dump_dir: Path) -> None:
        rc0 = parse_memory_file(dump_dir / "MEMORY001A.RC0")
        assert rc0.device_name == "RC-505MK2"
        assert rc0.mem is not None
        assert rc0.ifx is not None
        assert rc0.tfx is not None
        # Should have many sections
        assert len(rc0.mem.section_names) > 20
        assert len(rc0.ifx.section_names) > 100
        assert len(rc0.tfx.section_names) > 100

    def test_all_99_memories_parse(self, dump_dir: Path) -> None:
        """Every memory file should parse without error."""
        for n in range(1, 100):
            path = dump_dir / f"MEMORY{n:03d}A.RC0"
            if path.exists():
                rc0 = parse_memory_file(path)
                assert rc0.mem is not None
