from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import Callable, Protocol, Sequence, cast

import pytest

import dxfpy
from dxfpy.audit import AuditError
from dxfpy.document import Drawing
from dxfpy.entities import DXFEntity, Field
from dxfpy.entities.acad_table import (
    AcadTableBlockContent,
    AcadTableLinkedCellContent,
    TableContent,
)
from dxfpy.math import Vec2


class FieldHost(Protocol):
    def get_field(self) -> Field | None: ...

    def remove_field(
        self, key: str = "TEXT", *, text: str | None = None
    ) -> None: ...

    def new_acexpr_field(
        self,
        expression: str,
        child_fields: Sequence[Field],
        *,
        value: float,
        display: str,
        text: str,
        register_field_list: bool,
    ) -> tuple[Field, Field]: ...


@dataclass(frozen=True)
class HostCase:
    name: str
    factory: Callable[[], tuple[Drawing, FieldHost, DXFEntity]]
    visible_text: Callable[[FieldHost], str]


def live_fields(doc: Drawing) -> list[Field]:
    return [
        entity
        for entity in doc.objects
        if isinstance(entity, Field) and entity.is_alive
    ]


def live_field_handles(doc: Drawing) -> set[str]:
    return {field.dxf.handle for field in live_fields(doc) if field.dxf.handle}


def field_list_handles(doc: Drawing) -> list[str]:
    field_list = doc.objects.get_field_list()
    return list(field_list.handles) if field_list is not None else []


def field_tree_handles(field: Field | None) -> set[str]:
    if field is None:
        return set()
    return {item.dxf.handle for item in field.get_field_tree() if item.dxf.handle}


def assert_field_list_has_only_live_fields(doc: Drawing) -> None:
    field_handles = live_field_handles(doc)

    assert set(field_list_handles(doc)).issubset(field_handles)


def assert_no_field_has_missing_owner(doc: Drawing) -> None:
    for field in live_fields(doc):
        owner = field.dxf.owner
        if owner and owner != "0":
            assert doc.entitydb.get(owner) is not None


def assert_field_state_is_clean(doc: Drawing) -> None:
    assert_field_list_has_only_live_fields(doc)
    assert_no_field_has_missing_owner(doc)
    auditor = doc.audit()

    assert auditor.has_errors is False
    assert auditor.fixes == []


def roundtrip(doc: Drawing) -> Drawing:
    stream = StringIO()
    doc.write(stream)
    return dxfpy.read(StringIO(stream.getvalue()))


def test_audit_prunes_invalid_field_list_handles() -> None:
    doc = dxfpy.new("R2018")
    owner = doc.rootdict.dxf.handle
    field = doc.objects.add_field(owner=owner)
    field.set_acvar("Author", display="----")
    xrecord = doc.objects.add_xrecord(owner=owner)
    field_handle = field.dxf.handle
    xrecord_handle = xrecord.dxf.handle
    assert field_handle is not None
    assert xrecord_handle is not None
    field_list = doc.objects.setup_field_list()
    field_list.handles = [field_handle, xrecord_handle, "DEAD"]

    auditor = doc.audit()

    assert auditor.has_errors is False
    assert field_list.handles == [field_handle]
    assert any(
        fix.code == AuditError.POINTER_TARGET_NOT_EXIST
        and fix.entity is field_list
        and fix.data == [xrecord_handle, "DEAD"]
        for fix in auditor.fixes
    )


def replace_with_expression_field(host: FieldHost, line: DXFEntity) -> None:
    child = Field()
    child.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    host.new_acexpr_field(
        r"%<\_FldIdx 0>%",
        [child],
        value=10.0,
        display="10.0000",
        text="10.0000",
        register_field_list=True,
    )


def make_text_host() -> tuple[Drawing, FieldHost, DXFEntity]:
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    host = msp.add_text("A", dxfattribs={"insert": (0, 0)})
    host.new_acvar_field("Author", text="A", register_field_list=True)
    return doc, host, line


def make_mtext_host() -> tuple[Drawing, FieldHost, DXFEntity]:
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    host = msp.add_mtext("A", dxfattribs={"insert": (0, 0)})
    host.new_acvar_field("Author", text="A", register_field_list=True)
    return doc, host, line


def make_multileader_host() -> tuple[Drawing, FieldHost, DXFEntity]:
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    builder = msp.add_multileader_mtext("Standard")
    builder.set_content("A")
    builder.build(insert=Vec2(0, 0))
    host = builder.multileader
    host.new_acvar_field("Author", text="A", register_field_list=True)
    return doc, host, line


def make_attdef_host() -> tuple[Drawing, FieldHost, DXFEntity]:
    doc = dxfpy.new("R2018")
    line = doc.modelspace().add_line((0, 0), (10, 0))
    block = doc.blocks.new("B")
    host = block.add_attdef("TAG", (0, 0), text="A")
    host.new_acvar_field("Author", text="A", register_field_list=True)
    return doc, host, line


def make_attrib_host() -> tuple[Drawing, FieldHost, DXFEntity]:
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    block = doc.blocks.new("B")
    block.add_attdef("TAG", (0, 0), text="A")
    insert = msp.add_blockref("B", (0, 0))
    host = insert.add_attrib("TAG", "A", (0, 0))
    host.new_acvar_field("Author", text="A", register_field_list=True)
    return doc, host, line


def make_insert_attrib_helper_host() -> tuple[Drawing, FieldHost, DXFEntity]:
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    block = doc.blocks.new("B")
    block.add_attdef("TAG", (0, 0), text="A")
    insert = msp.add_blockref("B", (0, 0))
    host = insert.add_attrib_acvar_field(
        "TAG", "A", (0, 0), field_name="Author", register_field_list=True
    )
    return doc, host, line


def text_dxf_content(host: FieldHost) -> str:
    return str(getattr(host, "dxf").text)


def mtext_content(host: FieldHost) -> str:
    return str(getattr(host, "text"))


def multileader_content(host: FieldHost) -> str:
    get_content = getattr(host, "get_mtext_content")
    return str(get_content())


HOST_FACTORIES: tuple[
    tuple[str, Callable[[], tuple[Drawing, FieldHost, DXFEntity]]], ...
] = (
    ("TEXT", make_text_host),
    ("MTEXT", make_mtext_host),
    ("MULTILEADER", make_multileader_host),
    ("ATTDEF", make_attdef_host),
    ("ATTRIB", make_attrib_host),
    ("INSERT_ATTRIB_HELPER", make_insert_attrib_helper_host),
)

HOST_CASES: tuple[HostCase, ...] = (
    HostCase("TEXT", make_text_host, text_dxf_content),
    HostCase("MTEXT", make_mtext_host, mtext_content),
    HostCase("MULTILEADER", make_multileader_host, multileader_content),
    HostCase("ATTDEF", make_attdef_host, text_dxf_content),
    HostCase("ATTRIB", make_attrib_host, text_dxf_content),
    HostCase("INSERT_ATTRIB_HELPER", make_insert_attrib_helper_host, text_dxf_content),
)

COPY_HOST_CASES = HOST_CASES[:3]


@pytest.mark.parametrize("_name, factory", HOST_FACTORIES)
def test_replacing_linked_field_cleans_old_field_tree(
    _name: str, factory: Callable[[], tuple[Drawing, FieldHost, DXFEntity]]
) -> None:
    doc, host, line = factory()
    old_handles = field_tree_handles(host.get_field())

    replace_with_expression_field(host, line)

    new_handles = field_tree_handles(host.get_field())

    assert old_handles.isdisjoint(live_field_handles(doc))
    assert new_handles.issubset(live_field_handles(doc))
    assert_field_state_is_clean(doc)


@pytest.mark.parametrize("_name, factory", HOST_FACTORIES)
def test_replacing_linked_field_cleanup_survives_roundtrip(
    _name: str, factory: Callable[[], tuple[Drawing, FieldHost, DXFEntity]]
) -> None:
    doc, host, line = factory()

    replace_with_expression_field(host, line)

    loaded = roundtrip(doc)

    assert_field_state_is_clean(loaded)


@pytest.mark.parametrize("case", HOST_CASES, ids=lambda case: case.name)
def test_remove_field_deletes_field_tree_and_sets_static_text(case: HostCase) -> None:
    doc, host, _line = case.factory()
    old_handles = field_tree_handles(host.get_field())

    host.remove_field(text="STATIC")

    assert host.get_field() is None
    assert case.visible_text(host) == "STATIC"
    assert old_handles.isdisjoint(live_field_handles(doc))
    assert_field_state_is_clean(doc)


@pytest.mark.parametrize("case", HOST_CASES, ids=lambda case: case.name)
def test_remove_field_preserves_visible_text_by_default(case: HostCase) -> None:
    doc, host, _line = case.factory()

    host.remove_field()

    assert host.get_field() is None
    assert case.visible_text(host) == "A"
    assert_field_state_is_clean(doc)


@pytest.mark.parametrize("case", HOST_CASES, ids=lambda case: case.name)
def test_removed_field_cleanup_survives_roundtrip(case: HostCase) -> None:
    doc, host, _line = case.factory()

    host.remove_field(text="STATIC")

    loaded = roundtrip(doc)

    assert_field_state_is_clean(loaded)


@pytest.mark.parametrize("case", HOST_CASES, ids=lambda case: case.name)
def test_remove_missing_field_is_no_op(case: HostCase) -> None:
    doc, host, _line = case.factory()
    host.remove_field(text="FIRST")

    host.remove_field(text="SECOND")

    assert case.visible_text(host) == "FIRST"
    assert_field_state_is_clean(doc)


@pytest.mark.parametrize("case", COPY_HOST_CASES, ids=lambda case: case.name)
def test_copy_to_layout_deep_copies_registered_field_tree(case: HostCase) -> None:
    doc, host, line = case.factory()
    replace_with_expression_field(host, line)
    source_root = host.get_field()
    assert source_root is not None
    source_tree = source_root.get_field_tree()
    target = doc.layout("Layout1")

    clone_entity = cast(DXFEntity, host).copy_to_layout(target)
    clone = cast(FieldHost, clone_entity)
    clone_root = clone.get_field()

    assert clone_root is not None
    clone_tree = clone_root.get_field_tree()
    assert len(clone_tree) == len(source_tree)
    assert field_tree_handles(clone_root).isdisjoint(field_tree_handles(source_root))
    assert all(
        clone_field is not source_field
        for clone_field, source_field in zip(clone_tree, source_tree)
    )
    assert clone_root.get_reactors() == [clone_root.dxf.owner]
    for parent in clone_tree:
        for child in parent.get_child_fields():
            assert child.dxf.owner == parent.dxf.handle
    assert line.dxf.handle in {
        handle for field in clone_tree for handle in field.object_handles
    }
    assert field_tree_handles(clone_root).issubset(set(field_list_handles(doc)))

    loaded = roundtrip(doc)
    loaded_clone = cast(FieldHost, loaded.layout("Layout1")[0])
    loaded_root = loaded_clone.get_field()
    assert loaded_root is not None
    assert len(loaded_root.get_field_tree()) == len(source_tree)
    assert_field_state_is_clean(loaded)


@pytest.mark.parametrize("case", COPY_HOST_CASES, ids=lambda case: case.name)
def test_deleting_host_copy_preserves_source_field_tree(case: HostCase) -> None:
    doc, host, _line = case.factory()
    source_root = host.get_field()
    assert source_root is not None
    source_handles = field_tree_handles(source_root)
    target = doc.layout("Layout1")
    clone_entity = cast(DXFEntity, host).copy_to_layout(target)
    clone = cast(FieldHost, clone_entity)
    clone_handles = field_tree_handles(clone.get_field())

    target.delete_entity(clone_entity)  # type: ignore[arg-type]

    assert source_handles.issubset(live_field_handles(doc))
    assert clone_handles.isdisjoint(live_field_handles(doc))
    assert_field_state_is_clean(doc)


def test_copy_unregistered_field_tree_does_not_create_field_list() -> None:
    doc = dxfpy.new("R2018")
    source = doc.modelspace().add_mtext("A")
    source.new_acvar_field("Author", text="A")

    clone = source.copy_to_layout(doc.layout("Layout1"))

    assert clone.get_primary_field() is not source.get_primary_field()
    assert doc.objects.get_field_list() is None


def test_copy_preflights_invalid_target_field_list_before_binding() -> None:
    source_doc = dxfpy.new("R2018")
    source = source_doc.modelspace().add_mtext("A")
    source.new_acvar_field("Author", text="A", register_field_list=True)
    clone = source.copy()
    target_doc = dxfpy.new("R2018")
    invalid_field_list = target_doc.objects.add_xrecord()
    target_doc.rootdict.add("ACAD_FIELDLIST", invalid_field_list)
    target = target_doc.modelspace()
    entity_handles = set(target_doc.entitydb)
    object_count = len(target_doc.objects)

    with pytest.raises(dxfpy.DXFStructureError, match="FIELDLIST"):
        target.add_entity(clone)

    assert len(target) == 0
    assert set(target_doc.entitydb) == entity_handles
    assert len(target_doc.objects) == object_count
    assert clone.dxf.handle is None
    assert clone.doc is source_doc


def linked_cell_contents(
    table: AcadTableBlockContent, row: int, col: int
) -> list[AcadTableLinkedCellContent]:
    table_content = table.get_linked_table_content()
    if not isinstance(table_content, TableContent) or table_content.linked_data is None:
        return []
    return table_content.linked_data.get_cell(row, col).contents


def test_replacing_table_cell_field_keeps_field_state_clean() -> None:
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    table = msp.add_table((0, 0), [["FIELD", "VALUE"], ["AcVar", "----"]])

    table.new_cell_acvar_field(1, 1, "Author", text="----", register_field_list=True)
    old_handles = live_field_handles(doc)

    table.new_cell_acobjprop_field(
        1, 1, line, "Length", text="10.0000", register_field_list=True
    )

    assert old_handles.isdisjoint(live_field_handles(doc))
    assert linked_cell_contents(table, 1, 1)[0].content_type == 2
    assert_field_state_is_clean(doc)


def test_removing_table_cell_field_cleans_roundtrip_metadata() -> None:
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    table = msp.add_table((0, 0), [["FIELD", "VALUE"], ["AcVar", "----"]])
    table.new_cell_acvar_field(1, 1, "Author", text="----", register_field_list=True)

    table.set_cell_text(1, 1, "STATIC")

    cell = table.get_cell(1, 1)
    contents = linked_cell_contents(table, 1, 1)

    assert cell.field_handle is None
    assert live_fields(doc) == []
    assert contents[0].content_type == 1
    assert contents[0].text == "STATIC"
    assert_field_state_is_clean(doc)


def test_removed_table_cell_field_cleanup_survives_roundtrip() -> None:
    doc = dxfpy.new("R2018")
    table = doc.modelspace().add_table(
        (0, 0), [["FIELD", "VALUE"], ["AcVar", "----"]]
    )
    table.new_cell_acvar_field(1, 1, "Author", text="----", register_field_list=True)
    table.set_cell_text(1, 1, "STATIC")

    loaded = roundtrip(doc)
    loaded_table = list(loaded.modelspace().query("ACAD_TABLE"))[0]
    contents = linked_cell_contents(loaded_table, 1, 1)

    assert loaded_table.get_cell(1, 1).field_handle is None
    assert live_fields(loaded) == []
    assert contents[0].content_type == 1
    assert contents[0].text == "STATIC"
    assert_field_state_is_clean(loaded)


def test_remove_cell_field_preserves_field_display_text() -> None:
    doc = dxfpy.new("R2018")
    table = doc.modelspace().add_table(
        (0, 0), [["FIELD", "VALUE"], ["AcVar", "----"]]
    )
    table.new_cell_acvar_field(1, 1, "Author", text="VISIBLE", register_field_list=True)

    cell = table.remove_cell_field(1, 1)
    contents = linked_cell_contents(table, 1, 1)

    assert cell.field_handle is None
    assert cell.text == "VISIBLE"
    assert live_fields(doc) == []
    assert contents[0].content_type == 1
    assert contents[0].text == "VISIBLE"
    assert_field_state_is_clean(doc)


def test_remove_cell_field_uses_explicit_static_text() -> None:
    doc = dxfpy.new("R2018")
    table = doc.modelspace().add_table(
        (0, 0), [["FIELD", "VALUE"], ["AcVar", "----"]]
    )
    table.new_cell_acvar_field(1, 1, "Author", text="VISIBLE", register_field_list=True)

    cell = table.remove_cell_field(1, 1, text="EXPLICIT")
    contents = linked_cell_contents(table, 1, 1)

    assert cell.field_handle is None
    assert cell.text == "EXPLICIT"
    assert live_fields(doc) == []
    assert contents[0].content_type == 1
    assert contents[0].text == "EXPLICIT"
    assert_field_state_is_clean(doc)


def test_remove_cell_field_cleanup_survives_roundtrip() -> None:
    doc = dxfpy.new("R2018")
    table = doc.modelspace().add_table(
        (0, 0), [["FIELD", "VALUE"], ["AcVar", "----"]]
    )
    table.new_cell_acvar_field(1, 1, "Author", text="VISIBLE", register_field_list=True)
    table.remove_cell_field(1, 1)

    loaded = roundtrip(doc)
    loaded_table = list(loaded.modelspace().query("ACAD_TABLE"))[0]
    contents = linked_cell_contents(loaded_table, 1, 1)

    assert loaded_table.get_cell(1, 1).field_handle is None
    assert live_fields(loaded) == []
    assert contents[0].content_type == 1
    assert contents[0].text == "VISIBLE"
    assert_field_state_is_clean(loaded)


def test_remove_missing_cell_field_is_no_op() -> None:
    doc = dxfpy.new("R2018")
    table = doc.modelspace().add_table((0, 0), [["FIELD", "VALUE"]])

    cell = table.remove_cell_field(0, 1, text="IGNORED")

    assert cell.text == "VALUE"
    assert_field_state_is_clean(doc)
