from io import StringIO

import pytest

import dxfpy
from dxfpy.dynamic_blocks import (
    DynamicBlockReference,
    DynamicBlockVisibilityError,
    NotDynamicBlockReferenceError,
    UnknownVisibilityStateError,
    UnsupportedDynamicBlockReferenceError,
)
from dxfpy.dynblkhelper import (
    DynamicBlockVisibilityParameter,
    DynamicBlockVisibilityState,
    set_dynamic_block_visibility_parameter,
)


def load_visibility_fixture():
    return dxfpy.readzip("integration_tests/data/dynblks.zip", "dynblk1.dxf")


def test_dynamic_block_reference_requires_insert_entity():
    doc = dxfpy.new("R2018")
    line = doc.modelspace().add_line((0, 0), (1, 0))

    with pytest.raises(dxfpy.lldxf.const.DXFTypeError):
        DynamicBlockReference(line)


def test_plain_insert_reports_not_dynamic():
    doc = dxfpy.new("R2018")
    block = doc.blocks.new("PLAIN")
    block.add_line((0, 0), (1, 0))
    insert = doc.modelspace().add_blockref(block.name, (0, 0))
    dynamic = DynamicBlockReference(insert)

    assert dynamic.is_dynamic is False
    assert dynamic.definition is None
    assert dynamic.reference is None
    assert dynamic.definition_name is None
    assert dynamic.reference_name is None
    assert dynamic.visibility_state_names == ()
    assert dynamic.visibility_state is None
    assert dynamic.has_visibility is False
    assert dynamic.visible_entities() == ()

    with pytest.raises(NotDynamicBlockReferenceError):
        dynamic.set_visibility_state("ANY")


def test_dynamic_block_reference_reads_visibility_state_metadata():
    doc = load_visibility_fixture()
    insert = list(doc.modelspace().query("INSERT"))[0]
    dynamic = DynamicBlockReference(insert)

    assert dynamic.insert is insert
    assert dynamic.is_dynamic is True
    assert dynamic.is_anonymous_reference is True
    assert dynamic.definition_name == "XYZ"
    assert dynamic.reference_name == "*U4"
    assert dynamic.visibility_state_names == (
        "CircleVisibilityState",
        "SquareVisibilityState",
    )
    assert dynamic.visibility_state == "CircleVisibilityState"
    assert [entity.dxf.handle for entity in dynamic.visible_entities()] == ["2D6"]
    assert [
        entity.dxf.handle for entity in dynamic.visible_entities("SquareVisibilityState")
    ] == ["2D7"]


def test_dynamic_block_reference_sets_visibility_state_and_survives_roundtrip():
    doc = load_visibility_fixture()
    insert = list(doc.modelspace().query("INSERT"))[0]
    dynamic = DynamicBlockReference(insert)

    dynamic.set_visibility_state("SquareVisibilityState")

    assert dynamic.visibility_state == "SquareVisibilityState"
    reference = dynamic.reference

    assert reference is not None
    assert [entity.dxf.get("invisible", 0) for entity in reference] == [1, 0]
    assert doc.audit().has_errors is False

    stream = StringIO()
    doc.write(stream)
    loaded = dxfpy.read(StringIO(stream.getvalue()))
    loaded_insert = list(loaded.modelspace().query("INSERT"))[0]
    loaded_dynamic = DynamicBlockReference(loaded_insert)

    assert loaded_dynamic.visibility_state == "SquareVisibilityState"
    loaded_reference = loaded_dynamic.reference

    assert loaded_reference is not None
    assert [entity.dxf.get("invisible", 0) for entity in loaded_reference] == [1, 0]


def test_dynamic_block_reference_rejects_unknown_visibility_state():
    doc = load_visibility_fixture()
    insert = list(doc.modelspace().query("INSERT"))[0]
    dynamic = DynamicBlockReference(insert)

    with pytest.raises(UnknownVisibilityStateError):
        dynamic.set_visibility_state("MISSING")

    with pytest.raises(UnknownVisibilityStateError):
        dynamic.visible_entities("MISSING")


def test_dynamic_block_reference_reports_missing_visibility_support():
    doc = dxfpy.readzip("integration_tests/data/dynblks.zip", "dynblk0.dxf")
    insert = list(doc.modelspace().query("INSERT"))[0]
    dynamic = DynamicBlockReference(insert)

    assert dynamic.is_dynamic is True
    assert dynamic.has_visibility is False

    with pytest.raises(DynamicBlockVisibilityError):
        dynamic.set_visibility_state("ANY")


def test_dynamic_block_reference_rejects_direct_visibility_mutation():
    doc = dxfpy.new("R2018")
    block = doc.blocks.new("DIRECT_DYNAMIC")
    line = block.add_line((0, 0), (1, 0))
    set_dynamic_block_visibility_parameter(
        block,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="Visibility1",
            location=(0.0, 0.0, 0.0),
            states=(DynamicBlockVisibilityState("SHOW", (line.dxf.handle,)),),
        ),
        guid="{GUID}",
    )
    insert = doc.modelspace().add_blockref(block.name, (0, 0))
    dynamic = DynamicBlockReference(insert)

    assert dynamic.is_dynamic is True
    assert dynamic.is_anonymous_reference is False
    with pytest.raises(UnsupportedDynamicBlockReferenceError):
        dynamic.set_visibility_state("SHOW")


def test_dynamic_block_reference_exposes_property_table_metadata():
    doc = dxfpy.readfile(
        "tests/test_08_addons/autocad_nested_working_minimal_v1_edited.dxf"
    )
    inserts = list(doc.modelspace().query("INSERT"))
    dynamic = DynamicBlockReference(inserts[1])

    table = dynamic.property_table

    assert dynamic.has_property_table is True
    assert table is not None
    assert table.table_name == "Block Table1"
