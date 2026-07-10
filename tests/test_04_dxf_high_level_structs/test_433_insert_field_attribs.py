# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
import dxfpy


def test_insert_add_attrib_acvar_field():
    doc = dxfpy.new("R2007")
    block = doc.blocks.new("TEST")
    blockref = doc.modelspace().add_blockref("TEST", insert=(0, 0))

    attrib = blockref.add_attrib_acvar_field(
        "TAG1",
        "----",
        insert=(0, 0),
        field_name="Author",
        register_field_list=True,
    )

    primary = attrib.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcVar"
    assert primary.field_code == "\\AcVar Author"


def test_insert_add_attrib_dwgprops_field():
    doc = dxfpy.new("R2007")
    block = doc.blocks.new("TEST")
    blockref = doc.modelspace().add_blockref("TEST", insert=(0, 0))

    attrib = blockref.add_attrib_dwgprops_field(
        "TAG1",
        "VALUE-123",
        insert=(0, 0),
        property_name="ProjectCode",
        register_field_list=True,
    )

    primary = attrib.get_primary_field()
    assert primary is not None
    assert primary.field_code == "\\AcVar CustomDP.ProjectCode"
    assert doc.header.custom_vars.get("ProjectCode") == "VALUE-123"


def test_insert_add_attrib_acobjprop_field():
    doc = dxfpy.new("R2007")
    block = doc.blocks.new("TEST")
    line = doc.modelspace().add_line((0, 0), (10, 0))
    blockref = doc.modelspace().add_blockref("TEST", insert=(0, 0))

    attrib = blockref.add_attrib_acobjprop_field(
        "TAG1",
        "",
        insert=(0, 0),
        target=line,
        property_name="Length",
        register_field_list=True,
    )

    primary = attrib.get_primary_field()
    assert primary is not None
    assert attrib.dxf.owner == blockref.dxf.handle
    assert primary.evaluator_id == "AcObjProp"
    assert primary.object_handles == [line.dxf.handle]
