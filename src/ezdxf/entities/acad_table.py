# Copyright (c) 2019-2024 Manfred Moitzi
# License: MIT License
from __future__ import annotations
from typing import TYPE_CHECKING, Any, Iterable, Optional, Iterator, Sequence, cast
from typing_extensions import Self
import copy
from dataclasses import dataclass, field
from ezdxf.math import Vec3, Matrix44
from ezdxf.lldxf.tags import Tags, group_tags
from ezdxf.lldxf.types import dxftag
from ezdxf.tools.text import MTextEditor, plain_text
from ezdxf.lldxf.attributes import (
    DXFAttr,
    DXFAttributes,
    DefSubclass,
    XType,
    group_code_mapping,
)
from ezdxf.lldxf import const
from ezdxf.entities import factory
from .dxfentity import base_class, SubclassProcessor, DXFEntity, DXFTagStorage
from .dxfgfx import DXFGraphic, acdb_entity
from .dxfobj import DXFObject, Field
from .objectcollection import ObjectCollection
from .copy import default_copy

if TYPE_CHECKING:
    from ezdxf.entities import DXFNamespace
    from ezdxf.lldxf.tagwriter import AbstractTagWriter
    from ezdxf.document import Drawing

__all__ = [
    "AcadTable",
    "AcadTableBlockAttributeValue",
    "AcadTableContentFormat",
    "AcadTableCell",
    "AcadTableData",
    "AcadTableFormat",
    "TableStyleCellStyle",
    "TableStyleData",
    "AcadTableLinkedCell",
    "AcadTableLinkedCellContent",
    "AcadTableLinkedColumn",
    "AcadTableLinkedData",
    "AcadTableLinkedRow",
    "AcadTableBlockContent",
    "TableContent",
    "CellStyleMap",
    "TableGeometry",
    "TableStyle",
    "TableStyleManager",
    "acad_table_to_block",
    "read_acad_table_content",
]


CELL_OVERRIDE_BASE = 262144
CELL_OVERRIDE_ALIGNMENT = 1
CELL_OVERRIDE_LOCAL_COLOR = 2
CELL_OVERRIDE_LOCAL_TRUE_COLOR = 4
CELL_OVERRIDE_TEXT_STYLE = 16
CELL_OVERRIDE_TEXT_HEIGHT = 32


@dataclass
class AcadTableBlockAttributeValue:
    handle: str
    text: str = ""
    index: int = 0


@dataclass
class AcadTableContentFormat:
    flags90: int = 0
    flags91: int = 0
    flags92: int = 0
    flags93: int = 0
    format_string: str = ""
    margin: float = 0.0
    text_height: Optional[float] = None
    unknown94: Optional[int] = None
    color62: Optional[int] = None
    style_handle: Optional[str] = None
    block_scale: Optional[float] = None


@dataclass
class AcadTableFormat:
    kind: str = ""
    flags90: int = 0
    alignment: Optional[int] = None
    flags91: int = 0
    flags92: int = 0
    color62: Optional[int] = None
    flags93: int = 0
    table_cell_type171: Optional[int] = None
    flags94: Optional[int] = None
    content_format: Optional[AcadTableContentFormat] = None


@dataclass
class AcadTableLinkedCellContent:
    content_type: int = 0
    text: str = ""
    block_record_handle: Optional[str] = None
    block_scale: Optional[float] = None
    alignment: Optional[int] = None
    block_attributes: list[AcadTableBlockAttributeValue] = field(default_factory=list)
    content_format: Optional[AcadTableContentFormat] = None

    @property
    def is_block_content(self) -> bool:
        return self.content_type == 4


@dataclass
class AcadTableLinkedColumn:
    index: int
    width: float = 0.0
    table_format: Optional[AcadTableFormat] = None


@dataclass
class AcadTableLinkedRow:
    index: int
    height: float = 0.0
    table_format: Optional[AcadTableFormat] = None


@dataclass
class AcadTableLinkedCell:
    row: int
    col: int
    contents: list[AcadTableLinkedCellContent] = field(default_factory=list)
    table_format: Optional[AcadTableFormat] = None
    raw_table_flags90: Optional[int] = None
    raw_table_flags91: Optional[int] = None
    wrapper_block_record_handle: Optional[str] = None
    wrapper_block_name: Optional[str] = None
    wrapper_margin_x: Optional[float] = None
    wrapper_margin_y: Optional[float] = None


@dataclass
class AcadTableLinkedData:
    n_rows: int = 0
    n_cols: int = 0
    columns: list[AcadTableLinkedColumn] = field(default_factory=list)
    rows_meta: list[AcadTableLinkedRow] = field(default_factory=list)
    cells: list[AcadTableLinkedCell] = field(default_factory=list)

    @classmethod
    def from_tags(cls, tags: Tags, *, n_rows: int = 0, n_cols: int = 0) -> "AcadTableLinkedData":
        data = cls(n_rows=n_rows, n_cols=n_cols)
        cell_index = 0
        row_index = 0
        column_index = 0
        index = 0
        while index < len(tags):
            tag = tags[index]
            if tag.code == 90 and data.n_cols == 0 and not data.columns:
                data.n_cols = int(tag.value)
                index += 1
                continue
            if tag.code == 91 and data.n_rows == 0 and not data.cells:
                data.n_rows = int(tag.value)
                index += 1
                continue
            if tag.code == 1 and tag.value == "FORMATTEDTABLEDATACOLUMN_BEGIN":
                end = _find_marker_end(tags, index + 1, 309, "FORMATTEDTABLEDATACOLUMN_END")
                table_format = _parse_table_format(Tags(tags[index : end + 1]))
                if column_index < len(data.columns):
                    data.columns[column_index].table_format = table_format
                else:
                    data.columns.append(AcadTableLinkedColumn(index=column_index, table_format=table_format))
                index = end + 1
                continue
            if tag.code == 1 and tag.value == "TABLECOLUMN_BEGIN":
                end = _find_marker_end(tags, index + 1, 309, "TABLECOLUMN_END")
                column = _parse_linked_table_column(Tags(tags[index : end + 1]), column_index)
                if column_index < len(data.columns):
                    data.columns[column_index].width = column.width
                else:
                    data.columns.append(column)
                column_index += 1
                index = end + 1
                continue
            if tag.code == 1 and tag.value == "LINKEDTABLEDATACELL_BEGIN":
                end = _find_marker_end(tags, index + 1, 309, "LINKEDTABLEDATACELL_END")
                cell_tags = Tags(tags[index : end + 1])
                data.cells.append(
                    _parse_linked_table_cell(cell_tags, cell_index, data.n_cols)
                )
                cell_index += 1
                index = end + 1
                continue
            if tag.code == 1 and tag.value == "FORMATTEDTABLEDATACELL_BEGIN":
                end = _find_marker_end(tags, index + 1, 309, "FORMATTEDTABLEDATACELL_END")
                if len(data.cells):
                    data.cells[-1].table_format = _parse_table_format(Tags(tags[index : end + 1]))
                index = end + 1
                continue
            if tag.code == 1 and tag.value == "TABLECELL_BEGIN":
                end = _find_marker_end(tags, index + 1, 309, "TABLECELL_END")
                if len(data.cells):
                    raw90, raw91, margin_x, margin_y, wrapper_block_record_handle = _parse_table_cell_wrapper(
                        Tags(tags[index : end + 1])
                    )
                    data.cells[-1].raw_table_flags90 = raw90
                    data.cells[-1].raw_table_flags91 = raw91
                    data.cells[-1].wrapper_margin_x = margin_x
                    data.cells[-1].wrapper_margin_y = margin_y
                    data.cells[-1].wrapper_block_record_handle = wrapper_block_record_handle
                index = end + 1
                continue
            if tag.code == 1 and tag.value == "FORMATTEDTABLEDATAROW_BEGIN":
                end = _find_marker_end(tags, index + 1, 309, "FORMATTEDTABLEDATAROW_END")
                table_format = _parse_table_format(Tags(tags[index : end + 1]))
                if row_index < len(data.rows_meta):
                    data.rows_meta[row_index].table_format = table_format
                else:
                    data.rows_meta.append(AcadTableLinkedRow(index=row_index, table_format=table_format))
                index = end + 1
                continue
            if tag.code == 1 and tag.value == "TABLEROW_BEGIN":
                end = _find_marker_end(tags, index + 1, 309, "TABLEROW_END")
                row = _parse_linked_table_row(Tags(tags[index : end + 1]), row_index)
                if row_index < len(data.rows_meta):
                    data.rows_meta[row_index].height = row.height
                else:
                    data.rows_meta.append(row)
                row_index += 1
                index = end + 1
                continue
            index += 1
        return data

    def rows(self) -> list[list[AcadTableLinkedCell]]:
        if self.n_rows <= 0 or self.n_cols <= 0:
            return [list(self.cells)] if len(self.cells) else []
        rows: list[list[AcadTableLinkedCell]] = []
        for index in range(self.n_rows):
            start = index * self.n_cols
            rows.append(self.cells[start : start + self.n_cols])
        return rows

    def get_cell(self, row: int, col: int) -> AcadTableLinkedCell:
        index = row * max(self.n_cols, 1) + col
        return self.cells[index]

    def get_row(self, row: int) -> AcadTableLinkedRow:
        return self.rows_meta[row]

    def get_column(self, col: int) -> AcadTableLinkedColumn:
        return self.columns[col]


@dataclass
class AcadTableCell:
    row: int
    col: int
    cell_type: int = 1
    flags: int = 0
    merged_value: int = 0
    autofit_flag: int = 0
    border_width: int = 0
    border_height: int = 0
    override_flags: int = 0
    virtual_edge_flag: int = 0
    rotation: float = 0.0
    text: str = ""
    block_record_handle: Optional[str] = None
    block_scale: float = 1.0
    block_attribute_count: int = 0
    text_height: Optional[float] = None
    alignment: Optional[int] = None
    text_style: Optional[str] = None
    content_color: Optional[int] = None
    fill_color: Optional[int] = None
    fill_true_color: Optional[int] = None
    fill_enabled: Optional[int] = None
    field_handle: Optional[str] = None
    field_tags: Optional[Tags] = None
    field_display_text: str = ""
    block_attributes: list[AcadTableBlockAttributeValue] = field(default_factory=list)
    linked_cell_contents: list[AcadTableLinkedCellContent] = field(default_factory=list)
    linked_text: str = ""
    wrapper_block_record_handle: Optional[str] = None
    wrapper_block_name: Optional[str] = None
    wrapper_margin_x: Optional[float] = None
    wrapper_margin_y: Optional[float] = None

    @property
    def is_text_cell(self) -> bool:
        return self.cell_type == 1

    @property
    def is_block_cell(self) -> bool:
        return self.cell_type == 2

    @property
    def has_block_attributes(self) -> bool:
        return len(self.block_attributes) > 0

    @property
    def has_field(self) -> bool:
        return self.field_handle is not None

    def set_text_height(self, value: Optional[float]) -> None:
        if value is None:
            self.text_height = None
            self.override_flags &= ~CELL_OVERRIDE_TEXT_HEIGHT
        else:
            value = float(value)
            if value <= 0.0:
                raise const.DXFValueError("text height has to be greater than 0")
            self.text_height = value
            self.override_flags |= CELL_OVERRIDE_BASE | CELL_OVERRIDE_TEXT_HEIGHT

    def set_alignment(self, value: Optional[int]) -> None:
        if value is None:
            self.alignment = None
            self.override_flags &= ~CELL_OVERRIDE_ALIGNMENT
        else:
            value = int(value)
            if value < 1 or value > 9:
                raise const.DXFValueError("alignment has to be in range 1..9")
            self.alignment = value
            self.override_flags |= CELL_OVERRIDE_BASE | CELL_OVERRIDE_ALIGNMENT

    def set_content_color(
        self, aci: Optional[int], true_color: Optional[int] = None
    ) -> None:
        content = plain_text(self.text)
        if aci is None:
            self.text = content
            self.content_color = None
            return
        aci = int(aci)
        if aci < 0 or aci > 256:
            raise const.DXFValueError("ACI color has to be in range 0..256")
        editor = MTextEditor().aci(aci)
        if true_color is not None:
            true_color = int(true_color)
            if true_color < 0:
                raise const.DXFValueError("true color has to be greater than 0")
            editor.append(rf"\c{true_color};")
        editor.append(content)
        self.text = "{" + str(editor) + "}"
        self.content_color = aci

    def set_text_content(self, text: str) -> None:
        self.text = str(text)
        self.field_handle = None
        self.field_tags = None
        self.field_display_text = ""

    def set_fill_color(
        self, aci: Optional[int], true_color: Optional[int] = None
    ) -> None:
        if aci is None and true_color is None:
            self.fill_color = None
            self.fill_true_color = None
            self.fill_enabled = None
            self.override_flags &= ~(
                CELL_OVERRIDE_LOCAL_COLOR | CELL_OVERRIDE_LOCAL_TRUE_COLOR
            )
            return
        if aci is None:
            raise const.DXFValueError(
                "ACI color is required for local fill override"
            )
        aci = int(aci)
        if aci < 0 or aci > 256:
            raise const.DXFValueError("ACI color has to be in range 0..256")
        self.fill_color = aci
        self.fill_enabled = 0
        self.override_flags |= CELL_OVERRIDE_BASE | CELL_OVERRIDE_LOCAL_COLOR
        if true_color is None:
            self.fill_true_color = None
            self.override_flags &= ~CELL_OVERRIDE_LOCAL_TRUE_COLOR
        else:
            true_color = int(true_color)
            if true_color < 0:
                raise const.DXFValueError(
                    "true color has to be greater than or equal to 0"
                )
            self.fill_true_color = true_color
            self.override_flags |= CELL_OVERRIDE_LOCAL_TRUE_COLOR

    def set_fill_enabled(self, enabled: bool) -> None:
        if enabled:
            if self.fill_color in (None, 0):
                raise const.DXFValueError(
                    "enabling fill requires a non-zero fill color"
                )
            self.fill_enabled = 0
            self.override_flags |= CELL_OVERRIDE_BASE | CELL_OVERRIDE_LOCAL_COLOR
            return
        self.fill_color = 0
        self.fill_true_color = None
        self.fill_enabled = 1
        self.override_flags |= (
            CELL_OVERRIDE_BASE
            | CELL_OVERRIDE_LOCAL_COLOR
            | CELL_OVERRIDE_LOCAL_TRUE_COLOR
        )

    def clear_fill(self) -> None:
        self.set_fill_enabled(False)

    def set_text_color(
        self, aci: Optional[int], true_color: Optional[int] = None
    ) -> None:
        # Backwards-compatible alias for the validated semantic fill override.
        self.set_fill_color(aci, true_color)

    def set_text_style(self, name: Optional[str]) -> None:
        if name is None:
            self.text_style = None
            self.override_flags &= ~CELL_OVERRIDE_TEXT_STYLE
        else:
            self.text_style = str(name)
            if len(self.text_style) == 0:
                raise const.DXFValueError("text style name can not be empty")
            self.override_flags |= CELL_OVERRIDE_BASE | CELL_OVERRIDE_TEXT_STYLE

    def set_block(
        self, block_record_handle: str, *, block_scale: float = 1.0, alignment: int = 1
    ) -> None:
        if self.cell_type == 1 and len(self.text):
            self.linked_text = self.text
        block_record_handle = str(block_record_handle)
        if len(block_record_handle) == 0:
            raise const.DXFValueError("block record handle can not be empty")
        block_scale = float(block_scale)
        if block_scale <= 0.0:
            raise const.DXFValueError("block scale has to be greater than 0")
        self.cell_type = 2
        self.block_record_handle = block_record_handle
        self.block_scale = block_scale
        self.block_attribute_count = 0
        self.text = ""
        self.block_attributes = []
        self.linked_cell_contents = []
        self.wrapper_block_record_handle = None
        self.field_handle = None
        self.field_tags = None
        self.field_display_text = ""
        self.text_height = None
        self.text_style = None
        self.content_color = None
        self.fill_color = None
        self.fill_true_color = None
        self.fill_enabled = None
        self.set_alignment(alignment)


@dataclass
class AcadTableData:
    n_rows: int = 0
    n_cols: int = 0
    row_heights: list[float] = field(default_factory=list)
    col_widths: list[float] = field(default_factory=list)
    cells: list[AcadTableCell] = field(default_factory=list)
    suppress_title: Optional[int] = None
    suppress_column_header: Optional[int] = None
    trailing_tags: Tags = field(default_factory=Tags)

    def rows(self) -> list[list[AcadTableCell]]:
        if self.n_rows <= 0 or self.n_cols <= 0:
            return [list(self.cells)] if len(self.cells) else []
        rows: list[list[AcadTableCell]] = []
        for index in range(self.n_rows):
            start = index * self.n_cols
            rows.append(self.cells[start : start + self.n_cols])
        return rows

    def text_content(self) -> list[list[str]]:
        return [[cell.text for cell in row] for row in self.rows()]


@dataclass
class TableStyleCellStyle:
    text_style: str = ""
    text_height: float = 0.0
    alignment: int = 0
    text_color: int = 0
    fill_color: int = 0
    fill_enabled: int = 0
    data_type: int = 0
    unit_type: int = 0
    format_string: str = ""
    border_lineweights: dict[str, int] = field(default_factory=dict)
    border_visibility: dict[str, int] = field(default_factory=dict)
    border_colors: dict[str, int] = field(default_factory=dict)


@dataclass
class TableStyleData:
    flow_direction: int = 0
    flags: int = 0
    horizontal_cell_margin: float = 0.0
    vertical_cell_margin: float = 0.0
    suppress_title: int = 0
    suppress_column_header: int = 0
    cell_styles: list[TableStyleCellStyle] = field(default_factory=list)
    trailing_tags: Tags = field(default_factory=Tags)

    @property
    def title_style(self) -> Optional[TableStyleCellStyle]:
        return self.cell_styles[0] if len(self.cell_styles) > 0 else None

    @property
    def header_style(self) -> Optional[TableStyleCellStyle]:
        return self.cell_styles[1] if len(self.cell_styles) > 1 else None

    @property
    def data_style(self) -> Optional[TableStyleCellStyle]:
        return self.cell_styles[2] if len(self.cell_styles) > 2 else None


def _parse_acad_table_content(dxf, tags: Tags) -> AcadTableData:
    start = 1 if len(tags) and tags[0].code == 100 else 0
    data = AcadTableData()
    set_attrib = dxf.unprotected_set

    index = start
    version_loaded = False
    while index < len(tags):
        tag = tags[index]
        code = tag.code
        if code in (141, 142, 171):
            break
        if code == 280:
            if not version_loaded:
                set_attrib("version", int(tag.value))
                version_loaded = True
            elif data.suppress_title is None:
                data.suppress_title = int(tag.value)
        elif code == 281:
            if data.suppress_column_header is None:
                data.suppress_column_header = int(tag.value)
        elif code == 342:
            set_attrib("table_style_id", str(tag.value))
        elif code == 343:
            set_attrib("block_record_handle", str(tag.value))
        elif code == 11:
            set_attrib("horizontal_direction", tag.value)
        elif code == 90 and not dxf.hasattr("table_value"):
            set_attrib("table_value", int(tag.value))
        elif code == 91 and not dxf.hasattr("n_rows"):
            set_attrib("n_rows", int(tag.value))
        elif code == 92 and not dxf.hasattr("n_cols"):
            set_attrib("n_cols", int(tag.value))
        elif code == 93 and not dxf.hasattr("override_flag"):
            set_attrib("override_flag", int(tag.value))
        elif code == 94 and not dxf.hasattr("border_color_override_flag"):
            set_attrib("border_color_override_flag", int(tag.value))
        elif code == 95 and not dxf.hasattr("border_lineweight_override_flag"):
            set_attrib("border_lineweight_override_flag", int(tag.value))
        elif code == 96 and not dxf.hasattr("border_visibility_override_flag"):
            set_attrib("border_visibility_override_flag", int(tag.value))
        index += 1

    data.n_rows = int(dxf.get("n_rows", 0))
    data.n_cols = int(dxf.get("n_cols", 0))

    while index < len(tags) and tags[index].code == 141:
        data.row_heights.append(float(tags[index].value))
        index += 1
    while index < len(tags) and tags[index].code == 142:
        data.col_widths.append(float(tags[index].value))
        index += 1

    expected_cells = data.n_rows * data.n_cols
    cells: list[AcadTableCell] = []
    while index < len(tags) and (expected_cells == 0 or len(cells) < expected_cells):
        if tags[index].code != 171:
            break
        start_index = index
        index += 1
        while index < len(tags) and tags[index].code != 171:
            index += 1
        cells.append(_parse_acad_table_cell(tags[start_index:index], len(cells), data.n_cols))

    data.cells = cells
    data.trailing_tags = Tags(tags[index:])
    return data


def _parse_acad_table_cell(tags: Tags, cell_index: int, n_cols: int) -> AcadTableCell:
    row = cell_index // n_cols if n_cols else 0
    col = cell_index % n_cols if n_cols else cell_index
    cell = AcadTableCell(row=row, col=col)

    in_value = False
    plain_value_tags: list[str] = []
    chunked_value_tags: list[str] = []
    for code, value in tags:
        if in_value:
            if code == 304 and value == "ACVALUE_END":
                in_value = False
                continue
            if code == 302:
                chunked_value_tags.append(str(value))
            elif code in (1, 2, 3):
                plain_value_tags.append(str(value))
            continue

        if code == 171 and cell.cell_type == 1:
            cell.cell_type = int(value)
        elif code == 172:
            cell.flags = int(value)
        elif code == 173:
            cell.merged_value = int(value)
        elif code == 174:
            cell.autofit_flag = int(value)
        elif code == 175:
            cell.border_width = int(value)
        elif code == 176:
            cell.border_height = int(value)
        elif code == 91:
            cell.override_flags = int(value)
        elif code == 178:
            cell.virtual_edge_flag = int(value)
        elif code == 145:
            cell.rotation = float(value)
        elif code == 340:
            cell.block_record_handle = str(value)
        elif code == 144:
            cell.block_scale = float(value)
        elif code == 179:
            cell.block_attribute_count = int(value)
        elif code == 140:
            cell.text_height = float(value)
        elif code == 170:
            cell.alignment = int(value)
        elif code == 7:
            cell.text_style = str(value)
        elif code == 64:
            cell.content_color = int(value)
        elif code == 63:
            cell.fill_color = int(value)
        elif code in (420, 421):
            cell.fill_true_color = int(value)
        elif code == 283:
            cell.fill_enabled = int(value)
        elif code == 344:
            cell.field_handle = str(value)
        elif code == 301 and value == "CELL_VALUE":
            in_value = True

    cell.text = "".join(chunked_value_tags or plain_value_tags)
    return cell


def _find_marker_end(tags: Tags, start: int, end_code: int, end_value: str) -> int:
    index = start
    while index < len(tags):
        tag = tags[index]
        if tag.code == end_code and tag.value == end_value:
            return index
        index += 1
    raise const.DXFStructureError(f"missing marker end tag: {end_value}")


def _parse_content_format(tags: Tags) -> AcadTableContentFormat:
    content = AcadTableContentFormat()
    for code, value in tags:
        if code == 90 and content.flags90 == 0:
            content.flags90 = int(value)
        elif code == 91:
            content.flags91 = int(value)
        elif code == 92:
            content.flags92 = int(value)
        elif code == 93:
            content.flags93 = int(value)
        elif code == 300 and not content.format_string and value not in ("CONTENTFORMAT", ""):
            content.format_string = str(value)
        elif code == 40:
            content.margin = float(value)
        elif code == 140:
            content.text_height = float(value)
        elif code == 94:
            content.unknown94 = int(value)
        elif code == 62:
            content.color62 = int(value)
        elif code == 340:
            content.style_handle = str(value)
        elif code == 144:
            content.block_scale = float(value)
    return content


def _parse_table_format(tags: Tags) -> AcadTableFormat:
    table = AcadTableFormat()
    index = 0
    while index < len(tags):
        code, value = tags[index]
        if code == 300 and value in ("COLUMNTABLEFORMAT", "ROWTABLEFORMAT", "CELLTABLEFORMAT"):
            table.kind = str(value)
        elif code == 90 and table.flags90 == 0:
            table.flags90 = int(value)
        elif code == 170 and table.alignment is None:
            table.alignment = int(value)
        elif code == 91:
            table.flags91 = int(value)
        elif code == 92:
            table.flags92 = int(value)
        elif code == 62:
            table.color62 = int(value)
        elif code == 93:
            table.flags93 = int(value)
        elif code == 171:
            table.table_cell_type171 = int(value)
        elif code == 94:
            table.flags94 = int(value)
        elif code == 1 and tags[index].value == "CONTENTFORMAT_BEGIN":
            end = _find_marker_end(tags, index + 1, 309, "CONTENTFORMAT_END")
            table.content_format = _parse_content_format(Tags(tags[index : end + 1]))
            index = end
        index += 1
    return table


def _parse_linked_table_column(tags: Tags, index: int) -> AcadTableLinkedColumn:
    column = AcadTableLinkedColumn(index=index)
    for code, value in tags:
        if code == 40:
            column.width = float(value)
            break
    return column


def _parse_linked_table_row(tags: Tags, index: int) -> AcadTableLinkedRow:
    row = AcadTableLinkedRow(index=index)
    for code, value in tags:
        if code == 40:
            row.height = float(value)
            break
    return row


def _parse_table_cell_wrapper(
    tags: Tags,
) -> tuple[Optional[int], Optional[int], Optional[float], Optional[float], Optional[str]]:
    raw90: Optional[int] = None
    raw91: Optional[int] = None
    margin_x: Optional[float] = None
    margin_y: Optional[float] = None
    wrapper_block_record_handle: Optional[str] = None
    for code, value in tags:
        if code == 90 and raw90 is None:
            raw90 = int(value)
        elif code == 91 and raw91 is None:
            raw91 = int(value)
        elif code == 40 and margin_x is None:
            margin_x = float(value)
        elif code == 41 and margin_y is None:
            margin_y = float(value)
        elif code == 330 and wrapper_block_record_handle is None:
            wrapper_block_record_handle = str(value)
    return raw90, raw91, margin_x, margin_y, wrapper_block_record_handle


def _parse_linked_table_cell(tags: Tags, cell_index: int, n_cols: int) -> AcadTableLinkedCell:
    row = cell_index // n_cols if n_cols else 0
    col = cell_index % n_cols if n_cols else cell_index
    cell = AcadTableLinkedCell(row=row, col=col)

    index = 0
    while index < len(tags):
        tag = tags[index]
        if tag.code == 1 and tag.value == "CELLCONTENT_BEGIN":
            end = _find_marker_end(tags, index + 1, 309, "CELLCONTENT_END")
            cell.contents.append(_parse_linked_cell_content(Tags(tags[index : end + 1])))
            index = end + 1
            continue
        index += 1
    return cell


def _parse_linked_cell_content(tags: Tags) -> AcadTableLinkedCellContent:
    content = AcadTableLinkedCellContent()
    pending_attr: Optional[AcadTableBlockAttributeValue] = None
    pending_handle: Optional[str] = None
    in_value = False
    plain_value_tags: list[str] = []
    chunked_value_tags: list[str] = []

    for code, value in tags:
        if in_value:
            if code == 304 and value == "ACVALUE_END":
                in_value = False
                continue
            if code == 302:
                chunked_value_tags.append(str(value))
            elif code in (1, 2, 3):
                plain_value_tags.append(str(value))
            continue

        if code == 90 and content.content_type == 0:
            content.content_type = int(value)
        elif code == 340:
            content.block_record_handle = str(value)
        elif code == 144:
            content.block_scale = float(value)
        elif code == 170:
            content.alignment = int(value)
        elif code == 330:
            pending_handle = str(value)
        elif code in (300, 301) and value == "VALUE":
            in_value = True
        elif code == 301 and pending_handle is not None:
            pending_attr = AcadTableBlockAttributeValue(handle=pending_handle, text=str(value))
            content.block_attributes.append(pending_attr)
            pending_handle = None
        elif code == 92 and pending_attr is not None:
            pending_attr.index = int(value)
            pending_attr = None

    content.text = "".join(chunked_value_tags or plain_value_tags)
    return content


def _parse_table_style(tags: Tags) -> TableStyleData:
    start = 1 if len(tags) and tags[0].code == 100 else 0
    data = TableStyleData()
    index = start

    if index < len(tags) and tags[index].code == 280:
        index += 1  # version tag handled by dxfattribs loader
    if index < len(tags) and tags[index].code == 3:
        index += 1  # name tag handled by dxfattribs loader
    if index < len(tags) and tags[index].code == 70:
        data.flow_direction = int(tags[index].value)
        index += 1
    if index < len(tags) and tags[index].code == 71:
        data.flags = int(tags[index].value)
        index += 1
    if index < len(tags) and tags[index].code == 40:
        data.horizontal_cell_margin = float(tags[index].value)
        index += 1
    if index < len(tags) and tags[index].code == 41:
        data.vertical_cell_margin = float(tags[index].value)
        index += 1
    if index < len(tags) and tags[index].code == 280:
        data.suppress_title = int(tags[index].value)
        index += 1
    if index < len(tags) and tags[index].code == 281:
        data.suppress_column_header = int(tags[index].value)
        index += 1

    while index < len(tags):
        if tags[index].code != 7:
            break
        cell_style = TableStyleCellStyle(text_style=str(tags[index].value))
        index += 1
        if index < len(tags) and tags[index].code == 140:
            cell_style.text_height = float(tags[index].value)
            index += 1
        if index < len(tags) and tags[index].code == 170:
            cell_style.alignment = int(tags[index].value)
            index += 1
        if index < len(tags) and tags[index].code == 62:
            cell_style.text_color = int(tags[index].value)
            index += 1
        if index < len(tags) and tags[index].code == 63:
            cell_style.fill_color = int(tags[index].value)
            index += 1
        if index < len(tags) and tags[index].code == 283:
            cell_style.fill_enabled = int(tags[index].value)
            index += 1
        if index < len(tags) and tags[index].code == 90:
            cell_style.data_type = int(tags[index].value)
            index += 1
        if index < len(tags) and tags[index].code == 91:
            cell_style.unit_type = int(tags[index].value)
            index += 1
        if index < len(tags) and tags[index].code == 1:
            cell_style.format_string = str(tags[index].value)
            index += 1
        for code, name in ((274, "top"), (275, "right"), (276, "bottom"), (277, "left"), (278, "vertical"), (279, "horizontal")):
            if index < len(tags) and tags[index].code == code:
                cell_style.border_lineweights[name] = int(tags[index].value)
                index += 1
            if index < len(tags) and tags[index].code == code + 10:
                cell_style.border_visibility[name] = int(tags[index].value)
                index += 1
            color_code = 64 if code == 274 else 65 if code == 275 else 66 if code == 276 else 67 if code == 277 else 68 if code == 278 else 69
            if index < len(tags) and tags[index].code == color_code:
                cell_style.border_colors[name] = int(tags[index].value)
                index += 1
        data.cell_styles.append(cell_style)

    data.trailing_tags = Tags(tags[index:])
    return data


def _default_table_style_data() -> TableStyleData:
    def make_style(text_height: float, alignment: int) -> TableStyleCellStyle:
        return TableStyleCellStyle(
            text_style="Standard",
            text_height=text_height,
            alignment=alignment,
            text_color=0,
            fill_color=7,
            fill_enabled=0,
            data_type=512,
            unit_type=0,
            format_string="",
            border_lineweights={
                "top": -2,
                "right": -2,
                "bottom": -2,
                "left": -2,
                "vertical": -2,
                "horizontal": -2,
            },
            border_visibility={
                "top": 1,
                "right": 1,
                "bottom": 1,
                "left": 1,
                "vertical": 1,
                "horizontal": 1,
            },
            border_colors={
                "top": 0,
                "right": 0,
                "bottom": 0,
                "left": 0,
                "vertical": 0,
                "horizontal": 0,
            },
        )

    return TableStyleData(
        flow_direction=0,
        flags=0,
        horizontal_cell_margin=1.5,
        vertical_cell_margin=1.5,
        suppress_title=0,
        suppress_column_header=0,
        cell_styles=[
            make_style(4.5, 2),
            make_style(6.0, 5),
            make_style(4.5, 5),
        ],
    )


def _export_table_style_data(tagwriter: AbstractTagWriter, data: TableStyleData) -> None:
    def export_cell_style(cell_style: TableStyleCellStyle) -> None:
        write_tag2(7, cell_style.text_style)
        write_tag2(140, cell_style.text_height)
        write_tag2(170, cell_style.alignment)
        write_tag2(62, cell_style.text_color)
        write_tag2(63, cell_style.fill_color)
        write_tag2(283, cell_style.fill_enabled)
        write_tag2(90, cell_style.data_type)
        write_tag2(91, cell_style.unit_type)
        write_tag2(1, cell_style.format_string)
        for code, name in ((274, "top"), (275, "right"), (276, "bottom"), (277, "left"), (278, "vertical"), (279, "horizontal")):
            write_tag2(code, cell_style.border_lineweights.get(name, -2))
            write_tag2(code + 10, cell_style.border_visibility.get(name, 1))
            color_code = 64 if code == 274 else 65 if code == 275 else 66 if code == 276 else 67 if code == 277 else 68 if code == 278 else 69
            write_tag2(color_code, cell_style.border_colors.get(name, 0))

    write_tag2 = tagwriter.write_tag2
    write_tag2(280, 0)
    write_tag2(70, data.flow_direction)
    write_tag2(71, data.flags)
    write_tag2(40, data.horizontal_cell_margin)
    write_tag2(41, data.vertical_cell_margin)
    write_tag2(280, data.suppress_title)
    write_tag2(281, data.suppress_column_header)
    for cell_style in data.cell_styles:
        export_cell_style(cell_style)
    if len(data.trailing_tags):
        tagwriter.write_tags(data.trailing_tags)


acdb_block_reference = DefSubclass(
    "AcDbBlockReference",
    {
        # Block name: an anonymous block begins with a *T value
        "geometry": DXFAttr(2),
        # Insertion point:
        "insert": DXFAttr(10, xtype=XType.point3d, default=Vec3(0, 0, 0)),
    },
)
acdb_block_reference_group_codes = group_code_mapping(acdb_block_reference)

acdb_table = DefSubclass(
    "AcDbTable",
    {
        # Table data version number: 0 = 2010
        "version": DXFAttr(280),
        # Hard of the TABLESTYLE object:
        "table_style_id": DXFAttr(342),
        # Handle of the associated anonymous BLOCK containing the graphical
        # representation:
        "block_record_handle": DXFAttr(343),
        # Horizontal direction vector:
        "horizontal_direction": DXFAttr(11),
        # Flag for table value (unsigned integer):
        "table_value": DXFAttr(90),
        # Number of rows:
        "n_rows": DXFAttr(91),
        # Number of columns:
        "n_cols": DXFAttr(92),
        # Flag for an override:
        "override_flag": DXFAttr(93),
        # Flag for an override of border color:
        "border_color_override_flag": DXFAttr(94),
        # Flag for an override of border lineweight:
        "border_lineweight_override_flag": DXFAttr(95),
        # Flag for an override of border visibility:
        "border_visibility_override_flag": DXFAttr(96),
        # 141: Row height; this value is repeated, 1 value per row
        # 142: Column height; this value is repeated, 1 value per column
        # for every cell:
        #      171: Cell type; this value is repeated, 1 value per cell:
        #           1 = text type
        #           2 = block type
        #      172: Cell flag value; this value is repeated, 1 value per cell
        #      173: Cell merged value; this value is repeated, 1 value per cell
        #      174: Boolean flag indicating if the autofit option is set for the
        #           cell; this value is repeated, 1 value per cell
        #      175: Cell border width (applicable only for merged cells); this
        #           value is repeated, 1 value per cell
        #      176: Cell border height (applicable for merged cells); this value
        #           is repeated, 1 value per cell
        #       91: Cell override flag; this value is repeated, 1 value per cell
        #           (from AutoCAD 2007)
        #      178: Flag value for a virtual edge
        #      145: Rotation value (real; applicable for a block-type cell and
        #           a text-type cell)
        #      344: Hard pointer ID of the FIELD object. This applies only to a
        #           text-type cell. If the text in the cell contains one or more
        #           fields, only the ID of the FIELD object is saved.
        #           The text string (group codes 1 and 3) is ignored
        #        1: Text string in a cell. If the string is shorter than 250
        #           characters, all characters appear in code 1.
        #           If the string is longer than 250 characters, it is divided
        #           into chunks of 250 characters.
        #           The chunks are contained in one or more code 2 codes.
        #           If code 2 codes are used, the last group is a code 1 and is
        #           shorter than 250 characters.
        #           This value applies only to text-type cells and is repeated,
        #           1 value per cell
        #        2: Text string in a cell, in 250-character chunks; optional.
        #           This value applies only to text-type cells and is repeated,
        #           1 value per cell
        #      340: Hard-pointer ID of the block table record.
        #           This value applies only to block-type cells and is repeated,
        #           1 value per cell
        #      144: Block scale (real). This value applies only to block-type
        #           cells and is repeated, 1 value per cell
        #      176: Number of attribute definitions in the block table record
        #           (applicable only to a block-type cell)
        #      for every ATTDEF:
        #           331: Soft pointer ID of the attribute definition in the
        #                block table record, referenced by group code 179
        #                (applicable only for a block-type cell). This value is
        #                repeated once per attribute definition
        #           300: Text string value for an attribute definition, repeated
        #                once per attribute definition and applicable only for
        #                a block-type cell
        #        7: Text style name (string); override applied at the cell level
        #      140: Text height value; override applied at the cell level
        #      170: Cell alignment value; override applied at the cell level
        #       64: Value for the color of cell content; override applied at the
        #           cell level
        #       63: Value for the background (fill) color of cell content;
        #           override applied at the cell level
        #       69: True color value for the top border of the cell;
        #           override applied at the cell level
        #       65: True color value for the right border of the cell;
        #           override applied at the cell level
        #       66: True color value for the bottom border of the cell;
        #           override applied at the cell level
        #       68: True color value for the left border of the cell;
        #           override applied at the cell level
        #      279: Lineweight for the top border of the cell;
        #           override applied at the cell level
        #      275: Lineweight for the right border of the cell;
        #           override applied at the cell level
        #      276: Lineweight for the bottom border of the cell;
        #           override applied at the cell level
        #      278: Lineweight for the left border of the cell;
        #           override applied at the cell level
        #      283: Boolean flag for whether the fill color is on;
        #           override applied at the cell level
        #      289: Boolean flag for the visibility of the top border of the cell;
        #           override applied at the cell level
        #      285: Boolean flag for the visibility of the right border of the cell;
        #           override applied at the cell level
        #      286: Boolean flag for the visibility of the bottom border of the cell;
        #           override applied at the cell level
        #      288: Boolean flag for the visibility of the left border of the cell;
        #           override applied at the cell level
        #       70: Flow direction;
        #           override applied at the table entity level
        #       40: Horizontal cell margin;
        #           override applied at the table entity level
        #       41: Vertical cell margin;
        #           override applied at the table entity level
        #      280: Flag for whether the title is suppressed;
        #           override applied at the table entity level
        #      281: Flag for whether the header row is suppressed;
        #           override applied at the table entity level
        #        7: Text style name (string);
        #           override applied at the table entity level.
        #           There may be one entry for each cell type
        #      140: Text height (real);
        #           override applied at the table entity level.
        #           There may be one entry for each cell type
        #      170: Cell alignment (integer);
        #           override applied at the table entity level.
        #           There may be one entry for each cell type
        #       63: Color value for cell background or for the vertical, left
        #           border of the table; override applied at the table entity
        #           level. There may be one entry for each cell type
        #       64: Color value for cell content or for the horizontal, top
        #           border of the table; override applied at the table entity
        #           level. There may be one entry for each cell type
        #       65: Color value for the horizontal, inside border lines;
        #           override applied at the table entity level
        #       66: Color value for the horizontal, bottom border lines;
        #           override applied at the table entity level
        #       68: Color value for the vertical, inside border lines;
        #           override applied at the table entity level
        #       69: Color value for the vertical, right border lines;
        #           override applied at the table entity level
        #      283: Flag for whether background color is enabled (default = 0);
        #           override applied at the table entity level.
        #           There may be one entry for each cell type: 0/1 = Disabled/Enabled
        #      274-279: Lineweight for each border type of the cell (default = kLnWtByBlock);
        #               override applied at the table entity level.
        #               There may be one group for each cell type
        #      284-289: Flag for visibility of each border type of the cell (default = 1);
        #               override applied at the table entity level.
        #               There may be one group for each cell type: 0/1 = Invisible/Visible
        #  97: Standard/title/header row data type
        #  98: Standard/title/header row unit type
        #   4: Standard/title/header row format string
        #
        # AutoCAD 2007 and before:
        # 177: Cell override flag value (before AutoCAD 2007)
        #  92: Extended cell flags (from AutoCAD 2007), COLLISION: group code
        #      also used by n_cols
        # 301: Text string in a cell. If the string is shorter than 250
        #      characters, all characters appear in code 302.
        #      If the string is longer than 250 characters, it is divided into
        #      chunks of 250 characters.
        #      The chunks are contained in one or more code 303 codes.
        #      If code 393 codes are used, the last group is a code 1 and is
        #      shorter than 250 characters.
        #      --- WRONG: The text is divided into chunks of group code 2 and the last
        #          chuck has group code 1.
        #      This value applies only to text-type cells and is repeated,
        #      1 value per cell (from AutoCAD 2007)
        # 302: Text string in a cell, in 250-character chunks; optional.
        #      This value applies only to text-type cells and is repeated,
        #      302 value per cell (from AutoCAD 2007)
        #      --- WRONG: 302 contains all the text as a long string, tested with more
        #          than 66000 characters
        # BricsCAD writes long text in cells with both methods: 302 & (2, 2, 2, ..., 1)
        #
        # REMARK from Autodesk:
        # Group code 178 is a flag value for a virtual edge. A virtual edge is
        # used when a grid line is shared by two cells.
        # For example, if a table contains one row and two columns and it
        # contains cell A and cell B, the central grid line
        # contains the right edge of cell A and the left edge of cell B.
        # One edge is real, and the other edge is virtual.
        # The virtual edge points to the real edge; both edges have the same
        # set of properties, including color, lineweight, and visibility.
    },
)
acdb_table_group_codes = group_code_mapping(acdb_table)


# todo: implement ACAD_TABLE
class AcadTable(DXFGraphic):
    """DXF ACAD_TABLE entity"""

    DXFTYPE = "ACAD_TABLE"
    DXFATTRIBS = DXFAttributes(
        base_class, acdb_entity, acdb_block_reference, acdb_table
    )
    MIN_DXF_VERSION_FOR_EXPORT = const.DXF2007

    def __init__(self):
        super().__init__()
        self.data: Optional[AcadTableData] = None

    def copy_data(self, entity: Self, copy_strategy=default_copy) -> None:
        """Copy data."""
        assert isinstance(entity, AcadTable)
        entity.data = copy.deepcopy(self.data)

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        if processor:
            processor.fast_load_dxfattribs(
                dxf, acdb_block_reference_group_codes, subclass=2
            )
            tags = processor.subclass_by_index(3)
            if tags is not None:
                self.load_table(tags)
        return dxf

    def load_table(self, tags: Tags):
        self.data = _parse_acad_table_content(self.dxf, tags)

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        """Export entity specific data as DXF tags."""
        super().export_entity(tagwriter)
        tagwriter.write_tag2(const.SUBCLASS_MARKER, acdb_block_reference.name)
        self.dxf.export_dxf_attribs(tagwriter, ["geometry", "insert"])
        tagwriter.write_tag2(const.SUBCLASS_MARKER, acdb_table.name)
        self.export_table(tagwriter)

    def export_table(self, tagwriter: AbstractTagWriter):
        pass

    def __referenced_blocks__(self) -> Iterable[str]:
        """Support for "ReferencedBlocks" protocol."""
        if self.doc:
            block_record_handle = self.dxf.get("block_record_handle", None)
            if block_record_handle:
                return (block_record_handle,)
        return tuple()


acdb_table_style = DefSubclass(
    "AcDbTableStyle",
    {
        # Table style version: 0 = 2010
        "version": DXFAttr(280),
        # Table style description (string; 255 characters maximum):
        "name": DXFAttr(3),
        # FlowDirection (integer):
        # 0 = Down
        # 1 = Up
        "flow_direction": DXFAttr(70),
        # Flags (bit-coded)
        "flags": DXFAttr(71),
        # Horizontal cell margin (real; default = 0.06)
        "horizontal_cell_margin": DXFAttr(40),
        # Vertical cell margin (real; default = 0.06)
        "vertical_cell_margin": DXFAttr(41),
        # Flag for whether the title is suppressed:
        # 0/1 = not suppressed/suppressed
        "suppress_title": DXFAttr(280),
        # Flag for whether the column heading is suppressed:
        # 0/1 = not suppressed/suppressed
        "suppress_column_header": DXFAttr(281),
        # The following group codes are repeated for every cell in the table
        #   7: Text style name (string; default = STANDARD)
        # 140: Text height (real)
        # 170: Cell alignment (integer)
        #  62: Text color (integer; default = BYBLOCK)
        #  63: Cell fill color (integer; default = 7)
        # 283: Flag for whether background color is enabled (default = 0):
        #      0/1 = disabled/enabled
        #  90: Cell data type
        #  91: Cell unit type
        # 274-279: Lineweight associated with each border type of the cell
        #          (default = kLnWtByBlock)
        # 284-289: Flag for visibility associated with each border type of the cell
        #          (default = 1): 0/1 = Invisible/Visible
        # 64-69: Color value associated with each border type of the cell
        #        (default = BYBLOCK)
    },
)


@factory.register_entity
class TableStyle(DXFObject):
    """DXF TABLESTYLE entity

    Every ACAD_TABLE has its own table style.

    Requires DXF version AC1021/R2007
    """

    DXFTYPE = "TABLESTYLE"
    DXFATTRIBS = DXFAttributes(base_class, acdb_table_style)
    MIN_DXF_VERSION_FOR_EXPORT = const.DXF2007

    def __init__(self) -> None:
        super().__init__()
        self.data: Optional[TableStyleData] = None

    def copy_data(self, entity: Self, copy_strategy=default_copy) -> None:
        assert isinstance(entity, TableStyle)
        entity.data = copy.deepcopy(self.data)

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        if processor:
            tags = processor.subclass_by_index(1)
            if tags is None:
                raise const.DXFStructureError(
                    f"Missing subclass AcDbTableStyle in TABLESTYLE(#{dxf.handle})"
                )
            start = 1 if len(tags) and tags[0].code == 100 else 0
            index = start
            if index < len(tags) and tags[index].code == 280:
                dxf.version = int(tags[index].value)
                index += 1
            if index < len(tags) and tags[index].code == 3:
                dxf.name = str(tags[index].value)
                index += 1
            if index < len(tags) and tags[index].code == 70:
                dxf.flow_direction = int(tags[index].value)
                index += 1
            if index < len(tags) and tags[index].code == 71:
                dxf.flags = int(tags[index].value)
                index += 1
            if index < len(tags) and tags[index].code == 40:
                dxf.horizontal_cell_margin = float(tags[index].value)
                index += 1
            if index < len(tags) and tags[index].code == 41:
                dxf.vertical_cell_margin = float(tags[index].value)
                index += 1
            if index < len(tags) and tags[index].code == 280:
                dxf.suppress_title = int(tags[index].value)
                index += 1
            if index < len(tags) and tags[index].code == 281:
                dxf.suppress_column_header = int(tags[index].value)
            self.data = _parse_table_style(tags)
        return dxf

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        super().export_entity(tagwriter)
        tagwriter.write_tag2(const.SUBCLASS_MARKER, acdb_table_style.name)
        self.dxf.export_dxf_attribs(tagwriter, ["name"])
        if self.data is None:
            _export_table_style_data(tagwriter, _default_table_style_data())
        else:
            _export_table_style_data(tagwriter, self.data)

    @property
    def title_style(self) -> Optional[TableStyleCellStyle]:
        return self.data.title_style if self.data is not None else None

    @property
    def header_style(self) -> Optional[TableStyleCellStyle]:
        return self.data.header_style if self.data is not None else None

    @property
    def data_style(self) -> Optional[TableStyleCellStyle]:
        return self.data.data_style if self.data is not None else None


class TableStyleManager(ObjectCollection[TableStyle]):
    def __init__(self, doc: Drawing):
        super().__init__(doc, dict_name="ACAD_TABLESTYLE", object_type="TABLESTYLE")

    def create_required_entries(self) -> None:
        if "Standard" not in self:
            style = self.new("Standard")
            style.data = _default_table_style_data()


@factory.register_entity
class TableContent(DXFTagStorage):
    DXFTYPE = "TABLECONTENT"

    def __init__(self) -> None:
        super().__init__()
        self.linked_data: Optional[AcadTableLinkedData] = None
        self.table_style_handle: Optional[str] = None

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        if processor:
            tags = processor.subclass_by_index(2)
            if tags is not None:
                self.linked_data = AcadTableLinkedData.from_tags(tags)
        return dxf

    def rows(self) -> list[list[AcadTableLinkedCell]]:
        if self.linked_data is None:
            return []
        return self.linked_data.rows()

    def get_row(self, row: int) -> AcadTableLinkedRow:
        if self.linked_data is None:
            raise IndexError("TABLECONTENT has no parsed row data")
        return self.linked_data.get_row(row)

    def get_column(self, col: int) -> AcadTableLinkedColumn:
        if self.linked_data is None:
            raise IndexError("TABLECONTENT has no parsed column data")
        return self.linked_data.get_column(col)

    def get_cell(self, row: int, col: int) -> AcadTableLinkedCell:
        if self.linked_data is None:
            raise IndexError("TABLECONTENT has no parsed cell data")
        return self.linked_data.get_cell(row, col)

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        if self.linked_data is None or len(self.xtags.subclasses) > 1:
            super().export_entity(tagwriter)
            return
        write_tag2 = tagwriter.write_tag2
        write_tag2(const.SUBCLASS_MARKER, "AcDbLinkedData")
        write_tag2(1, "")
        write_tag2(300, "")
        write_tag2(const.SUBCLASS_MARKER, "AcDbLinkedTableData")
        _export_linked_table_data(
            tagwriter,
            self.linked_data,
            table_style_handle=self.table_style_handle,
        )


@factory.register_entity
class CellStyleMap(DXFTagStorage):
    DXFTYPE = "CELLSTYLEMAP"

    def __init__(self) -> None:
        super().__init__()
        self.data: Optional[TableStyleData] = None
        self.text_style_handle: str = "0"

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        if len(self.xtags.subclasses) > 1:
            super().export_entity(tagwriter)
            return
        write_tag2 = tagwriter.write_tag2
        write_tag2(const.SUBCLASS_MARKER, "AcDbCellStyleMap")
        _export_cell_style_map_data(
            tagwriter,
            self.data if self.data is not None else _default_table_style_data(),
            text_style_handle=self.text_style_handle,
        )


@factory.register_entity
class TableGeometry(DXFTagStorage):
    DXFTYPE = "TABLEGEOMETRY"

    def __init__(self) -> None:
        super().__init__()
        self.n_rows = 0
        self.n_cols = 0

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        if processor:
            tags = processor.subclass_by_index(1)
            if tags is not None:
                self.n_rows = int(tags.get_first_value(90, 0))
                self.n_cols = int(tags.get_first_value(91, 0))
        return dxf

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        if len(self.xtags.subclasses) > 1:
            super().export_entity(tagwriter)
            return
        write_tag2 = tagwriter.write_tag2
        write_tag2(const.SUBCLASS_MARKER, "AcDbTableGeometry")
        write_tag2(90, self.n_rows)
        write_tag2(91, self.n_cols)
        write_tag2(92, self.n_rows)


@factory.register_entity
class AcadTableBlockContent(DXFTagStorage):
    DXFTYPE = "ACAD_TABLE"
    DXFATTRIBS = DXFAttributes(
        base_class, acdb_entity, acdb_block_reference, acdb_table
    )

    def __init__(self) -> None:
        super().__init__()
        self.data: Optional[AcadTableData] = None
        self.linked_data: Optional[AcadTableLinkedData] = None

    @property
    def is_graphic_entity(self) -> bool:
        return True

    def set_owner(self, owner: Optional[str], paperspace: int = 0) -> None:
        self.dxf.owner = owner
        if paperspace:
            self.dxf.paperspace = paperspace
        else:
            self.dxf.discard("paperspace")

    def setup_text_table(
        self,
        insert: Vec3,
        content: Sequence[Sequence[str]],
        *,
        style_name: str = "Standard",
        row_heights: Optional[Sequence[float]] = None,
        col_widths: Optional[Sequence[float]] = None,
    ) -> None:
        if self.doc is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
        rows = [list(row) for row in content]
        if not rows:
            raise const.DXFValueError("ACAD_TABLE requires at least one row")
        n_cols = len(rows[0])
        if n_cols == 0:
            raise const.DXFValueError("ACAD_TABLE requires at least one column")
        for row in rows:
            if len(row) != n_cols:
                raise const.DXFValueError("ACAD_TABLE content has inconsistent row lengths")

        n_rows = len(rows)
        if row_heights is None:
            if n_rows >= 3:
                heights = [11.0, 9.0] + [9.0] * (n_rows - 2)
                suppress_title = 0
                suppress_header = 0
            elif n_rows == 2:
                heights = [9.0, 9.0]
                suppress_title = 1
                suppress_header = 0
            else:
                heights = [9.0]
                suppress_title = 1
                suppress_header = 1
        else:
            heights = [float(h) for h in row_heights]
            if len(heights) != n_rows:
                raise const.DXFValueError("row_heights count does not match content rows")
            suppress_title = 0 if n_rows >= 3 else 1
            suppress_header = 0 if n_rows >= 2 else 1

        if col_widths is None:
            widths = [63.5] * n_cols
        else:
            widths = [float(w) for w in col_widths]
            if len(widths) != n_cols:
                raise const.DXFValueError("col_widths count does not match content columns")

        style = self.doc.table_styles.get(style_name)
        if style is None:
            raise const.DXFValueError(f"TABLESTYLE '{style_name}' does not exist")

        cells: list[AcadTableCell] = []
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                cells.append(
                    AcadTableCell(
                        row=row_index,
                        col=col_index,
                        cell_type=1,
                        flags=0,
                        merged_value=0,
                        autofit_flag=0,
                        border_width=1,
                        border_height=1,
                        override_flags=CELL_OVERRIDE_BASE,
                        virtual_edge_flag=0,
                        rotation=0.0,
                        text=str(value),
                    )
                )

        self.data = AcadTableData(
            n_rows=n_rows,
            n_cols=n_cols,
            row_heights=heights,
            col_widths=widths,
            cells=cells,
            suppress_title=suppress_title,
            suppress_column_header=suppress_header,
        )

        self.dxf.version = 0
        self.dxf.table_style_id = style.dxf.handle
        self.dxf.horizontal_direction = Vec3(1, 0, 0)
        self.dxf.table_value = 22
        self.dxf.n_rows = n_rows
        self.dxf.n_cols = n_cols
        self.dxf.override_flag = 0
        self.dxf.border_color_override_flag = 0
        self.dxf.border_lineweight_override_flag = 0
        self.dxf.border_visibility_override_flag = 0
        self.dxf.insert = Vec3(insert)

        block = self.doc.blocks.new_anonymous_block(type_char="T")
        self.dxf.geometry = block.name
        self.dxf.block_record_handle = block.block_record_handle
        self._build_text_table_geometry(block, style)

    def _build_text_table_geometry(self, block, style: TableStyle) -> None:
        assert self.data is not None
        widths = self.data.col_widths
        heights = self.data.row_heights
        total_width = sum(widths)
        y = 0.0
        block.add_line((0, 0), (total_width, 0))
        for height in heights:
            y -= height
            block.add_line((0, y), (total_width, y))
        x = 0.0
        block.add_line((0, 0), (0, -sum(heights)))
        for width in widths:
            x += width
            block.add_line((x, 0), (x, -sum(heights)))

        for cell in self.data.cells:
            style_bucket = self.get_row_style_bucket(cell.row) if style is not None else None
            if cell.is_block_cell:
                self._add_cell_blockref(block, cell)
            else:
                self._add_cell_mtext(block, cell, style_bucket)

    def _add_cell_mtext(self, block, cell: AcadTableCell, style_bucket: Optional[TableStyleCellStyle]) -> None:
        assert self.data is not None
        widths = self.data.col_widths
        heights = self.data.row_heights
        x0 = sum(widths[: cell.col])
        y0 = -sum(heights[: cell.row])
        width = widths[cell.col]
        height = heights[cell.row]
        margin_x = 1.5
        margin_y = 1.5
        attachment = cell.alignment
        if attachment is None:
            attachment = style_bucket.alignment if style_bucket is not None else 5
        char_height = cell.text_height
        if char_height is None:
            char_height = style_bucket.text_height if style_bucket is not None else 4.5
        insert = _table_cell_insert(
            x0,
            y0,
            width,
            height,
            attachment,
            margin_x,
            margin_y,
        )
        text_style = cell.text_style
        if text_style is None:
            text_style = style_bucket.text_style if style_bucket is not None else "Standard"
        visible_text = cell.field_display_text if cell.has_field or cell.field_tags is not None else cell.text
        mtext = block.add_mtext(
            visible_text,
            dxfattribs={
                "insert": insert,
                "char_height": char_height,
                "width": max(width - margin_x * 2.0, 0.0),
                "style": text_style,
                "attachment_point": attachment,
            },
        )
        mtext.dxf.color = 0
        mtext.dxf.discard("true_color")
        if cell.has_field or cell.field_tags is not None:
            self._attach_cell_field_to_mtext(mtext, cell)

    @staticmethod
    def _extract_field_display_text(field: Field) -> str:
        return AcadTableBlockContent._extract_field_tags_display_text(field.tags)

    @staticmethod
    def _extract_field_tags_display_text(tags: Tags) -> str:
        for tag in reversed(tags):
            if tag.code == 301:
                return str(tag.value)
        return ""

    def _capture_cell_field_state(self, cell: AcadTableCell) -> None:
        from .dxfobj import Field

        if self.doc is None or cell.field_handle is None:
            return
        wrapper = self.doc.entitydb.get(cell.field_handle)
        if not isinstance(wrapper, Field) or not wrapper.is_alive:
            return
        primary = wrapper
        children = wrapper.get_child_fields()
        if wrapper.is_text_wrapper and len(children):
            primary = children[0]
        if not isinstance(primary, Field) or not primary.is_alive:
            return
        if cell.field_tags is None:
            cell.field_tags = Tags(primary.tags)
        if len(cell.field_display_text) == 0:
            cell.field_display_text = self._extract_field_display_text(primary)

    def _attach_cell_field_to_mtext(self, mtext, cell: AcadTableCell) -> None:
        if self.doc is None:
            return
        if cell.field_tags is None:
            self._capture_cell_field_state(cell)
        if cell.field_tags is None:
            return
        field = self.doc.objects.add_field(owner="0")
        field.reset(cell.field_tags)
        wrapper = mtext.set_linked_field(field, text=cell.field_display_text)
        cell.field_handle = wrapper.dxf.handle

    def _destroy_geometry_field_support(self, block) -> None:
        if self.doc is None:
            return
        for mtext in list(block.query("MTEXT")):
            get_field_dict = getattr(mtext, "get_field_dict", None)
            if not callable(get_field_dict):
                continue
            try:
                field_dict = mtext.get_field_dict()
            except AttributeError:
                continue
            for key, entry in list(field_dict.items()):
                if isinstance(entry, Field):
                    field_dict.discard(key)
                    entry._delete_field_tree()

    def _add_cell_blockref(self, block, cell: AcadTableCell) -> None:
        assert self.data is not None
        if self.doc is None or cell.block_record_handle is None:
            return
        block_name = cell.wrapper_block_name
        if not block_name:
            block_record = self.doc.entitydb.get(cell.block_record_handle)
            if block_record is None:
                return
            block_name = block_record.dxf.get("name")
        if not isinstance(block_name, str) or len(block_name) == 0:
            return
        widths = self.data.col_widths
        heights = self.data.row_heights
        x0 = sum(widths[: cell.col])
        y0 = -sum(heights[: cell.row])
        width = widths[cell.col]
        height = heights[cell.row]
        insert = _table_cell_insert(
            x0,
            y0,
            width,
            height,
            cell.alignment if cell.alignment is not None else 1,
            1.5,
            1.5,
        )
        block.add_blockref(
            block_name,
            insert,
            dxfattribs={
                "xscale": cell.block_scale,
                "yscale": cell.block_scale,
                "zscale": cell.block_scale,
            },
        )

    def rebuild_text_table_geometry(self) -> None:
        if self.doc is None or self.data is None:
            return
        block_name = self.dxf.get("geometry")
        if not block_name:
            return
        block = self.doc.blocks.get(block_name)
        if block is None:
            return
        style = self.get_table_style()
        if style is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid TABLESTYLE")
        for cell in self.data.cells:
            if cell.field_handle is not None and cell.field_tags is None:
                self._capture_cell_field_state(cell)
        self._destroy_geometry_field_support(block)
        block.delete_all_entities()
        self._build_text_table_geometry(block, style)
        self._sync_linked_table_content()

    def set_cell_text_height(self, row: int, col: int, value: Optional[float]) -> AcadTableCell:
        cell = self.get_cell(row, col)
        cell.set_text_height(value)
        self.rebuild_text_table_geometry()
        return cell

    def set_col_width(self, index: int, value: float) -> None:
        if self.data is None:
            raise IndexError("ACAD_TABLE has no parsed column data")
        value = float(value)
        if value <= 0.0:
            raise const.DXFValueError("column width has to be greater than 0")
        self.data.col_widths[index] = value
        self.rebuild_text_table_geometry()

    def set_row_height(self, index: int, value: float) -> None:
        if self.data is None:
            raise IndexError("ACAD_TABLE has no parsed row data")
        value = float(value)
        if value <= 0.0:
            raise const.DXFValueError("row height has to be greater than 0")
        self.data.row_heights[index] = value
        self.rebuild_text_table_geometry()

    def set_title_suppressed(self, state: bool = True) -> None:
        if self.data is None:
            raise IndexError("ACAD_TABLE has no parsed table data")
        self.data.suppress_title = int(bool(state))
        self.rebuild_text_table_geometry()

    def set_column_header_suppressed(self, state: bool = True) -> None:
        if self.data is None:
            raise IndexError("ACAD_TABLE has no parsed table data")
        self.data.suppress_column_header = int(bool(state))
        self.rebuild_text_table_geometry()

    def set_cell_alignment(self, row: int, col: int, value: Optional[int]) -> AcadTableCell:
        cell = self.get_cell(row, col)
        cell.set_alignment(value)
        self.rebuild_text_table_geometry()
        return cell

    def set_cell_content_color(
        self, row: int, col: int, aci: Optional[int], true_color: Optional[int] = None
    ) -> AcadTableCell:
        cell = self.get_cell(row, col)
        cell.set_content_color(aci, true_color)
        self.rebuild_text_table_geometry()
        return cell

    def set_cell_text(self, row: int, col: int, text: str) -> AcadTableCell:
        cell = self.get_cell(row, col)
        cell.set_text_content(text)
        self.rebuild_text_table_geometry()
        return cell

    def remove_cell_field(
        self, row: int, col: int, *, text: Optional[str] = None
    ) -> AcadTableCell:
        """Remove the linked ``FIELD`` from a text cell.

        Args:
            row: Zero-based row index.
            col: Zero-based column index.
            text: Optional static replacement text. If omitted, the current
                field display text is preserved when available.

        Returns:
            Updated table cell.

        """
        cell = self.get_cell(row, col)
        if not cell.is_text_cell:
            raise const.DXFValueError("target cell is not a text cell")
        if cell.field_handle is None and cell.field_tags is None:
            return cell
        replacement_text = text if text is not None else self._field_cell_text(cell)
        cell.set_text_content(replacement_text)
        self.rebuild_text_table_geometry()
        return cell

    def _field_cell_text(self, cell: AcadTableCell) -> str:
        """Returns best available static replacement text for a field cell."""
        if cell.field_handle is not None:
            self._capture_cell_field_state(cell)
        if len(cell.field_display_text):
            return cell.field_display_text
        if cell.field_tags is not None:
            display = self._extract_field_tags_display_text(cell.field_tags)
            if len(display):
                return display
        return cell.text

    def set_cell_linked_field(
        self,
        row: int,
        col: int,
        field: Field,
        *,
        text: str = "",
        register_field_list: bool = False,
    ) -> Field | None:
        """Attach a linked FIELD object to a text cell.

        Args:
            row: Zero-based row index.
            col: Zero-based column index.
            field: FIELD object to attach to the cell.
            text: Cached visible display text.
            register_field_list: Accepted for consistency with text-like field
                hosts. ACAD_TABLE field synchronization maintains FIELDLIST
                entries for all table field objects when field cells are rebuilt.

        Returns:
            Wrapper FIELD object created for the synchronized table cell, or
            ``None`` if the wrapper cannot be resolved.

        """
        if not isinstance(field, Field):
            raise const.DXFTypeError(f"invalid DXF type: {type(field).__name__}")
        if self.doc is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
        if field.doc is not None and field.doc is not self.doc:
            raise const.DXFStructureError("field belongs to a different DXF document")
        cell = self.get_cell(row, col)
        if not cell.is_text_cell:
            raise const.DXFValueError("target cell is not a text cell")
        cell.set_text_content("")
        cell.field_tags = Tags(field.tags)
        cell.field_display_text = text or self._extract_field_display_text(field)
        self.rebuild_text_table_geometry()
        current_wrapper = self.doc.entitydb.get(cell.field_handle)
        return (
            current_wrapper
            if isinstance(current_wrapper, Field) and current_wrapper.is_alive
            else None
        )

    def new_cell_linked_field(
        self,
        row: int,
        col: int,
        *,
        dxfattribs: Optional[dict[str, Any]] = None,
        text: str = "",
        register_field_list: bool = False,
    ) -> tuple[Field, Field | None]:
        """Create and attach a linked FIELD object to a text cell.

        Args:
            row: Zero-based row index.
            col: Zero-based column index.
            dxfattribs: Optional DXF attributes for the new FIELD object.
            text: Cached visible display text.
            register_field_list: See :meth:`set_cell_linked_field`.

        Returns:
            Tuple ``(primary_field, wrapper_field)``.

        """
        field = cast(Field, factory.new("FIELD", dxfattribs=dxfattribs))
        wrapper = self.set_cell_linked_field(
            row,
            col,
            field,
            text=text,
            register_field_list=register_field_list,
        )
        current_field = self.get_cell_primary_field(row, col)
        return current_field if current_field is not None else field, wrapper

    def new_cell_acvar_field(
        self,
        row: int,
        col: int,
        name: str,
        *,
        text: str = "",
        register_field_list: bool = False,
    ) -> tuple[Field, Field | None]:
        """Create an ``AcVar`` field in a text cell.

        Args:
            row: Zero-based row index.
            col: Zero-based column index.
            name: AutoCAD variable name, e.g. ``"Author"``.
            text: Cached visible display text.
            register_field_list: See :meth:`set_cell_linked_field`.

        Returns:
            Tuple ``(primary_field, wrapper_field)``.

        """
        field = cast(Field, factory.new("FIELD", dxfattribs={}))
        field.set_acvar(name, display=text)
        wrapper = self.set_cell_linked_field(
            row,
            col,
            field,
            text=text,
            register_field_list=register_field_list,
        )
        current_field = self.get_cell_primary_field(row, col)
        return current_field if current_field is not None else field, wrapper

    def new_cell_dwgprops_field(
        self,
        row: int,
        col: int,
        name: str,
        *,
        field_format: str = "",
        value: Optional[str] = None,
        text: str = "",
        register_field_list: bool = False,
    ) -> tuple[Field, Field | None]:
        """Create a drawing-property field in a text cell.

        Args:
            row: Zero-based row index.
            col: Zero-based column index.
            name: Custom drawing property name.
            field_format: Optional AutoCAD field formatting code.
            value: Optional stored custom property value.
            text: Cached visible display text.
            register_field_list: See :meth:`set_cell_linked_field`.

        Returns:
            Tuple ``(primary_field, wrapper_field)``.

        """
        if self.doc is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
        field = cast(Field, factory.new("FIELD", dxfattribs={}))
        if value is None:
            value = text
        if self.doc is not None:
            custom_vars = self.doc.header.custom_vars
            if custom_vars.has_tag(name):
                custom_vars.replace(name, value)
            else:
                custom_vars.append(name, value)
        field.set_dwgprops(name, field_format=field_format, value=value, display=text)
        wrapper = self.set_cell_linked_field(
            row,
            col,
            field,
            text=text,
            register_field_list=register_field_list,
        )
        current_field = self.get_cell_primary_field(row, col)
        return current_field if current_field is not None else field, wrapper

    def new_cell_acobjprop_field(
        self,
        row: int,
        col: int,
        target: DXFEntity | str,
        property_name: str,
        *,
        field_format: str = "%lu2",
        value: Any = None,
        display: Optional[str] = None,
        text: Optional[str] = None,
        register_field_list: bool = False,
    ) -> tuple[Field, Field | None]:
        """Create an object-property field in a text cell.

        Args:
            row: Zero-based row index.
            col: Zero-based column index.
            target: Referenced DXF entity or handle string.
            property_name: AutoCAD object property name, e.g. ``"Length"``.
            field_format: AutoCAD field formatting code.
            value: Optional evaluated property value.
            display: Optional cached field display string.
            text: Optional cached visible cell text.
            register_field_list: See :meth:`set_cell_linked_field`.

        Returns:
            Tuple ``(primary_field, wrapper_field)``.

        """
        if text is None and display is not None:
            text = display
        if text is None:
            text = ""
        if self.doc is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
        field = cast(Field, factory.new("FIELD", dxfattribs={}))
        field.set_acobjprop(
            target,
            property_name,
            field_format=field_format,
            value=value,
            display=display or text,
        )
        wrapper = self.set_cell_linked_field(
            row,
            col,
            field,
            text=text,
            register_field_list=register_field_list,
        )
        current_field = self.get_cell_primary_field(row, col)
        return current_field if current_field is not None else field, wrapper

    def new_cell_acexpr_field(
        self,
        row: int,
        col: int,
        expression: str,
        child_fields: Sequence[Field],
        *,
        field_format: str = "%lu2",
        value: Any = None,
        display: Optional[str] = None,
        text: Optional[str] = None,
        register_field_list: bool = False,
    ) -> tuple[Field, Field | None]:
        """Create an expression field in a text cell.

        Args:
            row: Zero-based row index.
            col: Zero-based column index.
            expression: ``AcExpr`` expression using ``%<\\_FldIdx n>%`` child
                placeholders.
            child_fields: Child FIELD objects used by the expression.
            field_format: AutoCAD field formatting code.
            value: Optional evaluated expression value.
            display: Optional cached field display string.
            text: Optional cached visible cell text.
            register_field_list: See :meth:`set_cell_linked_field`.

        Returns:
            Tuple ``(primary_field, wrapper_field)``.

        """
        if self.doc is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
        if display is None and value is not None:
            if isinstance(value, float) and field_format == "%lu2":
                display = f"{value:.4f}"
            else:
                display = str(value)
        if text is None and display is not None:
            text = display
        expr = Field.build_acexpr(
            self.doc,
            expression,
            child_fields,
            field_format=field_format,
            value=value,
            display=display or "",
        )
        wrapper = self.set_cell_linked_field(
            row,
            col,
            expr,
            text=text or "",
            register_field_list=register_field_list,
        )
        current_field = self.get_cell_primary_field(row, col)
        if current_field is not None:
            child_handles = self._transfer_child_fields(expr, current_field)
            expr._delete_field_tree(exclude_handles=child_handles)
            return current_field, wrapper
        return expr, wrapper

    @staticmethod
    def _transfer_child_fields(source: Field, target: Field) -> list[str]:
        """Move child ``FIELD`` ownership from source to target."""
        handles: list[str] = []
        for child_field in source.get_child_fields():
            child_field.dxf.owner = target.dxf.handle
            if child_field.dxf.handle is not None:
                handles.append(child_field.dxf.handle)
        return handles

    def set_cell_text_style(
        self, row: int, col: int, style_name: Optional[str]
    ) -> AcadTableCell:
        if style_name is not None:
            if self.doc is None:
                raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
            if style_name not in self.doc.styles:
                raise const.DXFValueError(f"text style '{style_name}' does not exist")
        cell = self.get_cell(row, col)
        cell.set_text_style(style_name)
        self.rebuild_text_table_geometry()
        return cell

    def set_cell_text_color(
        self, row: int, col: int, aci: Optional[int], true_color: Optional[int] = None
    ) -> AcadTableCell:
        cell = self.get_cell(row, col)
        cell.set_text_color(aci, true_color)
        self.rebuild_text_table_geometry()
        return cell

    def set_cell_fill_color(
        self, row: int, col: int, aci: Optional[int], true_color: Optional[int] = None
    ) -> AcadTableCell:
        cell = self.get_cell(row, col)
        cell.set_fill_color(aci, true_color)
        self.rebuild_text_table_geometry()
        return cell

    def set_cell_block(
        self,
        row: int,
        col: int,
        block_name: str,
        *,
        block_scale: float = 1.0,
        alignment: int = 1,
    ) -> AcadTableCell:
        if self.doc is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
        if block_name not in self.doc.blocks:
            raise const.DXFValueError(f"block '{block_name}' does not exist")
        block_layout = self.doc.blocks.get(block_name)
        cell = self.get_cell(row, col)
        cell.set_block(
            block_layout.block_record_handle,
            block_scale=block_scale,
            alignment=alignment,
        )
        self.rebuild_text_table_geometry()
        return cell

    def set_cell_block_attribs(self, row: int, col: int, values: dict[str, str]) -> AcadTableCell:
        if self.doc is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
        cell = self.get_cell(row, col)
        if not cell.is_block_cell or cell.block_record_handle is None:
            raise const.DXFValueError("target cell is not a block cell")
        block_name = self.get_cell_block_name(row, col)
        if block_name == "":
            raise const.DXFValueError("block cell has no resolvable block name")
        block = self.doc.blocks.get(block_name)
        attribs: list[AcadTableBlockAttributeValue] = []
        index = 1
        for attdef in block.attdefs():
            attdef.dxf.lock_position = 0
            setattr(attdef, "_force_optional_version_tag", True)
            tag = attdef.dxf.tag
            if tag in values:
                attribs.append(
                    AcadTableBlockAttributeValue(
                        handle=attdef.dxf.handle,
                        text=str(values[tag]),
                        index=index,
                    )
                )
                index += 1
        missing = sorted(set(values.keys()) - {attdef.dxf.tag for attdef in block.attdefs()})
        if missing:
            raise const.DXFValueError(
                f"block {block_name!r} has no ATTDEF tags: {', '.join(missing)}"
            )
        cell.block_attributes = attribs
        cell.block_attribute_count = len(attribs)
        self._ensure_block_cell_wrapper(cell, block_name)
        self.rebuild_text_table_geometry()
        self._sync_linked_table_content()
        return cell

    def _ensure_block_cell_wrapper(self, cell: AcadTableCell, block_name: str) -> None:
        if self.doc is None:
            return
        if cell.wrapper_block_record_handle is not None:
            return
        wrapper = self.doc.blocks.new_anonymous_block()
        cell.wrapper_block_name = wrapper.name
        if len(cell.linked_text):
            label = wrapper.add_mtext(
                cell.linked_text,
                dxfattribs={
                    "color": 0,
                    "transparency": 16777216,
                    "insert": (1.5, -21.5, 0.0),
                    "char_height": 4.5,
                    "width": 3.1,
                    "attachment_point": 1,
                    "flow_direction": 5,
                    "line_spacing_style": 1,
                    "line_spacing_factor": 1.0,
                },
            )
            setattr(label, "_force_optional_line_spacing_style", True)
        insert = Vec3(4.780000000000001, -27.5, 0.0)
        scale = cell.block_scale * (4.0 / 3.0)
        blockref = wrapper.add_blockref(
            block_name,
            insert,
            dxfattribs={
                "color": 0,
                "transparency": 16777216,
                "xscale": scale,
                "yscale": scale,
                "zscale": scale,
            },
        )
        blockref.set_xdata("ACAD", [(1000, "_DRAW_ANNO")])
        block = self.doc.blocks.get(block_name)
        attdefs = {attdef.dxf.tag: attdef for attdef in block.attdefs()}
        for attrib in cell.block_attributes:
            entity = self.doc.entitydb.get(attrib.handle)
            if entity is None:
                continue
            tag = entity.dxf.get("tag")
            if tag not in attdefs:
                continue
            attdef = attdefs[tag]
            dxfattribs = attdef.dxfattribs(drop={"prompt", "handle", "owner"})
            location = Vec3(dxfattribs.pop("insert")) * scale + insert
            dxfattribs["height"] = float(dxfattribs.get("height", 2.5)) * scale
            attached = blockref.add_attrib(tag, attrib.text, location, dxfattribs)
            attached.dxf.lock_position = 0
            setattr(attached, "_force_optional_version_tag", True)
        if blockref.seqend is not None:
            blockref.seqend.dxf.color = 0
            blockref.seqend.dxf.transparency = 16777216
        cell.wrapper_block_record_handle = wrapper.block_record_handle

    def _sync_linked_table_content(self) -> None:
        if self.doc is None or self.data is None:
            return
        has_block_attributes = any(cell.block_attributes for cell in self.data.cells)
        has_field_cells = any(cell.field_handle for cell in self.data.cells)
        if (
            not has_block_attributes
            and not has_field_cells
            and self.get_linked_table_content() is None
        ):
            return
        xrecord = self._get_or_create_roundtrip_xrecord()
        table_content = self._get_or_create_table_content(xrecord)
        self._get_or_create_table_geometry(xrecord)
        self._ensure_table_style_roundtrip_support()
        if has_field_cells:
            field_copy_handles = self._ensure_table_field_roundtrip_support(
                table_content
            )
        else:
            self._delete_table_field_roundtrip_support(table_content)
            field_copy_handles = {}
        table_content.table_style_handle = self.dxf.get("table_style_id")
        table_content.linked_data = _make_linked_table_data(
            self, field_copy_handles=field_copy_handles
        )
        self.linked_data = table_content.linked_data

    def _delete_table_field_roundtrip_support(self, table_content: TableContent) -> None:
        """Delete field copies owned by linked ``TABLECONTENT`` metadata."""
        if self.doc is None:
            return
        wrappers = [
            entity
            for entity in self.doc.objects
            if isinstance(entity, Field) and entity.dxf.owner == table_content.dxf.handle
        ]
        for wrapper in wrappers:
            wrapper._delete_field_tree()

    def _ensure_table_field_roundtrip_support(self, table_content: TableContent) -> dict[str, str]:
        if self.doc is None or self.data is None:
            return {}
        self._delete_table_field_roundtrip_support(table_content)

        field_list = self.doc.objects.setup_field_list()
        mapping: dict[str, str] = {}
        for cell in self.data.cells:
            if cell.field_handle is None:
                continue
            self._capture_cell_field_state(cell)
            if cell.field_tags is None:
                continue
            child_copy = self.doc.objects.add_field(owner="0")
            child_copy.reset(cell.field_tags)
            wrapper_copy = self.doc.objects.add_field(owner=table_content.dxf.handle)
            wrapper_copy.set_text_wrapper(child_copy, text=cell.field_display_text)
            child_copy.dxf.owner = wrapper_copy.dxf.handle
            wrapper_copy.dxf.owner = table_content.dxf.handle
            mapping[cell.field_handle] = wrapper_copy.dxf.handle

        field_list.handles = [
            entity.dxf.handle
            for entity in self.doc.objects
            if entity.dxftype() == "FIELD" and entity.dxf.handle is not None
        ]
        return mapping

    def _ensure_table_style_roundtrip_support(self) -> None:
        style = self.get_table_style()
        if style is None or self.doc is None:
            return
        reactors = set(style.get_reactors())
        owner_dict_handle = self.doc.rootdict.get_required_dict("ACAD_TABLESTYLE").dxf.handle
        reactors.add(owner_dict_handle)
        if self.dxf.handle is not None:
            reactors.add(self.dxf.handle)
        style.set_reactors(sorted(reactors))
        xdict = style.get_extension_dict() if style.has_extension_dict else style.new_extension_dict()
        support_dict = xdict.dictionary
        cell_style_map = support_dict.get("ACAD_ROUNDTRIP_2008_TABLESTYLE_CELLSTYLEMAP")
        if not isinstance(cell_style_map, CellStyleMap):
            cell_style_map = self.doc.objects.new_entity(
                "CELLSTYLEMAP", {"owner": support_dict.dxf.handle}
            )
            support_dict.add("ACAD_ROUNDTRIP_2008_TABLESTYLE_CELLSTYLEMAP", cell_style_map)
        cell_style_map.dxf.owner = support_dict.dxf.handle
        cell_style_map.set_reactors([support_dict.dxf.handle])
        cell_style_map.data = copy.deepcopy(style.data if style.data is not None else _default_table_style_data())
        if "Standard" in self.doc.styles:
            cell_style_map.text_style_handle = self.doc.styles.get("Standard").dxf.handle

    def _get_or_create_roundtrip_xrecord(self):
        if self.doc is None:
            raise const.DXFStructureError("ACAD_TABLE requires a valid DXF document")
        xdict = self.get_extension_dict() if self.has_extension_dict else self.new_extension_dict()
        owner_dict = xdict.dictionary
        xrecord = owner_dict.get("ACAD_XREC_ROUNDTRIP")
        if xrecord is None:
            xrecord = xdict.add_xrecord("ACAD_XREC_ROUNDTRIP")
        xrecord.set_reactors([owner_dict.dxf.handle])
        link_tags = [tag for tag in getattr(xrecord, "tags", Tags()) if tag.code in (360, 361)]
        xrecord.reset(
            [
                (102, "ACAD_ROUNDTRIP_2008_TABLE_ENTITY"),
                *link_tags,
                (70, 2),
                (90, 1),
                (10, (0.0, 0.0, 0.0)),
                (90, 0),
                (90, 2),
            ]
        )
        return xrecord

    def _get_or_create_table_content(self, xrecord):
        assert self.doc is not None
        existing = self.get_linked_table_content()
        if isinstance(existing, TableContent) and existing.is_alive:
            table_content = existing
        else:
            table_content = self.doc.objects.new_entity(
                "TABLECONTENT", {"owner": xrecord.dxf.handle}
            )
        tags = [tag for tag in xrecord.tags if tag.code != 360]
        insert_at = 1 if len(tags) else 0
        tags.insert(insert_at, dxftag(360, table_content.dxf.handle))
        xrecord.tags = Tags(tags)
        table_content.dxf.owner = xrecord.dxf.handle
        return table_content

    def _get_or_create_table_geometry(self, xrecord):
        assert self.doc is not None and self.data is not None
        geom_handle = None
        for tag in xrecord.tags:
            if tag.code == 361:
                geom_handle = str(tag.value)
                break
        table_geometry = None
        if geom_handle is not None:
            entity = self.doc.entitydb.get(geom_handle)
            if isinstance(entity, TableGeometry) and entity.is_alive:
                table_geometry = entity
        if table_geometry is None:
            table_geometry = self.doc.objects.new_entity(
                "TABLEGEOMETRY", {"owner": xrecord.dxf.handle}
            )
        table_geometry.dxf.owner = xrecord.dxf.handle
        table_geometry.n_rows = self.data.n_rows
        table_geometry.n_cols = self.data.n_cols
        tags = [tag for tag in xrecord.tags if tag.code != 361]
        tags.append(dxftag(361, table_geometry.dxf.handle))
        xrecord.tags = Tags(tags)
        return table_geometry

    def set_cell_fill_enabled(self, row: int, col: int, enabled: bool) -> AcadTableCell:
        cell = self.get_cell(row, col)
        cell.set_fill_enabled(enabled)
        self.rebuild_text_table_geometry()
        return cell

    def clear_cell_fill(self, row: int, col: int) -> AcadTableCell:
        cell = self.get_cell(row, col)
        cell.clear_fill()
        self.rebuild_text_table_geometry()
        return cell

    def load_dxf_attribs(
        self, processor: Optional[SubclassProcessor] = None
    ) -> DXFNamespace:
        dxf = super().load_dxf_attribs(processor)
        if processor:
            processor.fast_load_dxfattribs(
                dxf, acdb_block_reference_group_codes, subclass=2
            )
            tags = processor.subclass_by_index(3)
            if tags is not None:
                self.data = _parse_acad_table_content(dxf, tags)
        return dxf

    def export_entity(self, tagwriter: AbstractTagWriter) -> None:
        if len(self.xtags.subclasses) > 1:
            super().export_entity(tagwriter)
            return

        self.export_acdb_entity(tagwriter)
        tagwriter.write_tag2(const.SUBCLASS_MARKER, acdb_block_reference.name)
        self.dxf.export_dxf_attribs(tagwriter, ["geometry", "insert"])
        tagwriter.write_tag2(const.SUBCLASS_MARKER, acdb_table.name)
        self.export_table(tagwriter)

    def export_acdb_entity(self, tagwriter: AbstractTagWriter) -> None:
        if tagwriter.dxfversion > const.DXF12:
            tagwriter.write_tag2(const.SUBCLASS_MARKER, acdb_entity.name)
        self.dxf.export_dxf_attribs(tagwriter, ["paperspace", "layer", "color", "lineweight"])

    def export_table(self, tagwriter: AbstractTagWriter) -> None:
        if self.data is None:
            return
        write_tag2 = tagwriter.write_tag2
        dxf = self.dxf
        # Preserve omitted AutoCAD table flags; writing default tags changes replay fidelity.
        if dxf.hasattr("version"):
            write_tag2(280, dxf.version)
        write_tag2(342, dxf.table_style_id)
        write_tag2(343, dxf.block_record_handle)
        tagwriter.write_vertex(11, dxf.horizontal_direction)
        write_tag2(90, dxf.table_value)
        write_tag2(91, self.data.n_rows)
        write_tag2(92, self.data.n_cols)
        write_tag2(93, dxf.override_flag)
        write_tag2(94, dxf.border_color_override_flag)
        write_tag2(95, dxf.border_lineweight_override_flag)
        write_tag2(96, dxf.border_visibility_override_flag)
        if self.data.suppress_title is not None:
            write_tag2(280, self.data.suppress_title)
        if self.data.suppress_column_header is not None:
            write_tag2(281, self.data.suppress_column_header)
        for value in self.data.row_heights:
            write_tag2(141, value)
        for value in self.data.col_widths:
            write_tag2(142, value)
        for cell in self.data.cells:
            write_tag2(171, cell.cell_type)
            write_tag2(172, cell.flags)
            write_tag2(173, cell.merged_value)
            write_tag2(174, cell.autofit_flag)
            write_tag2(175, cell.border_width)
            write_tag2(176, cell.border_height)
            write_tag2(91, _export_cell_override_flags(cell))
            write_tag2(178, cell.virtual_edge_flag)
            write_tag2(145, cell.rotation)
            if cell.text_style is not None:
                write_tag2(7, cell.text_style)
            if cell.text_height is not None:
                write_tag2(140, cell.text_height)
            if cell.fill_color is not None:
                write_tag2(63, cell.fill_color)
            if cell.fill_true_color is not None:
                write_tag2(421, cell.fill_true_color)
            if cell.fill_enabled is not None:
                write_tag2(283, cell.fill_enabled)
            if cell.field_handle is not None:
                write_tag2(344, cell.field_handle)
            if cell.is_block_cell and cell.block_record_handle is not None:
                shell_block_handle = cell.block_record_handle
                shell_block_attrib_count = cell.block_attribute_count
                if cell.block_attributes and cell.wrapper_block_record_handle is not None:
                    shell_block_handle = cell.wrapper_block_record_handle
                    shell_block_attrib_count = 0
                write_tag2(340, shell_block_handle)
                write_tag2(144, cell.block_scale)
                write_tag2(179, shell_block_attrib_count)
            if cell.alignment is not None:
                write_tag2(170, cell.alignment)
            write_tag2(92, 0)
            write_tag2(301, "CELL_VALUE")
            write_tag2(93, 1 if cell.is_block_cell else 6)
            write_tag2(90, 4)
            if cell.is_text_cell:
                write_tag2(1, cell.text)
            write_tag2(94, 0)
            write_tag2(300, "")
            if cell.is_text_cell:
                write_tag2(302, cell.text)
            else:
                write_tag2(302, "")
            write_tag2(304, "ACVALUE_END")

    def __referenced_blocks__(self) -> Iterable[str]:
        """Support for the "ReferencedBlocks" protocol."""
        if self.doc:
            block_record_handle = self.dxf.get("block_record_handle", None)
            if block_record_handle:
                return (block_record_handle,)
        return tuple()

    def rows(self) -> list[list[AcadTableCell]]:
        if self.data is None:
            return []
        return self.data.rows()

    def get_cell(self, row: int, col: int) -> AcadTableCell:
        self.load_linked_data()
        if self.data is None:
            raise IndexError("ACAD_TABLE has no parsed cell data")
        index = row * max(self.data.n_cols, 1) + col
        return self.data.cells[index]

    def get_cell_block_name(self, row: int, col: int) -> str:
        cell = self.get_cell(row, col)
        handle = cell.block_record_handle
        if handle is None or self.doc is None:
            return ""
        block_record = self.doc.entitydb.get(handle)
        if block_record is None:
            return ""
        return block_record.dxf.get("name", "")

    def get_cell_block_attribs(self, row: int, col: int) -> dict[str, str]:
        cell = self.get_cell(row, col)
        attribs = self.resolve_block_attribute_tags(cell)
        if attribs:
            return attribs
        return self._resolve_geometry_block_attribute_tags(cell)

    def get_cell_field(self, row: int, col: int):
        from .dxfobj import Field

        cell = self.get_cell(row, col)
        handle = cell.field_handle
        if handle is None or self.doc is None:
            return None
        field = self.doc.entitydb.get(handle)
        return field if isinstance(field, Field) and field.is_alive else None

    def get_cell_primary_field(self, row: int, col: int):
        field = self.get_cell_field(row, col)
        if field is None:
            return None
        child_fields = field.get_child_fields()
        if field.is_text_wrapper and len(child_fields):
            return child_fields[0]
        return field

    def get_table_style(self) -> Optional[TableStyle]:
        if self.doc is None:
            return None
        handle = self.dxf.get("table_style_id")
        if handle is None:
            return None
        style = self.doc.entitydb.get(handle)
        return style if isinstance(style, TableStyle) and style.is_alive else None

    def get_row_style_bucket(self, row: int) -> Optional[TableStyleCellStyle]:
        style = self.get_table_style()
        if style is None or style.data is None:
            return None
        suppress_title = bool(self.data.suppress_title) if self.data is not None and self.data.suppress_title is not None else bool(style.data.suppress_title)
        suppress_header = bool(self.data.suppress_column_header) if self.data is not None and self.data.suppress_column_header is not None else bool(style.data.suppress_column_header)

        if not suppress_title:
            if row == 0:
                return style.title_style
            row -= 1
        if not suppress_header:
            if row == 0:
                return style.header_style
        return style.data_style

    def get_cell_style_bucket(self, row: int, col: int) -> Optional[TableStyleCellStyle]:
        return self.get_row_style_bucket(row)

    def get_linked_row(self, row: int) -> AcadTableLinkedRow:
        linked = self.load_linked_data()
        if linked is None:
            raise IndexError("ACAD_TABLE has no linked row data")
        return linked.get_row(row)

    def get_linked_column(self, col: int) -> AcadTableLinkedColumn:
        linked = self.load_linked_data()
        if linked is None:
            raise IndexError("ACAD_TABLE has no linked column data")
        return linked.get_column(col)

    def get_linked_cell(self, row: int, col: int) -> AcadTableLinkedCell:
        linked = self.load_linked_data()
        if linked is None:
            raise IndexError("ACAD_TABLE has no linked cell data")
        return linked.get_cell(row, col)

    def resolve_block_attribute_tags(self, cell: AcadTableCell) -> dict[str, str]:
        if self.doc is None or not cell.block_attributes:
            return {}
        result: dict[str, str] = {}
        for attrib in cell.block_attributes:
            entity = self.doc.entitydb.get(attrib.handle)
            if entity is None:
                continue
            tag = entity.dxf.get("tag")
            if isinstance(tag, str) and len(tag):
                result[tag] = attrib.text
        return result

    def _resolve_geometry_block_attribute_tags(self, cell: AcadTableCell) -> dict[str, str]:
        insert = self._geometry_block_insert_for_cell(cell)
        if insert is None or self.doc is None:
            return {}
        wrapper_insert = insert
        if insert.dxf.name.startswith("*"):
            wrapper_block = self.doc.blocks.get(insert.dxf.name)
            nested_inserts = list(wrapper_block.query("INSERT"))
            if not nested_inserts:
                return {}
            wrapper_insert = nested_inserts[0]
        result: dict[str, str] = {}
        for attrib in getattr(wrapper_insert, "attribs", []):
            tag = attrib.dxf.get("tag")
            text = attrib.dxf.get("text")
            if isinstance(tag, str) and isinstance(text, str):
                result[tag] = text
        return result

    def _geometry_block_insert_for_cell(self, cell: AcadTableCell):
        if self.doc is None or self.data is None or not cell.is_block_cell:
            return None
        block_name = self.get_block_name()
        if not block_name:
            return None
        geometry = self.doc.blocks.get(block_name)
        inserts = list(geometry.query("INSERT"))
        block_cells = [candidate for candidate in self.data.cells if candidate.is_block_cell]
        try:
            index = block_cells.index(cell)
        except ValueError:
            return None
        if index >= len(inserts):
            return None
        return inserts[index]

    def get_linked_table_content_handle(self) -> Optional[str]:
        if not self.has_extension_dict or self.doc is None:
            return None
        try:
            xdict = self.get_extension_dict()
        except AttributeError:
            return None
        if not xdict.has_valid_dictionary:
            return None
        xrecord = xdict.dictionary.get("ACAD_XREC_ROUNDTRIP")
        if xrecord is None:
            return None
        tags = getattr(xrecord, "tags", None)
        if tags is None:
            return None
        for tag in tags:
            if tag.code == 360:
                return str(tag.value)
        return None

    def get_linked_table_content(self) -> Optional[DXFTagStorage]:
        if self.doc is None:
            return None
        handle = self.get_linked_table_content_handle()
        if handle is None:
            return None
        entity = self.doc.entitydb.get(handle)
        if isinstance(entity, DXFTagStorage) and entity.dxftype() == "TABLECONTENT":
            return entity
        return None

    def load_linked_data(self) -> Optional[AcadTableLinkedData]:
        if self.linked_data is not None:
            return self.linked_data
        table_content = self.get_linked_table_content()
        if table_content is None:
            return None
        if isinstance(table_content, TableContent) and table_content.linked_data is not None:
            self.linked_data = table_content.linked_data
            if self.data is not None and self.linked_data.n_rows == 0:
                self.linked_data.n_rows = self.data.n_rows
                self.linked_data.n_cols = self.data.n_cols
            self._merge_linked_data()
            return self.linked_data
        try:
            tags = table_content.xtags.get_subclass("AcDbLinkedTableData")
        except const.DXFKeyError:
            return None
        n_rows = self.data.n_rows if self.data is not None else 0
        n_cols = self.data.n_cols if self.data is not None else 0
        self.linked_data = AcadTableLinkedData.from_tags(tags, n_rows=n_rows, n_cols=n_cols)
        self._merge_linked_data()
        return self.linked_data

    def _merge_linked_data(self) -> None:
        if self.data is None or self.linked_data is None:
            return
        for linked_cell in self.linked_data.cells:
            index = linked_cell.row * max(self.data.n_cols, 1) + linked_cell.col
            if index >= len(self.data.cells):
                continue
            cell = self.data.cells[index]
            cell.linked_cell_contents = linked_cell.contents
            cell.wrapper_block_record_handle = linked_cell.wrapper_block_record_handle
            cell.wrapper_margin_x = linked_cell.wrapper_margin_x
            cell.wrapper_margin_y = linked_cell.wrapper_margin_y
            for content in linked_cell.contents:
                if content.is_block_content:
                    if content.block_record_handle is not None:
                        cell.block_record_handle = content.block_record_handle
                    if content.block_scale is not None:
                        cell.block_scale = content.block_scale
                    if content.alignment is not None:
                        cell.alignment = content.alignment
                    if content.block_attributes:
                        cell.block_attributes = content.block_attributes

    def proxy_graphic_content(self) -> Iterable[DXFGraphic]:
        return super().__virtual_entities__()

    def _block_content(self) -> Iterator[DXFGraphic]:
        block_name: str = self.get_block_name()
        return self.doc.blocks.get(block_name, [])  # type: ignore

    def get_block_name(self) -> str:
        return self.dxf.get("geometry", "")

    def get_insert_location(self) -> Vec3:
        return self.dxf.get("insert", Vec3())

    def __virtual_entities__(self) -> Iterator[DXFGraphic]:
        """Implements the SupportsVirtualEntities protocol."""
        insert: Vec3 = Vec3(self.get_insert_location())
        m: Optional[Matrix44] = None
        if insert:
            # TODO: OCS transformation (extrusion) is ignored yet
            m = Matrix44.translate(insert.x, insert.y, insert.z)

        for entity in self._block_content():
            try:
                clone = entity.copy()
            except const.DXFTypeError:
                continue
            if m is not None:
                try:
                    clone.transform(m)
                except:  # skip entity at any transformation issue
                    continue
            yield clone


def acad_table_to_block(table: DXFEntity) -> None:
    """Converts the given ACAD_TABLE entity to a block references (INSERT entity).

    The original ACAD_TABLE entity will be destroyed.

    .. versionadded:: 1.1

    """
    if not isinstance(table, AcadTableBlockContent):
        return
    doc = table.doc
    owner = table.dxf.owner
    block_name = table.get_block_name()
    if doc is None or block_name == "" or owner is None:
        return
    try:
        layout = doc.layouts.get_layout_by_key(owner)
    except const.DXFKeyError:
        return
    # replace ACAD_TABLE entity by INSERT entity
    layout.add_blockref(
        block_name,
        insert=table.get_insert_location(),
        dxfattribs={"layer": table.dxf.get("layer", "0")},
    )
    layout.delete_entity(table)  # type: ignore


def read_acad_table_content(table: DXFTagStorage) -> list[list[str]]:
    """Returns the content of an ACAD_TABLE entity as list of table rows.

    If the count of table rows or table columns is missing the complete content is
    stored in the first row.
    """
    if table.dxftype() != "ACAD_TABLE":
        raise const.DXFTypeError(f"Expected ACAD_TABLE entity, got {str(table)}")
    data = getattr(table, "data", None)
    if isinstance(data, AcadTableData):
        return data.text_content()
    acdb_table = table.xtags.get_subclass("AcDbTable")

    nrows = acdb_table.get_first_value(91, 0)
    ncols = acdb_table.get_first_value(92, 0)
    split_code = 171  # DXF R2004
    if acdb_table.has_tag(302):
        split_code = 301  # DXF R2007 and later
    values = _load_table_values(acdb_table, split_code)
    if nrows * ncols == 0:
        return [values]
    content: list[list[str]] = []
    for index in range(nrows):
        start = index * ncols
        content.append(values[start : start + ncols])
    return content


def _load_table_values(tags: Tags, split_code: int) -> list[str]:
    values: list[str] = []
    for group in group_tags(tags, splitcode=split_code):
        g_tags = Tags(group)
        if g_tags.has_tag(302):  # DXF R2007 and later
            # contains all text as one long string, with more than 66000 chars tested
            values.append(g_tags.get_first_value(302))
        else:  
            # DXF R2004
            # Text is divided into chunks (2, 2, 2, ..., 1) or (3, 3, 3, ..., 1)
            # DXF reference says group code 2, BricsCAD writes group code 3
            s = "".join(tag.value for tag in g_tags if 1 <= tag.code <= 3)
            values.append(s)
    return values


def _default_linked_column_format() -> AcadTableFormat:
    return AcadTableFormat(kind="COLUMNTABLEFORMAT", flags90=3, alignment=0)


def _default_linked_row_format() -> AcadTableFormat:
    return AcadTableFormat(kind="ROWTABLEFORMAT", flags90=2, alignment=0)


def _default_text_content_format(
    *, style_handle: str = "0", display_height: float = 0.18
) -> AcadTableContentFormat:
    return AcadTableContentFormat(
        flags90=0,
        flags91=0,
        flags92=512,
        flags93=0,
        format_string="",
        margin=0.0,
        text_height=1.0,
        unknown94=1,
        color62=0,
        style_handle=style_handle,
        block_scale=display_height,
    )


def _default_block_label_content_format(
    *, style_handle: str = "0", display_height: float = 4.5
) -> AcadTableContentFormat:
    return AcadTableContentFormat(
        flags90=3,
        flags91=0,
        flags92=4,
        flags93=0,
        format_string="",
        margin=0.0,
        text_height=1.0,
        unknown94=1,
        color62=0,
        style_handle=style_handle,
        block_scale=display_height,
    )


def _default_block_content_format(*, block_scale: float = 1.0) -> AcadTableContentFormat:
    return AcadTableContentFormat(
        flags90=264,
        flags91=256,
        flags92=512,
        flags93=0,
        format_string="",
        margin=0.0,
        text_height=block_scale,
        unknown94=1,
        color62=0,
        style_handle="0",
        block_scale=0.18,
    )


def _default_text_cell_format(alignment: int = 1) -> AcadTableFormat:
    return AcadTableFormat(
        kind="CELLTABLEFORMAT",
        flags90=1,
        alignment=alignment,
        flags91=0,
        flags92=0,
        color62=257,
        flags93=1,
        table_cell_type171=0,
        flags94=0,
        content_format=_default_text_content_format(),
    )


def _default_attributed_text_cell_format(alignment: int = 1) -> AcadTableFormat:
    return AcadTableFormat(
        kind="CELLTABLEFORMAT",
        flags90=1,
        alignment=alignment,
        flags91=0,
        flags92=0,
        color62=257,
        flags93=1,
        table_cell_type171=0,
        flags94=0,
        content_format=AcadTableContentFormat(
            flags90=0,
            flags91=0,
            flags92=512,
            flags93=0,
            format_string="",
            margin=0.0,
            text_height=1.0,
            unknown94=5,
            color62=0,
            style_handle="0",
            block_scale=0.18,
        ),
    )


def _default_block_cell_format(alignment: int = 1) -> AcadTableFormat:
    return AcadTableFormat(
        kind="CELLTABLEFORMAT",
        flags90=1,
        alignment=alignment,
        flags91=16,
        flags92=0,
        color62=257,
        flags93=1,
        table_cell_type171=0,
        flags94=0,
        content_format=_default_text_content_format(),
    )


def _make_linked_table_data(
    table: AcadTableBlockContent,
    *,
    field_copy_handles: Optional[dict[str, str]] = None,
) -> AcadTableLinkedData:
    data = table.data
    assert data is not None
    linked = AcadTableLinkedData(n_rows=data.n_rows, n_cols=data.n_cols)
    has_attributed_block_cells = any(cell.block_attributes for cell in data.cells)
    linked.columns = [
        AcadTableLinkedColumn(index=index, width=width, table_format=_default_linked_column_format())
        for index, width in enumerate(data.col_widths)
    ]
    linked.rows_meta = [
        AcadTableLinkedRow(index=index, height=height, table_format=_default_linked_row_format())
        for index, height in enumerate(data.row_heights)
    ]
    linked.cells = []
    for cell in data.cells:
        if cell.is_block_cell:
            block_content = AcadTableLinkedCellContent(
                content_type=4,
                text="",
                block_record_handle=cell.block_record_handle,
                block_scale=cell.block_scale,
                alignment=cell.alignment,
                block_attributes=list(cell.block_attributes),
                content_format=_default_block_content_format(block_scale=4.0 / 3.0),
            )
            contents = [block_content]
            if cell.block_attributes:
                style_bucket = table.get_row_style_bucket(cell.row)
                style_name = style_bucket.text_style if style_bucket is not None else "Standard"
                style_handle = "0"
                display_height = style_bucket.text_height if style_bucket is not None else 4.5
                if table.doc is not None and style_name in table.doc.styles:
                    style_handle = table.doc.styles.get(style_name).dxf.handle
                contents = [
                    AcadTableLinkedCellContent(
                        content_type=1,
                        text=cell.linked_text,
                        content_format=_default_block_label_content_format(
                            style_handle=style_handle,
                            display_height=display_height,
                        ),
                    ),
                    block_content,
                ]
            table_format = _default_block_cell_format(cell.alignment or 1)
            raw91 = 1
        else:
            style_bucket = table.get_row_style_bucket(cell.row)
            style_name = style_bucket.text_style if style_bucket is not None else "Standard"
            style_handle = "0"
            display_height = style_bucket.text_height if style_bucket is not None else 4.5
            if table.doc is not None and style_name in table.doc.styles:
                style_handle = table.doc.styles.get(style_name).dxf.handle
            content_format = _default_text_content_format()
            table_format = _default_text_cell_format(cell.alignment or 1)
            if has_attributed_block_cells:
                if cell.row == 0:
                    header_bucket = table.get_table_style().header_style if table.get_table_style() is not None else None
                    if header_bucket is not None:
                        display_height = header_bucket.text_height
                elif cell.row == 1:
                    data_bucket = table.get_table_style().data_style if table.get_table_style() is not None else None
                    if data_bucket is not None:
                        display_height = data_bucket.text_height
                content_format = _default_block_label_content_format(
                    style_handle=style_handle,
                    display_height=display_height,
                )
                table_format = _default_attributed_text_cell_format(cell.alignment or 1)
            field_copy_handle = None
            if field_copy_handles is not None and cell.field_handle is not None:
                field_copy_handle = field_copy_handles.get(cell.field_handle)
            if field_copy_handle is not None:
                field_content_format = _default_block_label_content_format(
                    style_handle=style_handle,
                    display_height=display_height,
                )
                table_format = AcadTableFormat(
                    kind="CELLTABLEFORMAT",
                    flags90=1,
                    alignment=cell.alignment or 1,
                    flags91=0,
                    flags92=0,
                    color62=257,
                    flags93=1,
                    table_cell_type171=0,
                    flags94=0,
                    content_format=field_content_format,
                )
                contents = [
                    AcadTableLinkedCellContent(
                        content_type=2,
                        text="",
                        block_record_handle=field_copy_handle,
                        content_format=field_content_format,
                    )
                ]
            else:
                contents = [
                    AcadTableLinkedCellContent(
                        content_type=1,
                        text=cell.text,
                        content_format=content_format,
                    )
                ]
            raw91 = 0
        linked.cells.append(
            AcadTableLinkedCell(
                row=cell.row,
                col=cell.col,
                contents=contents,
                table_format=table_format,
                raw_table_flags90=0,
                raw_table_flags91=raw91,
                wrapper_block_record_handle=cell.wrapper_block_record_handle,
                wrapper_block_name=cell.wrapper_block_name,
            )
        )
    return linked


def _export_linked_table_data(
    tagwriter: AbstractTagWriter,
    linked: AcadTableLinkedData,
    *,
    table_style_handle: Optional[str] = None,
) -> None:
    write_tag2 = tagwriter.write_tag2
    write_tag2(90, linked.n_cols)
    for column in linked.columns:
        _export_linked_table_column(tagwriter, column)
    write_tag2(91, len(rows := (linked.rows() if linked.n_rows and linked.n_cols else [linked.cells])))
    for row_index, cells in enumerate(rows):
        _export_linked_table_row(
            tagwriter,
            row_index,
            linked.rows_meta[row_index] if row_index < len(linked.rows_meta) else AcadTableLinkedRow(index=row_index, height=0.0, table_format=_default_linked_row_format()),
            cells,
        )
    write_tag2(92, 0)
    write_tag2(const.SUBCLASS_MARKER, "AcDbFormattedTableData")
    write_tag2(300, "TABLEFORMAT")
    write_tag2(1, "TABLEFORMAT_BEGIN")
    write_tag2(90, 4)
    write_tag2(170, 0)
    write_tag2(309, "TABLEFORMAT_END")
    write_tag2(90, 0)
    write_tag2(const.SUBCLASS_MARKER, "AcDbTableContent")
    if table_style_handle is not None:
        write_tag2(340, table_style_handle)


def _export_linked_table_column(tagwriter: AbstractTagWriter, column: AcadTableLinkedColumn) -> None:
    write_tag2 = tagwriter.write_tag2
    write_tag2(300, "COLUMN")
    write_tag2(1, "LINKEDTABLEDATACOLUMN_BEGIN")
    write_tag2(300, "")
    write_tag2(91, 0)
    write_tag2(301, "CUSTOMDATA")
    write_tag2(1, "DATAMAP_BEGIN")
    write_tag2(90, 0)
    write_tag2(309, "DATAMAP_END")
    write_tag2(309, "LINKEDTABLEDATACOLUMN_END")
    _export_formatted_table_format(tagwriter, column.table_format or _default_linked_column_format(), "FORMATTEDTABLEDATACOLUMN_BEGIN")
    write_tag2(1, "TABLECOLUMN_BEGIN")
    write_tag2(90, 0)
    write_tag2(40, column.width)
    write_tag2(309, "TABLECOLUMN_END")


def _export_linked_table_row(
    tagwriter: AbstractTagWriter,
    row_index: int,
    row_meta: AcadTableLinkedRow,
    cells: Sequence[AcadTableLinkedCell],
) -> None:
    write_tag2 = tagwriter.write_tag2
    write_tag2(301, "ROW")
    write_tag2(1, "LINKEDTABLEDATAROW_BEGIN")
    write_tag2(90, len(cells))
    for cell in cells:
        write_tag2(300, "CELL")
        _export_linked_table_cell(tagwriter, cell)
    write_tag2(91, 0)
    write_tag2(301, "CUSTOMDATA")
    write_tag2(1, "DATAMAP_BEGIN")
    write_tag2(90, 0)
    write_tag2(309, "DATAMAP_END")
    write_tag2(309, "LINKEDTABLEDATAROW_END")
    _export_formatted_table_format(tagwriter, row_meta.table_format or _default_linked_row_format(), "FORMATTEDTABLEDATAROW_BEGIN")
    write_tag2(1, "TABLEROW_BEGIN")
    write_tag2(90, row_index + 1)
    write_tag2(40, row_meta.height)
    write_tag2(309, "TABLEROW_END")


def _export_linked_table_cell(tagwriter: AbstractTagWriter, cell: AcadTableLinkedCell) -> None:
    write_tag2 = tagwriter.write_tag2
    write_tag2(1, "LINKEDTABLEDATACELL_BEGIN")
    write_tag2(90, 0)
    write_tag2(300, "")
    write_tag2(91, 0)
    write_tag2(301, "CUSTOMDATA")
    write_tag2(1, "DATAMAP_BEGIN")
    checksum = _linked_cell_checksum(cell)
    if checksum is None:
        write_tag2(90, 0)
    else:
        write_tag2(90, 1)
        write_tag2(300, "ACAD_ROUNDTRIP_2008_CELL_CHECKSUM")
        write_tag2(301, "DATAMAP_VALUE")
        write_tag2(93, 2)
        write_tag2(90, 2)
        write_tag2(140, checksum)
        write_tag2(94, 0)
        write_tag2(300, "")
        write_tag2(302, "")
        write_tag2(304, "ACVALUE_END")
    write_tag2(309, "DATAMAP_END")
    write_tag2(92, 0)
    write_tag2(95, len(cell.contents))
    for content in cell.contents:
        write_tag2(302, "CONTENT")
        content_format = content.content_format or _default_text_content_format()
        _export_linked_cell_content(tagwriter, content, content_format=content_format)
    write_tag2(309, "LINKEDTABLEDATACELL_END")
    table_format = cell.table_format or _default_text_cell_format()
    if _use_rich_text_cell_wrapper(cell, table_format):
        _export_rich_text_cell_table_format(tagwriter, cell, table_format)
    else:
        _export_formatted_table_format(tagwriter, table_format, "FORMATTEDTABLEDATACELL_BEGIN")
    write_tag2(1, "TABLECELL_BEGIN")
    write_tag2(90, cell.raw_table_flags90 or 0)
    write_tag2(91, cell.raw_table_flags91 or 0)
    if cell.wrapper_block_record_handle is not None:
        write_tag2(91, 0)
        write_tag2(40, 0.0)
        write_tag2(41, 0.0)
        write_tag2(330, cell.wrapper_block_record_handle)
    write_tag2(309, "TABLECELL_END")


def _linked_cell_checksum(cell: AcadTableLinkedCell) -> Optional[float]:
    if len(cell.contents) != 1 or cell.contents[0].content_type != 1:
        return None
    table_format = cell.table_format
    if table_format is None or table_format.content_format is None:
        return None
    if table_format.content_format.unknown94 != 5:
        return None
    return 84.0 if cell.row == 0 else 72.0


def _use_rich_text_cell_wrapper(cell: AcadTableLinkedCell, table_format: AcadTableFormat) -> bool:
    if len(cell.contents) != 1 or cell.contents[0].content_type != 1:
        return False
    content_format = table_format.content_format
    if content_format is None or content_format.unknown94 != 5:
        return False
    return cell.row in (0, 1)


def _export_rich_text_cell_table_format(
    tagwriter: AbstractTagWriter,
    cell: AcadTableLinkedCell,
    table_format: AcadTableFormat,
) -> None:
    write_tag2 = tagwriter.write_tag2
    write_tag2(1, "FORMATTEDTABLEDATACELL_BEGIN")
    write_tag2(300, table_format.kind)
    write_tag2(1, "TABLEFORMAT_BEGIN")
    write_tag2(90, table_format.flags90)
    if table_format.alignment is not None:
        write_tag2(170, table_format.alignment)
    write_tag2(91, table_format.flags91)
    write_tag2(92, table_format.flags92)
    if table_format.color62 is not None:
        write_tag2(62, table_format.color62)
    write_tag2(93, table_format.flags93)
    content_format = table_format.content_format
    assert content_format is not None
    write_tag2(300, "CONTENTFORMAT")
    write_tag2(1, "CONTENTFORMAT_BEGIN")
    _export_content_format(tagwriter, content_format)
    write_tag2(309, "CONTENTFORMAT_END")
    write_tag2(171, 1)
    write_tag2(301, "MARGIN")
    write_tag2(1, "CELLMARGIN_BEGIN")
    for value in (1.5, 1.5, 1.5, 1.5, 0.18, 0.18):
        write_tag2(40, value)
    write_tag2(309, "CELLMARGIN_END")
    flags94 = 6 if cell.row == 0 else 5
    write_tag2(94, flags94)
    masks = (1, 2, 4, 8, 16, 32) if cell.row == 0 else (2, 4, 8, 16, 32)
    for mask in masks:
        write_tag2(95, mask)
        write_tag2(302, "GRIDFORMAT")
        write_tag2(1, "GRIDFORMAT_BEGIN")
        write_tag2(90, 37)
        write_tag2(91, 1)
        write_tag2(62, 0)
        write_tag2(92, -2)
        write_tag2(340, "0")
        write_tag2(93, 0)
        write_tag2(40, 0.045)
        write_tag2(309, "GRIDFORMAT_END")
    write_tag2(309, "TABLEFORMAT_END")
    write_tag2(309, "FORMATTEDTABLEDATACELL_END")


def _export_linked_cell_content(
    tagwriter: AbstractTagWriter,
    content: AcadTableLinkedCellContent,
    *,
    content_format: AcadTableContentFormat,
) -> None:
    write_tag2 = tagwriter.write_tag2
    write_tag2(1, "CELLCONTENT_BEGIN")
    write_tag2(90, content.content_type)
    if content.content_type == 2:
        if content.block_record_handle is not None:
            write_tag2(340, content.block_record_handle)
        write_tag2(91, 0)
    elif content.is_block_content:
        if content.block_record_handle is not None:
            write_tag2(340, content.block_record_handle)
        write_tag2(91, len(content.block_attributes))
        for attrib in content.block_attributes:
            write_tag2(330, attrib.handle)
            write_tag2(301, attrib.text)
            write_tag2(92, attrib.index)
    else:
        write_tag2(300, "VALUE")
        write_tag2(93, 6)
        write_tag2(90, 4)
        write_tag2(1, content.text)
        write_tag2(94, 0)
        write_tag2(300, "")
        write_tag2(302, content.text)
        write_tag2(304, "ACVALUE_END")
        write_tag2(91, 0)
    write_tag2(309, "CELLCONTENT_END")
    write_tag2(1, "FORMATTEDCELLCONTENT_BEGIN")
    write_tag2(170, 1)
    write_tag2(300, "CONTENTFORMAT")
    write_tag2(1, "CONTENTFORMAT_BEGIN")
    _export_content_format(tagwriter, content_format)
    write_tag2(309, "CONTENTFORMAT_END")
    write_tag2(309, "FORMATTEDCELLCONTENT_END")


def _export_formatted_table_format(
    tagwriter: AbstractTagWriter,
    table_format: AcadTableFormat,
    marker_begin: str,
) -> None:
    write_tag2 = tagwriter.write_tag2
    write_tag2(1, marker_begin)
    write_tag2(300, table_format.kind)
    write_tag2(1, "TABLEFORMAT_BEGIN")
    write_tag2(90, table_format.flags90)
    if table_format.alignment is not None:
        write_tag2(170, table_format.alignment)

    # AutoCAD omits the zero-only 91/92/93 flags for the simpler row/column
    # table format wrappers inside TABLECONTENT.
    compact_wrapper = (
        table_format.kind in {"ROWTABLEFORMAT", "COLUMNTABLEFORMAT"}
        and table_format.content_format is None
        and table_format.flags91 == 0
        and table_format.flags92 == 0
        and table_format.flags93 == 0
        and table_format.color62 is None
        and table_format.table_cell_type171 is None
        and table_format.flags94 is None
    )
    if not compact_wrapper:
        write_tag2(91, table_format.flags91)
        write_tag2(92, table_format.flags92)
    if table_format.color62 is not None:
        write_tag2(62, table_format.color62)
    if not compact_wrapper:
        write_tag2(93, table_format.flags93)
    if table_format.content_format is not None:
        write_tag2(300, "CONTENTFORMAT")
        write_tag2(1, "CONTENTFORMAT_BEGIN")
        _export_content_format(tagwriter, table_format.content_format)
        write_tag2(309, "CONTENTFORMAT_END")
    if table_format.table_cell_type171 is not None:
        write_tag2(171, table_format.table_cell_type171)
    if table_format.flags94 is not None:
        write_tag2(94, table_format.flags94)
    write_tag2(309, "TABLEFORMAT_END")
    write_tag2(309, marker_begin.replace("BEGIN", "END"))


def _export_cell_style_map_data(
    tagwriter: AbstractTagWriter,
    data: TableStyleData,
    *,
    text_style_handle: str,
) -> None:
    write_tag2 = tagwriter.write_tag2

    def export_grid_formats() -> None:
        for mask in (1, 2, 4, 8, 16, 32):
            write_tag2(95, mask)
            write_tag2(302, "GRIDFORMAT")
            write_tag2(1, "GRIDFORMAT_BEGIN")
            write_tag2(90, 0)
            write_tag2(91, 1)
            write_tag2(62, 0)
            write_tag2(92, -2)
            write_tag2(340, "0")
            write_tag2(93, 0)
            write_tag2(40, 0.045)
            write_tag2(309, "GRIDFORMAT_END")

    def export_cell_style(name: str, height: float, unknown94: int, style90: int, style91: int, style92: int) -> None:
        write_tag2(300, "CELLSTYLE")
        write_tag2(1, "TABLEFORMAT_BEGIN")
        write_tag2(90, style90)
        write_tag2(170, 1)
        write_tag2(91, style91)
        write_tag2(92, style92)
        write_tag2(62, 257)
        write_tag2(93, 1)
        write_tag2(300, "CONTENTFORMAT")
        write_tag2(1, "CONTENTFORMAT_BEGIN")
        write_tag2(90, 0)
        write_tag2(91, 0)
        write_tag2(92, 512)
        write_tag2(93, 0)
        write_tag2(300, "")
        write_tag2(40, 0.0)
        write_tag2(140, 1.0)
        write_tag2(94, unknown94)
        write_tag2(62, 0)
        write_tag2(340, text_style_handle)
        write_tag2(144, height)
        write_tag2(309, "CONTENTFORMAT_END")
        write_tag2(171, 1)
        write_tag2(301, "MARGIN")
        write_tag2(1, "CELLMARGIN_BEGIN")
        for value in (
            data.horizontal_cell_margin,
            data.horizontal_cell_margin,
            data.vertical_cell_margin,
            data.vertical_cell_margin,
            0.18,
            0.18,
        ):
            write_tag2(40, value)
        write_tag2(309, "CELLMARGIN_END")
        write_tag2(94, 6)
        export_grid_formats()
        write_tag2(309, "TABLEFORMAT_END")
        write_tag2(1, "CELLSTYLE_BEGIN")
        write_tag2(90, style90 - 4)
        write_tag2(91, style91 + 1)
        write_tag2(300, name)
        write_tag2(309, "CELLSTYLE_END")

    header_height = data.header_style.text_height if data.header_style is not None else 6.0
    data_height = data.data_style.text_height if data.data_style is not None else 4.5
    title_height = data.title_style.text_height if data.title_style is not None else 4.5
    write_tag2(90, 3)
    export_cell_style("_TITLE", header_height, 5, 5, 0, 32768)
    export_cell_style("_HEADER", data_height, 5, 6, 0, 0)
    export_cell_style("_DATA", title_height, 2, 7, 1, 0)


def _export_content_format(tagwriter: AbstractTagWriter, content: AcadTableContentFormat) -> None:
    write_tag2 = tagwriter.write_tag2
    write_tag2(90, content.flags90)
    write_tag2(91, content.flags91)
    write_tag2(92, content.flags92)
    write_tag2(93, content.flags93)
    write_tag2(300, content.format_string)
    write_tag2(40, content.margin)
    if content.text_height is not None:
        write_tag2(140, content.text_height)
    if content.unknown94 is not None:
        write_tag2(94, content.unknown94)
    if content.color62 is not None:
        write_tag2(62, content.color62)
    if content.style_handle is not None:
        write_tag2(340, content.style_handle)
    if content.block_scale is not None:
        write_tag2(144, content.block_scale)


def _export_cell_override_flags(cell: AcadTableCell) -> int:
    flags = cell.override_flags | CELL_OVERRIDE_BASE
    if cell.text_height is not None:
        flags |= CELL_OVERRIDE_TEXT_HEIGHT
    else:
        flags &= ~CELL_OVERRIDE_TEXT_HEIGHT
    if cell.alignment is not None:
        flags |= CELL_OVERRIDE_ALIGNMENT
    else:
        flags &= ~CELL_OVERRIDE_ALIGNMENT
    if cell.text_style is not None:
        flags |= CELL_OVERRIDE_TEXT_STYLE
    else:
        flags &= ~CELL_OVERRIDE_TEXT_STYLE
    if cell.fill_color is not None:
        flags |= CELL_OVERRIDE_LOCAL_COLOR
    else:
        flags &= ~CELL_OVERRIDE_LOCAL_COLOR
    if cell.fill_true_color is not None or cell.fill_enabled == 1:
        flags |= CELL_OVERRIDE_LOCAL_TRUE_COLOR
    else:
        flags &= ~CELL_OVERRIDE_LOCAL_TRUE_COLOR
    return flags


def _table_cell_insert(
    x0: float,
    y0: float,
    width: float,
    height: float,
    attachment: int,
    margin_x: float,
    margin_y: float,
) -> tuple[float, float, float]:
    if attachment in (2, 5, 8):
        x = x0 + width * 0.5
    elif attachment in (3, 6, 9):
        x = x0 + width - margin_x
    else:
        x = x0 + margin_x

    if attachment in (4, 5, 6):
        y = y0 - height * 0.5
    elif attachment in (7, 8, 9):
        y = y0 - height + margin_y
    else:
        y = y0 - margin_y
    return x, y, 0.0
