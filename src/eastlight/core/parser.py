"""Regex-based parser for Roland RC-505 MK2 RC0 files.

RC0 files use a pseudo-XML format with positional single-letter tags (<A>, <B>, ...).
Some sections use numeric tags (<0>, <1>) and symbols (<#>) which are invalid XML,
so standard XML parsers cannot handle them. This module uses regex-based parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Match top-level elements: <mem id="N">, <ifx id="N">, <tfx id="N">, <sys>
_TOP_LEVEL_RE = re.compile(
    r"<(mem|ifx|tfx|sys)(?:\s+id=\"(\d+)\")?>(.+?)</\1>",
    re.DOTALL,
)

# Match sections within a top-level element: <TRACK1>...</TRACK1>, <AA_LPF>...</AA_LPF>
_SECTION_RE = re.compile(
    r"<([A-Z][A-Z0-9_]*)>\n(.*?)</\1>",
    re.DOTALL,
)

# Match fields within a section: <A>123</A>, <0>45</0>, <#>67</#>
_FIELD_RE = re.compile(
    r"<([^/][^>]*)>(-?\d+)</\1>",
)

# Match the database header
_DATABASE_RE = re.compile(
    r'<database\s+name="([^"]+)"\s+revision="(\d+)">'
)

# Match the count footer
_COUNT_RE = re.compile(
    r"<count>(\d+)</count>"
)


@dataclass
class RC0Field:
    """A single field within a section (e.g., tag='A', value=50)."""

    tag: str
    value: int


@dataclass
class RC0Section:
    """A named section within a top-level element (e.g., TRACK1, AA_LPF)."""

    name: str
    fields: dict[str, int] = field(default_factory=dict)

    def __getitem__(self, tag: str) -> int:
        return self.fields[tag]

    def __setitem__(self, tag: str, value: int) -> None:
        self.fields[tag] = value

    def get(self, tag: str, default: int = 0) -> int:
        return self.fields.get(tag, default)


@dataclass
class RC0TopLevel:
    """A top-level element: mem, ifx, tfx, or sys."""

    element: str  # "mem", "ifx", "tfx", "sys"
    id: int | None  # 0-98 for mem/ifx/tfx, None for sys
    sections: dict[str, RC0Section] = field(default_factory=dict)

    def __getitem__(self, section_name: str) -> RC0Section:
        return self.sections[section_name]

    def __contains__(self, section_name: str) -> bool:
        return section_name in self.sections

    @property
    def section_names(self) -> list[str]:
        return list(self.sections.keys())


@dataclass
class RC0File:
    """A parsed RC0 file."""

    path: Path
    device_name: str  # "RC-505MK2"
    revision: int  # 0
    elements: list[RC0TopLevel] = field(default_factory=list)
    count: int = 0  # save counter from footer

    @property
    def mem(self) -> RC0TopLevel | None:
        """The <mem> element, if present."""
        return next((e for e in self.elements if e.element == "mem"), None)

    @property
    def ifx(self) -> RC0TopLevel | None:
        """The <ifx> element, if present."""
        return next((e for e in self.elements if e.element == "ifx"), None)

    @property
    def tfx(self) -> RC0TopLevel | None:
        """The <tfx> element, if present."""
        return next((e for e in self.elements if e.element == "tfx"), None)

    @property
    def sys(self) -> RC0TopLevel | None:
        """The <sys> element, if present."""
        return next((e for e in self.elements if e.element == "sys"), None)


def parse_sections(body: str) -> dict[str, RC0Section]:
    """Parse all sections from a top-level element body."""
    sections: dict[str, RC0Section] = {}
    for match in _SECTION_RE.finditer(body):
        section_name = match.group(1)
        section_body = match.group(2)
        fields = {}
        for field_match in _FIELD_RE.finditer(section_body):
            tag = field_match.group(1)
            value = int(field_match.group(2))
            fields[tag] = value
        sections[section_name] = RC0Section(name=section_name, fields=fields)
    return sections


def parse_rc0(path: str | Path) -> RC0File:
    """Parse an RC0 file and return its structured representation.

    Args:
        path: Path to the RC0 file.

    Returns:
        RC0File with all elements, sections, and fields parsed.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file doesn't contain a valid database header.
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8")

    # Parse database header
    header_match = _DATABASE_RE.search(content)
    if not header_match:
        raise ValueError(f"No <database> header found in {path}")
    device_name = header_match.group(1)
    revision = int(header_match.group(2))

    # Parse count footer
    count_match = _COUNT_RE.search(content)
    count = int(count_match.group(1)) if count_match else 0

    # Parse top-level elements
    elements = []
    for match in _TOP_LEVEL_RE.finditer(content):
        element_name = match.group(1)
        element_id = int(match.group(2)) if match.group(2) else None
        element_body = match.group(3)
        sections = parse_sections(element_body)
        elements.append(RC0TopLevel(
            element=element_name,
            id=element_id,
            sections=sections,
        ))

    return RC0File(
        path=path,
        device_name=device_name,
        revision=revision,
        elements=elements,
        count=count,
    )


def parse_memory_file(path: str | Path) -> RC0File:
    """Parse a memory RC0 file (MEMORY001A.RC0 etc.).

    Convenience wrapper that validates the file contains mem, ifx, and tfx elements.
    """
    rc0 = parse_rc0(path)
    if rc0.mem is None:
        raise ValueError(f"Memory file {path} missing <mem> element")
    if rc0.ifx is None:
        raise ValueError(f"Memory file {path} missing <ifx> element")
    if rc0.tfx is None:
        raise ValueError(f"Memory file {path} missing <tfx> element")
    return rc0


def parse_system_file(path: str | Path) -> RC0File:
    """Parse a system RC0 file (SYSTEM1.RC0 etc.).

    Convenience wrapper that validates the file contains a sys element.
    """
    rc0 = parse_rc0(path)
    if rc0.sys is None:
        raise ValueError(f"System file {path} missing <sys> element")
    return rc0
