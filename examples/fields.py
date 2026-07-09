# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
"""Create and inspect object-backed AutoCAD fields.

This example shows common SDK workflows for:

- ``TEXT`` and ``MTEXT`` fields
- ``MULTILEADER`` fields with MTEXT content
- drawing-property fields
- object-property fields
- expression fields composed from child fields
- ``ACAD_TABLE`` text-cell fields

The generated DXF file is meant for inspection in AutoCAD or BricsCAD, which are
responsible for evaluating/updating the fields after opening the file.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import Field
from ezdxf.math import Vec2

OUT = Path("~/Desktop/Outbox").expanduser()


class FieldDemoBuilder:
    """Build a compact DXF document that demonstrates field helpers."""

    def __init__(self) -> None:
        """Initialize the demo document and modelspace."""
        self.doc = ezdxf.new("R2018")
        self.msp = self.doc.modelspace()
        self.line = self.msp.add_line((0, 20), (10, 20))
        self.circle = self.msp.add_circle((5, 8), radius=3)

    def build(self) -> Drawing:
        """Create all demo entities and return the DXF document."""
        self._add_title()
        self._add_mtext_fields()
        self._add_text_fields()
        self._add_multileader_fields()
        self._add_expression_field()
        self._add_table_fields()
        return self.doc

    def _add_title(self) -> None:
        """Add a title to the demo drawing."""
        self.msp.add_mtext(
            "Field API Demo",
            dxfattribs={"insert": (0, 58, 0), "char_height": 3.5, "width": 80},
        )

    def _add_mtext_fields(self) -> None:
        """Add drawing-variable and object-property MTEXT fields."""
        self._add_label("Author (MTEXT):", (0, 50, 0))
        self.msp.add_mtext_acvar_field(
            "Author",
            text="----",
            dxfattribs=self._mtext_attribs(30, 50),
            register_field_list=True,
        )
        self._add_label("Line Length:", (0, 44, 0))
        self.msp.add_mtext_acobjprop_field(
            self.line,
            "Length",
            dxfattribs=self._mtext_attribs(30, 44),
            register_field_list=True,
        )
        self._add_label("Circle Area:", (0, 38, 0))
        self.msp.add_mtext_acobjprop_field(
            self.circle,
            "Area",
            dxfattribs=self._mtext_attribs(30, 38),
            register_field_list=True,
        )

    def _add_text_fields(self) -> None:
        """Add drawing-property and object-property TEXT fields."""
        self._add_text_label("ProjectCode (TEXT):", (60, 50, 0))
        self.msp.add_text_dwgprops_field(
            "ProjectCode",
            text="VALUE-123",
            height=2.5,
            dxfattribs={"insert": (96, 50, 0)},
            register_field_list=True,
        )
        self._add_text_label("Circle Radius (TEXT):", (60, 44, 0))
        self.msp.add_text_acobjprop_field(
            self.circle,
            "Radius",
            height=2.5,
            dxfattribs={"insert": (96, 44, 0)},
            register_field_list=True,
        )

    def _add_multileader_fields(self) -> None:
        """Add MTEXT-content MULTILEADER fields."""
        self._add_multileader("Author", Vec2(88, 36))
        self._add_multileader("ProjectCode", Vec2(88, 28), dwgprops=True)

    def _add_expression_field(self) -> None:
        """Add an AcExpr field made from two object-property child fields."""
        expression = "(%<\\_FldIdx 0>%+%<\\_FldIdx 1>%)"
        children = [self._line_length_field(), self._circle_radius_field()]
        self._add_label("Length + Radius:", (0, 30, 0))
        self.msp.add_mtext_acexpr_field(
            expression,
            children,
            value=13.0,
            display="13.0000",
            dxfattribs=self._mtext_attribs(30, 30),
            register_field_list=True,
        )

    def _add_table_fields(self) -> None:
        """Add object-backed fields to ACAD_TABLE text cells."""
        table = self.msp.add_table(
            (0, -20),
            [
                ["FIELD", "VALUE"],
                ["AcVar", "----"],
                ["DWGPROPS", "VALUE-123"],
                ["AcObjProp", "10.0000"],
            ],
            col_widths=[28.0, 28.0],
        )
        table.new_cell_acvar_field(
            1, 1, "Author", text="----", register_field_list=True
        )
        table.new_cell_dwgprops_field(
            2, 1, "ProjectCode", text="VALUE-123", register_field_list=True
        )
        table.new_cell_acobjprop_field(
            3, 1, self.line, "Length", text="10.0000", register_field_list=True
        )

    def _add_multileader(
        self, name: str, insert: Vec2, *, dwgprops: bool = False
    ) -> None:
        """Add a MULTILEADER with either AcVar or DWGPROPS content."""
        builder = self.msp.add_multileader_mtext("Standard")
        builder.set_content("FIELD")
        builder.build(insert=insert)
        if dwgprops:
            builder.multileader.new_dwgprops_field(
                name, text="VALUE-123", register_field_list=True
            )
        else:
            builder.multileader.new_acvar_field(
                name, text="----", register_field_list=True
            )

    def _add_label(self, text: str, insert: tuple[float, float, float]) -> None:
        """Add an MTEXT label."""
        self.msp.add_mtext(
            text, dxfattribs={"insert": insert, "char_height": 2.5, "width": 28}
        )

    def _add_text_label(self, text: str, insert: tuple[float, float, float]) -> None:
        """Add a TEXT label."""
        self.msp.add_text(text, height=2.5, dxfattribs={"insert": insert})

    def _mtext_attribs(self, x: float, y: float) -> dict[str, object]:
        """Return common MTEXT attributes for field hosts."""
        return {"insert": (x, y, 0), "char_height": 2.5, "width": 30}

    def _line_length_field(self) -> Field:
        """Return a detached child field for the line length."""
        field = Field()
        field.set_acobjprop(self.line, "Length", value=10.0, display="10.0000")
        return field

    def _circle_radius_field(self) -> Field:
        """Return a detached child field for the circle radius."""
        field = Field()
        field.set_acobjprop(self.circle, "Radius", value=3.0, display="3.0000")
        return field


def build_doc() -> Drawing:
    """Build and return the field demo document."""
    return FieldDemoBuilder().build()


def iter_primary_fields(doc: Drawing) -> Iterator[tuple[str, Field]]:
    """Yield primary fields hosted by modelspace entities and table cells."""
    for entity in doc.modelspace().query("TEXT MTEXT MULTILEADER"):
        field = entity.get_primary_field()
        if field is not None:
            yield f"{entity.dxftype()} #{entity.dxf.handle}", field
    yield from iter_table_cell_fields(doc)


def iter_table_cell_fields(doc: Drawing) -> Iterator[tuple[str, Field]]:
    """Yield primary fields hosted by ACAD_TABLE cells."""
    for table in doc.modelspace().query("ACAD_TABLE"):
        for row_index, row in enumerate(table.rows()):
            for col_index, _cell in enumerate(row):
                field = table.get_cell_primary_field(row_index, col_index)
                if field is not None:
                    label = f"ACAD_TABLE #{table.dxf.handle}[{row_index}, {col_index}]"
                    yield label, field


def print_field_summary(doc: Drawing) -> None:
    """Print field evaluator IDs and field codes for quick inspection."""
    for host, field in iter_primary_fields(doc):
        print(f"{host}: {field.evaluator_id} -> {field.field_code}")


def main() -> None:
    """Create the field demo DXF and print hosted field metadata."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "fields_api_demo.dxf"
    doc = build_doc()
    print_field_summary(doc)
    doc.saveas(path)
    print(f"created: {path}")


if __name__ == "__main__":
    main()
