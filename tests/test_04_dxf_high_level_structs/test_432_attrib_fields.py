# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
import dxfpy


def test_attdef_new_dwgprops_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    block = doc.blocks.new("TEST")
    attdef = block.add_attdef("TAG1", insert=(0, 0), text="TEXT")

    child, wrapper = attdef.new_dwgprops_field(
        "ProjectCode", text="VALUE-123", register_field_list=True
    )

    assert attdef.dxf.text == "VALUE-123"
    assert attdef.get_field() is wrapper
    assert attdef.get_primary_field() is child
    assert child.evaluator_id == "AcVar"
    assert child.field_code == "\\AcVar CustomDP.ProjectCode"


def test_attrib_new_dwgprops_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    block = doc.blocks.new("TEST")
    blockref = doc.modelspace().add_blockref("TEST", insert=(0, 0))
    attrib = blockref.add_attrib("TAG1", "TEXT", insert=(0, 0))

    child, wrapper = attrib.new_dwgprops_field(
        "ProjectCode", text="VALUE-123", register_field_list=True
    )

    assert attrib.dxf.text == "VALUE-123"
    assert attrib.get_field() is wrapper
    assert attrib.get_primary_field() is child
    assert child.evaluator_id == "AcVar"
    assert child.field_code == "\\AcVar CustomDP.ProjectCode"


def test_add_attdef_acvar_field():
    doc = dxfpy.new("R2007")
    block = doc.blocks.new("TEST")
    attdef = block.add_attdef_acvar_field(
        "TAG1",
        insert=(0, 0),
        text="----",
        field_name="Author",
        register_field_list=True,
    )
    primary = attdef.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcVar"
    assert primary.field_code == "\\AcVar Author"


def test_add_attdef_dwgprops_field():
    doc = dxfpy.new("R2007")
    block = doc.blocks.new("TEST")
    attdef = block.add_attdef_dwgprops_field(
        "TAG1",
        insert=(0, 0),
        text="VALUE-123",
        property_name="ProjectCode",
        register_field_list=True,
    )
    primary = attdef.get_primary_field()
    assert primary is not None
    assert primary.field_code == "\\AcVar CustomDP.ProjectCode"
    assert doc.header.custom_vars.get("ProjectCode") == "VALUE-123"


def test_add_attdef_acobjprop_field():
    doc = dxfpy.new("R2007")
    block = doc.blocks.new("TEST")
    line = doc.modelspace().add_line((0, 0), (10, 0))
    attdef = block.add_attdef_acobjprop_field(
        "TAG1",
        insert=(0, 0),
        text="",
        target=line,
        property_name="Length",
        register_field_list=True,
    )
    primary = attdef.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcObjProp"
    assert primary.object_handles == [line.dxf.handle]
