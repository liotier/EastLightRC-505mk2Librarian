"""Tests for the schema loader."""

from __future__ import annotations

from pathlib import Path

from eastlight.core.schema import SchemaRegistry, load_schema_from_yaml


class TestLoadSchema:
    def test_load_track_schema(self) -> None:
        schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
        schema = load_schema_from_yaml(schema_dir / "track.yaml")
        assert schema.section == "TRACK"
        assert len(schema.instances) == 6  # TRACK1-TRACK6
        assert "A" in schema.fields
        assert schema.fields["A"].name == "reverse"
        assert schema.fields["C"].name == "pan"
        assert schema.fields["C"].range == (0, 100)

    def test_tag_to_name(self) -> None:
        schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
        schema = load_schema_from_yaml(schema_dir / "track.yaml")
        assert schema.tag_to_name("U") == "tempo_x10"
        assert schema.tag_to_name("W") == "has_audio"
        assert schema.tag_to_name("Z") is None  # doesn't exist

    def test_name_to_tag(self) -> None:
        schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
        schema = load_schema_from_yaml(schema_dir / "track.yaml")
        assert schema.name_to_tag("pan") == "C"
        assert schema.name_to_tag("tempo_x10") == "U"
        assert schema.name_to_tag("nonexistent") is None


class TestSchemaRegistry:
    def test_register_and_get(self) -> None:
        schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
        registry = SchemaRegistry()
        schema = load_schema_from_yaml(schema_dir / "track.yaml")
        registry.register(schema)

        # Get by type name
        assert registry.get("TRACK") is schema
        # Get by instance name
        assert registry.get("TRACK1") is schema
        assert registry.get("TRACK6") is schema
        # Unknown
        assert registry.get("NONEXISTENT") is None

    def test_load_all(self) -> None:
        schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
        registry = SchemaRegistry()
        registry.load_all(schema_dir)
        # Should have at least TRACK and NAME schemas
        assert registry.get("TRACK") is not None
        assert registry.get("NAME") is not None
