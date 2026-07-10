from io import StringIO

import pytest
import dxfpy
from dxfpy.entities.dxfentity import RAW_TAGS_OVERRIDE_ATTRIBUTE
from dxfpy.lldxf.extendedtags import ExtendedTags
from dxfpy.lldxf.tagwriter import TagWriter
from dxfpy.math import Vec2
from dxfpy.dynblkhelper import (
    _clone_non_attdef_entities,
    _clone_property_attdef,
    _new_tag_storage_object,
    _owner_from_raw_tags,
    DynamicBlockBasePointParameter,
    DynamicBlockPropertiesTable,
    DynamicBlockPropertyColumn,
    DynamicBlockPropertyRow,
    DynamicBlockLinearGrip,
    DynamicBlockLinearParameter,
    DynamicBlockLookupAction,
    DynamicBlockLookupActionBinding,
    DynamicBlockLookupGrip,
    DynamicBlockLookupParameter,
    DynamicBlockStretchAction,
    DynamicBlockStretchActionTarget,
    DynamicBlockVisibilityParameter,
    DynamicBlockVisibilityState,
    get_dynamic_block_definition,
    get_dynamic_block_base_point_parameter,
    get_dynamic_block_linear_grips,
    get_dynamic_block_linear_parameters,
    get_dynamic_block_lookup_actions,
    get_dynamic_block_lookup_grips,
    get_dynamic_block_lookup_parameters,
    get_dynamic_block_properties_table,
    get_dynamic_block_property_columns,
    get_dynamic_block_property_assoc_networks,
    get_dynamic_block_property_representation_families,
    get_dynamic_block_property_representations,
    get_dynamic_block_property_rows,
    register_source_entity_handle_mapping,
    restore_raw_entity_export,
    snapshot_raw_dynamic_block_definition,
    snapshot_raw_dynamic_block_layout,
    snapshot_raw_entity_export,
    restore_raw_dynamic_block_definition,
    restore_raw_dynamic_block_layout,
    set_dynamic_block_definition_metadata,
    set_dynamic_block_properties_editor_support,
    get_dynamic_block_reference,
    get_dynamic_block_stretch_actions,
    get_dynamic_block_visibility_entities,
    get_dynamic_block_entity_by_rep_index_path,
    get_dynamic_block_entity_rep_index_path,
    get_dynamic_block_visibility_parameter,
    get_dynamic_block_visibility_state,
    get_dynamic_block_visibility_state_handles,
    get_dynamic_block_visibility_states,
    set_dynamic_block_base_point_parameter,
    set_dynamic_block_linear_parameter,
    set_dynamic_block_lookup_parameter,
    setup_dynamic_block_property_attdef_support,
    set_dynamic_block_properties_table,
    set_dynamic_block_reference,
    set_dynamic_block_visibility_parameter,
    set_dynamic_block_visibility_state,
)


def make_dynamic_insert(doc, current_state: str):
    msp = doc.modelspace()
    base = doc.blocks.get("DYN_VIS_PROBE_BASE")
    if base is None:
        base = doc.blocks.new("DYN_VIS_PROBE_BASE")
        parameter = DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="Visibility1Param",
            location=(0.0, 14.0, 0.0),
            states=(
                DynamicBlockVisibilityState("STATE_A", ("EF", "EE", "ED", "EC", "F0")),
                DynamicBlockVisibilityState("STATE_B", ("F1", "F2", "EC", "ED", "EE")),
                DynamicBlockVisibilityState("STATE_C", ("F4", "F3", "F6", "F5", "EC", "EE", "ED")),
            ),
        )
        set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}")

    anon = doc.blocks.new_anonymous_block(type_char="U")
    insert = msp.add_blockref(anon.name, (0, 0))
    set_dynamic_block_reference(anon, base)
    set_dynamic_block_visibility_state(insert, base, state=current_state)
    return insert


def make_dynamic_insert_with_entities(doc, current_state: str):
    msp = doc.modelspace()
    base = doc.blocks.get("DYN_VIS_PROBE_BASE_ENTS")
    if base is None:
        base = doc.blocks.new("DYN_VIS_PROBE_BASE_ENTS")
        common1 = base.add_line((0, 0), (1, 0))
        common2 = base.add_line((0, 1), (1, 1))
        state_a = base.add_circle((1, 1), radius=0.5)
        state_b = base.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
        state_c1 = base.add_line((0, 0), (1, 1))
        state_c2 = base.add_line((0, 1), (1, 0))
        base_handles = {
            "common1": common1.dxf.handle,
            "common2": common2.dxf.handle,
            "state_a": state_a.dxf.handle,
            "state_b": state_b.dxf.handle,
            "state_c1": state_c1.dxf.handle,
            "state_c2": state_c2.dxf.handle,
        }
        parameter = DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="Visibility1Param",
            location=(0.0, 14.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "STATE_A",
                    (
                        base_handles["common1"],
                        base_handles["common2"],
                        base_handles["state_a"],
                    ),
                ),
                DynamicBlockVisibilityState(
                    "STATE_B",
                    (
                        base_handles["common1"],
                        base_handles["common2"],
                        base_handles["state_b"],
                    ),
                ),
                DynamicBlockVisibilityState(
                    "STATE_C",
                    (
                        base_handles["common1"],
                        base_handles["common2"],
                        base_handles["state_c1"],
                        base_handles["state_c2"],
                    ),
                ),
            ),
        )
        set_dynamic_block_visibility_parameter(
            base, parameter, guid="{GUID}", true_name="DYN_VIS_PROBE_BASE_ENTS"
        )
        setattr(base, "_dyn_base_handles", base_handles)
    else:
        base_handles = getattr(base, "_dyn_base_handles")

    anon = doc.blocks.new_anonymous_block(type_char="U")
    anon.add_line((0, 0), (1, 0))
    anon.add_line((0, 1), (1, 1))
    anon.add_circle((1, 1), radius=0.5)
    anon.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
    anon.add_line((0, 0), (1, 1))
    anon.add_line((0, 1), (1, 0))
    insert = msp.add_blockref(anon.name, (0, 0))
    set_dynamic_block_reference(anon, base)
    set_dynamic_block_visibility_state(insert, base, state=current_state)
    return insert


def make_dynamic_properties_insert(doc):
    msp = doc.modelspace()
    base = doc.blocks.new("DYN_PROP_PROBE_BASE")
    base.add_line((0, 0), (1, 0))
    base.add_line((0, 1), (1, 1))
    base.add_circle((1, 1), radius=0.5)
    attdef1 = base.add_attdef("PARAM_1", insert=(10, 14), text="Block Table1")
    attdef2 = base.add_attdef("PARAM_2", insert=(10, 10), text="Block Table1")
    attdef3 = base.add_attdef("PARAM_3", insert=(10, 6), text="Block Table1")

    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility State",
        parameter_name="Visibility1Param",
        location=(0.0, 14.0, 0.0),
        states=(
            DynamicBlockVisibilityState("STATE_A", tuple(e.dxf.handle for e in base if e.dxftype() != "ATTDEF")),
            DynamicBlockVisibilityState("STATE_B", tuple(e.dxf.handle for e in base if e.dxftype() != "ATTDEF")),
            DynamicBlockVisibilityState("STATE_C", tuple(e.dxf.handle for e in base if e.dxftype() != "ATTDEF")),
        ),
    )
    set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}", true_name="DYN_PROP_PROBE_BASE")
    table = DynamicBlockPropertiesTable(
        handle="",
        label="Block Table",
        table_name="Block Table1",
        description="",
        location=(32.0, 20.0, 0.0),
        grip_location=(32.0, 20.0, 0.0),
        columns=(
            DynamicBlockPropertyColumn(attdef1.dxf.handle, "ATTDEF", "PARAM_1", "Block Table1"),
            DynamicBlockPropertyColumn(attdef2.dxf.handle, "ATTDEF", "PARAM_2", "Block Table1"),
            DynamicBlockPropertyColumn(attdef3.dxf.handle, "ATTDEF", "PARAM_3", "Block Table1"),
            DynamicBlockPropertyColumn("", "BLOCKVISIBILITYPARAMETER", "VisibilityState", "VisibilityState"),
        ),
        rows=(
            DynamicBlockPropertyRow(0, ("VAL 1", "VAL 1", "VAL 1", "STATE_A")),
            DynamicBlockPropertyRow(1, ("VAL 2", "VAL 1", "VAL 3", "STATE_B")),
            DynamicBlockPropertyRow(2, ("VAL 3", "VAL 2", "VAL 1", "STATE_C")),
        ),
    )
    set_dynamic_block_properties_table(base, table)
    set_dynamic_block_properties_editor_support(base, table)

    anon = doc.blocks.new_anonymous_block(type_char="U")
    anon.add_line((0, 0), (1, 0))
    anon.add_line((0, 1), (1, 1))
    anon.add_circle((1, 1), radius=0.5)
    set_dynamic_block_reference(anon, base)
    insert = msp.add_blockref(anon.name, (0, 0))
    set_dynamic_block_visibility_state(insert, base, state="STATE_A")
    return insert


def attach_linear_stretch_probe(block):
    doc = block.doc
    assert doc is not None
    graph = block.block_record.get_extension_dict().dictionary.get("ACAD_ENHANCEDBLOCK")
    assert graph is not None

    table = get_dynamic_block_properties_table(block)
    assert table is not None

    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")
    entities = list(block)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    attdef2 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_2")
    attdef3 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_3")

    linear = _new_tag_storage_object(
        doc,
        "BLOCKLINEARPARAMETER",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 45), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Linear"), (98, 33), (99, 378), (1071, 32)],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [
                (100, "AcDbBlock2PtParameter"),
                (1010, (0.0, 0.0, 0.0)),
                (1011, (1.0, 0.0, 0.0)),
                (170, 4),
                (91, 49),
                (91, 46),
                (91, 0),
                (91, 0),
                (171, 1),
                (92, 49),
                (301, "DisplacementX"),
                (172, 1),
                (93, 49),
                (302, "DisplacementY"),
                (173, 1),
                (94, 46),
                (303, "DisplacementX"),
                (174, 1),
                (95, 46),
                (304, "DisplacementY"),
                (177, 0),
            ],
            [
                (100, "AcDbBlockLinearParameter"),
                (305, "Distance1"),
                (306, ""),
                (140, 1.0),
                (307, ""),
                (96, 1),
                (141, 0.0),
                (142, 0.0),
                (143, 0.0),
                (175, 0),
            ],
        ],
    )
    end_grip = _new_tag_storage_object(
        doc,
        "BLOCKLINEARGRIP",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 46), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "End Grip"), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockGrip"), (91, 47), (92, 48), (1010, (1.0, 0.0, 0.0)), (280, 1), (93, -1)],
            [(100, "AcDbBlockLinearGrip"), (140, 1.0), (141, 0.0), (142, 0.0)],
        ],
    )
    _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 47), (98, 33), (99, 378), (1, ""), (70, 40), (140, 1.797693134862314e+99)],
            [(100, "AcDbBlockGripExpr"), (91, 45), (300, "UpdatedEndX")],
        ],
    )
    _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 48), (98, 33), (99, 378), (1, ""), (70, 40), (140, 1.797693134862314e+99)],
            [(100, "AcDbBlockGripExpr"), (91, 45), (300, "UpdatedEndY")],
        ],
    )
    base_grip = _new_tag_storage_object(
        doc,
        "BLOCKLINEARGRIP",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 49), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Base Grip"), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockGrip"), (91, 50), (92, 51), (1010, (0.0, 0.0, 0.0)), (280, 1), (93, -1)],
            [(100, "AcDbBlockLinearGrip"), (140, -1.0), (141, 0.0), (142, 0.0)],
        ],
    )
    _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 50), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 45), (300, "UpdatedBaseX")],
        ],
    )
    _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 51), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 45), (300, "UpdatedBaseY")],
        ],
    )
    stretch = _new_tag_storage_object(
        doc,
        "BLOCKSTRETCHACTION",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 52), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Stretch1"), (98, 33), (99, 378), (1071, 0)],
            [
                (100, "AcDbBlockAction"),
                (70, 1),
                (91, 32),
                (71, 6),
                (330, grip.dxf.handle),
                (330, table.handle),
                (330, attdef3.dxf.handle),
                (330, attdef2.dxf.handle),
                (330, attdef1.dxf.handle),
                (330, stretch_entity.dxf.handle),
                (1010, (1.0, -0.5, 0.0)),
            ],
            [
                (100, "AcDbBlockStretchAction"),
                (92, 45),
                (301, "EndXDelta"),
                (93, 45),
                (302, "EndYDelta"),
                (72, 2),
                (1011, (2.0, 1.0, 0.0)),
                (1011, (0.5, -0.5, 0.0)),
                (73, 4),
                (331, stretch_entity.dxf.handle),
                (74, 2),
                (94, 1),
                (94, 2),
                (331, attdef1.dxf.handle),
                (74, 1),
                (94, 0),
                (331, attdef2.dxf.handle),
                (74, 1),
                (94, 0),
                (331, attdef3.dxf.handle),
                (74, 1),
                (94, 0),
                (75, 1),
                (95, 32),
                (76, 1),
                (94, 0),
                (140, 1.0),
                (141, 0.0),
                (280, 0),
            ],
        ],
    )

    return linear, end_grip, base_grip, stretch


def attach_lookup_probe(block):
    doc = block.doc
    assert doc is not None
    graph = block.block_record.get_extension_dict().dictionary.get("ACAD_ENHANCEDBLOCK")
    assert graph is not None

    linear_entity = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKLINEARPARAMETER")
    lookup_action_internal = _new_tag_storage_object(
        doc,
        "BLOCKLOOKUPACTION",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 57), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Lookup1"), (98, 33), (99, 378), (1071, 2)],
            [(100, "AcDbBlockAction"), (70, 0), (71, 0), (1010, (16.5, 19.5, 0.0))],
            [
                (100, "AcDbBlockLookupAction"),
                (92, 5),
                (93, 1),
                (301, ""),
                (302, "0"),
                (302, "8"),
                (302, "7"),
                (302, "6"),
                (302, "5"),
                (303, ""),
                (94, 45),
                (95, 40),
                (96, 2),
                (282, 0),
                (305, "Custom"),
                (281, 0),
                (304, "UpdatedDistance"),
                (280, 1),
            ],
        ],
    )
    lookup_parameter = _new_tag_storage_object(
        doc,
        "BLOCKLOOKUPPARAMETER",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 71), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Lookup"), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [(100, "AcDbBlock1PtParameter"), (1010, (19.28, 23.15, 0.0)), (93, 72), (170, 0), (171, 0)],
            [(100, "AcDbBlockLookUpParameter"), (303, "Lookup1"), (304, ""), (94, 75)],
        ],
    )
    lookup_grip = _new_tag_storage_object(
        doc,
        "BLOCKLOOKUPGRIP",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 72), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Grip"), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockGrip"), (91, 73), (92, 74), (1010, (19.28, 23.15, 0.0)), (280, 0), (93, -1)],
            [(100, "AcDbBlockLookUpGrip")],
        ],
    )
    lookup_x = _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 73), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 71), (300, "UpdatedX")],
        ],
    )
    lookup_y = _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 74), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 71), (300, "UpdatedY")],
        ],
    )
    lookup_action_public = _new_tag_storage_object(
        doc,
        "BLOCKLOOKUPACTION",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 75), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Lookup3"), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockAction"), (70, 0), (71, 0), (1010, (20.01, 22.42, 0.0))],
            [
                (100, "AcDbBlockLookupAction"),
                (92, 5),
                (93, 2),
                (301, ""),
                (302, "10"),
                (302, "len 1"),
                (302, "20"),
                (302, "len 2"),
                (302, "32"),
                (302, "len 3"),
                (302, "40"),
                (302, "len 4"),
                (302, "50"),
                (302, "len 5"),
                (303, ""),
                (94, 45),
                (95, 40),
                (96, 2),
                (282, 0),
                (305, "Custom"),
                (281, 0),
                (304, "UpdatedDistance"),
                (303, ""),
                (94, 71),
                (95, 1),
                (96, 0),
                (282, 1),
                (305, "Custom"),
                (281, 1),
                (304, "lookupString"),
                (280, 1),
            ],
        ],
    )

    linear_subclass = linear_entity.xtags.get_subclass("AcDbBlockLinearParameter")
    linear_subclass.clear()
    from dxfpy.lldxf.types import dxftag

    linear_subclass.extend(
        dxftag(code, value)
        for code, value in [
            (100, "AcDbBlockLinearParameter"),
            (305, "Distance1"),
            (306, ""),
            (140, -5.441939436423126),
            (307, ""),
            (96, 8),
            (141, 0.0),
            (142, 0.0),
            (143, 0.0),
            (175, 5),
            (144, 10.0),
            (144, 20.0),
            (144, 32.0),
            (144, 40.0),
            (144, 50.0),
        ]
    )
    return lookup_parameter, lookup_grip, lookup_x, lookup_y, lookup_action_internal, lookup_action_public


def test_get_dynamic_block_visibility_parameter_and_state():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert(doc, "STATE_C")

    block = get_dynamic_block_definition(insert)
    parameter = get_dynamic_block_visibility_parameter(insert)

    assert block is not None
    assert block.name == "DYN_VIS_PROBE_BASE"
    assert parameter is not None
    assert parameter.label == "Visibility State"
    assert parameter.parameter_name == "Visibility1Param"
    assert parameter.location == (0.0, 14.0, 0.0)
    assert parameter.all_entity_handles == (
        "EF",
        "EE",
        "ED",
        "EC",
        "F0",
        "F1",
        "F2",
        "F4",
        "F3",
        "F6",
        "F5",
    )
    assert tuple(state.name for state in parameter.states) == (
        "STATE_A",
        "STATE_B",
        "STATE_C",
    )
    assert parameter.states[0].entity_handles == ("EF", "EE", "ED", "EC", "F0")
    assert parameter.states[2].entity_handles == (
        "F4",
        "F3",
        "F6",
        "F5",
        "EC",
        "EE",
        "ED",
    )
    assert get_dynamic_block_visibility_states(insert) == (
        "STATE_A",
        "STATE_B",
        "STATE_C",
    )
    assert get_dynamic_block_visibility_state(insert) == "STATE_C"


def test_get_dynamic_block_visibility_state_varies_per_insert():
    doc = dxfpy.new("R2018")
    insert_a = make_dynamic_insert(doc, "STATE_A")
    insert_b = make_dynamic_insert(doc, "STATE_B")

    assert get_dynamic_block_visibility_state(insert_a) == "STATE_A"
    assert get_dynamic_block_visibility_state(insert_b) == "STATE_B"


def test_set_dynamic_block_visibility_state_updates_existing_autocad_cache_record():
    doc = dxfpy.readzip("integration_tests/data/dynblks.zip", "dynblk1.dxf")
    insert = list(doc.modelspace().query("INSERT"))[0]
    definition = get_dynamic_block_definition(insert)

    assert definition is not None
    assert get_dynamic_block_visibility_state(insert) == "CircleVisibilityState"

    set_dynamic_block_visibility_state(
        insert, definition, state="SquareVisibilityState"
    )

    reference = get_dynamic_block_reference(insert)
    assert reference is not None
    assert get_dynamic_block_visibility_state(insert) == "SquareVisibilityState"
    assert [entity.dxf.get("invisible", 0) for entity in reference] == [1, 0]


def test_set_dynamic_block_visibility_state_rejects_unknown_state():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert(doc, "STATE_A")
    definition = get_dynamic_block_definition(insert)

    assert definition is not None
    with pytest.raises(
        dxfpy.lldxf.const.DXFValueError,
        match="unknown dynamic block visibility state",
    ):
        set_dynamic_block_visibility_state(insert, definition, state="MISSING")


def test_get_dynamic_block_visibility_entities_resolves_base_and_reference_entities():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert_with_entities(doc, "STATE_C")

    base = get_dynamic_block_definition(insert)
    ref = get_dynamic_block_reference(insert)

    assert base is not None
    assert ref is not None
    assert get_dynamic_block_visibility_state_handles(insert) == tuple(
        entity.dxf.handle for entity in get_dynamic_block_visibility_entities(base, "STATE_C")
    )

    base_entities = get_dynamic_block_visibility_entities(base, "STATE_C")
    ref_entities = get_dynamic_block_visibility_entities(insert)

    assert [entity.dxftype() for entity in base_entities] == [
        "LINE",
        "LINE",
        "LINE",
        "LINE",
    ]
    assert [entity.dxftype() for entity in ref_entities] == [
        "LINE",
        "LINE",
        "LINE",
        "LINE",
    ]
    assert tuple(entity.dxf.handle for entity in ref_entities) == tuple(
        entity.dxf.handle for entity in list(ref)[:2] + list(ref)[4:6]
    )


def test_dynamic_block_visibility_roundtrip_preserves_visibility_helpers():
    doc = dxfpy.new("R2018")
    make_dynamic_insert_with_entities(doc, "STATE_A")
    make_dynamic_insert_with_entities(doc, "STATE_C")

    stream = StringIO()
    doc.write(stream)
    loaded = dxfpy.read(StringIO(stream.getvalue()))
    inserts = list(loaded.modelspace().query("INSERT"))

    assert get_dynamic_block_visibility_state(inserts[0]) == "STATE_A"
    assert get_dynamic_block_visibility_state(inserts[1]) == "STATE_C"
    assert get_dynamic_block_visibility_states(inserts[0]) == (
        "STATE_A",
        "STATE_B",
        "STATE_C",
    )
    assert [entity.dxftype() for entity in get_dynamic_block_visibility_entities(inserts[1])] == [
        "LINE",
        "LINE",
        "LINE",
        "LINE",
    ]


def test_dynamic_block_helpers_register_required_appids():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert(doc, "STATE_A")

    assert insert is not None
    for name in (
        "AcDbDynamicBlockGUID",
        "AcDbDynamicBlockTrueName",
        "AcDbBlockRepETag",
        "AcDbBlockRepBTag",
    ):
        assert name in doc.appids


def test_dynamic_block_reference_gets_xdict_and_blkrefs_appdata():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert(doc, "STATE_A")
    reference = get_dynamic_block_reference(insert)

    assert reference is not None
    assert reference.block_record.has_extension_dict is True
    assert reference.block_record.blkref_handles == [insert.dxf.handle]


def test_dynamic_block_visibility_state_accumulates_blkref_handles_for_shared_reference():
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    base = doc.blocks.new("DYN_VIS_SHARED_REF")
    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility State",
        parameter_name="Visibility1Param",
        location=(0.0, 14.0, 0.0),
        states=(
            DynamicBlockVisibilityState("STATE_A", ()),
            DynamicBlockVisibilityState("STATE_B", ()),
        ),
    )
    set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}")
    anon = doc.blocks.new_anonymous_block(type_char="U")
    set_dynamic_block_reference(anon, base)
    insert_a = msp.add_blockref(anon.name, (0, 0))
    insert_b = msp.add_blockref(anon.name, (1, 0))

    set_dynamic_block_visibility_state(insert_a, base, state="STATE_A")
    set_dynamic_block_visibility_state(insert_b, base, state="STATE_B")

    assert anon.block_record.blkref_handles == [insert_a.dxf.handle, insert_b.dxf.handle]


def test_dynamic_block_visibility_writing_adds_required_classes():
    doc = dxfpy.new("R2018")
    make_dynamic_insert(doc, "STATE_A")

    stream = StringIO()
    doc.write(stream)
    data = stream.getvalue()

    assert "AcDbEvalGraph" in data
    assert "AcAeEditorObj" in data
    assert "AcAeEEMgrObj" in data
    assert "AcDbBlockVisibilityParameter" in data
    assert "AcDbBlockVisibilityGrip" in data
    assert "AcDbBlockRepresentationData" in data

    loaded = dxfpy.read(StringIO(data))
    counts = {
        cls.dxf.name: cls.dxf.get("instance_count")
        for cls in loaded.classes
        if cls.dxf.name
        in {
            "ACAD_EVALUATION_GRAPH",
            "BLOCKVISIBILITYPARAMETER",
            "BLOCKVISIBILITYGRIP",
            "BLOCKGRIPLOCATIONCOMPONENT",
            "ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION",
            "ACDB_BLOCKREPRESENTATION_DATA",
        }
    }
    assert counts["ACAD_EVALUATION_GRAPH"] == 1
    assert counts["BLOCKVISIBILITYPARAMETER"] == 1
    assert counts["BLOCKVISIBILITYGRIP"] == 1
    assert counts["BLOCKGRIPLOCATIONCOMPONENT"] == 2


def test_dynamic_block_linear_writing_adds_required_classes():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    set_dynamic_block_linear_parameter(
        base,
        DynamicBlockLinearParameter(
            handle="",
            label="Linear",
            parameter_name="Distance1",
            description="",
            base_point=(0.0, 0.0, 0.0),
            end_point=(10.0, 0.0, 0.0),
            distance=10.0,
            expr_id=0,
            end_grip_label="End Grip",
            end_grip_location=(2.0, 3.0, 0.0),
        ),
        DynamicBlockStretchAction(
            handle="",
            label="Stretch",
            action_location=(1.0, -0.5, 0.0),
            x_expr_id=0,
            x_name="EndXDelta",
            y_expr_id=0,
            y_name="EndYDelta",
            selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
            dependency_handles=(),
            targets=(),
        ),
    )

    stream = StringIO()
    doc.write(stream)
    data = stream.getvalue()

    assert "AcDbBlockBasepointParameter" in data
    assert "AcDbBlockLinearParameter" in data
    assert "AcDbBlockLinearGrip" in data
    assert "AcDbBlockStretchAction" in data

    loaded = dxfpy.read(StringIO(data))
    counts = {
        cls.dxf.name: cls.dxf.get("instance_count")
        for cls in loaded.classes
        if cls.dxf.name
        in {
            "BLOCKBASEPOINTPARAMETER",
            "BLOCKLINEARPARAMETER",
            "BLOCKLINEARGRIP",
            "BLOCKSTRETCHACTION",
        }
    }
    assert counts["BLOCKBASEPOINTPARAMETER"] == 1
    assert counts["BLOCKLINEARPARAMETER"] == 1
    assert counts["BLOCKLINEARGRIP"] == 1
    assert counts["BLOCKSTRETCHACTION"] == 1


def test_dynamic_block_entities_get_block_rep_etag_xdata():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert_with_entities(doc, "STATE_B")
    base = get_dynamic_block_definition(insert)
    ref = get_dynamic_block_reference(insert)

    assert base is not None
    assert ref is not None
    for index, entity in enumerate(base):
        tags = entity.get_xdata("AcDbBlockRepETag")
        assert list(tags) == [(1070, 1), (1071, index), (1005, entity.dxf.handle)]
    for index, entity in enumerate(ref):
        tags = entity.get_xdata("AcDbBlockRepETag")
        assert list(tags) == [(1070, 1), (1071, index), (1005, entity.dxf.handle)]


def test_dynamic_block_insert_enhanced_cache_sets_reactors():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert(doc, "STATE_A")

    rep = insert.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
    cache = rep.get("AppDataCache")
    enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")
    xrecord = enhanced.get("6")

    assert enhanced.get_reactors() == [cache.dxf.handle]
    assert xrecord.get_reactors() == [enhanced.dxf.handle]


def test_basepoint_linear_insert_writes_extended_cache_records():
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    attdef2 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_2")
    attdef3 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_3")
    table = get_dynamic_block_properties_table(base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        end_grip_label="End Grip",
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(
            grip.dxf.handle,
            table.handle,
            attdef3.dxf.handle,
            attdef2.dxf.handle,
            attdef1.dxf.handle,
            stretch_entity.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(stretch_entity.dxf.handle, 2, (1, 2)),
            DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef2.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef3.dxf.handle, 1, (0,)),
        ),
    )
    set_dynamic_block_linear_parameter(base, linear, action)

    anon = doc.blocks.new_anonymous_block(type_char="U")
    set_dynamic_block_reference(anon, base)
    dyn_insert = msp.add_blockref(anon.name, (0, 0))
    set_dynamic_block_visibility_state(dyn_insert, base, state="STATE_A")

    rep = dyn_insert.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
    cache = rep.get("AppDataCache")
    enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")
    history = cache.get("ACAD_ENHANCEDBLOCKHISTORY")

    assert set(enhanced.keys()) >= {"1", "5", "16", "20"}
    assert "6" not in set(enhanced.keys())
    assert history is not None
    assert list(enhanced.get("1").tags)[-2:] == [
        (10, (0.0, 14.0, 0.0)),
        (1, "STATE_A"),
    ]
    assert list(enhanced.get("5").tags)[-1] == (10, (0.0, 0.0, 0.0))
    assert list(enhanced.get("16").tags)[-3:] == [
        (10, (0.0, 0.0, 0.0)),
        (10, (1.0, 0.0, 0.0)),
        (10, (0.0, 0.0, -1.0)),
    ]
    assert list(enhanced.get("20").tags)[-1] == (40, 0.0)
    assert (300, "GRIPLOC") in list(history.tags)


def test_dynamic_block_reference_propagates_nested_dynamic_insert_state_and_cache():
    doc = dxfpy.new("R2018")
    child_insert = make_dynamic_insert_with_entities(doc, "STATE_B")
    child_base = get_dynamic_block_definition(child_insert)
    child_ref = get_dynamic_block_reference(child_insert)

    assert child_base is not None
    assert child_ref is not None

    parent_base = doc.blocks.new("DYN_NESTED_PROPAGATE_PARENT")
    parent_line = parent_base.add_line((0, 0), (20, 0))
    source_nested = parent_base.add_blockref(child_ref.name, (40, 0))
    set_dynamic_block_visibility_parameter(
        parent_base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="ParentVisibility",
            location=(0.0, 10.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "SHOW_CHILD",
                    (parent_line.dxf.handle, source_nested.dxf.handle),
                ),
                DynamicBlockVisibilityState("LINE_ONLY", (parent_line.dxf.handle,)),
            ),
        ),
        guid="{PARENT}",
    )
    set_dynamic_block_visibility_state(source_nested, child_base, state="STATE_B")

    parent_ref = doc.blocks.new_anonymous_block(type_char="U")
    _clone_non_attdef_entities(parent_base, parent_ref)
    set_dynamic_block_reference(parent_ref, parent_base)

    target_nested = next(entity for entity in parent_ref if entity.dxftype() == "INSERT")

    assert target_nested.has_extension_dict is True
    assert get_dynamic_block_definition(target_nested) == child_base
    assert get_dynamic_block_reference(target_nested) == child_ref
    assert get_dynamic_block_visibility_state(target_nested) == "STATE_B"
    rep = target_nested.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
    cache = rep.get("AppDataCache")
    enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")

    assert set(enhanced.keys()) >= {"6"}


def test_set_dynamic_block_base_point_parameter_creates_basepoint_only_graph():
    doc = dxfpy.new("R2018")
    block = doc.blocks.new("DYN_BASEPOINT_ONLY")
    block.add_line((0, 0), (1, 0))
    set_dynamic_block_definition_metadata(
        block,
        guid="{GUID}",
        true_name="DYN_BASEPOINT_ONLY",
    )

    created = set_dynamic_block_base_point_parameter(
        block,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(2.0, 3.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    parsed = get_dynamic_block_base_point_parameter(block)

    assert created.handle
    assert parsed is not None
    assert parsed.location == (2.0, 3.0, 0.0)


def test_raw_dynamic_block_definition_snapshot_restore_preserves_supported_linear_shape():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    attdef2 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_2")
    attdef3 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_3")
    table = get_dynamic_block_properties_table(base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    set_dynamic_block_linear_parameter(
        base,
        DynamicBlockLinearParameter(
            handle="",
            label="Linear",
            parameter_name="Distance1",
            description="",
            base_point=(0.0, 0.0, 0.0),
            end_point=(1.0, 0.0, 0.0),
            distance=1.0,
            expr_id=0,
            end_grip_label="End Grip",
        ),
        DynamicBlockStretchAction(
            handle="",
            label="Stretch",
            action_location=(1.0, -0.5, 0.0),
            x_expr_id=0,
            x_name="EndXDelta",
            y_expr_id=0,
            y_name="EndYDelta",
            selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
            dependency_handles=(
                grip.dxf.handle,
                table.handle,
                attdef3.dxf.handle,
                attdef2.dxf.handle,
                attdef1.dxf.handle,
                stretch_entity.dxf.handle,
            ),
            targets=(
                DynamicBlockStretchActionTarget(stretch_entity.dxf.handle, 2, (1, 2)),
                DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
                DynamicBlockStretchActionTarget(attdef2.dxf.handle, 1, (0,)),
                DynamicBlockStretchActionTarget(attdef3.dxf.handle, 1, (0,)),
            ),
        ),
    )
    base.block_record.preview_data = bytes.fromhex("01020304")
    base.block_record.dxf.units = 1

    snapshot = snapshot_raw_dynamic_block_definition(base)
    clone = doc.blocks.new("DYN_RAW_RESTORED")
    entity_handle_map = []
    for entity in base:
        copied = entity.copy()
        clone.add_entity(copied)
        entity_handle_map.append((entity.dxf.handle, copied.dxf.handle))
    restore_raw_dynamic_block_definition(clone, snapshot, entity_handle_map)

    restored_visibility = get_dynamic_block_visibility_parameter(clone)
    restored_basepoint = get_dynamic_block_base_point_parameter(clone)
    restored_props = get_dynamic_block_properties_table(clone)
    restored_linear = get_dynamic_block_linear_parameters(clone)

    assert restored_visibility is not None
    assert restored_basepoint is not None
    assert restored_props is not None
    assert len(restored_linear) == 1
    assert restored_basepoint.location == (0.0, 0.0, 0.0)
    assert restored_linear[0].parameter_name == "Distance1"
    assert clone.block_record.preview_data == bytes.fromhex("01020304")
    assert clone.block_record.dxf.units == 1


def test_raw_dynamic_block_layout_restore_remaps_entity_and_xdata_handles_for_export():
    doc = dxfpy.new("R2018")
    doc.appids.new("SELF_REF")

    source = doc.blocks.new("RAW_LAYOUT_SOURCE")
    line = source.add_line((0, 0), (1, 0))
    source_handle = line.dxf.handle
    line.set_xdata("SELF_REF", [(1005, source_handle)])

    snapshot = snapshot_raw_dynamic_block_layout(source)
    clone = doc.blocks.new("RAW_LAYOUT_CLONE")
    restore_raw_dynamic_block_layout(clone, snapshot)

    restored_line = next(entity for entity in clone if entity.dxftype() == "LINE")

    assert restored_line.dxf.handle != source_handle
    assert list(restored_line.get_xdata("SELF_REF")) == [(1005, restored_line.dxf.handle)]

    stream = StringIO()
    restored_line.export_dxf(TagWriter(stream, dxfversion=doc.dxfversion))
    exported = ExtendedTags.from_text(stream.getvalue())

    assert exported.get_handle() == restored_line.dxf.handle
    assert source_handle not in stream.getvalue()


def test_raw_dynamic_block_layout_snapshot_preserves_authored_mtext_column_xdata():
    from dxfpy.entities.mtext import ColumnType, MTextColumns

    doc = dxfpy.new("R2010")
    if "ACAD" not in doc.appids:
        doc.appids.new("ACAD")

    block = doc.blocks.new("RAW_MTEXT_SOURCE")
    mtext = block.add_mtext(
        "A",
        dxfattribs={
            "insert": (0, 0, 0),
            "line_spacing_style": 1,
            "line_spacing_factor": 1.0,
        },
    )
    cols = MTextColumns()
    cols.column_type = ColumnType.STATIC
    cols.count = 2
    cols.width = 1.0
    cols.gutter_width = 0.2
    cols.defined_height = 2.0
    mtext._columns = cols
    mtext.set_xdata(
        "ACAD",
        [
            (1000, "ACAD_MTEXT_COLUMN_INFO_BEGIN"),
            (1070, 2),
            (1070, 1),
            (1000, "ACAD_MTEXT_COLUMN_INFO_END"),
        ],
    )

    snapshot = snapshot_raw_dynamic_block_layout(block)
    entity_text = snapshot[1][0][0]
    tags = ExtendedTags.from_text(entity_text)

    assert "ACAD_MTEXT_COLUMN_INFO_BEGIN" in entity_text
    assert "ACAD_MTEXT_COLUMNS_BEGIN" not in entity_text
    assert any(tag.code == 73 and tag.value == 1 for tag in tags)
    assert any(tag.code == 44 and tag.value == 1.0 for tag in tags)


def test_raw_dynamic_block_layout_restore_preserves_multileader_proxy_payload():
    from dxfpy.render.mleader import ConnectionSide
    from dxfpy.lldxf.tagwriter import TagWriter

    doc = dxfpy.new("R2010")
    block = doc.blocks.new("RAW_MLEADER_SOURCE")
    builder = block.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    mleader = next(entity for entity in block if entity.dxftype() == "MULTILEADER")
    mleader.proxy_graphic = b"\x01\x02\x03\x04"

    snapshot = snapshot_raw_dynamic_block_layout(block)
    clone = doc.blocks.new("RAW_MLEADER_CLONE")
    restore_raw_dynamic_block_layout(clone, snapshot)

    restored = next(entity for entity in clone if entity.dxftype() == "MULTILEADER")
    stream = StringIO()
    restored.export_dxf(TagWriter(stream, dxfversion=doc.dxfversion))
    text = stream.getvalue().replace("\r\n", "\n")

    assert getattr(restored, "_raw_tags_override") is not None
    assert "\n 92\n4\n310\n01020304\n" in text


def test_raw_dynamic_block_definition_restore_preserves_multileader_proxy_payload():
    from dxfpy.render.mleader import ConnectionSide

    doc = dxfpy.new("R2010")
    block = doc.blocks.new("RAW_DEF_MLEADER_SOURCE")
    builder = block.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    mleader = next(entity for entity in block if entity.dxftype() == "MULTILEADER")
    mleader.proxy_graphic = b"\x01\x02\x03\x04"

    snapshot = snapshot_raw_dynamic_block_definition(block)
    clone = doc.blocks.new("RAW_DEF_MLEADER_CLONE")
    entity_handle_map = []
    for entity in block:
        copied = entity.copy()
        if copied.dxftype() == "MULTILEADER":
            copied.proxy_graphic = None
        clone.add_entity(copied)
        entity_handle_map.append((entity.dxf.handle, copied.dxf.handle))

    restore_raw_dynamic_block_definition(clone, snapshot, entity_handle_map)

    restored = next(entity for entity in clone if entity.dxftype() == "MULTILEADER")
    stream = StringIO()
    restored.export_dxf(TagWriter(stream, dxfversion=doc.dxfversion))
    text = stream.getvalue().replace("\r\n", "\n")

    assert getattr(restored, "_raw_tags_override") is not None
    assert "\n 92\n4\n310\n01020304\n" in text


def test_raw_dynamic_block_definition_restore_remaps_external_multileader_style_handles():
    from dxfpy.render.mleader import ConnectionSide

    source_doc = dxfpy.new("R2010")
    target_doc = dxfpy.new("R2010")
    target_style = target_doc.mleader_styles.get("Standard")
    assert target_style is not None
    assert target_doc.entitydb.reset_handle(target_style, "F1") is True

    source = source_doc.blocks.new("RAW_DEF_MLEADER_EXT_SOURCE")
    builder = source.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    clone = target_doc.blocks.new("RAW_DEF_MLEADER_EXT_CLONE")
    builder = clone.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    source_style = source_doc.mleader_styles.get("Standard")
    assert source_style is not None
    register_source_entity_handle_mapping(source_style, target_style)

    snapshot = snapshot_raw_dynamic_block_definition(source)
    entity_handle_map = [(s.dxf.handle, t.dxf.handle) for s, t in zip(source, clone)]
    restore_raw_dynamic_block_definition(clone, snapshot, entity_handle_map)

    restored = next(entity for entity in clone if entity.dxftype() == "MULTILEADER")
    stream = StringIO()
    restored.export_dxf(TagWriter(stream, dxfversion=target_doc.dxfversion))
    refs: list[tuple[str, str]] = []
    for tag in ExtendedTags.from_text(stream.getvalue()):
        if tag.code != 340:
            continue
        target = target_doc.entitydb.get(str(tag.value))
        refs.append((str(tag.value), target.dxftype() if target is not None else ""))

    assert (target_style.dxf.handle, "MLEADERSTYLE") in refs
    assert all(value != source_style.dxf.handle for value, _ in refs)


def test_owner_from_raw_tags_skips_reactor_handles():
    tags = (
        (0, "MLEADERSTYLE"),
        (5, "18A7"),
        (102, "{ACAD_REACTORS"),
        (330, "19D"),
        (102, "}"),
        (330, "F"),
    )

    assert _owner_from_raw_tags(tags) == "F"


def test_raw_dynamic_block_layout_snapshot_uses_authored_file_text_when_available(
    tmp_path,
):
    from dxfpy.render.mleader import ConnectionSide

    source_doc = dxfpy.new("R2010")
    block = source_doc.blocks.new("RAW_FILE_TEXT_BLOCK")
    builder = block.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    path = tmp_path / "raw_file_text_block.dxf"
    source_doc.saveas(path)

    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    text = text.replace("\n270\n2\n", "\n", 1)
    path.write_text(text, encoding="utf-8", errors="surrogateescape")

    loaded = dxfpy.readfile(path)
    loaded_block = loaded.blocks.get("RAW_FILE_TEXT_BLOCK")
    snapshot = snapshot_raw_dynamic_block_layout(loaded_block)
    entity_text = next(entry[0] for entry in snapshot[1] if "MULTILEADER" in entry[0])

    assert "\n270\n2\n" not in entity_text


def test_dynamic_block_visibility_descendant_authoring_is_rejected():
    doc = dxfpy.new("R2018")
    child_insert = make_dynamic_insert_with_entities(doc, "STATE_A")
    child_ref = get_dynamic_block_reference(child_insert)

    assert child_ref is not None
    child_state_handles = tuple(
        entity.dxf.handle
        for entity in child_ref
        if entity.dxftype() in {"LINE", "CIRCLE"} and entity.dxf.get("invisible", 0) == 0
    )

    parent_base = doc.blocks.new("DYN_VIS_NESTED_DESCENDANT")
    parent_line = parent_base.add_line((0, 0), (20, 0))
    parent_base.add_blockref(child_ref.name, (40, 0))
    with pytest.raises(
        dxfpy.lldxf.const.DXFValueError,
        match="nested dynamic block visibility descendants are not supported",
    ):
        set_dynamic_block_visibility_parameter(
            parent_base,
            DynamicBlockVisibilityParameter(
                handle="",
                label="Visibility State",
                parameter_name="ParentVisibility",
                location=(0.0, 10.0, 0.0),
                states=(
                    DynamicBlockVisibilityState(
                        "SHOW_DESC",
                        (parent_line.dxf.handle, *child_state_handles),
                    ),
                    DynamicBlockVisibilityState("LINE_ONLY", (parent_line.dxf.handle,)),
                ),
            ),
            guid="{PARENT}",
        )


def test_set_dynamic_block_linear_parameter_rejects_nested_descendant_targets():
    doc = dxfpy.new("R2018")
    child_insert = make_dynamic_insert_with_entities(doc, "STATE_A")
    child_ref = get_dynamic_block_reference(child_insert)
    parent_insert = make_dynamic_properties_insert(doc)
    parent_base = get_dynamic_block_definition(parent_insert)

    assert child_ref is not None
    assert parent_base is not None
    child_line = next(entity for entity in child_ref if entity.dxftype() == "LINE")
    parent_base.add_blockref(child_ref.name, (40, 0))

    entities = list(parent_base)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    table = get_dynamic_block_properties_table(parent_base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    set_dynamic_block_base_point_parameter(
        parent_base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        end_grip_label="End Grip",
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(
            grip.dxf.handle,
            table.handle,
            attdef1.dxf.handle,
            child_line.dxf.handle,
            stretch_entity.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(child_line.dxf.handle, 1, (1,)),
            DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
        ),
    )
    with pytest.raises(
        dxfpy.lldxf.const.DXFValueError,
        match="nested dynamic block linear descendant targets are not supported",
    ):
        set_dynamic_block_linear_parameter(parent_base, linear, action)


def test_dynamic_block_writer_applies_invisible_mask_to_default_and_active_states():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert_with_entities(doc, "STATE_C")

    base = doc.blocks.get("DYN_VIS_PROBE_BASE_ENTS")
    ref = get_dynamic_block_reference(insert)

    assert base is not None
    assert ref is not None

    # Base dynamic definition defaults to the first state (STATE_A).
    base_invisible = [entity.dxf.get("invisible", 0) for entity in base]
    assert base_invisible == [0, 0, 0, 1, 1, 1]

    # Active anonymous reference reflects the requested current state (STATE_C).
    ref_invisible = [entity.dxf.get("invisible", 0) for entity in ref]
    assert ref_invisible == [0, 0, 1, 1, 0, 0]


def test_dynamic_block_properties_writer_adds_visibility_only_support_blocks():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)

    assert insert is not None
    zero_carrier_blocks = []
    for block in doc.blocks:
        if not block.name.startswith("*U"):
            continue
        if not any(entity.dxftype() == "ATTDEF" for entity in block):
            zero_carrier_blocks.append(block)
    assert len(zero_carrier_blocks) == 5


def test_get_dynamic_block_properties_table_reads_columns_rows_and_grip_location():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)

    table = get_dynamic_block_properties_table(insert)

    assert isinstance(table, DynamicBlockPropertiesTable)
    assert table.label == "Block Table"
    assert table.table_name == "Block Table1"
    assert table.location == (32.0, 20.0, 0.0)
    assert table.grip_location == (32.0, 20.0, 0.0)
    assert table.description == ""
    assert [column.source_dxftype for column in table.columns] == [
        "ATTDEF",
        "ATTDEF",
        "ATTDEF",
        "BLOCKVISIBILITYPARAMETER",
    ]
    assert [column.name for column in table.columns] == [
        "PARAM_1",
        "PARAM_2",
        "PARAM_3",
        "VisibilityState",
    ]
    assert [row.values for row in table.rows] == [
        ("VAL 1", "VAL 1", "VAL 1", "STATE_A"),
        ("VAL 2", "VAL 1", "VAL 3", "STATE_B"),
        ("VAL 3", "VAL 2", "VAL 1", "STATE_C"),
    ]


def test_dynamic_block_property_column_and_row_helpers():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)

    columns = get_dynamic_block_property_columns(insert)
    rows = get_dynamic_block_property_rows(insert)

    assert len(columns) == 4
    assert isinstance(columns[0], DynamicBlockPropertyColumn)
    assert len(rows) == 3
    assert isinstance(rows[0], DynamicBlockPropertyRow)
    assert rows[1].index == 1


def test_dynamic_block_properties_writer_adds_attdef_support_metadata():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = doc.blocks.get("DYN_PROP_PROBE_BASE")

    assert insert is not None
    assert base is not None

    attdefs = [entity for entity in base if entity.dxftype() == "ATTDEF"]
    assert len(attdefs) == 3
    for attdef in attdefs:
        assert attdef.has_extension_dict is True
        assert "AcadAnnotative" in attdef.xdata.data
        context_root = attdef.get_extension_dict().dictionary.get("AcDbContextDataManager")
        assert context_root is not None


def test_dynamic_block_properties_writer_clones_attdefs_into_active_reference():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    table = get_dynamic_block_properties_table(insert)
    ref = get_dynamic_block_reference(insert)

    assert table is not None
    assert ref is not None
    attdefs = [entity for entity in ref if entity.dxftype() == "ATTDEF"]
    assert [attdef.dxf.tag for attdef in attdefs] == ["PARAM_1", "PARAM_2", "PARAM_3"]
    assert [attdef.dxf.get("invisible", 0) for attdef in attdefs] == [0, 0, 0]
    assert [attdef.get_reactors() for attdef in attdefs] == [[table.handle], [table.handle], [table.handle]]


def test_dynamic_block_reference_preserves_invisible_property_attdefs():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    for entity in base:
        if entity.dxftype() == "ATTDEF":
            entity.dxf.invisible = 1

    anon = doc.blocks.new_anonymous_block(type_char="U")
    set_dynamic_block_reference(anon, base)

    attdefs = [entity for entity in anon if entity.dxftype() == "ATTDEF"]
    assert [attdef.dxf.get("invisible", 0) for attdef in attdefs] == [1, 1, 1]


def test_dynamic_block_reference_preserves_missing_context_record_for_preexisting_attdefs():
    doc = dxfpy.new("R2018")
    base = doc.blocks.new("DYN_REF_ATTDEF_CONTEXT")
    base.add_line((0, 0), (1, 0))
    base_attdef = base.add_attdef("X", insert=(0, 0), text="Block Table1", dxfattribs={"flags": 1, "invisible": 1})
    setup_dynamic_block_property_attdef_support(
        base_attdef,
        10,
        annotative=True,
        create_context_record=False,
    )

    anon = doc.blocks.new_anonymous_block(type_char="U")
    anon.add_line((0, 0), (1, 0))
    anon_attdef = anon.add_attdef("X", insert=(0, 0), text="############", dxfattribs={"flags": 1, "invisible": 1})
    setup_dynamic_block_property_attdef_support(
        anon_attdef,
        10,
        annotative=True,
        create_context_record=False,
    )

    set_dynamic_block_reference(anon, base, clone_property_attdefs=False, normalize_entities=True)

    attdef = next(entity for entity in anon if entity.dxftype() == "ATTDEF")
    rep_tags = list(attdef.get_xdata("AcDbBlockRepETag"))
    annotative_tags = list(attdef.get_xdata("AcadAnnotative"))
    assert attdef.has_extension_dict is True
    assert rep_tags == [(1070, 1), (1071, 10), (1005, "0")]
    assert annotative_tags == [
        (1000, "AnnotativeData"),
        (1002, "{"),
        (1070, 1),
        (1070, 0),
        (1002, "}"),
    ]
    mgr = attdef.get_extension_dict().dictionary.get("AcDbContextDataManager")
    assert mgr is not None
    scales = mgr.get("ACDB_ANNOTATIONSCALES")
    assert scales is not None
    assert list(scales.keys()) == []


def test_dynamic_block_properties_writer_marks_property_graph_links():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)
    table = get_dynamic_block_properties_table(insert)

    assert base is not None
    assert table is not None
    assert base.block_record.has_xdata("AcDbDynamicBlockTrueName2") is True
    assert base.block_record.has_xdata("AcDbDynamicBlockTrueName") is False

    graph = next(obj for obj in doc.objects if obj.dxftype() == "ACAD_EVALUATION_GRAPH")
    visibility = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKVISIBILITYPARAMETER")

    assert graph.has_xdata("AcadBPTGraphNodeId") is True
    assert visibility.get_reactors() == [table.handle]


def test_dynamic_block_properties_writer_hides_attdefs_for_nondefault_state():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = doc.blocks.get("DYN_PROP_PROBE_BASE")
    ref = get_dynamic_block_reference(insert)

    assert base is not None
    assert ref is not None
    set_dynamic_block_visibility_state(insert, base, state="STATE_B")

    attdefs = [entity for entity in ref if entity.dxftype() == "ATTDEF"]
    assert [attdef.dxf.get("invisible", 0) for attdef in attdefs] == [1, 1, 1]


def test_dynamic_block_properties_writer_root_assocnetwork_is_direct():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)

    assert insert is not None
    root = doc.rootdict.get("ACAD_ASSOCNETWORK")
    assert root is not None
    assert root.dxftype() == "DICTIONARY"
    assoc = root.get("ACAD_ASSOCNETWORK")
    assert assoc is not None
    assert assoc.dxftype() == "ACDBASSOCNETWORK"


def test_dynamic_block_properties_writer_sets_table_reactors_on_hidden_carriers():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    table = get_dynamic_block_properties_table(insert)
    reps = [rep for rep in get_dynamic_block_property_representations(insert) if not rep.is_active]

    assert table is not None
    assert reps
    hidden_block = doc.blocks.get(reps[0].block_name)
    assert hidden_block is not None
    for attdef in hidden_block:
        if attdef.dxftype() == "ATTDEF":
            assert attdef.get_reactors() == [table.handle]


def test_dynamic_block_property_assoc_networks_are_empty_for_minimal_authored_fixture():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)

    networks = get_dynamic_block_property_assoc_networks(insert)

    assert len(networks) == 3
    assert [(var.name, var.value) for var in networks[0].variables] == [
        ("user1", "1"),
        ("user2", "1"),
    ]


def test_dynamic_block_property_representations_include_active_blocks():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)

    reps = get_dynamic_block_property_representations(insert)

    assert len(reps) == 7
    rep = next(r for r in reps if r.is_active)
    assert rep.is_active is True
    assert rep.block_name.startswith("*U")
    assert [carrier.tag for carrier in rep.carriers] == ["PARAM_1", "PARAM_2", "PARAM_3"]
    assert [carrier.invisible for carrier in rep.carriers] == [0, 0, 0]


def test_dynamic_block_property_representation_families_group_by_signature():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)

    families = get_dynamic_block_property_representation_families(insert)

    assert len(families) == 5
    counts = {
        (
            family.carrier_count,
            family.carrier_texts,
            family.carrier_visibility,
            family.assoc_signature,
        ): len(family.block_names)
        for family in families
    }
    assert counts[(2, ("", ""), (0, 0), (("user1", "1"), ("user2", "1")))] == 1
    assert counts[(2, ("", ""), (1, 1), (("user1", "2"), ("user2", "1")))] == 1
    assert counts[(2, ("", ""), (1, 1), (("user1", "3"), ("user2", "2")))] == 1
    assert counts[(3, ("Block Table1", "Block Table1", "Block Table1"), (0, 0, 0), ())] == 2
    assert counts[(3, ("Block Table1", "Block Table1", "Block Table1"), (1, 1, 1), ())] == 2


def test_dynamic_block_properties_editor_support_rerun_replaces_hidden_support():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)
    table = get_dynamic_block_properties_table(base)

    assert base is not None
    assert table is not None
    reps_before = get_dynamic_block_property_representations(base)
    assoc_before = get_dynamic_block_property_assoc_networks(base)
    anon_before = sum(1 for block in doc.blocks if block.name.startswith("*U"))

    set_dynamic_block_properties_editor_support(base, table)

    reps_after = get_dynamic_block_property_representations(base)
    assoc_after = get_dynamic_block_property_assoc_networks(base)
    anon_after = sum(1 for block in doc.blocks if block.name.startswith("*U"))

    assert len(reps_after) == len(reps_before)
    assert len(assoc_after) == len(assoc_before)
    assert anon_after == anon_before


def test_get_dynamic_block_linear_parameters_and_grips_reads_linear_stack():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    linear_entity, end_grip_entity, base_grip_entity, _ = attach_linear_stretch_probe(base)

    parameters = get_dynamic_block_linear_parameters(insert)
    grips = get_dynamic_block_linear_grips(base)

    assert len(parameters) == 1
    assert isinstance(parameters[0], DynamicBlockLinearParameter)
    assert parameters[0].handle == linear_entity.dxf.handle
    assert parameters[0].label == "Linear"
    assert parameters[0].parameter_name == "Distance1"
    assert parameters[0].base_point == (0.0, 0.0, 0.0)
    assert parameters[0].end_point == (1.0, 0.0, 0.0)
    assert parameters[0].distance == 1.0
    assert parameters[0].base_grip_handle == base_grip_entity.dxf.handle
    assert parameters[0].end_grip_handle == end_grip_entity.dxf.handle
    assert parameters[0].base_grip_label == "Base Grip"
    assert parameters[0].end_grip_label == "End Grip"

    assert len(grips) == 2
    assert all(isinstance(grip, DynamicBlockLinearGrip) for grip in grips)
    grip_by_label = {grip.label: grip for grip in grips}
    assert grip_by_label["Base Grip"].offset == (-1.0, 0.0, 0.0)
    assert grip_by_label["End Grip"].offset == (1.0, 0.0, 0.0)
    assert grip_by_label["End Grip"].location == (1.0, 0.0, 0.0)


def test_get_dynamic_block_stretch_actions_reads_targets_and_selection_window():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    _, _, _, stretch_entity = attach_linear_stretch_probe(base)

    actions = get_dynamic_block_stretch_actions(insert)

    assert len(actions) == 1
    assert isinstance(actions[0], DynamicBlockStretchAction)
    assert actions[0].handle == stretch_entity.dxf.handle
    assert actions[0].label == "Stretch1"
    assert actions[0].action_location == (1.0, -0.5, 0.0)
    assert actions[0].x_expr_id == 45
    assert actions[0].x_name == "EndXDelta"
    assert actions[0].y_expr_id == 45
    assert actions[0].y_name == "EndYDelta"
    assert actions[0].selection_window == ((2.0, 1.0, 0.0), (0.5, -0.5, 0.0))
    assert len(actions[0].dependency_handles) == 6
    assert [target.mode for target in actions[0].targets] == [2, 1, 1, 1]
    assert actions[0].targets[0].components == (1, 2)
    assert actions[0].targets[1].components == (0,)


def test_get_dynamic_block_lookup_parameters_and_grips_reads_lookup_stack():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    attach_linear_stretch_probe(base)
    lookup_parameter_entity, lookup_grip_entity, _, _, _, _ = attach_lookup_probe(base)

    linear = get_dynamic_block_linear_parameters(base)
    parameters = get_dynamic_block_lookup_parameters(insert)
    grips = get_dynamic_block_lookup_grips(base)

    assert len(linear) == 1
    assert linear[0].value_set_type == 8
    assert linear[0].value_count == 5
    assert linear[0].allowed_values == (10.0, 20.0, 32.0, 40.0, 50.0)

    assert len(parameters) == 1
    assert isinstance(parameters[0], DynamicBlockLookupParameter)
    assert parameters[0].handle == lookup_parameter_entity.dxf.handle
    assert parameters[0].label == "Lookup"
    assert parameters[0].parameter_name == "Lookup1"
    assert parameters[0].location == (19.28, 23.15, 0.0)
    assert parameters[0].expr_id == 71
    assert parameters[0].action_expr_id == 75
    assert parameters[0].grip_handle == lookup_grip_entity.dxf.handle
    assert parameters[0].grip_label == "Grip"

    assert len(grips) == 1
    assert isinstance(grips[0], DynamicBlockLookupGrip)
    assert grips[0].handle == lookup_grip_entity.dxf.handle
    assert grips[0].label == "Grip"
    assert grips[0].parameter_expr_id == 71
    assert grips[0].x_expr_id == 73
    assert grips[0].y_expr_id == 74


def test_get_dynamic_block_lookup_actions_reads_entries_and_bindings():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    attach_linear_stretch_probe(base)
    _, _, _, _, internal_action, public_action = attach_lookup_probe(base)

    actions = get_dynamic_block_lookup_actions(insert)

    assert len(actions) == 2
    assert all(isinstance(action, DynamicBlockLookupAction) for action in actions)
    action_by_handle = {action.handle: action for action in actions}

    internal = action_by_handle[internal_action.dxf.handle]
    assert internal.label == "Lookup1"
    assert internal.expr_id == 57
    assert internal.row_count == 5
    assert internal.column_count == 1
    assert internal.entries == (("0",), ("8",), ("7",), ("6",), ("5",))
    assert len(internal.bindings) == 1
    assert isinstance(internal.bindings[0], DynamicBlockLookupActionBinding)
    assert internal.bindings[0].expr_id == 45
    assert internal.bindings[0].value_code == 40
    assert internal.bindings[0].value_type == 2
    assert internal.bindings[0].property_name == "UpdatedDistance"
    assert internal.enabled == 1

    public = action_by_handle[public_action.dxf.handle]
    assert public.label == "Lookup3"
    assert public.expr_id == 75
    assert public.row_count == 5
    assert public.column_count == 2
    assert public.entries == (
        ("10", "len 1"),
        ("20", "len 2"),
        ("32", "len 3"),
        ("40", "len 4"),
        ("50", "len 5"),
    )
    assert len(public.bindings) == 2
    assert public.bindings[0].expr_id == 45
    assert public.bindings[0].property_name == "UpdatedDistance"
    assert public.bindings[1].expr_id == 71
    assert public.bindings[1].value_code == 1
    assert public.bindings[1].value_type == 0
    assert public.bindings[1].flag282 == 1
    assert public.bindings[1].flag281 == 1
    assert public.bindings[1].property_name == "lookupString"


def test_set_dynamic_block_linear_parameter_patches_graph_and_visibility():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    attdef2 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_2")
    attdef3 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_3")
    table = get_dynamic_block_properties_table(base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    parameter = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        base_grip_label="Base Grip",
        end_grip_label="End Grip",
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch1",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(
            grip.dxf.handle,
            table.handle,
            attdef3.dxf.handle,
            attdef2.dxf.handle,
            attdef1.dxf.handle,
            stretch_entity.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(stretch_entity.dxf.handle, 2, (1, 2)),
            DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef2.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef3.dxf.handle, 1, (0,)),
        ),
    )

    created = set_dynamic_block_linear_parameter(base, parameter, action)
    linear = get_dynamic_block_linear_parameters(base)
    actions = get_dynamic_block_stretch_actions(base)
    grips = get_dynamic_block_linear_grips(base)
    visibility = get_dynamic_block_visibility_parameter(base)

    assert created.handle
    assert len(linear) == 1
    assert linear[0].handle == created.handle
    assert linear[0].base_grip_label == "Base Grip"
    assert linear[0].end_grip_label == "End Grip"
    assert len(actions) == 1
    assert actions[0].label == "Stretch1"
    assert len(grips) == 2
    assert visibility is not None
    assert tuple(len(state.entity_handles) for state in visibility.states) == (3, 3, 3)
    assert len(visibility.all_entity_handles) == 6
    graph = base.block_record.get_extension_dict().dictionary.get("ACAD_ENHANCEDBLOCK")
    assert graph is not None
    assert list(graph.get_xdata("AcadBPTGraphNodeId")) == [(1071, 32)]
    table_entity = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLE")
    table_sub = list(table_entity.xtags.get_subclass("AcDbBlockPropertiesTable"))
    chunks = [table_sub[5 + i * 15 : 5 + (i + 1) * 15] for i in range(4)]
    assert chunks[-1][0].value == visibility.handle
    assert chunks[-1][5].value == 6

    set_dynamic_block_visibility_state(insert, base, state="STATE_B")
    ref = get_dynamic_block_reference(insert)

    assert ref is not None
    assert [entity.dxf.get("invisible", 0) for entity in ref if entity.dxftype() == "ATTDEF"] == [0, 0, 0]


def test_set_dynamic_block_properties_table_preserves_existing_linear_parameter():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    attdef2 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_2")
    attdef3 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_3")
    table = get_dynamic_block_properties_table(base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        base_grip_label="Base Grip",
        end_grip_label="End Grip",
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch1",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(
            grip.dxf.handle,
            table.handle,
            attdef3.dxf.handle,
            attdef2.dxf.handle,
            attdef1.dxf.handle,
            stretch_entity.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(stretch_entity.dxf.handle, 2, (1, 2)),
            DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef2.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef3.dxf.handle, 1, (0,)),
        ),
    )
    set_dynamic_block_linear_parameter(base, linear, action)

    rewritten = DynamicBlockPropertiesTable(
        handle="",
        label=table.label,
        table_name=table.table_name,
        description=table.description,
        location=table.location,
        grip_location=table.grip_location,
        columns=table.columns,
        rows=table.rows,
    )
    set_dynamic_block_properties_table(base, rewritten)

    new_linear = get_dynamic_block_linear_parameters(base)
    new_actions = get_dynamic_block_stretch_actions(base)

    assert len(new_linear) == 1
    assert new_linear[0].parameter_name == "Distance1"
    assert new_linear[0].base_grip_label == "Base Grip"
    assert len(new_actions) == 1
    assert new_actions[0].label == "Stretch1"


def test_set_dynamic_block_linear_parameter_rejects_second_linear_parameter():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    parameter = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        base_grip_label="Base Grip",
        end_grip_label="End Grip",
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch1",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(),
        targets=(),
    )
    set_dynamic_block_linear_parameter(base, parameter, action)

    with pytest.raises(dxfpy.DXFValueError):
        set_dynamic_block_linear_parameter(base, parameter, action)


def test_set_dynamic_block_base_point_parameter_roundtrip_helper():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    created = set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    parsed = get_dynamic_block_base_point_parameter(base)

    assert created.handle
    assert parsed is not None
    assert parsed.handle == created.handle
    assert parsed.label == "Base Point"
    assert parsed.base_point == (0.0, 0.0, 0.0)


def test_set_dynamic_block_base_point_parameter_patches_visibility_only_graph():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_insert(doc, "STATE_A")
    base = get_dynamic_block_definition(insert)

    assert base is not None
    created = set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    graph = base.block_record.get_extension_dict().dictionary.get("ACAD_ENHANCEDBLOCK")
    visibility = get_dynamic_block_visibility_parameter(base)

    assert graph is not None
    assert visibility is not None
    owned = [obj for obj in doc.objects if obj.dxf.owner == graph.dxf.handle]
    grip = next(obj for obj in owned if obj.dxftype() == "BLOCKVISIBILITYGRIP")
    x_comp = next(
        obj
        for obj in owned
        if obj.dxftype() == "BLOCKGRIPLOCATIONCOMPONENT"
        and obj.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedX"
    )
    y_comp = next(
        obj
        for obj in owned
        if obj.dxftype() == "BLOCKGRIPLOCATIONCOMPONENT"
        and obj.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedY"
    )
    eval_graph = list(graph.xtags.get_subclass("AcDbEvalGraph"))

    assert (96, 5) in [(tag.code, tag.value) for tag in eval_graph]
    assert [tag.value for tag in eval_graph if tag.code == 360] == [
        created.handle,
        visibility.handle,
        grip.dxf.handle,
        x_comp.dxf.handle,
        y_comp.dxf.handle,
    ]
    assert visibility.handle == next(obj for obj in owned if obj.dxftype() == "BLOCKVISIBILITYPARAMETER").dxf.handle
    assert grip.xtags.get_subclass("AcDbEvalExpr").get_first_value(90, -1) == 3
    assert grip.xtags.get_subclass("AcDbBlockGrip").get_first_value(91, -1) == 4
    assert grip.xtags.get_subclass("AcDbBlockGrip").get_first_value(92, -1) == 5


def test_set_dynamic_block_linear_parameter_uses_basepoint_branch_when_present():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    attdef2 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_2")
    attdef3 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_3")
    table = get_dynamic_block_properties_table(base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        end_grip_label="End Grip",
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(
            grip.dxf.handle,
            table.handle,
            attdef3.dxf.handle,
            attdef2.dxf.handle,
            attdef1.dxf.handle,
            stretch_entity.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(stretch_entity.dxf.handle, 2, (1, 2)),
            DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef2.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef3.dxf.handle, 1, (0,)),
        ),
    )
    created = set_dynamic_block_linear_parameter(base, linear, action)
    parsed = get_dynamic_block_linear_parameters(base)
    graph = base.block_record.get_extension_dict().dictionary.get("ACAD_ENHANCEDBLOCK")
    table_entity = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLE")

    assert created.handle
    assert len(parsed) == 1
    assert parsed[0].handle == created.handle
    assert parsed[0].base_grip_handle == ""
    assert parsed[0].end_grip_handle
    assert graph is not None
    assert list(graph.get_xdata("AcadBPTGraphNodeId")) == [(1071, 6)]
    stretch_entity_obj = next(
        obj
        for obj in doc.objects
        if obj.dxftype() == "BLOCKSTRETCHACTION" and obj.dxf.owner == graph.dxf.handle
    )
    action_tags = [
        (tag.code, tag.value)
        for tag in stretch_entity_obj.xtags.get_subclass("AcDbBlockAction")
    ]
    stretch_tags = [
        (tag.code, tag.value)
        for tag in stretch_entity_obj.xtags.get_subclass("AcDbBlockStretchAction")
    ]
    assert action_tags[1:4] == [(70, 1), (91, 5), (71, 6)]
    assert action_tags[4:6] == [(330, created.end_grip_handle), (330, next(obj for obj in doc.objects if obj.dxftype() == "BLOCKBASEPOINTPARAMETER").dxf.handle)]
    assert stretch_tags[-7:] == [(75, 1), (95, 5), (76, 1), (94, 0), (140, 1.0), (141, 0.0), (280, 0)]
    table_sub = list(table_entity.xtags.get_subclass("AcDbBlockPropertiesTable"))
    chunks = [table_sub[5 + i * 15 : 5 + (i + 1) * 15] for i in range(4)]
    assert chunks[-1][5].value == 1
    visibility_entity = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKVISIBILITYPARAMETER")
    tags = list(visibility_entity.xtags.get_subclass("AcDbBlockVisibilityParameter"))
    ref_chunks = []
    index = 0
    while index < len(tags):
        if tags[index].code != 303:
            index += 1
            continue
        index += 1
        if index < len(tags) and tags[index].code == 94:
            index += 1
        while index < len(tags) and tags[index].code == 332:
            index += 1
        if index < len(tags) and tags[index].code == 95:
            count = int(tags[index].value)
            index += 1
        else:
            count = 0
        refs = []
        while index < len(tags) and tags[index].code == 333:
            refs.append(str(tags[index].value))
            index += 1
        ref_chunks.append((count, refs))
    assert all(count == 5 for count, _refs in ref_chunks)
    assert all(refs[:2] == [table_entity.dxf.handle, grip.dxf.handle] for _count, refs in ref_chunks)


def test_basepoint_linear_branch_normalizes_simple_line_targets_like_working_file():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    line1 = entities[0]
    line2 = entities[1]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")

    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(12.0, 0.0, 0.0),
        distance=12.0,
        expr_id=0,
        end_grip_label="End Grip",
        end_grip_location=(12.0, 24.0, 0.0),
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch1",
        action_location=(12.0, -6.0, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((26.0, 20.0, 0.0), (8.0, -6.0, 0.0)),
        dependency_handles=(attdef1.dxf.handle, line1.dxf.handle, line2.dxf.handle),
        targets=(
            DynamicBlockStretchActionTarget(line1.dxf.handle, 1, (1,)),
            DynamicBlockStretchActionTarget(line2.dxf.handle, 1, (1,)),
            DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
        ),
    )
    set_dynamic_block_linear_parameter(base, linear, action)

    actions = get_dynamic_block_stretch_actions(base)
    graph = base.block_record.get_extension_dict().dictionary.get("ACAD_ENHANCEDBLOCK")

    assert graph is not None
    assert len(actions) == 1
    assert len(actions[0].dependency_handles) == 5
    assert [(target.mode, target.components) for target in actions[0].targets] == [
        (1, (1,)),
        (1, (1,)),
    ]
    stretch_entity_obj = next(
        obj
        for obj in doc.objects
        if obj.dxftype() == "BLOCKSTRETCHACTION" and obj.dxf.owner == graph.dxf.handle
    )
    stretch_tags = [
        (tag.code, tag.value)
        for tag in stretch_entity_obj.xtags.get_subclass("AcDbBlockStretchAction")
    ]
    assert stretch_tags[-4:] == [(75, 0), (140, 1.0), (141, 0.0), (280, 0)]
    assert sum(1 for code, _value in stretch_tags if code == 331) == 2


def test_set_dynamic_block_linear_parameter_preserves_explicit_grip_location():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(10.0, 0.0, 0.0),
        distance=10.0,
        expr_id=0,
        end_grip_label="End Grip",
        end_grip_location=(2.0, 3.0, 0.0),
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(),
        targets=(),
    )

    created = set_dynamic_block_linear_parameter(base, linear, action)
    parsed = get_dynamic_block_linear_parameters(base)
    grips = get_dynamic_block_linear_grips(base)

    assert created.handle
    assert len(parsed) == 1
    assert parsed[0].end_point == (10.0, 0.0, 0.0)
    assert parsed[0].end_grip_location == (2.0, 3.0, 0.0)
    assert any(grip.label == "End Grip" and grip.location == (2.0, 3.0, 0.0) for grip in grips)


def test_dynamic_block_visibility_state_preserves_invisible_property_attdefs_for_linear_blocks():
    doc = dxfpy.new("R2018")
    msp = doc.modelspace()
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    attdef2 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_2")
    attdef3 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_3")
    table = get_dynamic_block_properties_table(base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    for attdef in (attdef1, attdef2, attdef3):
        attdef.dxf.invisible = 1
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        end_grip_label="End Grip",
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(
            grip.dxf.handle,
            table.handle,
            attdef3.dxf.handle,
            attdef2.dxf.handle,
            attdef1.dxf.handle,
            stretch_entity.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(stretch_entity.dxf.handle, 2, (1, 2)),
            DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef2.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef3.dxf.handle, 1, (0,)),
        ),
    )
    set_dynamic_block_linear_parameter(base, linear, action)

    anon = doc.blocks.new_anonymous_block(type_char="U")
    _clone_non_attdef_entities(base, anon)
    for attdef in (attdef1, attdef2, attdef3):
        _clone_property_attdef(attdef, anon, text=attdef.dxf.text, invisible=True)
    set_dynamic_block_reference(anon, base, clone_property_attdefs=False)
    dyn_insert = msp.add_blockref(anon.name, (0, 0))
    set_dynamic_block_visibility_state(dyn_insert, base, state="STATE_A")

    cloned = [entity for entity in anon if entity.dxftype() == "ATTDEF"]
    assert [attdef.dxf.get("invisible", 0) for attdef in cloned] == [1, 1, 1]


def test_set_dynamic_block_linear_parameter_keeps_property_attdefs_out_of_visibility_states():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    stretch_entity = entities[0]
    attdefs = [entity for entity in entities if entity.dxftype() == "ATTDEF"]
    attdef_handles = {entity.dxf.handle for entity in attdefs}
    table = get_dynamic_block_properties_table(base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0.0, 0.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        end_grip_label="End Grip",
    )
    action = DynamicBlockStretchAction(
        handle="",
        label="Stretch",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(
            grip.dxf.handle,
            table.handle,
            *[attdef.dxf.handle for attdef in reversed(attdefs)],
            stretch_entity.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(stretch_entity.dxf.handle, 2, (1, 2)),
            *[DynamicBlockStretchActionTarget(attdef.dxf.handle, 1, (0,)) for attdef in attdefs],
        ),
    )
    set_dynamic_block_linear_parameter(base, linear, action)

    visibility = get_dynamic_block_visibility_parameter(base)

    assert visibility is not None
    assert attdef_handles.issubset(set(visibility.all_entity_handles))
    assert all(attdef_handles.isdisjoint(set(state.entity_handles)) for state in visibility.states)


def test_set_dynamic_block_lookup_parameter_patches_graph_and_linear_values():
    doc = dxfpy.new("R2018")
    insert = make_dynamic_properties_insert(doc)
    base = get_dynamic_block_definition(insert)

    assert base is not None
    entities = list(base)
    stretch_entity = entities[0]
    attdef1 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    attdef2 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_2")
    attdef3 = next(entity for entity in entities if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_3")
    table = get_dynamic_block_properties_table(base)
    grip = next(obj for obj in doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")

    assert table is not None
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(1.0, 0.0, 0.0),
        distance=1.0,
        expr_id=0,
        base_grip_label="Base Grip",
        end_grip_label="End Grip",
    )
    stretch = DynamicBlockStretchAction(
        handle="",
        label="Stretch1",
        action_location=(1.0, -0.5, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((2.0, 1.0, 0.0), (0.5, -0.5, 0.0)),
        dependency_handles=(
            grip.dxf.handle,
            table.handle,
            attdef3.dxf.handle,
            attdef2.dxf.handle,
            attdef1.dxf.handle,
            stretch_entity.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(stretch_entity.dxf.handle, 2, (1, 2)),
            DynamicBlockStretchActionTarget(attdef1.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef2.dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(attdef3.dxf.handle, 1, (0,)),
        ),
    )
    set_dynamic_block_linear_parameter(base, linear, stretch)

    lookup = DynamicBlockLookupParameter(
        handle="",
        label="Lookup",
        parameter_name="Lookup1",
        description="",
        location=(19.28, 23.15, 0.0),
        expr_id=0,
        action_expr_id=75,
        grip_label="Grip",
    )
    helper_action = DynamicBlockLookupAction(
        handle="",
        label="Lookup1",
        action_location=(16.5, 19.5, 0.0),
        expr_id=57,
        row_count=5,
        column_count=1,
        entries=(("0",), ("8",), ("7",), ("6",), ("5",)),
        bindings=(
            DynamicBlockLookupActionBinding(
                group_label="",
                expr_id=45,
                value_code=40,
                value_type=2,
                flag282=0,
                display_name="Custom",
                flag281=0,
                property_name="UpdatedDistance",
            ),
        ),
        enabled=1,
    )
    public_action = DynamicBlockLookupAction(
        handle="",
        label="Lookup3",
        action_location=(20.01, 22.42, 0.0),
        expr_id=75,
        row_count=5,
        column_count=2,
        entries=(("10", "len 1"), ("20", "len 2"), ("32", "len 3"), ("40", "len 4"), ("50", "len 5")),
        bindings=(
            DynamicBlockLookupActionBinding(
                group_label="",
                expr_id=45,
                value_code=40,
                value_type=2,
                flag282=0,
                display_name="Custom",
                flag281=0,
                property_name="UpdatedDistance",
            ),
            DynamicBlockLookupActionBinding(
                group_label="",
                expr_id=71,
                value_code=1,
                value_type=0,
                flag282=1,
                display_name="Custom",
                flag281=1,
                property_name="lookupString",
            ),
        ),
        enabled=1,
    )

    created = set_dynamic_block_lookup_parameter(base, lookup, (helper_action, public_action))
    linear_after = get_dynamic_block_linear_parameters(base)
    lookup_parameters = get_dynamic_block_lookup_parameters(base)
    lookup_grips = get_dynamic_block_lookup_grips(base)
    lookup_actions = get_dynamic_block_lookup_actions(base)

    assert created.handle
    assert len(linear_after) == 1
    assert linear_after[0].value_set_type == 8
    assert linear_after[0].value_count == 5
    assert linear_after[0].allowed_values == (10.0, 20.0, 32.0, 40.0, 50.0)
    assert len(lookup_parameters) == 1
    assert lookup_parameters[0].handle == created.handle
    assert lookup_parameters[0].parameter_name == "Lookup1"
    assert len(lookup_grips) == 1
    assert lookup_grips[0].parameter_expr_id == 71
    assert len(lookup_actions) == 2
    assert {action.label for action in lookup_actions} == {"Lookup1", "Lookup3"}


def test_restore_raw_entity_export_replays_insert_attached_attrib_context_data():
    source_doc = dxfpy.new("R2010")
    source_block = source_doc.blocks.new("SRC")
    source_insert = source_block.add_blockref("TARGET", (1, 2))
    source_attrib = source_insert.add_attrib("TAG", "TEXT", insert=(3, 4))
    mgr = source_attrib.new_extension_dict().dictionary.add_new_dict(
        "AcDbContextDataManager"
    )
    mgr.add_new_dict("ACDB_ANNOTATIONSCALES")
    snapshot = snapshot_raw_entity_export(source_insert)

    assert len(snapshot.attached_entity_snapshots) == 2

    target_doc = dxfpy.new("R2010")
    target_block = target_doc.blocks.new("SRC")
    target_insert = target_block.add_blockref("TARGET", (1, 2))
    target_insert.add_attrib("TAG", "TEXT", insert=(3, 4))

    restore_raw_entity_export(target_insert, snapshot)

    target_attrib = target_insert.attribs[0]
    assert target_attrib.has_extension_dict is True
    target_mgr = target_attrib.get_extension_dict().dictionary.get("AcDbContextDataManager")
    assert target_mgr is not None
    assert target_mgr.get("ACDB_ANNOTATIONSCALES") is not None
    assert getattr(target_attrib, RAW_TAGS_OVERRIDE_ATTRIBUTE, "").startswith(
        "  0\nATTRIB\n"
    )
    assert getattr(target_insert.seqend, RAW_TAGS_OVERRIDE_ATTRIBUTE, "").startswith(
        "  0\nSEQEND\n"
    )


def test_restore_raw_dynamic_block_layout_replays_insert_attached_attrib_context_data():
    source_doc = dxfpy.new("R2010")
    source_block = source_doc.blocks.new("SRC_LAYOUT")
    source_insert = source_block.add_blockref("TARGET", (1, 2))
    source_attrib = source_insert.add_attrib("TAG", "TEXT", insert=(3, 4))
    mgr = source_attrib.new_extension_dict().dictionary.add_new_dict(
        "AcDbContextDataManager"
    )
    mgr.add_new_dict("ACDB_ANNOTATIONSCALES")
    snapshot = snapshot_raw_dynamic_block_layout(source_block)

    target_doc = dxfpy.new("R2010")
    target_block = target_doc.blocks.new("SRC_LAYOUT")

    restore_raw_dynamic_block_layout(target_block, snapshot)

    restored_insert = list(target_block)[0]
    restored_attrib = restored_insert.attribs[0]
    assert restored_attrib.has_extension_dict is True
    restored_mgr = restored_attrib.get_extension_dict().dictionary.get(
        "AcDbContextDataManager"
    )
    assert restored_mgr is not None
    assert restored_mgr.get("ACDB_ANNOTATIONSCALES") is not None
    assert getattr(restored_attrib, RAW_TAGS_OVERRIDE_ATTRIBUTE, "").startswith(
        "  0\nATTRIB\n"
    )
