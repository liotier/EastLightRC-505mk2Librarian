"""Typed data model for RC-505 MK2 memories and system settings.

Wraps the raw parsed RC0 data with schema-aware named access,
validation, change tracking, and undo/redo support.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .parser import RC0File, RC0Section
from .schema import SchemaRegistry, SectionSchema


# --- Change tracking and undo/redo ---


@dataclass
class FieldChange:
    """Record of a single field value change (for undo/redo and observers)."""

    section_name: str
    tag: str
    param_name: str | None  # None if no schema
    old_value: int
    new_value: int


# Observer callback type: receives the change that just happened
ChangeListener = Callable[[FieldChange], None]


class UndoStack:
    """Simple undo/redo stack for field changes."""

    def __init__(self, max_depth: int = 200) -> None:
        self._undo: list[FieldChange] = []
        self._redo: list[FieldChange] = []
        self._max_depth = max_depth

    def push(self, change: FieldChange) -> None:
        """Record a change. Clears the redo stack."""
        self._undo.append(change)
        if len(self._undo) > self._max_depth:
            self._undo.pop(0)
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return len(self._undo) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo) > 0

    def pop_undo(self) -> FieldChange | None:
        """Pop the most recent change for undoing. Returns None if empty."""
        if not self._undo:
            return None
        change = self._undo.pop()
        self._redo.append(change)
        return change

    def pop_redo(self) -> FieldChange | None:
        """Pop the most recent undone change for redoing. Returns None if empty."""
        if not self._redo:
            return None
        change = self._redo.pop()
        self._undo.append(change)
        return change

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()


# --- Data model ---


@dataclass
class ResolvedSection:
    """A section with both raw tag access and schema-resolved named access."""

    raw: RC0Section
    schema: SectionSchema | None = None
    _listeners: list[ChangeListener] = field(default_factory=list, repr=False)
    _undo_stack: UndoStack | None = field(default=None, repr=False)

    def add_listener(self, listener: ChangeListener) -> None:
        """Register a change listener (for GUI binding)."""
        self._listeners.append(listener)

    def remove_listener(self, listener: ChangeListener) -> None:
        self._listeners.remove(listener)

    def _notify(self, change: FieldChange) -> None:
        """Notify all listeners of a change and push to undo stack."""
        if self._undo_stack is not None:
            self._undo_stack.push(change)
        for listener in self._listeners:
            listener(change)

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
        old_value = self.raw.get(tag)
        self.raw[tag] = value
        self._notify(FieldChange(
            section_name=self.raw.name,
            tag=tag,
            param_name=param_name,
            old_value=old_value,
            new_value=value,
        ))

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
        old_value = self.raw.get(tag)
        self.raw[tag] = value
        param_name = self.schema.tag_to_name(tag) if self.schema else None
        self._notify(FieldChange(
            section_name=self.raw.name,
            tag=tag,
            param_name=param_name,
            old_value=old_value,
            new_value=value,
        ))


class Memory:
    """A resolved RC-505 MK2 memory with schema-aware access."""

    def __init__(self, rc0: RC0File, registry: SchemaRegistry) -> None:
        self._rc0 = rc0
        self._registry = registry
        self._resolved: dict[str, ResolvedSection] = {}
        self._undo_stack = UndoStack()
        self._dirty = False
        self._resolve_all()

    def _resolve_all(self) -> None:
        """Resolve all sections against the schema registry."""
        for element in self._rc0.elements:
            for section_name, section in element.sections.items():
                schema = self._registry.get(section_name)
                self._resolved[section_name] = ResolvedSection(
                    raw=section,
                    schema=schema,
                    _undo_stack=self._undo_stack,
                )

    @property
    def rc0(self) -> RC0File:
        return self._rc0

    @property
    def undo_stack(self) -> UndoStack:
        return self._undo_stack

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

    def set_name(self, new_name: str) -> None:
        """Set the memory display name (max 12 ASCII chars, space-padded)."""
        name_section = self.section("NAME")
        if name_section is None:
            raise ValueError("No NAME section in this memory")
        padded = new_name[:12].ljust(12)
        for i, tag in enumerate("ABCDEFGHIJKL"):
            name_section.set_by_tag(tag, ord(padded[i]))

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

    def undo(self) -> FieldChange | None:
        """Undo the most recent change. Returns the change that was undone."""
        change = self._undo_stack.pop_undo()
        if change is None:
            return None
        # Apply the reverse without triggering another undo push
        section = self._resolved.get(change.section_name)
        if section:
            section.raw[change.tag] = change.old_value
        return change

    def redo(self) -> FieldChange | None:
        """Redo the most recently undone change. Returns the change that was redone."""
        change = self._undo_stack.pop_redo()
        if change is None:
            return None
        section = self._resolved.get(change.section_name)
        if section:
            section.raw[change.tag] = change.new_value
        return change
