"""Tests for the RC0 writer — round-trip fidelity is the critical property."""

from __future__ import annotations

from pathlib import Path

import pytest

from eastlight.core.parser import parse_memory_file, parse_rc0, parse_system_file
from eastlight.core.writer import write_rc0


class TestWriteRC0:
    def test_write_produces_valid_rc0(self, sample_rc0_path: Path, tmp_path: Path) -> None:
        """Written file should parse back without errors."""
        rc0 = parse_memory_file(sample_rc0_path)
        out_path = tmp_path / "output.RC0"
        write_rc0(rc0, out_path)
        rc0_back = parse_memory_file(out_path)
        assert rc0_back.device_name == rc0.device_name
        assert rc0_back.count == rc0.count

    def test_roundtrip_preserves_all_fields(self, sample_rc0_path: Path) -> None:
        """parse → write → parse must produce identical field values."""
        rc0 = parse_rc0(sample_rc0_path)
        written = write_rc0(rc0)
        rc0_back = parse_rc0.__wrapped__(written, rc0.path) if hasattr(parse_rc0, '__wrapped__') else _parse_from_string(written, rc0.path)

        for orig_elem, back_elem in zip(rc0.elements, rc0_back.elements):
            assert orig_elem.element == back_elem.element
            assert orig_elem.id == back_elem.id
            assert orig_elem.section_names == back_elem.section_names
            for sec_name in orig_elem.section_names:
                orig_sec = orig_elem[sec_name]
                back_sec = back_elem[sec_name]
                assert orig_sec.fields == back_sec.fields, (
                    f"Section {sec_name} fields differ: "
                    f"orig={orig_sec.fields} vs back={back_sec.fields}"
                )

    def test_tab_indented_fields(self, sample_rc0_path: Path) -> None:
        """Fields must be tab-indented (matching device format)."""
        rc0 = parse_rc0(sample_rc0_path)
        written = write_rc0(rc0)
        # Every field line should start with a tab
        for line in written.split("\n"):
            if "></" in line and not line.startswith("<"):
                assert line.startswith("\t"), f"Field line not tab-indented: {line!r}"

    def test_no_trailing_newline(self, sample_rc0_path: Path) -> None:
        """Output must not end with a newline (matching device format)."""
        rc0 = parse_rc0(sample_rc0_path)
        written = write_rc0(rc0)
        assert not written.endswith("\n")
        assert written.endswith("</count>")

    def test_count_footer_format(self, sample_rc0_path: Path) -> None:
        """Count footer must be 4-digit zero-padded."""
        rc0 = parse_rc0(sample_rc0_path)
        rc0.count = 13
        written = write_rc0(rc0)
        assert "<count>0013</count>" in written

    def test_database_header(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        written = write_rc0(rc0)
        assert '<database name="RC-505MK2" revision="0">' in written

    def test_xml_declaration(self, sample_rc0_path: Path) -> None:
        rc0 = parse_rc0(sample_rc0_path)
        written = write_rc0(rc0)
        assert written.startswith('<?xml version="1.0" encoding="utf-8"?>')


class TestRoundTripRealFiles:
    """Round-trip tests against real device dump files."""

    @pytest.fixture
    def dump_dir(self) -> Path:
        d = Path("/tmp/rc505-dump/ROLAND/DATA")
        if not d.exists():
            pytest.skip("Device dump not available")
        return d

    def test_memory001a_roundtrip_values(self, dump_dir: Path) -> None:
        """Parse → write → parse Memory001A: all field values must match."""
        rc0 = parse_memory_file(dump_dir / "MEMORY001A.RC0")
        written = write_rc0(rc0)
        rc0_back = _parse_from_string(written, rc0.path)

        for orig_elem, back_elem in zip(rc0.elements, rc0_back.elements):
            assert orig_elem.element == back_elem.element
            assert orig_elem.id == back_elem.id
            for sec_name in orig_elem.section_names:
                orig_fields = orig_elem[sec_name].fields
                back_fields = back_elem[sec_name].fields
                assert orig_fields == back_fields, (
                    f"Section {sec_name}: {_field_diff(orig_fields, back_fields)}"
                )

    def test_memory001a_roundtrip_byte_exact(self, dump_dir: Path) -> None:
        """Parse → write must produce byte-for-byte identical output."""
        original = (dump_dir / "MEMORY001A.RC0").read_text(encoding="utf-8")
        rc0 = parse_memory_file(dump_dir / "MEMORY001A.RC0")
        written = write_rc0(rc0)
        if original != written:
            # Find first difference for debugging
            for i, (a, b) in enumerate(zip(original, written)):
                if a != b:
                    context = 40
                    pytest.fail(
                        f"Byte-exact mismatch at position {i}:\n"
                        f"  original: ...{original[max(0,i-context):i+context]!r}...\n"
                        f"  written:  ...{written[max(0,i-context):i+context]!r}..."
                    )
            if len(original) != len(written):
                pytest.fail(
                    f"Length mismatch: original={len(original)}, written={len(written)}"
                )

    def test_system1_roundtrip_values(self, dump_dir: Path) -> None:
        """Round-trip SYSTEM1.RC0: all field values must match."""
        rc0 = parse_system_file(dump_dir / "SYSTEM1.RC0")
        written = write_rc0(rc0)
        rc0_back = _parse_from_string(written, rc0.path)

        for orig_elem, back_elem in zip(rc0.elements, rc0_back.elements):
            for sec_name in orig_elem.section_names:
                assert orig_elem[sec_name].fields == back_elem[sec_name].fields, (
                    f"System section {sec_name} roundtrip mismatch"
                )

    def test_all_memories_roundtrip_values(self, dump_dir: Path) -> None:
        """Every memory file must round-trip with identical field values."""
        failures = []
        for n in range(1, 100):
            path = dump_dir / f"MEMORY{n:03d}A.RC0"
            if not path.exists():
                continue
            rc0 = parse_memory_file(path)
            written = write_rc0(rc0)
            rc0_back = _parse_from_string(written, path)
            for orig_elem, back_elem in zip(rc0.elements, rc0_back.elements):
                for sec_name in orig_elem.section_names:
                    if orig_elem[sec_name].fields != back_elem[sec_name].fields:
                        failures.append(f"Memory{n:03d}A/{sec_name}")
        assert not failures, f"Roundtrip failures: {failures}"


def _parse_from_string(content: str, path: Path) -> "RC0File":
    """Helper: parse RC0 from a string (write to temp, then parse)."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".RC0", delete=False, encoding="utf-8") as f:
        f.write(content)
        f.flush()
        return parse_rc0(Path(f.name))


def _field_diff(a: dict, b: dict) -> str:
    """Helper: describe field differences."""
    diffs = []
    for key in sorted(set(a.keys()) | set(b.keys())):
        va = a.get(key, "<missing>")
        vb = b.get(key, "<missing>")
        if va != vb:
            diffs.append(f"{key}: {va} → {vb}")
    return "; ".join(diffs) if diffs else "(identical)"
