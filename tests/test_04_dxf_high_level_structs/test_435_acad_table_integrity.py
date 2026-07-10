from __future__ import annotations

from dataclasses import dataclass
from io import StringIO

import dxfpy
from dxfpy.document import Drawing
from dxfpy.entities import DXFEntity, Field, MText, XRecord
from dxfpy.entities.acad_table import (
    AcadTableBlockContent,
    AcadTableCell,
    AcadTableData,
    AcadTableLinkedCell,
    AcadTableLinkedCellContent,
    TableContent,
    TableGeometry,
)
from dxfpy.layouts import BlockLayout
from dxfpy.lldxf.tags import DXFTag
from dxfpy.lldxf.tagwriter import TagCollector


@dataclass(frozen=True)
class BlockAttributeExpectation:
    """Expected block-cell attribute values by public and linked keys."""

    by_tag: dict[str, str]
    by_handle: dict[str, str]
    block_scale: float
    alignment: int


@dataclass(frozen=True)
class AcadTableIntegrityInspector:
    """Validates ACAD_TABLE semantic, geometry, and metadata integrity."""

    doc: Drawing
    table: AcadTableBlockContent

    @property
    def data(self) -> AcadTableData:
        """Returns parsed semantic table data."""
        assert self.table.data is not None
        return self.table.data

    @property
    def geometry_block(self) -> BlockLayout:
        """Returns the table geometry block layout."""
        block = self.doc.blocks.get(self.table.dxf.geometry)
        assert block is not None
        return block

    def assert_plain_text_table_integrity(self) -> None:
        """Assert that a text-only table has no unnecessary metadata."""
        self.assert_core_table_integrity()
        self.assert_no_roundtrip_metadata()
        self.assert_clean_field_state()

    def assert_linked_roundtrip_integrity(self) -> None:
        """Assert that linked roundtrip objects match semantic data."""
        self.assert_core_table_integrity()
        self._assert_roundtrip_links_are_live()
        self._assert_table_content_matches_data()
        self._assert_table_geometry_matches_data()
        self.assert_clean_field_state()

    def assert_core_table_integrity(self) -> None:
        """Assert semantic data, shell state, and geometry agree."""
        self._assert_data_dimensions()
        self._assert_geometry_block_pointer()
        self._assert_geometry_entity_counts()
        self._assert_cell_field_handles_are_live()

    def assert_no_roundtrip_metadata(self) -> None:
        """Assert that a table does not carry TABLECONTENT metadata."""
        assert self._roundtrip_xrecord() is None
        assert self._table_content() is None

    def assert_clean_field_state(self) -> None:
        """Assert FIELDLIST, owners, and audit state are clean."""
        self._assert_field_list_has_only_live_fields()
        self._assert_no_field_has_missing_owner()
        self._assert_doc_audit_is_clean()

    def assert_all_fields_are_registered(self) -> None:
        """Assert the FIELDLIST registers every live FIELD object."""
        field_list = self.doc.objects.get_field_list()
        assert field_list is not None
        assert set(field_list.handles) == self._live_field_handles()

    def assert_field_cell(
        self, row: int, col: int, evaluator_id: str, text: str
    ) -> None:
        """Assert a field cell and its geometry MTEXT agree."""
        primary = self.table.get_cell_primary_field(row, col)
        mtext = self.geometry_mtext(row, col)
        assert primary is not None
        assert primary.evaluator_id == evaluator_id
        assert mtext.text == text
        assert mtext.get_primary_field() is not None
        assert mtext.get_primary_field().evaluator_id == evaluator_id

    def assert_block_cell_attribs(
        self,
        row: int,
        col: int,
        block_name: str,
        expected: BlockAttributeExpectation,
    ) -> None:
        """Assert a block cell and its linked attributes agree."""
        cell = self.table.get_cell(row, col)
        block_content = self._linked_block_content(row, col)
        assert cell.is_block_cell is True
        assert self.table.get_cell_block_name(row, col) == block_name
        assert cell.block_scale == expected.block_scale
        assert cell.alignment == expected.alignment
        assert self.table.get_cell_block_attribs(row, col) == expected.by_tag
        assert self._attribute_values(block_content) == expected.by_handle

    def geometry_mtext(self, row: int, col: int) -> MText:
        """Returns the geometry MTEXT for a text cell."""
        cell = self.table.get_cell(row, col)
        assert cell.is_text_cell is True
        index = self._text_cell_index(cell)
        return list(self.geometry_block.query("MTEXT"))[index]

    def _assert_data_dimensions(self) -> None:
        """Assert row/column dimensions match cell collections."""
        assert self.table.dxf.n_rows == self.data.n_rows
        assert self.table.dxf.n_cols == self.data.n_cols
        assert len(self.data.cells) == self.data.n_rows * self.data.n_cols
        assert len(self.data.row_heights) == self.data.n_rows
        assert len(self.data.col_widths) == self.data.n_cols

    def _assert_geometry_block_pointer(self) -> None:
        """Assert shell BTR handle points at the geometry block."""
        assert (
            self.table.dxf.block_record_handle
            == self.geometry_block.block_record_handle
        )

    def _assert_geometry_entity_counts(self) -> None:
        """Assert geometry entity counts match semantic cell types."""
        grid_line_count = self.data.n_rows + self.data.n_cols + 2
        assert len(list(self.geometry_block.query("LINE"))) == grid_line_count
        mtext_count = len(list(self.geometry_block.query("MTEXT")))
        insert_count = len(list(self.geometry_block.query("INSERT")))
        assert mtext_count == self._text_cell_count()
        assert insert_count == self._block_cell_count()

    def _assert_cell_field_handles_are_live(self) -> None:
        """Assert each semantic field handle resolves to a live FIELD."""
        for cell in self.data.cells:
            if cell.field_handle is not None:
                field = self.doc.entitydb.get(cell.field_handle)
                assert isinstance(field, Field)
                assert field.is_alive

    def _assert_roundtrip_links_are_live(self) -> None:
        """Assert xrecord links point to live roundtrip objects."""
        xrecord = self._roundtrip_xrecord()
        content = self._table_content()
        geometry = self._table_geometry()
        assert xrecord is not None
        assert content is not None
        assert geometry is not None
        assert content.dxf.owner == xrecord.dxf.handle
        assert geometry.dxf.owner == xrecord.dxf.handle

    def _assert_table_content_matches_data(self) -> None:
        """Assert linked TABLECONTENT mirrors semantic cells."""
        content = self._table_content()
        assert content is not None
        linked = self.table.load_linked_data() or content.linked_data
        assert linked is not None
        assert linked.n_rows == self.data.n_rows
        assert linked.n_cols == self.data.n_cols
        assert len(linked.cells) == len(self.data.cells)
        for cell in self.data.cells:
            linked_cell = linked.get_cell(cell.row, cell.col)
            self._assert_linked_cell_matches(linked_cell, cell)

    def _assert_table_geometry_matches_data(self) -> None:
        """Assert TABLEGEOMETRY row/column counts match data."""
        geometry = self._table_geometry()
        assert geometry is not None
        assert geometry.n_rows == self.data.n_rows
        assert geometry.n_cols == self.data.n_cols

    def _assert_linked_cell_matches(
        self, linked_cell: AcadTableLinkedCell, cell: AcadTableCell
    ) -> None:
        """Assert one linked cell matches one semantic cell."""
        if cell.field_handle is not None:
            self._assert_field_content(linked_cell.contents)
        elif cell.is_block_cell:
            self._assert_block_content(linked_cell.contents, cell)
        else:
            self._assert_text_content(linked_cell.contents, cell)

    def _assert_field_content(
        self, contents: list[AcadTableLinkedCellContent]
    ) -> None:
        """Assert linked field-cell content references a FIELD copy."""
        assert len(contents) == 1
        content = contents[0]
        assert content.block_record_handle is not None
        field = self.doc.entitydb.get(content.block_record_handle)
        table_content = self._table_content()
        assert content.content_type == 2
        assert isinstance(field, Field)
        assert field.is_alive
        assert table_content is not None
        assert field.dxf.owner == table_content.dxf.handle

    def _assert_block_content(
        self, contents: list[AcadTableLinkedCellContent], cell: AcadTableCell
    ) -> None:
        """Assert linked block-cell content references semantic block data."""
        block_content = self._single_block_content(contents)
        assert block_content.block_record_handle == cell.block_record_handle
        assert block_content.block_attributes == cell.block_attributes

    def _assert_text_content(
        self, contents: list[AcadTableLinkedCellContent], cell: AcadTableCell
    ) -> None:
        """Assert linked text-cell content mirrors semantic text."""
        assert len(contents) == 1
        assert contents[0].content_type == 1
        assert contents[0].text == cell.text

    def _assert_field_list_has_only_live_fields(self) -> None:
        """Assert FIELDLIST has no stale FIELD handles."""
        field_list = self.doc.objects.get_field_list()
        if field_list is not None:
            assert set(field_list.handles).issubset(self._live_field_handles())

    def _assert_no_field_has_missing_owner(self) -> None:
        """Assert non-root FIELD owners resolve."""
        for field in self._live_fields():
            owner = field.dxf.owner
            if owner and owner != "0":
                assert self.doc.entitydb.get(owner) is not None

    def _assert_doc_audit_is_clean(self) -> None:
        """Assert document audit has no errors or fixes."""
        auditor = self.doc.audit()
        assert auditor.has_errors is False
        assert auditor.fixes == []

    def _roundtrip_xrecord(self) -> XRecord | None:
        """Returns the ACAD_TABLE roundtrip xrecord, if present."""
        if not self.table.has_extension_dict:
            return None
        xrecord = self.table.get_extension_dict().dictionary.get(
            "ACAD_XREC_ROUNDTRIP"
        )
        return xrecord if isinstance(xrecord, XRecord) else None

    def _table_content(self) -> TableContent | None:
        """Returns the linked TABLECONTENT object, if present."""
        entity = self.table.get_linked_table_content()
        assert entity is None or isinstance(entity, TableContent)
        return entity if isinstance(entity, TableContent) else None

    def _table_geometry(self) -> TableGeometry | None:
        """Returns the linked TABLEGEOMETRY object, if present."""
        entity = self._roundtrip_entity(361)
        assert entity is None or isinstance(entity, TableGeometry)
        return entity if isinstance(entity, TableGeometry) else None

    def _roundtrip_entity(self, code: int) -> DXFEntity | None:
        """Returns the roundtrip entity referenced by xrecord group code."""
        handle = self._roundtrip_handle(code)
        if handle is None:
            return None
        return self.doc.entitydb.get(handle)

    def _roundtrip_handle(self, code: int) -> str | None:
        """Returns a handle from the roundtrip xrecord."""
        xrecord = self._roundtrip_xrecord()
        if xrecord is None:
            return None
        for tag in xrecord.tags:
            if tag.code == code:
                return str(tag.value)
        return None

    def _linked_block_content(
        self, row: int, col: int
    ) -> AcadTableLinkedCellContent:
        """Returns the linked block content for a block cell."""
        content = self._table_content()
        assert content is not None and content.linked_data is not None
        linked_cell = content.linked_data.get_cell(row, col)
        return self._single_block_content(linked_cell.contents)

    @staticmethod
    def _single_block_content(
        contents: list[AcadTableLinkedCellContent],
    ) -> AcadTableLinkedCellContent:
        """Returns the only block content from a linked cell."""
        block_contents = [
            content for content in contents if content.is_block_content
        ]
        assert len(block_contents) == 1
        return block_contents[0]

    @staticmethod
    def _attribute_values(content: AcadTableLinkedCellContent) -> dict[str, str]:
        """Returns block attribute values keyed by ATTDEF handle."""
        return {attrib.handle: attrib.text for attrib in content.block_attributes}

    def _text_cell_index(self, target: AcadTableCell) -> int:
        """Returns the zero-based index of a text cell among text cells."""
        return [cell for cell in self.data.cells if cell.is_text_cell].index(target)

    def _text_cell_count(self) -> int:
        """Returns the semantic text-cell count."""
        return sum(1 for cell in self.data.cells if cell.is_text_cell)

    def _block_cell_count(self) -> int:
        """Returns the semantic block-cell count."""
        return sum(1 for cell in self.data.cells if cell.is_block_cell)

    def _live_fields(self) -> list[Field]:
        """Returns all live FIELD objects in the document."""
        return [
            entity
            for entity in self.doc.objects
            if isinstance(entity, Field) and entity.is_alive
        ]

    def _live_field_handles(self) -> set[str]:
        """Returns all live FIELD handles in the document."""
        return {
            field.dxf.handle for field in self._live_fields() if field.dxf.handle
        }


def test_text_only_acad_table_integrity_survives_roundtrip() -> None:
    doc = dxfpy.new("R2018")
    table = doc.modelspace().add_table(
        (1, 2),
        [["TITLE", "STATUS"], ["HEADER", "VALUE"], ["DATA", "OK"]],
        row_heights=[11.0, 9.0, 9.0],
        col_widths=[38.0, 28.0],
    )
    table.set_row_height(0, 20.0)
    table.set_col_width(1, 30.0)
    table.set_title_suppressed(True)
    table.set_cell_text(1, 1, "VALUE-LONG")

    AcadTableIntegrityInspector(doc, table).assert_plain_text_table_integrity()
    loaded = roundtrip(doc)
    loaded_table = single_modelspace_table(loaded)

    AcadTableIntegrityInspector(loaded, loaded_table).assert_plain_text_table_integrity()


def test_mixed_field_and_block_table_integrity_survives_roundtrip() -> None:
    doc = dxfpy.new("R2018")
    table = build_mixed_roundtrip_table(doc)

    inspector = AcadTableIntegrityInspector(doc, table)
    inspector.assert_linked_roundtrip_integrity()
    inspector.assert_all_fields_are_registered()
    inspector.assert_field_cell(1, 1, "AcObjProp", "10.0000")
    inspector.assert_field_cell(2, 1, "AcExpr", "25.0000")

    loaded = roundtrip(doc)
    loaded_inspector = AcadTableIntegrityInspector(
        loaded, single_modelspace_table(loaded)
    )

    loaded_inspector.assert_linked_roundtrip_integrity()
    loaded_inspector.assert_all_fields_are_registered()
    loaded_inspector.assert_field_cell(1, 1, "AcObjProp", "10.0000")
    loaded_inspector.assert_field_cell(2, 1, "AcExpr", "25.0000")


def test_acexpr_field_children_survive_later_table_rebuilds() -> None:
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    circle = msp.add_circle((25, 0), 2.5)
    table = msp.add_table(
        (0, 0),
        [["KIND", "VALUE"], ["Expression", "25.0000"], ["Later", "value"]],
        col_widths=[30.0, 35.0],
    )
    length = Field()
    length.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    radius = Field()
    radius.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    table.new_cell_acexpr_field(
        1,
        1,
        r"(%<\_FldIdx 0>%*%<\_FldIdx 1>%)",
        [length, radius],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    table.set_cell_alignment(2, 1, 5)

    assert_acexpr_children(table, 1, 1, [[line.dxf.handle], [circle.dxf.handle]])
    loaded = roundtrip(doc)
    loaded_line, loaded_circle = loaded.modelspace().query("LINE CIRCLE")
    loaded_table = single_modelspace_table(loaded)

    assert_acexpr_children(
        loaded_table,
        1,
        1,
        [[loaded_line.dxf.handle], [loaded_circle.dxf.handle]],
    )


def test_attributed_block_cell_linked_integrity_survives_roundtrip() -> None:
    doc = dxfpy.new("R2018")
    table = build_mixed_roundtrip_table(doc)
    values = block_attribute_expectation(doc, "TABLE_INTEGRITY_BLOCK")

    inspector = AcadTableIntegrityInspector(doc, table)
    inspector.assert_block_cell_attribs(3, 1, "TABLE_INTEGRITY_BLOCK", values)

    loaded = roundtrip(doc)
    loaded_values = block_attribute_expectation(loaded, "TABLE_INTEGRITY_BLOCK")
    loaded_inspector = AcadTableIntegrityInspector(
        loaded, single_modelspace_table(loaded)
    )

    loaded_inspector.assert_block_cell_attribs(
        3, 1, "TABLE_INTEGRITY_BLOCK", loaded_values
    )


def test_linked_block_cell_content_omits_rejected_scale_alignment_tags() -> None:
    doc = dxfpy.new("R2018")
    table = build_mixed_roundtrip_table(doc)

    codes = exported_block_cell_content_codes(table)

    assert 340 in codes
    assert 330 in codes
    assert 144 not in codes
    assert 170 not in codes


def build_mixed_roundtrip_table(doc: Drawing) -> AcadTableBlockContent:
    """Returns a table that requires field and block-cell roundtrip support."""
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    circle = msp.add_circle((25, 0), 2.5)
    block = doc.blocks.new("TABLE_INTEGRITY_BLOCK", base_point=(0, 0))
    block.add_lwpolyline([(0, 0), (4, 0), (4, 2), (0, 2)], close=True)
    block.add_attdef("NAME", insert=(0.5, 0.5), text="unset")
    table = msp.add_table(
        (0, 0),
        [
            ["KIND", "VALUE"],
            ["Length", "10.0000"],
            ["Expression", "25.0000"],
            ["Block", ""],
        ],
        col_widths=[30.0, 35.0],
    )
    table.new_cell_acobjprop_field(
        1, 1, line, "Length", text="10.0000", register_field_list=True
    )
    length = Field()
    length.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    radius = Field()
    radius.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    table.new_cell_acexpr_field(
        2,
        1,
        r"(%<\_FldIdx 0>%*%<\_FldIdx 1>%)",
        [length, radius],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )
    table.set_cell_block(
        3, 1, "TABLE_INTEGRITY_BLOCK", block_scale=1.25, alignment=5
    )
    table.set_cell_block_attribs(3, 1, {"NAME": "Widget"})
    return table


def block_attribute_expectation(
    doc: Drawing, block_name: str
) -> BlockAttributeExpectation:
    """Returns expected block-cell values keyed by tag and handle."""
    block = doc.blocks.get(block_name)
    return BlockAttributeExpectation(
        by_tag={attdef.dxf.tag: "Widget" for attdef in block.attdefs()},
        by_handle={attdef.dxf.handle: "Widget" for attdef in block.attdefs()},
        block_scale=1.25,
        alignment=5,
    )


def exported_block_cell_content_codes(table: AcadTableBlockContent) -> list[int]:
    """Returns DXF group codes in the linked block-cell content wrapper."""
    table_content = table.get_linked_table_content()
    assert isinstance(table_content, TableContent)
    assert table.doc is not None
    collector = TagCollector(dxfversion=table.doc.dxfversion)
    table_content.export_dxf(collector)
    tags = list(collector.tags)
    for start, tag in enumerate(tags):
        if tag.code == 1 and tag.value == "CELLCONTENT_BEGIN":
            content_tags = tags[start:content_end_index(tags, start)]
            if content_type(content_tags) == 4:
                return [content_tag.code for content_tag in content_tags]
    raise AssertionError("linked block-cell content not exported")


def content_end_index(tags: list[DXFTag], start: int) -> int:
    """Returns the end index of a CELLCONTENT tag section."""
    for index in range(start + 1, len(tags)):
        tag = tags[index]
        if tag.code == 309 and tag.value == "CELLCONTENT_END":
            return index + 1
    raise AssertionError("CELLCONTENT_END not exported")


def content_type(tags: list[DXFTag]) -> int | None:
    """Returns the linked cell content type."""
    for tag in tags:
        if tag.code == 90:
            return int(tag.value)
    return None


def assert_acexpr_children(
    table: AcadTableBlockContent,
    row: int,
    col: int,
    expected_object_handles: list[list[str]],
) -> None:
    """Assert ACAD_TABLE and TABLECONTENT AcExpr child fields."""
    primary = table.get_cell_primary_field(row, col)
    assert primary is not None
    assert primary.evaluator_id == "AcExpr"
    children = primary.get_child_fields()
    assert [child.object_handles for child in children] == expected_object_handles
    linked = linked_field_primary(table, row, col)
    assert linked is not None
    assert linked.evaluator_id == "AcExpr"
    assert linked.get_child_fields() == children


def linked_field_primary(
    table: AcadTableBlockContent, row: int, col: int
) -> Field | None:
    """Returns the TABLECONTENT primary FIELD copy for a cell."""
    linked_cell = table.get_linked_cell(row, col)
    for content in linked_cell.contents:
        if content.content_type != 2 or content.block_record_handle is None:
            continue
        assert table.doc is not None
        wrapper = table.doc.entitydb.get(content.block_record_handle)
        if not isinstance(wrapper, Field):
            return None
        children = wrapper.get_child_fields()
        return children[0] if wrapper.is_text_wrapper and children else wrapper
    return None


def single_modelspace_table(doc: Drawing) -> AcadTableBlockContent:
    """Returns the only ACAD_TABLE entity in modelspace."""
    tables = list(doc.modelspace().query("ACAD_TABLE"))
    assert len(tables) == 1
    table = tables[0]
    assert isinstance(table, AcadTableBlockContent)
    return table


def roundtrip(doc: Drawing) -> Drawing:
    """Returns a document loaded from its DXF text representation."""
    stream = StringIO()
    doc.write(stream)
    return dxfpy.read(StringIO(stream.getvalue()))
