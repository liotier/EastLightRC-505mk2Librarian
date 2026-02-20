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


class FXTypeEnum:
    """Mapping from FX type index (0-69) to effect name."""

    def __init__(self) -> None:
        self.ifx_types: dict[int, str] = {}  # index → "LPF", "DELAY", etc.
        self.tfx_types: dict[int, str] = {}
        self._ifx_reverse: dict[str, int] = {}
        self._tfx_reverse: dict[str, int] = {}

    def ifx_name(self, index: int) -> str | None:
        """Get IFX effect name from type index."""
        return self.ifx_types.get(index)

    def tfx_name(self, index: int) -> str | None:
        """Get TFX effect name from type index."""
        return self.tfx_types.get(index)

    def ifx_index(self, name: str) -> int | None:
        """Get IFX type index from effect name."""
        return self._ifx_reverse.get(name.upper())

    def tfx_index(self, name: str) -> int | None:
        """Get TFX type index from effect name."""
        return self._tfx_reverse.get(name.upper())


def load_fx_types(yaml_path: str | Path) -> FXTypeEnum:
    """Load FX type enum from a YAML file."""
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)

    enum = FXTypeEnum()
    for index, name in raw.get("ifx", {}).items():
        enum.ifx_types[int(index)] = str(name)
        enum._ifx_reverse[str(name).upper()] = int(index)
    for index, name in raw.get("tfx", {}).items():
        enum.tfx_types[int(index)] = str(name)
        enum._tfx_reverse[str(name).upper()] = int(index)
    return enum


# Subslot prefixes: AA, AB, ..., DD (4 groups × 4 slots)
_SUBSLOT_PREFIXES = frozenset(
    f"{g}{s}" for g in "ABCD" for s in "ABCD"
)


class SchemaRegistry:
    """Registry of all loaded section schemas."""

    def __init__(self) -> None:
        self._schemas: dict[str, SectionSchema] = {}
        self._instance_map: dict[str, SectionSchema] = {}  # "TRACK1" → track schema
        self._fx_effect_schemas: dict[str, SectionSchema] = {}  # "LPF" → effect schema
        self.fx_types: FXTypeEnum = FXTypeEnum()

    def register(self, schema: SectionSchema) -> None:
        """Register a section schema."""
        self._schemas[schema.section] = schema
        for instance in schema.instances:
            self._instance_map[instance] = schema

    def register_fx_effect(self, suffix: str, schema: SectionSchema) -> None:
        """Register an FX effect schema by suffix (e.g., 'LPF', 'DELAY')."""
        self._fx_effect_schemas[suffix.upper()] = schema

    def get(self, section_name: str) -> SectionSchema | None:
        """Look up schema by section type, instance name, or FX suffix.

        Accepts "TRACK" (type), "TRACK1" (instance), and "AA_LPF" (FX effect).
        For FX effect sections like "AA_LPF", strips the subslot prefix and
        looks up the effect schema by suffix.
        """
        # Direct match first
        result = self._schemas.get(section_name) or self._instance_map.get(section_name)
        if result is not None:
            return result

        # FX suffix match: "AA_LPF" → prefix="AA", suffix="LPF"
        if "_" in section_name:
            prefix, suffix = section_name.split("_", 1)
            if prefix in _SUBSLOT_PREFIXES:
                return self._fx_effect_schemas.get(suffix.upper())

        return None

    @property
    def section_types(self) -> list[str]:
        """All registered section type names."""
        return list(self._schemas.keys())

    @property
    def fx_effect_names(self) -> list[str]:
        """All registered FX effect suffix names (e.g., ['LPF', 'DELAY', ...])."""
        return sorted(self._fx_effect_schemas.keys())

    def load_all(self, schema_dir: str | Path | None = None) -> None:
        """Load all YAML schema files from a directory.

        If schema_dir is None, loads from the package's built-in schema/ directory.
        Automatically loads FX effect schemas from effects/ subdirectory
        and fx_types.yaml if present.
        """
        if schema_dir is None:
            schema_dir = resources.files("eastlight") / "schema"
        else:
            schema_dir = Path(schema_dir)

        schema_dir = Path(schema_dir)

        for yaml_file in sorted(schema_dir.glob("*.yaml")):
            if yaml_file.name == "fx_types.yaml":
                self.fx_types = load_fx_types(yaml_file)
                continue
            schema = load_schema_from_yaml(yaml_file)
            self.register(schema)

        # Load FX effect schemas from effects/ subdirectory
        effects_dir = schema_dir / "effects"
        if effects_dir.is_dir():
            for yaml_file in sorted(effects_dir.glob("*.yaml")):
                schema = load_schema_from_yaml(yaml_file)
                # The schema section name IS the effect suffix (e.g., "LPF")
                self.register_fx_effect(schema.section, schema)
