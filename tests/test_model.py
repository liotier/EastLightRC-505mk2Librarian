"""Tests for the typed data model."""

from __future__ import annotations

from pathlib import Path

import pytest

from eastlight.core.model import FieldChange, Memory
from eastlight.core.parser import parse_memory_file
from eastlight.core.schema import SchemaRegistry, load_schema_from_yaml


@pytest.fixture
def registry() -> SchemaRegistry:
    schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
    reg = SchemaRegistry()
    reg.load_all(schema_dir)
    return reg


class TestMemory:
    def test_name_decoding(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        assert mem.name == "Memory 1"

    def test_track_access(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        assert track1 is not None
        assert track1.get_by_name("pan") == 50
        assert track1.get_by_name("play_level") == 100
        assert track1.get_by_name("tempo_x10") == 700

    def test_track_by_tag(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        assert track1.get_by_tag("C") == 50
        assert track1.get_by_tag("U") == 700

    def test_as_dict(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        d = track1.as_dict()
        assert d["pan"] == 50
        assert d["tempo_x10"] == 700
        assert d["has_audio"] == 1

    def test_set_by_name(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        track1.set_by_name("pan", 75)
        assert track1.get_by_name("pan") == 75
        assert track1.get_by_tag("C") == 75

    def test_set_validates_range(
        self, sample_rc0_path: Path, registry: SchemaRegistry
    ) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        with pytest.raises(ValueError, match="out of range"):
            track1.set_by_name("pan", 200)

    def test_set_rejects_read_only(
        self, sample_rc0_path: Path, registry: SchemaRegistry
    ) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        with pytest.raises(ValueError, match="read-only"):
            track1.set_by_name("has_audio", 0)

    def test_section_names(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        names = mem.section_names
        assert "NAME" in names
        assert "TRACK1" in names
        assert "MASTER" in names
        assert "SETUP" in names  # from ifx/tfx


class TestUndoRedo:
    def test_undo_reverts_value(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        assert track1.get_by_name("pan") == 50
        track1.set_by_name("pan", 75)
        assert track1.get_by_name("pan") == 75
        change = mem.undo()
        assert change is not None
        assert change.old_value == 50
        assert change.new_value == 75
        assert track1.get_by_name("pan") == 50

    def test_redo_reapplies_value(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        track1.set_by_name("pan", 75)
        mem.undo()
        assert track1.get_by_name("pan") == 50
        change = mem.redo()
        assert change is not None
        assert track1.get_by_name("pan") == 75

    def test_undo_empty_returns_none(
        self, sample_rc0_path: Path, registry: SchemaRegistry
    ) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        assert mem.undo() is None

    def test_new_change_clears_redo(
        self, sample_rc0_path: Path, registry: SchemaRegistry
    ) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        track1.set_by_name("pan", 75)
        mem.undo()
        assert mem.undo_stack.can_redo
        track1.set_by_name("pan", 60)  # new change clears redo
        assert not mem.undo_stack.can_redo

    def test_multiple_undo(self, sample_rc0_path: Path, registry: SchemaRegistry) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        track1.set_by_name("pan", 60)
        track1.set_by_name("pan", 70)
        track1.set_by_name("pan", 80)
        assert track1.get_by_name("pan") == 80
        mem.undo()
        assert track1.get_by_name("pan") == 70
        mem.undo()
        assert track1.get_by_name("pan") == 60
        mem.undo()
        assert track1.get_by_name("pan") == 50


class TestChangeListener:
    def test_listener_receives_changes(
        self, sample_rc0_path: Path, registry: SchemaRegistry
    ) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        changes: list[FieldChange] = []
        track1.add_listener(changes.append)
        track1.set_by_name("pan", 75)
        assert len(changes) == 1
        assert changes[0].param_name == "pan"
        assert changes[0].old_value == 50
        assert changes[0].new_value == 75

    def test_remove_listener(
        self, sample_rc0_path: Path, registry: SchemaRegistry
    ) -> None:
        rc0 = parse_memory_file(sample_rc0_path)
        mem = Memory(rc0, registry)
        track1 = mem.track(1)
        changes: list[FieldChange] = []
        track1.add_listener(changes.append)
        track1.set_by_name("pan", 75)
        track1.remove_listener(changes.append)
        track1.set_by_name("pan", 80)
        assert len(changes) == 1  # only the first change
