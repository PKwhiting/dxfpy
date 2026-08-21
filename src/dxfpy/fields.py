"""Public helpers and constants for user-facing FIELD templates."""

from typing import Final

from .entities.fieldtemplate import (
    DrawingProperty,
    DrawingVariable,
    ObjectProperty,
    drawing_property,
    drawing_variable,
    object_property,
)


class FieldFormat:
    """Named AutoCAD FIELD formats for supported text-case transforms."""

    UPPERCASE: Final[str] = "%tc1"
    LOWERCASE: Final[str] = "%tc2"
    FIRST_CAPITAL: Final[str] = "%tc3"
    TITLE_CASE: Final[str] = "%tc4"


__all__ = [
    "FieldFormat",
    "DrawingProperty",
    "DrawingVariable",
    "ObjectProperty",
    "drawing_property",
    "drawing_variable",
    "object_property",
]
