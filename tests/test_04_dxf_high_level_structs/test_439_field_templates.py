# Copyright (c) 2026, Manfred Moitzi
# License: MIT License
from __future__ import annotations

from decimal import Decimal
from io import StringIO

import dxfpy
import pytest

from dxfpy.entities import Field
from dxfpy.fields import drawing_property, drawing_variable, object_property
from dxfpy.math import Vec2


def roundtrip(doc):
    stream = StringIO()
    doc.write(stream)
    return dxfpy.read(StringIO(stream.getvalue()))


def make_multileader(doc):
    builder = doc.modelspace().add_multileader_mtext("Standard")
    builder.set_content("INITIAL")
    builder.build(insert=Vec2(0, 0))
    return builder.multileader


def test_mtext_set_field_creates_drawing_property_from_plain_value():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")

    wrapper = mtext.set_field(
        "Client: {{ClientName}}", values={"ClientName": "Acme Solar"}
    )

    assert mtext.text == "Client: Acme Solar"
    assert wrapper.field_code == "Client: %<\\_FldIdx 0>%"
    child = wrapper.get_child_fields()[0]
    assert child.field_code == "\\AcVar CustomDP.ClientName"
    assert doc.header.custom_vars.get("ClientName") == "Acme Solar"
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert set(field_list.handles) == {
        wrapper.dxf.handle,
        child.dxf.handle,
    }


def test_template_field_roundtrip_preserves_complete_tree():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")
    mtext.set_field("Client: {{ClientName}}", values={"ClientName": "Acme"})

    loaded = roundtrip(doc)

    loaded_mtext = loaded.modelspace().query("MTEXT")[0]
    wrapper = loaded_mtext.get_field()
    assert wrapper is not None
    assert loaded_mtext.text == "Client: Acme"
    assert wrapper.field_code == "Client: %<\\_FldIdx 0>%"
    assert wrapper.get_child_fields()[0].field_code.endswith("ClientName")


def test_template_fields_register_field_list_by_default():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")

    wrapper = mtext.set_field("{{Value}}", values={"Value": "A"})

    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert set(field_list.handles) == {
        field.dxf.handle for field in wrapper.get_field_tree()
    }


def test_template_field_can_skip_field_list_registration():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")

    mtext.set_field(
        "{{Value}}",
        values={"Value": "A"},
        register_field_list=False,
    )

    assert doc.objects.get_field_list() is None


def test_calculated_drawing_property_field_hides_native_indices():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")

    wrapper = mtext.set_field(
        "SYSTEM SIZE: {{ModuleCount * (ModuleWatts / 1000)}} kW",
        values={"ModuleCount": 20, "ModuleWatts": 410},
    )

    assert mtext.text == "SYSTEM SIZE: 8.2 kW"
    assert wrapper.field_code == "SYSTEM SIZE: %<\\_FldIdx 0>% kW"
    expression = wrapper.get_child_fields()[0]
    assert expression.evaluator_id == "AcExpr"
    assert expression.field_code == (
        '\\AcExpr (%<\\_FldIdx 0>%*(%<\\_FldIdx 1>%/1000)) '
        '\\f "%lu2"'
    )
    assert [field.field_code for field in expression.get_child_fields()] == [
        "\\AcVar CustomDP.ModuleCount",
        "\\AcVar CustomDP.ModuleWatts",
    ]
    assert len(wrapper.get_field_tree()) == 4


def test_calculation_supports_add_subtract_multiply_divide_and_unary():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")

    mtext.set_field(
        "{{-(First + Second) * Factor / Divisor}}",
        values={"First": 10, "Second": 5, "Factor": 2, "Divisor": 3},
    )

    assert mtext.text == "-10"


def test_repeated_template_expression_reuses_direct_child():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")

    wrapper = mtext.set_field(
        "{{Name}} / {{Name}}", values={"Name": "VALUE"}
    )

    assert mtext.text == "VALUE / VALUE"
    assert wrapper.field_code == "%<\\_FldIdx 0>% / %<\\_FldIdx 0>%"
    assert len(wrapper.get_child_fields()) == 1


def test_existing_drawing_property_can_be_referenced_without_values():
    doc = dxfpy.new("R2018")
    doc.header.custom_vars.append("ClientName", "Existing Client")
    mtext = doc.modelspace().add_mtext("")

    mtext.set_field("Client: {{ClientName}}")

    assert mtext.text == "Client: Existing Client"


def test_drawing_property_helper_supports_alias_and_upsert():
    doc = dxfpy.new("R2018")
    doc.header.custom_vars.append("Project Number", "OLD")
    mtext = doc.modelspace().add_mtext("")

    mtext.set_field(
        "Project: {{project}}",
        values={
            "project": drawing_property(
                "Project Number", value="NEW", display="NEW"
            )
        },
    )

    assert mtext.text == "Project: NEW"
    assert doc.header.custom_vars.get("Project Number") == "NEW"
    assert len(doc.header.custom_vars) == 1
    child = mtext.get_primary_field()
    assert child is not None
    assert child.field_code == "\\AcVar CustomDP.Project Number"


def test_drawing_variable_helper_hides_acvar_implementation():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")

    mtext.set_field(
        "Sheet: {{sheet}}",
        values={"sheet": drawing_variable("CTab", display="A1")},
    )

    assert mtext.text == "Sheet: A1"
    child = mtext.get_primary_field()
    assert child is not None
    assert child.field_code == "\\AcVar CTab"
    assert doc.header.custom_vars.get("sheet") is None


def test_object_property_helper_infers_value_and_target_handle():
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    mtext = msp.add_mtext("")

    mtext.set_field(
        "Length: {{length}}",
        values={"length": object_property(line, "Length")},
    )

    assert mtext.text == "Length: 10.0000"
    child = mtext.get_primary_field()
    assert child is not None
    assert child.evaluator_id == "AcObjProp"
    assert child.object_handles == [line.dxf.handle]


def test_calculation_can_combine_object_properties():
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    length = msp.add_line((0, 0), (10, 0))
    width = msp.add_line((0, 0), (0, 5))
    mtext = msp.add_mtext("")

    wrapper = mtext.set_field(
        "Area: {{length * width}}",
        values={
            "length": object_property(length, "Length"),
            "width": object_property(width, "Length"),
        },
    )

    assert mtext.text == "Area: 50"
    expression = wrapper.get_child_fields()[0]
    assert [field.object_handles for field in expression.get_child_fields()] == [
        [length.dxf.handle],
        [width.dxf.handle],
    ]


def test_text_and_attrib_inherit_template_api():
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    text = msp.add_text("")
    block = doc.blocks.new("FIELD_ATTRIB")
    block.add_attdef("CLIENT")
    insert = msp.add_blockref(block.name, (0, 0))
    attrib = insert.add_attrib("CLIENT", "")

    text.set_field("{{Client}}", values={"Client": "TEXT"})
    attrib.set_field("{{Client}}", values={"Client": "ATTRIB"})

    assert text.dxf.text == "TEXT"
    assert attrib.dxf.text == "ATTRIB"
    assert text.get_primary_field() is not attrib.get_primary_field()
    assert doc.header.custom_vars.get("Client") == "ATTRIB"


def test_multileader_template_preserves_native_wrapper_shape():
    doc = dxfpy.new("R2018")
    multileader = make_multileader(doc)

    wrapper = multileader.set_field(
        "Total: {{First + Second}}",
        values={"First": 10, "Second": 5},
    )

    assert multileader.get_mtext_content() == "Total: 15"
    assert (94, 9) in wrapper.tags
    assert (6, "ACFD_FIELDTEXT_CHECKSUM") not in wrapper.tags
    expression = wrapper.get_child_fields()[0]
    assert (6, "ACAD_ROUNDTRIP_2008_FIELD_EVALOPTION") not in expression.tags


def test_low_level_set_field_object_remains_supported():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("VALUE")
    field = Field()
    field.set_acvar("Author", display="VALUE")

    attached = mtext.set_field(field)

    assert attached is field
    assert mtext.get_field() is field


def test_low_level_set_field_can_explicitly_register_field_list():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("VALUE")
    field = Field()
    field.set_acvar("Author", display="VALUE")

    mtext.set_field(field, register_field_list=True)

    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert field_list.handles == [field.dxf.handle]


def test_low_level_registration_preflights_invalid_field_list():
    doc = dxfpy.new("R2018")
    invalid_field_list = doc.objects.add_xrecord()
    doc.rootdict.add("ACAD_FIELDLIST", invalid_field_list)
    mtext = doc.modelspace().add_mtext("VALUE")
    field = Field()
    field.set_acvar("Author", display="VALUE")
    handles = set(doc.entitydb)

    with pytest.raises(dxfpy.DXFStructureError, match="FIELDLIST"):
        mtext.set_field(field, register_field_list=True)

    assert mtext.get_field() is None
    assert field.doc is None
    assert set(doc.entitydb) == handles


def test_low_level_registration_rejects_r12_before_attachment():
    doc = dxfpy.new("R12")
    text = doc.modelspace().add_text("VALUE")
    field = Field()
    field.set_acvar("Author", display="VALUE")

    with pytest.raises(dxfpy.DXFVersionError, match="R2000"):
        text.set_field(field, register_field_list=True)

    assert text.get_field() is None
    assert field.doc is None


def test_linked_field_registration_rejects_r12_before_attachment():
    doc = dxfpy.new("R12")
    text = doc.modelspace().add_text("ORIGINAL")
    field = Field()
    field.set_acvar("Author", display="VALUE")
    handles = set(doc.entitydb)

    with pytest.raises(dxfpy.DXFVersionError, match="R2000"):
        text.set_linked_field(
            field, text="VALUE", register_field_list=True
        )

    assert text.dxf.text == "ORIGINAL"
    assert text.get_field() is None
    assert field.doc is None
    assert set(doc.entitydb) == handles


def test_low_level_field_rejects_template_only_options():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("VALUE")
    field = Field()
    field.set_acvar("Author", display="VALUE")

    with pytest.raises(dxfpy.DXFTypeError, match="template options"):
        mtext.set_field(field, values={"Author": "A"})  # type: ignore[call-overload]

    assert mtext.get_field() is None


@pytest.mark.parametrize(
    "template",
    [
        "STATIC TEXT",
        "{{}}",
        "{{Value",
        "Value}}",
        "{{Value ** 2}}",
        "{{round(Value)}}",
        "{{Value.attribute}}",
    ],
)
def test_invalid_template_is_rejected_atomically(template):
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")
    handles = set(doc.entitydb)

    with pytest.raises(dxfpy.DXFValueError):
        mtext.set_field(template, values={"Value": 2})

    assert mtext.text == "ORIGINAL"
    assert mtext.get_field() is None
    assert set(doc.entitydb) == handles
    assert len(doc.header.custom_vars) == 0


def test_missing_template_value_is_rejected_atomically():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")

    with pytest.raises(dxfpy.DXFValueError, match="missing field value"):
        mtext.set_field("{{Missing}}")

    assert mtext.text == "ORIGINAL"
    assert mtext.get_field() is None


def test_unused_template_value_is_rejected_atomically():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")

    with pytest.raises(dxfpy.DXFValueError, match="unused field values"):
        mtext.set_field("{{Used}}", values={"Used": 1, "Unused": 2})

    assert mtext.get_field() is None
    assert len(doc.header.custom_vars) == 0


def test_non_numeric_calculation_value_is_rejected_atomically():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")

    with pytest.raises(dxfpy.DXFValueError, match="not numeric"):
        mtext.set_field("{{Client * 2}}", values={"Client": "Acme"})

    assert mtext.get_field() is None
    assert doc.header.custom_vars.get("Client") is None


def test_division_by_zero_is_rejected_atomically():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")

    with pytest.raises(dxfpy.DXFValueError, match="divides by zero"):
        mtext.set_field("{{Value / Zero}}", values={"Value": 1, "Zero": 0})

    assert mtext.get_field() is None
    assert len(doc.header.custom_vars) == 0


def test_foreign_object_property_is_rejected_atomically():
    doc = dxfpy.new("R2018")
    foreign_doc = dxfpy.new("R2018")
    foreign_line = foreign_doc.modelspace().add_line((0, 0), (1, 0))
    mtext = doc.modelspace().add_mtext("ORIGINAL")

    with pytest.raises(dxfpy.DXFStructureError, match="this document"):
        mtext.set_field(
            "{{length}}",
            values={"length": object_property(foreign_line, "Length")},
        )

    assert mtext.get_field() is None


def test_invalid_field_list_preflight_preserves_existing_field_and_properties():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")
    _, original = mtext.new_dwgprops_field(
        "Original", text="ORIGINAL", register_field_list=True
    )
    invalid_field_list = doc.objects.add_xrecord()
    doc.rootdict.add("ACAD_FIELDLIST", invalid_field_list)
    original_properties = list(doc.header.custom_vars.properties)

    with pytest.raises(dxfpy.DXFStructureError, match="FIELDLIST"):
        mtext.set_field("{{Replacement}}", values={"Replacement": "NEW"})

    assert mtext.get_field() is original
    assert mtext.text == "ORIGINAL"
    assert doc.header.custom_vars.properties == original_properties


def test_template_replacement_deletes_previous_field_tree():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("")
    first = mtext.set_field("{{First}}", values={"First": "A"})
    old_handles = {field.dxf.handle for field in first.get_field_tree()}

    second = mtext.set_field("{{Second}}", values={"Second": "B"})

    assert mtext.get_field() is second
    assert mtext.text == "B"
    assert old_handles.isdisjoint(doc.entitydb)
    field_list = doc.objects.get_field_list()
    assert field_list is not None
    assert set(field_list.handles) == {
        field.dxf.handle for field in second.get_field_tree()
    }


@pytest.mark.parametrize(
    "template, values",
    [
        ("Line 1\n{{Value}}", {"Value": "A"}),
        ("{{Value}}", {"Value": "Line 1\nLine 2"}),
        (
            "{{Value}}",
            {"Value": drawing_property("Value", value="A", display="A\nB")},
        ),
    ],
)
def test_line_breaks_are_rejected_before_writing_invalid_dxf(template, values):
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")
    handles = set(doc.entitydb)

    with pytest.raises(dxfpy.DXFValueError, match="line breaks"):
        mtext.set_field(template, values=values)

    assert mtext.text == "ORIGINAL"
    assert mtext.get_field() is None
    assert set(doc.entitydb) == handles
    assert len(doc.header.custom_vars) == 0


def test_field_dictionary_key_rejects_line_break_atomically():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")

    with pytest.raises(dxfpy.DXFValueError, match="line breaks"):
        mtext.set_field(
            "{{Value}}", key="BAD\nKEY", values={"Value": "A"}
        )

    assert mtext.text == "ORIGINAL"
    assert mtext.get_field() is None
    assert len(doc.header.custom_vars) == 0


def test_r12_rejects_all_field_templates():
    doc = dxfpy.new("R12")
    text = doc.modelspace().add_text("ORIGINAL")

    with pytest.raises(dxfpy.DXFVersionError, match="R2000"):
        text.set_field(
            "{{author}}",
            values={"author": drawing_variable("Author", display="A")},
        )

    assert text.get_field() is None


def test_r2000_rejects_drawing_property_templates():
    doc = dxfpy.new("R2000")
    mtext = doc.modelspace().add_mtext("ORIGINAL")

    with pytest.raises(dxfpy.DXFVersionError, match="R2004"):
        mtext.set_field("{{Project}}", values={"Project": "A"})

    assert mtext.get_field() is None
    assert len(doc.header.custom_vars) == 0


def test_r2000_supports_drawing_variable_template_roundtrip():
    doc = dxfpy.new("R2000")
    mtext = doc.modelspace().add_mtext("")
    mtext.set_field(
        "{{author}}",
        values={"author": drawing_variable("Author", display="A")},
    )

    loaded = roundtrip(doc)

    child = loaded.modelspace().query("MTEXT")[0].get_primary_field()
    assert child is not None
    assert child.field_code == "\\AcVar Author"


def test_r2004_supports_drawing_property_template_roundtrip():
    doc = dxfpy.new("R2004")
    mtext = doc.modelspace().add_mtext("")
    mtext.set_field("{{Project}}", values={"Project": "A"})

    loaded = roundtrip(doc)

    assert loaded.header.custom_vars.get("Project") == "A"
    assert loaded.modelspace().query("MTEXT")[0].get_field() is not None


@pytest.mark.parametrize("value", [Decimal("1e309"), Decimal("1e-400")])
def test_calculation_rejects_values_outside_finite_float_cache(value):
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")

    with pytest.raises(dxfpy.DXFValueError, match="numeric range"):
        mtext.set_field("{{Value * 2}}", values={"Value": value})

    assert mtext.get_field() is None
    assert len(doc.header.custom_vars) == 0


def test_deep_expression_reports_value_error_instead_of_recursion_error():
    doc = dxfpy.new("R2018")
    mtext = doc.modelspace().add_mtext("ORIGINAL")
    expression = " + ".join("Value" for _ in range(2000))

    with pytest.raises(dxfpy.DXFValueError, match="complex"):
        mtext.set_field(
            f"{{{{{expression}}}}}", values={"Value": 1}
        )

    assert mtext.get_field() is None
