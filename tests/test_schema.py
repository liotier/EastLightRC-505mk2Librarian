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

    def test_load_all_schemas_valid(self) -> None:
        """Every YAML schema file must load without errors."""
        schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
        registry = SchemaRegistry()
        registry.load_all(schema_dir)
        # Verify all expected section types loaded
        expected_types = [
            "TRACK", "NAME", "MASTER", "REC", "PLAY", "RHYTHM",
            "ASSIGN", "INPUT", "OUTPUT", "ROUTING", "MIXER", "EQ",
            "MASTER_FX", "FX_SETUP", "FX_SLOT", "FIXED_VALUE",
        ]
        for section_type in expected_types:
            assert registry.get(section_type) is not None, (
                f"Schema for {section_type} not loaded"
            )

    def test_instance_resolution(self) -> None:
        """Instance names must resolve to their parent schema."""
        schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
        registry = SchemaRegistry()
        registry.load_all(schema_dir)
        # Track instances
        for i in range(1, 7):
            assert registry.get(f"TRACK{i}") is not None
        # Assign instances
        for i in range(1, 17):
            assert registry.get(f"ASSIGN{i}") is not None
        # EQ instances
        for name in ["EQ_MIC1", "EQ_MIC2", "EQ_INST1L", "EQ_MAINOUTL", "EQ_SUBOUT2R"]:
            assert registry.get(name) is not None

    def test_schema_field_counts(self) -> None:
        """Each schema must have the expected number of fields."""
        schema_dir = Path(__file__).parent.parent / "src" / "eastlight" / "schema"
        registry = SchemaRegistry()
        registry.load_all(schema_dir)
        expected = {
            "TRACK": 25, "NAME": 12, "MASTER": 4, "REC": 6,
            "PLAY": 8, "RHYTHM": 13, "ASSIGN": 10, "INPUT": 13,
            "OUTPUT": 4, "ROUTING": 19, "MIXER": 22, "EQ": 12,
            "MASTER_FX": 3, "FX_SETUP": 1, "FX_SLOT": 3, "FIXED_VALUE": 2,
        }
        for section_type, count in expected.items():
            schema = registry.get(section_type)
            assert len(schema.fields) == count, (
                f"{section_type}: expected {count} fields, got {len(schema.fields)}"
            )
