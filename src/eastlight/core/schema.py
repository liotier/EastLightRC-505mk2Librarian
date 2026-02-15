"""Schema loader for RC-505 MK2 parameter mapping tables.

Loads YAML schema files that define the mapping from positional tags (A, B, C, ...)
to named parameters with types, ranges, and display metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml


@dataclass
class FieldDef:
    """Definition of a single field within a section."""

    tag: str  # Single letter or symbol: "A", "B", ..., "0", "#"
    name: str  # Human-readable name: "reverse", "pan", "play_level"
    type: str  # "bool", "int", "enum"
    display: str = ""  # Display label for UI: "Reverse", "Pan"
    default: int = 0
    range: tuple[int, int] | None = None  # (min, max) for int fields
    choices: dict[int, str] | None = None  # {0: "OFF", 1: "ON"} for enum fields
    unit: str = ""  # Display unit: "BPM", "dB", etc.
    computed: bool = False  # True = derived from other fields, not user-editable
    read_only: bool = False  # True = informational, don't write back


@dataclass
class SectionSchema:
    """Schema for one section type (e.g., TRACK, MASTER, ASSIGN)."""

    section: str  # Section type name
    instances: list[str] = field(default_factory=list)  # e.g., ["TRACK1", ..., "TRACK6"]
    fields: dict[str, FieldDef] = field(default_factory=dict)  # tag → FieldDef

    def tag_to_name(self, tag: str) -> str | None:
        """Resolve a positional tag to its parameter name."""
        fd = self.fields.get(tag)
        return fd.name if fd else None

    def name_to_tag(self, name: str) -> str | None:
        """Resolve a parameter name to its positional tag."""
        for tag, fd in self.fields.items():
            if fd.name == name:
                return tag
        return None

    @property
    def field_names(self) -> list[str]:
        """All parameter names in tag order."""
        return [fd.name for fd in self.fields.values()]


def _parse_field_def(tag: str, raw: dict) -> FieldDef:
    """Parse a single field definition from YAML."""
    range_val = raw.get("range")
    if range_val is not None:
        range_val = tuple(range_val)

    choices = raw.get("choices")
    if choices is not None:
        # YAML may parse int keys as ints already, but ensure consistency
        choices = {int(k): str(v) for k, v in choices.items()}

    return FieldDef(
        tag=tag,
        name=raw["name"],
        type=raw.get("type", "int"),
        display=raw.get("display", raw["name"]),
        default=raw.get("default", 0),
        range=range_val,
        choices=choices,
        unit=raw.get("unit", ""),
        computed=raw.get("computed", False),
        read_only=raw.get("read_only", False),
    )


def load_schema_from_yaml(yaml_path: str | Path) -> SectionSchema:
    """Load a section schema from a YAML file."""
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)

    fields = {}
    for tag, field_raw in raw.get("fields", {}).items():
        tag = str(tag)  # YAML may parse single letters as strings already
        fields[tag] = _parse_field_def(tag, field_raw)

    return SectionSchema(
        section=raw["section"],
        instances=raw.get("instances", []),
        fields=fields,
    )


class SchemaRegistry:
    """Registry of all loaded section schemas."""

    def __init__(self) -> None:
        self._schemas: dict[str, SectionSchema] = {}
        self._instance_map: dict[str, SectionSchema] = {}  # "TRACK1" → track schema

    def register(self, schema: SectionSchema) -> None:
        """Register a section schema."""
        self._schemas[schema.section] = schema
        for instance in schema.instances:
            self._instance_map[instance] = schema

    def get(self, section_name: str) -> SectionSchema | None:
        """Look up schema by section type or instance name.

        Accepts both "TRACK" (type) and "TRACK1" (instance).
        """
        return self._schemas.get(section_name) or self._instance_map.get(section_name)

    @property
    def section_types(self) -> list[str]:
        """All registered section type names."""
        return list(self._schemas.keys())

    def load_all(self, schema_dir: str | Path | None = None) -> None:
        """Load all YAML schema files from a directory.

        If schema_dir is None, loads from the package's built-in schema/ directory.
        """
        if schema_dir is None:
            schema_dir = resources.files("eastlight") / "schema"
        else:
            schema_dir = Path(schema_dir)

        for yaml_file in sorted(Path(schema_dir).glob("*.yaml")):
            schema = load_schema_from_yaml(yaml_file)
            self.register(schema)
