# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
import dxfpy
from dxfpy.entities.dxfobj import Field
from dxfpy.math import Vec2


def test_text_new_acvar_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    txt = doc.modelspace().add_text("TEXT")
    child, wrapper = txt.new_acvar_field("Author", text="----", register_field_list=True)

    assert txt.dxf.text == "----"
    assert txt.get_field() is wrapper
    assert txt.get_primary_field() is child
    assert child.evaluator_id == "AcVar"
    assert child.field_code == "\\AcVar Author"


def test_graphicsfactory_add_text_acobjprop_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    txt = msp.add_text_acobjprop_field(line, "Length", register_field_list=True)

    assert txt.dxf.text == "10.0000"
    primary = txt.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcObjProp"
    assert primary.object_handles == [line.dxf.handle]


def test_text_new_dwgprops_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    txt = doc.modelspace().add_text("TEXT")
    child, wrapper = txt.new_dwgprops_field(
        "ProjectCode", text="VALUE-123", register_field_list=True
    )

    assert txt.dxf.text == "VALUE-123"
    assert txt.get_field() is wrapper
    assert txt.get_primary_field() is child
    assert child.evaluator_id == "AcVar"
    assert child.field_code == "\\AcVar CustomDP.ProjectCode"


def test_text_set_linked_fields_attaches_multiple_custom_properties():
    doc = dxfpy.new("R2007")
    text = doc.modelspace().add_text("---- / ----")
    first = Field()
    first.set_dwgprops("ProjectCode", display="----")
    second = Field()
    second.set_dwgprops("Revision", display="----")

    wrapper = text.set_linked_fields(
        [first, second],
        field_code="%<\\_FldIdx 0>% / %<\\_FldIdx 1>%",
        register_field_list=True,
    )

    assert text.get_field() is wrapper
    assert wrapper.child_handles == [first.dxf.handle, second.dxf.handle]
    assert first.dxf.owner == wrapper.dxf.handle
    assert second.dxf.owner == wrapper.dxf.handle


def test_graphicsfactory_add_text_dwgprops_field():
    doc = dxfpy.new("R2007")
    txt = doc.modelspace().add_text_dwgprops_field(
        "ProjectCode",
        text="VALUE-123",
        register_field_list=True,
    )
    assert txt.dxf.text == "VALUE-123"
    primary = txt.get_primary_field()
    assert primary is not None
    assert primary.field_code == "\\AcVar CustomDP.ProjectCode"
    assert doc.header.custom_vars.get("ProjectCode") == "VALUE-123"


def test_graphicsfactory_add_text_acexpr_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    circle = msp.add_circle((5, 0), radius=2.5)
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")

    txt = msp.add_text_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    assert txt.dxf.text == "25.0000"
    primary = txt.get_primary_field()
    assert primary is not None
    assert primary.evaluator_id == "AcExpr"
    assert primary.field_code == "\\AcExpr (%<\\_FldIdx 0>%*%<\\_FldIdx 1>%) \\f \"%lu2\""
    children = primary.get_child_fields()
    assert len(children) == 2
    assert children[0].evaluator_id == "AcObjProp"
    assert children[1].evaluator_id == "AcObjProp"


def test_multileader_new_acvar_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    builder = msp.add_multileader_mtext("Standard")
    builder.set_content("TEXT")
    builder.build(insert=Vec2(0, 0))
    ml = builder.multileader

    child, wrapper = ml.new_acvar_field("Author", text="----", register_field_list=True)

    assert ml.get_mtext_content() == "----"
    assert ml.get_field() is wrapper
    assert ml.get_primary_field() is child
    assert child.evaluator_id == "AcVar"
    assert child.field_code == "\\AcVar Author"


def test_multileader_new_acobjprop_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    builder = msp.add_multileader_mtext("Standard")
    builder.set_content("TEXT")
    builder.build(insert=Vec2(0, 0))
    ml = builder.multileader

    child, wrapper = ml.new_acobjprop_field(line, "Length", register_field_list=True)

    assert ml.get_mtext_content() == "10.0000"
    assert ml.get_field() is wrapper
    assert ml.get_primary_field() is child
    assert child.evaluator_id == "AcObjProp"
    assert child.object_handles == [line.dxf.handle]
    assert (94, 27) in child.tags
    assert (6, "ACFD_FIELDTEXT_CHECKSUM") not in wrapper.tags
    assert (94, 9) in wrapper.tags


def test_multileader_new_dwgprops_field_creates_object_backed_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    builder = msp.add_multileader_mtext("Standard")
    builder.set_content("TEXT")
    builder.build(insert=Vec2(0, 0))
    ml = builder.multileader

    child, wrapper = ml.new_dwgprops_field(
        "ProjectCode", text="VALUE-123", register_field_list=True
    )

    assert ml.get_mtext_content() == "VALUE-123"
    assert ml.get_field() is wrapper
    assert ml.get_primary_field() is child
    assert child.evaluator_id == "AcVar"
    assert child.field_code == "\\AcVar CustomDP.ProjectCode"
    assert doc.header.custom_vars.get("ProjectCode") == "VALUE-123"


def test_multileader_set_linked_fields_uses_mleader_wrapper_shape():
    doc = dxfpy.new("R2007")
    builder = doc.modelspace().add_multileader_mtext("Standard")
    builder.set_content("---- / ----")
    builder.build(insert=Vec2(0, 0))
    multileader = builder.multileader
    first = Field()
    first.set_dwgprops("ProjectCode", display="----")
    second = Field()
    second.set_dwgprops("Revision", display="----")

    wrapper = multileader.set_linked_fields(
        [first, second],
        field_code="%<\\_FldIdx 0>% / %<\\_FldIdx 1>%",
        register_field_list=True,
    )

    assert wrapper.child_handles == [first.dxf.handle, second.dxf.handle]
    assert (94, 9) in wrapper.tags
    assert (6, "ACFD_FIELDTEXT_CHECKSUM") not in wrapper.tags
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert all(field.dxf.handle in field_list.handles for field in wrapper.get_field_tree())


def test_multileader_new_acexpr_field_creates_nested_expression_field():
    doc = dxfpy.new("R2007")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    circle = msp.add_circle((5, 0), radius=2.5)
    builder = msp.add_multileader_mtext("Standard")
    builder.set_content("TEXT")
    builder.build(insert=Vec2(0, 0))
    ml = builder.multileader
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")

    expr, wrapper = ml.new_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    assert ml.get_mtext_content() == "25.0000"
    assert ml.get_field() is wrapper
    assert ml.get_primary_field() is expr
    assert expr.evaluator_id == "AcExpr"
    assert expr.field_code == "\\AcExpr (%<\\_FldIdx 0>%*%<\\_FldIdx 1>%) \\f \"%lu2\""
    children = expr.get_child_fields()
    assert len(children) == 2
    assert children[0].evaluator_id == "AcObjProp"
    assert children[1].evaluator_id == "AcObjProp"
    assert (6, "ACAD_ROUNDTRIP_2008_FIELD_EVALOPTION") not in expr.tags
    assert (6, "ACFD_FIELDTEXT_CHECKSUM") not in wrapper.tags
    assert (94, 9) in wrapper.tags
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    for field in wrapper.get_field_tree():
        assert field.dxf.handle in field_list.handles
