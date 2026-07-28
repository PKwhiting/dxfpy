from io import StringIO

import pytest

import dxfpy
from dxfpy.dynamic_blocks import (
    DynamicBlockDefinition,
    DynamicBlockReference,
    DynamicBlockVisibilityError,
    NotDynamicBlockReferenceError,
    UnknownVisibilityStateError,
    UnsupportedDynamicBlockReferenceError,
)
from dxfpy.dynblkhelper import (
    _new_tag_storage_object,
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


def test_dynamic_block_definition_finds_true_name_and_point_parameters():
    doc, block = make_point_definition()

    definition = DynamicBlockDefinition.find(doc, "STRINGING")

    assert definition is not None
    assert definition.block is block
    assert definition.true_name == "STRINGING"
    assert definition.visibility_state_names == ("SHOW",)
    points = definition.point_parameters("SHOW")
    assert len(points) == 1
    assert points[0].name == "END"
    assert points[0].base_offset == (3.0, 0.0, 0.0)
    assert points[0].origin_offset == (5.0, 0.0, 0.0)


def test_dynamic_block_definition_materializes_filtered_static_state():
    doc, _ = make_point_definition()
    definition = DynamicBlockDefinition.find(doc, "STRINGING")
    assert definition is not None

    insert = definition.materialize_visibility_state(
        "SHOW",
        doc.modelspace(),
        (10, 20),
        predicate=lambda entity: entity.dxf.layer != "UNSEEN",
    )

    rendered = insert.block()
    assert len(rendered) == 1
    assert rendered.base_point == (2, 3, 0)
    assert rendered[0].dxf.color == 1
    assert rendered[0].dxf.invisible == 0


def test_dynamic_block_definition_rejects_unknown_state():
    doc, _ = make_point_definition()
    definition = DynamicBlockDefinition.find(doc, "STRINGING")
    assert definition is not None

    with pytest.raises(UnknownVisibilityStateError):
        definition.point_parameters("MISSING")


def test_dynamic_block_definition_points_survive_roundtrip():
    doc, _ = make_point_definition()
    stream = StringIO()
    doc.write(stream)

    loaded = dxfpy.read(StringIO(stream.getvalue()))
    definition = DynamicBlockDefinition.find(loaded, "STRINGING")

    assert definition is not None
    points = definition.point_parameters("SHOW")
    assert len(points) == 1
    assert points[0].name == "END"
    assert points[0].base_offset == (3.0, 0.0, 0.0)


def test_dynamic_block_definition_ignores_unrelated_visibility_handles():
    doc = dxfpy.new("R2018")
    block = doc.blocks.new("DYNAMIC")
    unrelated = doc.modelspace().add_line((0, 0), (1, 0))
    set_dynamic_block_visibility_parameter(
        block,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility",
            parameter_name="Visibility",
            location=(0, 0, 0),
            states=(
                DynamicBlockVisibilityState(
                    "SHOW", (unrelated.dxf.handle,)
                ),
            ),
        ),
        guid="{GUID}",
    )
    definition = DynamicBlockDefinition(block)

    assert definition.visible_entities("SHOW") == ()


def make_point_definition():
    doc = dxfpy.new("R2018")
    block = doc.blocks.new_anonymous_block(
        type_char="U", base_point=(2, 3)
    )
    visible = block.add_line((0, 0), (1, 0), dxfattribs={"color": 1})
    hidden = block.add_line(
        (0, 0), (2, 0), dxfattribs={"color": 2, "layer": "UNSEEN"}
    )
    hidden.dxf.invisible = 1
    point = _new_tag_storage_object(
        doc,
        "BLOCKPOINTPARAMETER",
        "0",
        [
            [(100, "AcDbEvalExpr"), (90, 7)],
            [(100, "AcDbBlockElement"), (300, "Endpoint")],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [(100, "AcDbBlock1PtParameter"), (1010, (3, 0, 0))],
            [
                (100, "AcDbBlockPointParameter"),
                (303, "END"),
                (1011, (5, 0, 0)),
            ],
        ],
    )
    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility",
        parameter_name="Visibility",
        location=(0, 0, 0),
        states=(
            DynamicBlockVisibilityState(
                "SHOW",
                (visible.dxf.handle, hidden.dxf.handle),
                (point.dxf.handle,),
            ),
        ),
    )
    set_dynamic_block_visibility_parameter(
        block, parameter, guid="{GUID}", true_name="STRINGING"
    )
    return doc, block
