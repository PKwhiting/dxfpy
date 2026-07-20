# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
from typing import cast
import io
import math
import dxfpy
import pytest

from dxfpy.entities.dxfobj import Field
from dxfpy.entities.mtext import MText
from dxfpy.lldxf.tagwriter import TagCollector, basic_tags_from_text


def test_set_text_wrapper_fields_links_multiple_children():
    doc = dxfpy.new("R2018")
    first = doc.objects.add_field(owner="0")
    first.set_dwgprops("First", display="A")
    second = doc.objects.add_field(owner="0")
    second.set_dwgprops("Second", display="B")
    wrapper = doc.objects.add_field(owner="0")

    wrapper.set_text_wrapper_fields(
        [first, second],
        field_code="%<\\_FldIdx 0>% / %<\\_FldIdx 1>%",
        text="---- / ----",
    )

    assert wrapper.evaluator_id == "_text"
    assert wrapper.field_code == "%<\\_FldIdx 0>% / %<\\_FldIdx 1>%"
    assert wrapper.child_handles == [first.dxf.handle, second.dxf.handle]

    stream = io.StringIO()
    doc.write(stream)
    stream.seek(0)
    reloaded = dxfpy.read(stream)
    reloaded_wrapper = reloaded.entitydb.get(wrapper.dxf.handle)
    assert isinstance(reloaded_wrapper, Field)
    assert reloaded_wrapper.field_code == wrapper.field_code
    assert reloaded_wrapper.child_handles == wrapper.child_handles


def test_set_text_wrapper_fields_rejects_invalid_child_type():
    wrapper = Field()

    with pytest.raises(dxfpy.DXFTypeError):
        wrapper.set_text_wrapper_fields([None], field_code="")  # type: ignore[list-item]

FIELD = """0
FIELD
5
0
330
0
100
AcDbField
1
AcVar
2
\\AcVar Author
90
0
301
----
98
4
"""

FIELD_WITH_OVERFLOW = """0
FIELD
5
0
330
0
100
AcDbField
1
AcExpr
2
abc
3
def
90
1
"""


@pytest.fixture
def entity():
    return Field.from_text(FIELD)


def test_registered():
    from dxfpy.entities.factory import ENTITY_CLASSES

    assert "FIELD" in ENTITY_CLASSES


def test_default_init():
    field = Field()
    assert field.dxftype() == "FIELD"
    assert field.dxf.handle is None
    assert field.dxf.owner is None
    assert len(field.tags) == 0


def test_default_new():
    field = Field.new(handle="ABBA", owner="0", dxfattribs={})
    assert field.dxf.n_child_fields is None
    assert len(field.tags) == 0


def test_load_from_text(entity):
    assert entity.evaluator_id == "AcVar"
    assert entity.field_code == "\\AcVar Author"
    assert entity.dxf.n_child_fields == 0


def test_write_dxf():
    entity = Field.from_text(FIELD)
    result = TagCollector.dxftags(entity)
    expected = basic_tags_from_text(FIELD)
    assert result == expected


def test_field_code_overflow():
    entity = Field.from_text(FIELD_WITH_OVERFLOW)
    assert entity.evaluator_id == "AcExpr"
    assert entity.field_code == "abcdef"
    assert entity.dxf.n_child_fields == 1


def test_reset_tags_updates_simple_attributes():
    entity = Field()
    entity.reset([(1, "AcVar"), (2, "\\AcVar Login"), (90, 0)])
    assert entity.evaluator_id == "AcVar"
    assert entity.field_code == "\\AcVar Login"
    assert entity.dxf.n_child_fields == 0


def test_reset_strips_leading_subclass_marker():
    entity = Field()
    entity.reset([(100, "AcDbField"), (1, "AcVar"), (2, "\\AcVar Login")])
    assert entity.tags[0] == (1, "AcVar")
    tags = TagCollector.dxftags(entity)
    assert (100, "AcDbField") in tags


def test_child_and_object_handles_from_tags():
    entity = Field()
    entity.reset(
        [
            (1, "_text"),
            (2, "%<\\_FldIdx 0>%"),
            (360, "A1"),
            (360, "A2"),
            (331, "B1"),
        ]
    )
    assert entity.is_text_wrapper is True
    assert entity.child_handles == ["A1", "A2"]
    assert entity.object_handles == ["B1"]


def test_set_text_wrapper_builds_minimal_wrapper_tags():
    child = Field.new(handle="ABBA", owner="0", dxfattribs={})
    wrapper = Field()
    wrapper.set_text_wrapper(child)
    assert wrapper.is_text_wrapper is True
    assert wrapper.field_code == "%<\\_FldIdx 0>%"
    assert wrapper.child_handles == ["ABBA"]
    assert (6, "ACFD_FIELDTEXT_CHECKSUM") in wrapper.tags
    assert (7, "ACFD_FIELD_VALUE") in wrapper.tags
    assert (301, "") in wrapper.tags


def test_set_text_wrapper_checksum_matches_visible_text():
    child = Field.new(handle="ABBA", owner="0", dxfattribs={})
    wrapper = Field()
    wrapper.set_text_wrapper(child, text="10.0000")
    assert (140, 1339.0) in wrapper.tags


def test_set_text_wrapper_accepts_custom_wrapper_flags():
    child = Field.new(handle="ABBA", owner="0", dxfattribs={})
    wrapper = Field()
    wrapper.set_text_wrapper(child, wrapper_flags=9)
    assert (94, 9) in wrapper.tags


def test_set_text_wrapper_can_omit_checksum_dataset():
    child = Field.new(handle="ABBA", owner="0", dxfattribs={})
    wrapper = Field()
    wrapper.set_text_wrapper(child, include_checksum=False)
    assert (6, "ACFD_FIELDTEXT_CHECKSUM") not in wrapper.tags
    assert (93, 0) in wrapper.tags


def test_normalize_acobjprop_cache_matches_manual_multileader_shape():
    field = Field()
    field.set_acobjprop("ABBA", "Length", value=10.0, display="10.0000")
    field.normalize_acobjprop_cache()
    assert (94, 27) in field.tags
    assert (93, 0) in field.tags
    assert (302, "") in field.tags
    assert (301, "") in field.tags


def test_set_acvar_builds_minimal_child_field():
    field = Field()
    field.set_acvar("Author", display="----")
    assert field.evaluator_id == "AcVar"
    assert field.field_code == "\\AcVar Author"
    assert field.dxf.n_child_fields == 0
    assert (6, "Variable") in field.tags
    assert (1, "Author") in field.tags
    assert (301, "----") in field.tags


def test_set_acobjprop_builds_object_property_field():
    field = Field()
    field.set_acobjprop("ABBA", "Length", value=10.0, display="10.0000")
    assert field.evaluator_id == "AcObjProp"
    assert field.field_code == "\\AcObjProp Object(%<\\_ObjIdx 0>%).Length \\f \"%lu2\""
    assert field.object_handles == ["ABBA"]
    assert (6, "ObjectPropertyName") in field.tags
    assert (1, "Length") in field.tags
    assert (301, "10.0000") in field.tags


def test_set_dwgprops_builds_customdp_field():
    field = Field()
    field.set_dwgprops("ProjectCode", display="VALUE-123")
    assert field.evaluator_id == "AcVar"
    assert field.field_code == "\\AcVar CustomDP.ProjectCode"
    assert (1, "CustomDP.ProjectCode") in field.tags
    assert (301, "VALUE-123") in field.tags


def test_set_dwgprops_builds_formatted_title_field():
    field = Field()
    field.set_dwgprops("Title", field_format="%tc1", display="VALUE")
    assert field.field_code == "\\AcVar CustomDP.Title \\f \"%tc1\""


def test_set_acexpr_builds_expression_field_with_two_children():
    child1 = Field.new(handle="A1", owner="0", dxfattribs={})
    child2 = Field.new(handle="A2", owner="0", dxfattribs={})
    field = Field()
    field.set_acexpr(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        display="25.0000",
    )
    assert field.evaluator_id == "AcExpr"
    assert field.field_code == "\\AcExpr (%<\\_FldIdx 0>%*%<\\_FldIdx 1>%) \\f \"%lu2\""
    assert field.dxf.n_child_fields == 2
    assert field.child_handles == ["A1", "A2"]
    assert (6, "ACAD_ROUNDTRIP_2008_FIELD_EVALOPTION") in field.tags
    assert (140, 25.0) in field.tags
    assert (301, "25.0000") in field.tags


def test_build_acexpr_rejects_non_field_children():
    doc = dxfpy.new("R2018")

    with pytest.raises(dxfpy.lldxf.const.DXFTypeError) as error:
        Field.build_acexpr(doc, "%<\\_FldIdx 0>%", [object()])

    assert "object" in str(error.value)


def test_clear_tags_clears_simple_attributes():
    entity = Field.from_text(FIELD)
    entity.clear()
    assert len(entity.tags) == 0
    assert entity.evaluator_id == ""
    assert entity.field_code == ""
    assert entity.dxf.n_child_fields is None


def test_add_field_to_objects_section():
    doc = dxfpy.new("R2007")
    field = cast(Field, doc.objects.add_field(owner="ABBA"))
    assert field.dxftype() == "FIELD"
    assert field.dxf.owner == "ABBA"


def test_minimal_export_from_dxfattribs():
    doc = dxfpy.new("R2007")
    field = cast(
        Field,
        doc.objects.add_field(
            owner="ABBA",
            dxfattribs={
                "evaluator_id": "AcVar",
                "field_code": "\\AcVar Author",
                "n_child_fields": 0,
            },
        ),
    )
    tags = TagCollector.dxftags(field)
    assert (1, "AcVar") in tags
    assert (2, "\\AcVar Author") in tags


def test_writing_document_adds_field_class_definition():
    doc = dxfpy.new("R2007")
    cast(
        Field,
        doc.objects.add_field(
            owner="ABBA",
            dxfattribs={
                "evaluator_id": "AcVar",
                "field_code": "\\AcVar Author",
                "n_child_fields": 0,
            },
        ),
    )
    stream = io.StringIO()
    doc.write(stream)
    data = stream.getvalue()
    assert "  0\nCLASS\n  1\nFIELD\n  2\nAcDbField\n" in data


def test_mtext_new_field_creates_field_dict_and_links_field():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")
    field = cast(
        Field,
        mtext.new_field(
            dxfattribs={
                "evaluator_id": "AcVar",
                "field_code": "\\AcVar Author",
                "n_child_fields": 0,
            }
        ),
    )
    assert isinstance(mtext, MText)
    assert mtext.has_extension_dict is True
    assert mtext.has_field_dict() is True
    field_dict = mtext.get_field_dict()
    assert field_dict.dxf.owner == mtext.get_extension_dict().handle
    assert field_dict._value_code == 360
    assert mtext.get_field() is field
    assert field.dxf.owner == field_dict.dxf.handle


def test_mtext_set_field_replaces_existing_field():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")
    field1 = cast(
        Field,
        mtext.new_field(
            dxfattribs={
                "evaluator_id": "AcVar",
                "field_code": "\\AcVar Author",
            }
        ),
    )
    field2 = cast(
        Field,
        doc.objects.add_field(
            dxfattribs={
                "evaluator_id": "AcVar",
                "field_code": "\\AcVar Login",
            }
        ),
    )
    mtext.set_field(field2)
    assert field1.is_alive is False
    assert mtext.get_field() is field2


def test_mtext_get_primary_field_returns_child_of_text_wrapper():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")
    child = cast(
        Field,
        doc.objects.add_field(
            dxfattribs={
                "evaluator_id": "AcVar",
                "field_code": "\\AcVar Author",
            }
        ),
    )
    wrapper = cast(Field, doc.objects.add_field(dxfattribs={}))
    wrapper.set_text_wrapper(child)
    mtext.set_field(wrapper)
    assert mtext.get_field() is wrapper
    assert mtext.get_primary_field() is child


def test_mtext_get_field_returns_none_without_field_dict():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")
    assert mtext.get_field() is None


def test_writing_mtext_field_exports_xdictionary_and_field_dict():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")
    mtext.new_field(
        dxfattribs={
            "evaluator_id": "AcVar",
            "field_code": "\\AcVar Author",
        }
    )
    stream = io.StringIO()
    doc.write(stream)
    data = stream.getvalue()
    assert "{ACAD_XDICTIONARY" in data
    assert "ACAD_FIELD" in data
    assert "\\AcVar Author" in data


def test_setup_field_list_creates_rootdict_entry():
    doc = dxfpy.new("R2007")
    field_list = doc.objects.setup_field_list()
    assert doc.rootdict.get("ACAD_FIELDLIST") is field_list
    assert field_list.dxf.owner == doc.rootdict.dxf.handle
    assert doc.rootdict.dxf.handle in field_list.get_reactors()
    assert field_list.dxf.flags == 2


def test_new_linked_field_creates_wrapper_and_registers_field_list():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")
    child, wrapper = mtext.new_linked_field(
        dxfattribs={
            "evaluator_id": "AcVar",
            "field_code": "\\AcVar Author",
        },
        text="----",
        register_field_list=True,
    )
    assert mtext.text == "----"
    assert mtext.get_field() is wrapper
    assert mtext.get_primary_field() is child
    assert child.dxf.owner == wrapper.dxf.handle
    assert mtext.get_field_dict().dxf.handle in wrapper.get_reactors()
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert wrapper.dxf.handle in field_list.handles
    assert child.dxf.handle in field_list.handles


def test_new_acvar_field_creates_object_backed_author_field():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")
    child, wrapper = mtext.new_acvar_field(
        "Author", text="----", register_field_list=True
    )
    assert child.evaluator_id == "AcVar"
    assert child.field_code == "\\AcVar Author"
    assert (301, "----") in child.tags
    assert wrapper.is_text_wrapper is True
    assert mtext.get_primary_field() is child


def test_new_dwgprops_field_creates_object_backed_custom_property_field():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext("TEXT")
    child, wrapper = mtext.new_dwgprops_field(
        "ProjectCode", text="VALUE-123", register_field_list=True
    )
    assert child.evaluator_id == "AcVar"
    assert child.field_code == "\\AcVar CustomDP.ProjectCode"
    assert mtext.get_primary_field() is child
    assert wrapper.is_text_wrapper is True


def test_new_acobjprop_field_creates_object_backed_length_field():
    doc = dxfpy.new("R2007")
    line = doc.modelspace().add_line((0, 0), (10, 0))
    mtext = doc.modelspace().add_mtext("TEXT")
    child, wrapper = mtext.new_acobjprop_field(
        line, "Length", text=None, register_field_list=True
    )
    assert child.evaluator_id == "AcObjProp"
    assert child.object_handles == [line.dxf.handle]
    assert "Length" in child.field_code
    assert mtext.text == "10.0000"
    assert (140, 1339.0) in wrapper.tags
    assert mtext.get_primary_field() is child
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert wrapper.dxf.handle in field_list.handles
    assert child.dxf.handle in field_list.handles


def test_writing_mtext_acobjprop_field_exports_property_reference():
    doc = dxfpy.new("R2007")
    line = doc.modelspace().add_line((0, 0), (10, 0))
    mtext = doc.modelspace().add_mtext("TEXT")
    mtext.new_acobjprop_field(line, "Length", register_field_list=True)
    stream = io.StringIO()
    doc.write(stream)
    data = stream.getvalue()
    assert "AcObjProp" in data
    assert "ObjectPropertyName" in data
    assert "Length" in data


def test_graphicsfactory_add_mtext_acvar_field():
    doc = dxfpy.new("R2007")
    mtext = doc.modelspace().add_mtext_acvar_field(
        "Author", text="----", register_field_list=True
    )
    assert isinstance(mtext, MText)
    assert mtext.text == "----"
    assert mtext.get_primary_field() is not None
    assert mtext.get_primary_field().field_code == "\\AcVar Author"


def test_graphicsfactory_add_mtext_acobjprop_field():
    doc = dxfpy.new("R2007")
    line = doc.modelspace().add_line((0, 0), (10, 0))
    mtext = doc.modelspace().add_mtext_acobjprop_field(
        line, "Length", register_field_list=True
    )
    assert isinstance(mtext, MText)
    assert mtext.text == "10.0000"
    assert mtext.get_primary_field() is not None
    assert "Length" in mtext.get_primary_field().field_code


def test_new_acobjprop_field_supports_circle_radius():
    doc = dxfpy.new("R2007")
    circle = doc.modelspace().add_circle((0, 0), radius=5)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(circle, "Radius", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "5.0000"
    assert "Radius" in child.field_code


def test_new_acobjprop_field_supports_circle_area():
    doc = dxfpy.new("R2007")
    circle = doc.modelspace().add_circle((0, 0), radius=2)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(circle, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "12.5664"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_arc_radius():
    doc = dxfpy.new("R2007")
    arc = doc.modelspace().add_arc((0, 0), radius=5, start_angle=0, end_angle=180)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(arc, "Radius", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "5.0000"
    assert "Radius" in child.field_code


def test_new_acobjprop_field_supports_arc_length():
    doc = dxfpy.new("R2007")
    arc = doc.modelspace().add_arc((0, 0), radius=5, start_angle=0, end_angle=180)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(arc, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "15.7080"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_arc_arc_length_alias():
    doc = dxfpy.new("R2007")
    arc = doc.modelspace().add_arc((0, 0), radius=5, start_angle=0, end_angle=180)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(arc, "ArcLength", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "15.7080"
    assert "ArcLength" in child.field_code


def test_new_acobjprop_field_supports_arc_area():
    doc = dxfpy.new("R2007")
    arc = doc.modelspace().add_arc((0, 0), radius=5, start_angle=0, end_angle=180)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(arc, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "39.2699"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_open_polyline2d_length():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline2d([(0, 0), (3, 4), (3, 8)])
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "9.0000"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_open_polyline3d_length():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline3d([(0, 0, 0), (3, 4, 0), (3, 8, 0)])
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "9.0000"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_open_polyline2d_area():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline2d([(0, 0), (3, 4), (3, 8)])
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "6.0000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_bulged_open_polyline2d_length():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline2d(
        [(0, 0, 1.0), (10, 0, 0.0), (10, 10, 0.0)], format="xyb"
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "25.7080"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_bulged_open_polyline2d_area():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline2d(
        [(0, 0, 1.0), (10, 0, 0.0), (10, 10, 0.0)], format="xyb"
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "89.2699"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_open_spline_area():
    doc = dxfpy.new("R2007")
    spline = doc.modelspace().add_open_spline([(0, 0), (3, 4), (6, 0), (9, 4)])
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(spline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "4.5000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_closed_spline_area():
    doc = dxfpy.new("R2007")
    spline = doc.modelspace().add_spline()
    spline.set_closed([(0, 0, 0), (3, 4, 0), (6, 0, 0), (3, -4, 0)], degree=3)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(spline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "16.2667"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_closed_polyline2d_length():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline2d(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "40.0000"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_closed_polyline2d_area():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline2d(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "100.0000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_closed_polyline3d_length():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline3d(
        [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], close=True
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "40.0000"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_simple_hatch_area():
    doc = dxfpy.new("R2007")
    hatch = doc.modelspace().add_hatch(color=1)
    hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(hatch, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "100.0000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_hatch_area_with_hole():
    doc = dxfpy.new("R2007")
    hatch = doc.modelspace().add_hatch(color=1)
    hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True)
    hatch.paths.add_polyline_path([(2, 2), (8, 2), (8, 8), (2, 8)], is_closed=True)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(hatch, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "64.0000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_hatch_edge_rect_area():
    doc = dxfpy.new("R2007")
    hatch = doc.modelspace().add_hatch(color=1)
    edge_path = hatch.paths.add_edge_path()
    edge_path.add_line((0, 0), (10, 0))
    edge_path.add_line((10, 0), (10, 10))
    edge_path.add_line((10, 10), (0, 10))
    edge_path.add_line((0, 10), (0, 0))
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(hatch, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "100.0000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_hatch_edge_arc_area():
    doc = dxfpy.new("R2007")
    hatch = doc.modelspace().add_hatch(color=1)
    edge_path = hatch.paths.add_edge_path()
    edge_path.add_line((0, 0), (10, 0))
    edge_path.add_arc((10, 5), radius=5, start_angle=270, end_angle=90, ccw=True)
    edge_path.add_line((10, 10), (0, 10))
    edge_path.add_line((0, 10), (0, 0))
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(hatch, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "139.2699"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_hatch_edge_ellipse_area():
    doc = dxfpy.new("R2007")
    hatch = doc.modelspace().add_hatch(color=1)
    edge_path = hatch.paths.add_edge_path()
    edge_path.add_ellipse(center=(5, 5), major_axis=(5, 0), ratio=0.5, start_angle=0, end_angle=360)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(hatch, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "39.2699"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_hatch_edge_spline_area():
    doc = dxfpy.new("R2007")
    hatch = doc.modelspace().add_hatch(color=1)
    edge_path = hatch.paths.add_edge_path()
    cps = [(0, 0), (3, 4), (6, 0), (3, -4), (0, 0)]
    edge_path.add_spline(control_points=cps, knot_values=[0.0, 0.0, 0.0, 0.0, 0.5, 1.0, 1.0, 1.0, 1.0], degree=3)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(hatch, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "14.4000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_canonicalized_bulged_hatch_area():
    doc = dxfpy.new("R2007")
    hatch = doc.modelspace().add_hatch(color=1)
    hatch.paths.add_polyline_path(
        [
            (8.0, 8.0, 0.0),
            (2.0, 8.0, 0.0),
            (2.0, 2.0, 0.1844830881382522),
            (2.763932022500209, 0.0, 0.0),
            (7.236067977499788, 0.0, 0.1844830881382522),
            (8.0, 2.0, 0.0),
        ],
        is_closed=True,
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(hatch, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "47.0397"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_ellipse_major_radius():
    doc = dxfpy.new("R2007")
    ellipse = doc.modelspace().add_ellipse((0, 0), major_axis=(5, 0), ratio=0.5)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(
        ellipse, "MajorRadius", register_field_list=True
    )
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "5.0000"
    assert "MajorRadius" in child.field_code


def test_new_acobjprop_field_supports_ellipse_minor_radius():
    doc = dxfpy.new("R2007")
    ellipse = doc.modelspace().add_ellipse((0, 0), major_axis=(5, 0), ratio=0.5)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(
        ellipse, "MinorRadius", register_field_list=True
    )
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "2.5000"
    assert "MinorRadius" in child.field_code


def test_new_acobjprop_field_supports_full_ellipse_area():
    doc = dxfpy.new("R2007")
    ellipse = doc.modelspace().add_ellipse((0, 0), major_axis=(5, 0), ratio=0.5)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(ellipse, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "39.2699"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_ellipse_arc_area():
    doc = dxfpy.new("R2007")
    ellipse = doc.modelspace().add_ellipse(
        (0, 0), major_axis=(5, 0), ratio=0.5, start_param=0.0, end_param=math.pi
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(ellipse, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "19.6350"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_closed_lwpolyline_area():
    doc = dxfpy.new("R2007")
    pline = doc.modelspace().add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(pline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "100.0000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_open_lwpolyline_length():
    doc = dxfpy.new("R2007")
    pline = doc.modelspace().add_lwpolyline([(0, 0), (3, 4), (3, 8)])
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(pline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "9.0000"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_open_lwpolyline_area():
    doc = dxfpy.new("R2007")
    pline = doc.modelspace().add_lwpolyline([(0, 0), (10, 0), (10, 10)])
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(pline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "50.0000"
    assert "Area" in child.field_code


def test_new_acobjprop_field_supports_closed_lwpolyline_length():
    doc = dxfpy.new("R2007")
    pline = doc.modelspace().add_lwpolyline(
        [(0, 0), (10, 0), (10, 10), (0, 10)], close=True
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(pline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "40.0000"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_bulged_open_lwpolyline_length():
    doc = dxfpy.new("R2007")
    pline = doc.modelspace().add_lwpolyline(
        [(0, 0, 0, 0, 1.0), (10, 0, 0, 0, 0.0), (10, 10, 0, 0, 0.0)],
        format="xyseb",
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(pline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "25.7080"
    assert "Length" in child.field_code


def test_new_acobjprop_field_supports_bulged_open_lwpolyline_area():
    doc = dxfpy.new("R2007")
    pline = doc.modelspace().add_lwpolyline(
        [(0, 0, 0, 0, 1.0), (10, 0, 0, 0, 0.0), (10, 10, 0, 0, 0.0)],
        format="xyseb",
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(pline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "89.2699"
    assert "Area" in child.field_code


def test_arc_diameter_is_not_inferred():
    doc = dxfpy.new("R2007")
    arc = doc.modelspace().add_arc((0, 0), radius=5, start_angle=0, end_angle=180)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(arc, "Diameter", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "TEXT"


def test_ellipse_length_is_not_inferred():
    doc = dxfpy.new("R2007")
    ellipse = doc.modelspace().add_ellipse((0, 0), major_axis=(5, 0), ratio=0.5)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(ellipse, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "TEXT"


def test_polyline2d_area_with_bulge_is_inferred():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline2d(
        [(0, 0, 1.0), (10, 0, 0.0), (10, 10, 0.0)], format="xyb"
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "89.2699"


def test_spline_length_is_not_inferred():
    doc = dxfpy.new("R2007")
    spline = doc.modelspace().add_open_spline([(0, 0), (3, 4), (6, 0), (9, 4)])
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(spline, "Length", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "TEXT"


def test_open_polyline3d_area_is_not_inferred():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline3d([(0, 0, 0), (3, 4, 0), (3, 8, 0)])
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "TEXT"


def test_closed_polyline3d_area_is_not_inferred():
    doc = dxfpy.new("R2007")
    polyline = doc.modelspace().add_polyline3d(
        [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0)], close=True
    )
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(polyline, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "TEXT"


def test_hatch_area_with_bulged_hole_is_not_inferred():
    doc = dxfpy.new("R2007")
    hatch = doc.modelspace().add_hatch(color=1)
    hatch.paths.add_polyline_path([(0, 0), (10, 0), (10, 10), (0, 10)], is_closed=True)
    hatch.paths.add_polyline_path([(2, 2, 1.0), (8, 2, 0.0), (8, 8, 0.0)], is_closed=True)
    mtext = doc.modelspace().add_mtext("TEXT")
    child, _ = mtext.new_acobjprop_field(hatch, "Area", register_field_list=True)
    assert child.evaluator_id == "AcObjProp"
    assert mtext.text == "TEXT"
