"""RC0 file writer — serializes the data model back to Roland's pseudo-XML format.

Produces output that is byte-for-byte compatible with the device's expected format,
preserving tag order, line breaks, and the count footer.
"""

from __future__ import annotations

from pathlib import Path

from .parser import RC0File, RC0Section, RC0TopLevel


def _write_fields(section: RC0Section, indent: str = "") -> str:
    """Serialize a section's fields to RC0 format."""
    lines = []
    for tag, value in section.fields.items():
        lines.append(f"{indent}<{tag}>{value}</{tag}>")
    return "\n".join(lines)


def _write_section(section: RC0Section, indent: str = "") -> str:
    """Serialize a complete section (name + fields)."""
    fields_str = _write_fields(section, indent + "")
    return f"{indent}<{section.name}>\n{fields_str}\n{indent}</{section.name}>"


def _write_top_level(element: RC0TopLevel) -> str:
    """Serialize a top-level element (mem, ifx, tfx, sys)."""
    if element.id is not None:
        header = f'<{element.element} id="{element.id}">'
    else:
        header = f"<{element.element}>"

    sections = []
    for section in element.sections.values():
        sections.append(_write_section(section))

    footer = f"</{element.element}>"
    return header + "\n" + "\n".join(sections) + "\n" + footer


def write_rc0(rc0: RC0File, path: str | Path | None = None) -> str:
    """Serialize an RC0File back to string format.

    Args:
        rc0: The parsed RC0 file to serialize.
        path: If provided, write to this path. Otherwise just return the string.

    Returns:
        The serialized RC0 content as a string.
    """
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<database name="{rc0.device_name}" revision="{rc0.revision}">',
    ]

    for element in rc0.elements:
        lines.append(_write_top_level(element))

    lines.append("</database>")
    lines.append(f"<count>{rc0.count:04d}</count>")
    lines.append("")  # trailing newline

    content = "\n".join(lines)

    if path is not None:
        path = Path(path)
        path.write_text(content, encoding="utf-8")

    return content
