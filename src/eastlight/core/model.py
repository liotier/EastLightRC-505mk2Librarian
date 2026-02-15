"""Typed data model for RC-505 MK2 memories and system settings.

Wraps the raw parsed RC0 data with schema-aware named access,
validation, and change tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .parser import RC0File, RC0Section
from .schema import SchemaRegistry, SectionSchema


@dataclass
class ResolvedSection:
    """A section with both raw tag access and schema-resolved named access."""

    raw: RC0Section
    schema: SectionSchema | None = None

    def get_by_name(self, param_name: str) -> int | None:
        """Get a parameter value by its human-readable name."""
        if self.schema is None:
            return None
        tag = self.schema.name_to_tag(param_name)
        if tag is None:
            return None
        return self.raw.get(tag)

    def set_by_name(self, param_name: str, value: int) -> None:
        """Set a parameter value by its human-readable name."""
        if self.schema is None:
            raise ValueError(f"No schema loaded for section {self.raw.name}")
        tag = self.schema.name_to_tag(param_name)
        if tag is None:
            raise KeyError(f"Unknown parameter '{param_name}' in {self.raw.name}")
        fd = self.schema.fields.get(tag)
        if fd and fd.read_only:
            raise ValueError(f"Parameter '{param_name}' is read-only")
        if fd and fd.range is not None:
            lo, hi = fd.range
            if not lo <= value <= hi:
                raise ValueError(
                    f"Value {value} out of range [{lo}, {hi}] for '{param_name}'"
                )
        self.raw[tag] = value

    def as_dict(self) -> dict[str, int]:
        """Return all fields as {name: value} dict using schema names."""
        if self.schema is None:
            return dict(self.raw.fields)
        result = {}
        for tag, value in self.raw.fields.items():
            name = self.schema.tag_to_name(tag)
            result[name or tag] = value
        return result

    def get_by_tag(self, tag: str) -> int:
        """Get raw value by positional tag."""
        return self.raw.get(tag)

    def set_by_tag(self, tag: str, value: int) -> None:
        """Set raw value by positional tag."""
        self.raw[tag] = value


class Memory:
    """A resolved RC-505 MK2 memory with schema-aware access."""

    def __init__(self, rc0: RC0File, registry: SchemaRegistry) -> None:
        self._rc0 = rc0
        self._registry = registry
        self._resolved: dict[str, ResolvedSection] = {}
        self._resolve_all()

    def _resolve_all(self) -> None:
        """Resolve all sections against the schema registry."""
        for element in self._rc0.elements:
            for section_name, section in element.sections.items():
                schema = self._registry.get(section_name)
                self._resolved[section_name] = ResolvedSection(
                    raw=section,
                    schema=schema,
                )

    @property
    def rc0(self) -> RC0File:
        return self._rc0

    @property
    def memory_id(self) -> int | None:
        """The 0-indexed memory ID from the XML."""
        mem = self._rc0.mem
        return mem.id if mem else None

    @property
    def name(self) -> str:
        """Decoded display name from NAME section."""
        name_section = self.section("NAME")
        if name_section is None:
            return ""
        chars = []
        for tag in "ABCDEFGHIJKL":
            code = name_section.get_by_tag(tag)
            if code == 0:
                break
            chars.append(chr(code))
        return "".join(chars).rstrip()

    def section(self, name: str) -> ResolvedSection | None:
        """Get a resolved section by name."""
        return self._resolved.get(name)

    def track(self, num: int) -> ResolvedSection | None:
        """Get TRACK1-TRACK6 section."""
        return self.section(f"TRACK{num}")

    @property
    def section_names(self) -> list[str]:
        """All section names in this memory."""
        return list(self._resolved.keys())
