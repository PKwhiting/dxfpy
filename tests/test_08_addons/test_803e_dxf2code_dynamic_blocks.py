# Copyright (c) 2019 Manfred Moitzi
# License: MIT License
from io import StringIO
from pathlib import Path
from collections import Counter

import pytest
import ezdxf
from ezdxf.entities.dxfobj import Field
from ezdxf.lldxf.extendedtags import ExtendedTags
from ezdxf.lldxf.tagwriter import TagWriter
from ezdxf.addons.dxf2code import (
    document_to_code_file,
    entities_to_code,
    block_to_code,
)
from ezdxf._fidelity_compare import compare_replay_documents
from ezdxf.dynblkhelper import (
    DynamicBlockBasePointParameter,
    DynamicBlockLinearParameter,
    DynamicBlockLookupAction,
    DynamicBlockLookupActionBinding,
    DynamicBlockLookupParameter,
    DynamicBlockPropertiesTable,
    DynamicBlockPropertyColumn,
    DynamicBlockPropertyRow,
    DynamicBlockStretchAction,
    DynamicBlockStretchActionTarget,
    DynamicBlockVisibilityParameter,
    DynamicBlockVisibilityState,
    get_dynamic_block_base_point_parameter,
    get_dynamic_block_definition,
    get_dynamic_block_entity_rep_index_path,
    get_dynamic_block_linear_parameters,
    get_dynamic_block_lookup_actions,
    get_dynamic_block_lookup_parameters,
    get_dynamic_block_properties_table,
    get_dynamic_block_reference,
    get_dynamic_block_stretch_actions,
    get_dynamic_block_visibility_entities,
    get_dynamic_block_visibility_state,
    get_dynamic_block_visibility_states,
    restore_raw_entity_export,
    set_dynamic_block_base_point_parameter,
    set_dynamic_block_linear_parameter,
    set_dynamic_block_lookup_parameter,
    set_dynamic_block_properties_editor_support,
    set_dynamic_block_properties_table,
    set_dynamic_block_reference,
    set_dynamic_block_visibility_parameter,
    set_dynamic_block_visibility_state,
    snapshot_raw_entity_export,
    snapshot_raw_extension_subtree,
)


import ezdxf.entities
from ezdxf.lldxf.types import dxftag
from ezdxf.lldxf.tags import Tags  # required by exec() or eval()
from ezdxf.entities.ltype import LinetypePattern  # required by exec() or eval()
from ezdxf.math import Vec2, Vec3
from tests.test_08_addons.dxf2code_support import (
    block_dependencies as _block_dependencies,
    execute_code_in_namespace,
    replay_doc_to_new_doc,
    sort_blocks as _sort_blocks,
)

doc = ezdxf.new("R2010")
msp = doc.modelspace()
NESTED_WORKING_ORACLE = Path(__file__).parent / "autocad_nested_working_minimal_v1_edited.dxf"
NESTED_RICHER_CHILD_ORACLE = Path(__file__).parent / "autocad_nested_richer_child_gen2_v1.dxf"
NESTED_TWO_CHILDREN_ORACLE = Path(__file__).parent / "autocad_nested_two_children_candidate_gen2.dxf"
NESTED_TWO_CHILDREN_MIXED_ORACLE = Path(__file__).parent / "autocad_nested_two_children_mixed_states_gen2_v2.dxf"
NESTED_THREE_LEVEL_MIXED_ORACLE = Path(__file__).parent / "autocad_nested_three_level_mixed_gen2_v3.dxf"
def translate_to_code_and_execute(entity):
    code = entities_to_code([entity], layout="msp")
    exec(code.import_str() + "\n" + str(code), globals())
    return msp[-1]


def _dynamic_block_by_public_name(doc: ezdxf.document.Drawing, public_name: str):
    for block in doc.blocks:
        block_record = block.block_record
        if block_record.has_xdata("AcDbDynamicBlockTrueName") and (
            block_record.get_xdata("AcDbDynamicBlockTrueName").get_first_value(1000, "")
            == public_name
        ):
            return block
        if block_record.has_xdata("AcDbDynamicBlockTrueName2") and (
            block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
            == public_name
        ):
            return block
    raise StopIteration(public_name)


def _add_supported_linear_visibility_geometry(block):
    common1 = block.add_line((0, 0), (24, 0))
    common2 = block.add_line((0, 18), (24, 18))
    state_a = block.add_circle((12, 9), radius=4)
    state_b = block.add_lwpolyline([(4, 3), (20, 3), (12, 15)], close=True)
    return common1, common2, state_a, state_b


def _add_supported_linear_visibility_reference_block(doc, base):
    anon = doc.blocks.new_anonymous_block(type_char="U")
    _add_supported_linear_visibility_geometry(anon)
    set_dynamic_block_reference(anon, base)
    return anon


def build_supported_linear_visibility_replay_doc() -> tuple[ezdxf.document.Drawing, str]:
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    base = source_doc.blocks.new_anonymous_block(type_char="U")
    public_name = "DYN_PROP_BASEPOINT_LINEAR_REPLAY"

    common1, common2, state_a, state_b = _add_supported_linear_visibility_geometry(base)
    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility State",
        parameter_name="Visibility1",
        location=(0.0, 30.0, 0.0),
        states=(
            DynamicBlockVisibilityState(
                "STATE_A",
                (common1.dxf.handle, common2.dxf.handle, state_a.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_B",
                (common1.dxf.handle, common2.dxf.handle, state_b.dxf.handle),
            ),
        ),
    )
    set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}", true_name=public_name)
    props = DynamicBlockPropertiesTable(
        handle="",
        label="Block Table",
        table_name="Block Table1",
        description="",
        location=(36.0, 24.0, 0.0),
        grip_location=(36.0, 24.0, 0.0),
        columns=(
            DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_1", "Block Table1"),
            DynamicBlockPropertyColumn("", "BLOCKVISIBILITYPARAMETER", "VisibilityState", "VisibilityState"),
        ),
        rows=(
            DynamicBlockPropertyRow(0, ("A", "STATE_A")),
            DynamicBlockPropertyRow(1, ("B", "STATE_B")),
        ),
    )
    props = set_dynamic_block_properties_table(base, props)
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
    attdef = next(entity for entity in base if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    linear = DynamicBlockLinearParameter(
        handle="",
        label="Linear",
        parameter_name="Distance1",
        description="",
        base_point=(0.0, 0.0, 0.0),
        end_point=(12.0, 0.0, 0.0),
        distance=12.0,
        expr_id=0,
        base_grip_label="Base Grip",
        end_grip_label="End Grip",
        base_grip_location=(0.0, 0.0, 0.0),
        end_grip_location=(12.0, 24.0, 0.0),
    )
    stretch = DynamicBlockStretchAction(
        handle="",
        label="Stretch1",
        action_location=(12.0, -6.0, 0.0),
        x_expr_id=0,
        x_name="EndXDelta",
        y_expr_id=0,
        y_name="EndYDelta",
        selection_window=((26.0, 20.0, 0.0), (8.0, -6.0, 0.0)),
        dependency_handles=(attdef.dxf.handle, common1.dxf.handle, common2.dxf.handle),
        targets=(
            DynamicBlockStretchActionTarget(common1.dxf.handle, 1, (1,)),
            DynamicBlockStretchActionTarget(common2.dxf.handle, 1, (1,)),
            DynamicBlockStretchActionTarget(attdef.dxf.handle, 1, (0,)),
        ),
    )
    set_dynamic_block_linear_parameter(base, linear, stretch)
    set_dynamic_block_properties_editor_support(base, props)

    def add_reference_block_and_insert(state: str, insert_point: tuple[float, float]):
        anon = _add_supported_linear_visibility_reference_block(source_doc, base)
        insert = source_msp.add_blockref(anon.name, insert_point)
        set_dynamic_block_visibility_state(insert, base, state=state)
        return insert

    add_reference_block_and_insert("STATE_A", (0, 0))
    add_reference_block_and_insert("STATE_B", (80, 0))
    return source_doc, public_name


def build_basepoint_only_replay_doc() -> tuple[ezdxf.document.Drawing, str]:
    source_doc = ezdxf.new("R2018")
    base = source_doc.blocks.new("DYN_BASEPOINT_ONLY_REPLAY")
    base.add_line((0, 0), (24, 0))
    public_name = "DYN_BASEPOINT_ONLY_REPLAY"
    from ezdxf.dynblkhelper import set_dynamic_block_definition_metadata

    set_dynamic_block_definition_metadata(
        base,
        guid="{GUID}",
        true_name=public_name,
    )
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(5.0, 6.0, 0.0),
            base_point=(0.0, 0.0, 0.0),
            second_point=(0.0, 0.0, 0.0),
            expr_id=0,
        ),
    )
    return source_doc, public_name


def build_plain_wrapper_nested_dynamic_replay_doc() -> tuple[ezdxf.document.Drawing, str]:
    source_doc, child_public_name = build_supported_linear_visibility_replay_doc()
    child_base = next(
        block
        for block in source_doc.blocks
        if block.block_record.has_xdata("AcDbDynamicBlockTrueName2")
        and block.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
        == child_public_name
    )
    child_ref = _add_supported_linear_visibility_reference_block(source_doc, child_base)
    wrapper = source_doc.blocks.new("PLAIN_WRAPPER_NESTED_DYNAMIC")
    wrapper.add_blockref(child_ref.name, (0, 0))
    source_doc.modelspace().add_blockref(wrapper.name, (600, 0))
    return source_doc, wrapper.name


def assert_supported_linear_visibility_replay_doc(doc: ezdxf.document.Drawing, public_name: str) -> None:
    new_inserts = list(doc.modelspace().query("INSERT"))

    assert len(new_inserts) == 2
    state_by_x = {
        round(float(insert.dxf.insert.x), 3): get_dynamic_block_visibility_state(insert)
        for insert in new_inserts
    }
    assert state_by_x[0.0] == "STATE_A"
    assert state_by_x[80.0] == "STATE_B"

    new_base = next(
        block
        for block in doc.blocks
        if block.block_record.has_xdata("AcDbDynamicBlockTrueName2")
        and block.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "") == public_name
    )
    new_linear = get_dynamic_block_linear_parameters(new_base)
    new_actions = get_dynamic_block_stretch_actions(new_base)
    new_props = get_dynamic_block_properties_table(new_base)
    ref_count = sum(
        1
        for block in doc.blocks
        if block.block_record.has_xdata("AcDbBlockRepBTag")
        and block.block_record.get_xdata("AcDbBlockRepBTag").get_first_value(1005, "") == new_base.block_record_handle
    )

    assert new_props is not None
    assert [row.values for row in new_props.rows] == [("A", "STATE_A"), ("B", "STATE_B")]
    assert len(new_linear) == 1
    assert new_linear[0].parameter_name == "Distance1"
    assert new_linear[0].end_grip_location == (12.0, 24.0, 0.0)
    assert len(new_actions) == 1
    assert [(target.mode, target.components) for target in new_actions[0].targets] == [
        (1, (1,)),
        (1, (1,)),
    ]
    assert ref_count >= 4

    for insert in new_inserts:
        rep = insert.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
        cache = rep.get("AppDataCache")
        enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")
        history = cache.get("ACAD_ENHANCEDBLOCKHISTORY")
        assert set(enhanced.keys()) >= {"1", "5", "16", "20"}
        assert "6" not in set(enhanced.keys())
        assert history is not None


def build_nested_supported_linear_visibility_replay_doc() -> tuple[ezdxf.document.Drawing, str]:
    source_doc, child_public_name = build_supported_linear_visibility_replay_doc()
    child_base = next(
        block
        for block in source_doc.blocks
        if block.block_record.has_xdata("AcDbDynamicBlockTrueName2")
        and block.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
        == child_public_name
    )
    child_ref = _add_supported_linear_visibility_reference_block(source_doc, child_base)
    parent_base = source_doc.blocks.new("PARENT_NESTED_BASE")
    parent_line = parent_base.add_line((0, 0), (20, 0))
    parent_child = parent_base.add_blockref(child_ref.name, (40, 0))
    set_dynamic_block_visibility_parameter(
        parent_base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="ParentVis",
            location=(0.0, 10.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "SHOW",
                    (parent_line.dxf.handle, parent_child.dxf.handle),
                ),
                DynamicBlockVisibilityState("LINE_ONLY", (parent_line.dxf.handle,)),
            ),
        ),
        guid="{PARENT}",
    )
    set_dynamic_block_visibility_state(parent_child, child_base, state="STATE_B")

    parent_anon = source_doc.blocks.new_anonymous_block(type_char="U")
    for entity in parent_base:
        parent_anon.add_entity(entity.copy())
    set_dynamic_block_reference(parent_anon, parent_base)
    parent_insert = source_doc.modelspace().add_blockref(parent_anon.name, (200, 0))
    set_dynamic_block_visibility_state(parent_insert, parent_base, state="SHOW")
    return source_doc, child_public_name


def build_multi_nested_supported_linear_visibility_replay_doc() -> tuple[ezdxf.document.Drawing, str]:
    source_doc, child_public_name = build_supported_linear_visibility_replay_doc()
    child_base = next(
        block
        for block in source_doc.blocks
        if block.block_record.has_xdata("AcDbDynamicBlockTrueName2")
        and block.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
        == child_public_name
    )
    child_ref = _add_supported_linear_visibility_reference_block(source_doc, child_base)
    parent_base = source_doc.blocks.new("PARENT_NESTED_MULTI_BASE")
    parent_line = parent_base.add_line((0, 0), (20, 0))
    parent_circle = parent_base.add_circle((0, 8), radius=2)
    parent_poly = parent_base.add_lwpolyline([(-3, 4), (3, 4), (0, 12)], close=True)
    parent_child_a = parent_base.add_blockref(child_ref.name, (40, 0))
    parent_child_b = parent_base.add_blockref(child_ref.name, (80, 0))
    set_dynamic_block_visibility_parameter(
        parent_base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="ParentVis",
            location=(0.0, 18.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "SHOW_BOTH",
                    (
                        parent_line.dxf.handle,
                        parent_circle.dxf.handle,
                        parent_child_a.dxf.handle,
                        parent_child_b.dxf.handle,
                    ),
                ),
                DynamicBlockVisibilityState(
                    "ALT_GEOM",
                    (
                        parent_line.dxf.handle,
                        parent_poly.dxf.handle,
                        parent_child_a.dxf.handle,
                        parent_child_b.dxf.handle,
                    ),
                ),
            ),
        ),
        guid="{PARENT_MULTI}",
    )
    set_dynamic_block_visibility_state(parent_child_a, child_base, state="STATE_B")
    set_dynamic_block_visibility_state(parent_child_b, child_base, state="STATE_B")

    parent_anon = source_doc.blocks.new_anonymous_block(type_char="U")
    for entity in parent_base:
        parent_anon.add_entity(entity.copy())
    set_dynamic_block_reference(parent_anon, parent_base)
    parent_insert = source_doc.modelspace().add_blockref(parent_anon.name, (260, 0))
    set_dynamic_block_visibility_state(parent_insert, parent_base, state="SHOW_BOTH")
    return source_doc, child_public_name


def build_multi_nested_mixed_state_replay_doc() -> tuple[ezdxf.document.Drawing, str]:
    source_doc, child_public_name = build_supported_linear_visibility_replay_doc()
    child_base = next(
        block
        for block in source_doc.blocks
        if block.block_record.has_xdata("AcDbDynamicBlockTrueName2")
        and block.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
        == child_public_name
    )
    child_ref_a = _add_supported_linear_visibility_reference_block(source_doc, child_base)
    child_ref_b = _add_supported_linear_visibility_reference_block(source_doc, child_base)
    parent_base = source_doc.blocks.new("PARENT_NESTED_MULTI_MIXED_BASE")
    parent_line = parent_base.add_line((0, 0), (20, 0))
    parent_circle = parent_base.add_circle((0, 8), radius=2)
    parent_poly = parent_base.add_lwpolyline([(-3, 4), (3, 4), (0, 12)], close=True)
    parent_child_a = parent_base.add_blockref(child_ref_a.name, (40, 0))
    parent_child_b = parent_base.add_blockref(child_ref_b.name, (80, 0))
    set_dynamic_block_visibility_parameter(
        parent_base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="ParentVis",
            location=(0.0, 18.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "SHOW_MIXED",
                    (
                        parent_line.dxf.handle,
                        parent_circle.dxf.handle,
                        parent_child_a.dxf.handle,
                        parent_child_b.dxf.handle,
                    ),
                ),
                DynamicBlockVisibilityState(
                    "ALT_GEOM",
                    (
                        parent_line.dxf.handle,
                        parent_poly.dxf.handle,
                        parent_child_a.dxf.handle,
                        parent_child_b.dxf.handle,
                    ),
                ),
            ),
        ),
        guid="{PARENT_MULTI_MIXED}",
    )
    set_dynamic_block_visibility_state(parent_child_a, child_base, state="STATE_A")
    set_dynamic_block_visibility_state(parent_child_b, child_base, state="STATE_B")

    parent_anon = source_doc.blocks.new_anonymous_block(type_char="U")
    for entity in parent_base:
        parent_anon.add_entity(entity.copy())
    set_dynamic_block_reference(parent_anon, parent_base)
    parent_insert = source_doc.modelspace().add_blockref(parent_anon.name, (340, 0))
    set_dynamic_block_visibility_state(parent_insert, parent_base, state="SHOW_MIXED")
    return source_doc, child_public_name


def build_three_level_nested_mixed_state_replay_doc() -> tuple[ezdxf.document.Drawing, str]:
    source_doc, child_public_name = build_multi_nested_mixed_state_replay_doc()
    source_msp = source_doc.modelspace()
    middle_insert = next(
        insert
        for insert in source_msp.query("INSERT")
        if round(float(insert.dxf.insert.x), 3) == 340.0
    )
    middle_base = get_dynamic_block_definition(middle_insert)
    middle_ref = get_dynamic_block_reference(middle_insert)

    assert middle_base is not None
    assert middle_ref is not None
    parent_base = source_doc.blocks.new("PARENT_NESTED_LEVEL3_BASE")
    parent_line = parent_base.add_line((0, 0), (30, 0))
    parent_circle = parent_base.add_circle((0, 12), radius=2)
    parent_poly = parent_base.add_lwpolyline([(-4, 6), (4, 6), (0, 16)], close=True)
    parent_child = parent_base.add_blockref(middle_ref.name, (120, 0))
    set_dynamic_block_visibility_parameter(
        parent_base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="ParentLevel3Vis",
            location=(0.0, 24.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "SHOW_CHILD",
                    (
                        parent_line.dxf.handle,
                        parent_circle.dxf.handle,
                        parent_child.dxf.handle,
                    ),
                ),
                DynamicBlockVisibilityState(
                    "ALT_GEOM",
                    (
                        parent_line.dxf.handle,
                        parent_poly.dxf.handle,
                        parent_child.dxf.handle,
                    ),
                ),
            ),
        ),
        guid="{PARENT_LEVEL3}",
    )
    set_dynamic_block_visibility_state(parent_child, middle_base, state="SHOW_MIXED")

    parent_anon = source_doc.blocks.new_anonymous_block(type_char="U")
    for entity in parent_base:
        parent_anon.add_entity(entity.copy())
    set_dynamic_block_reference(parent_anon, parent_base)
    top_insert = source_msp.add_blockref(parent_anon.name, (420, 0))
    set_dynamic_block_visibility_state(top_insert, parent_base, state="SHOW_CHILD")
    return source_doc, child_public_name


def build_multi_richer_child_mixed_state_replay_doc() -> tuple[ezdxf.document.Drawing, str]:
    source_doc, child_public_name = build_supported_linear_visibility_replay_doc()
    child_base = next(
        block
        for block in source_doc.blocks
        if block.block_record.has_xdata("AcDbDynamicBlockTrueName2")
        and block.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
        == child_public_name
    )
    child_ref_a = _add_supported_linear_visibility_reference_block(source_doc, child_base)
    child_ref_b = _add_supported_linear_visibility_reference_block(source_doc, child_base)
    parent_base = source_doc.blocks.new("PARENT_NESTED_RICHER_MULTI_MIXED_BASE")
    parent_line = parent_base.add_line((0, 0), (24, 0))
    parent_circle = parent_base.add_circle((0, 10), radius=2)
    parent_poly = parent_base.add_lwpolyline([(-4, 5), (4, 5), (0, 15)], close=True)
    parent_child_a = parent_base.add_blockref(child_ref_a.name, (40, 0))
    parent_child_b = parent_base.add_blockref(child_ref_b.name, (90, 0))
    set_dynamic_block_visibility_parameter(
        parent_base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="ParentVis",
            location=(0.0, 22.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "SHOW_MIXED",
                    (
                        parent_line.dxf.handle,
                        parent_circle.dxf.handle,
                        parent_child_a.dxf.handle,
                        parent_child_b.dxf.handle,
                    ),
                ),
                DynamicBlockVisibilityState(
                    "ALT_GEOM",
                    (
                        parent_line.dxf.handle,
                        parent_poly.dxf.handle,
                        parent_child_a.dxf.handle,
                        parent_child_b.dxf.handle,
                    ),
                ),
            ),
        ),
        guid="{PARENT_RICHER_MULTI_MIXED}",
    )
    set_dynamic_block_visibility_state(parent_child_a, child_base, state="STATE_A")
    set_dynamic_block_visibility_state(parent_child_b, child_base, state="STATE_B")

    parent_anon = source_doc.blocks.new_anonymous_block(type_char="U")
    for entity in parent_base:
        parent_anon.add_entity(entity.copy())
    set_dynamic_block_reference(parent_anon, parent_base)
    parent_insert = source_doc.modelspace().add_blockref(parent_anon.name, (520, 0))
    set_dynamic_block_visibility_state(parent_insert, parent_base, state="SHOW_MIXED")
    return source_doc, child_public_name


def assert_nested_parent_insert_states(
    doc: ezdxf.document.Drawing,
    *,
    insert_x: float,
    outer_state: str,
    child_public_name: str,
    nested_count: int,
    nested_state: str,
) -> None:
    parent_insert = next(
        insert
        for insert in doc.modelspace().query("INSERT")
        if round(float(insert.dxf.insert.x), 3) == insert_x
    )
    parent_ref = get_dynamic_block_reference(parent_insert)

    assert parent_ref is not None
    assert get_dynamic_block_visibility_state(parent_insert) == outer_state
    nested_inserts = list(parent_ref.query("INSERT"))
    assert len(nested_inserts) == nested_count
    refs = []
    for nested_insert in nested_inserts:
        nested_base = get_dynamic_block_definition(nested_insert)
        nested_ref = get_dynamic_block_reference(nested_insert)

        assert nested_base is not None
        assert nested_ref is not None
        assert (
            nested_base.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
            == child_public_name
        )
        assert nested_insert.has_extension_dict is True
        assert get_dynamic_block_visibility_state(nested_insert) == nested_state
        rep = nested_insert.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
        cache = rep.get("AppDataCache")
        enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")
        assert set(enhanced.keys()) >= {"1", "5", "16", "20"}
        assert "6" not in set(enhanced.keys())
        refs.append(nested_ref.name)
    assert len(set(refs)) == 1


def assert_nested_parent_insert_mixed_states(
    doc: ezdxf.document.Drawing,
    *,
    insert_x: float,
    outer_state: str,
    child_public_name: str,
    expected_states: tuple[tuple[float, str], ...],
) -> None:
    parent_insert = next(
        insert
        for insert in doc.modelspace().query("INSERT")
        if round(float(insert.dxf.insert.x), 3) == insert_x
    )
    parent_ref = get_dynamic_block_reference(parent_insert)

    assert parent_ref is not None
    assert get_dynamic_block_visibility_state(parent_insert) == outer_state
    nested_inserts = sorted(
        list(parent_ref.query("INSERT")),
        key=lambda entity: round(float(entity.dxf.insert.x), 6),
    )
    assert len(nested_inserts) == len(expected_states)
    refs = []
    for nested_insert, (expected_x, expected_state) in zip(nested_inserts, expected_states):
        nested_base = get_dynamic_block_definition(nested_insert)
        nested_ref = get_dynamic_block_reference(nested_insert)

        assert nested_base is not None
        assert nested_ref is not None
        assert round(float(nested_insert.dxf.insert.x), 3) == expected_x
        assert (
            nested_base.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
            == child_public_name
        )
        assert nested_insert.has_extension_dict is True
        assert get_dynamic_block_visibility_state(nested_insert) == expected_state
        refs.append(nested_ref.name)
    assert len(set(refs)) == len({state for _x, state in expected_states})


def assert_three_level_nested_parent_insert_mixed_states(
    doc: ezdxf.document.Drawing,
    *,
    insert_x: float,
    child_public_name: str,
) -> None:
    top_insert = next(
        insert
        for insert in doc.modelspace().query("INSERT")
        if round(float(insert.dxf.insert.x), 3) == insert_x
    )
    top_ref = get_dynamic_block_reference(top_insert)

    assert top_ref is not None
    assert get_dynamic_block_visibility_state(top_insert) == "SHOW_CHILD"
    middle_insert = list(top_ref.query("INSERT"))[0]
    middle_base = get_dynamic_block_definition(middle_insert)
    middle_ref = get_dynamic_block_reference(middle_insert)

    assert middle_base is not None
    assert middle_ref is not None
    assert middle_insert.has_extension_dict is True
    assert get_dynamic_block_visibility_state(middle_insert) == "SHOW_MIXED"

    nested_inserts = sorted(
        list(middle_ref.query("INSERT")),
        key=lambda entity: round(float(entity.dxf.insert.x), 6),
    )
    assert len(nested_inserts) == 2
    refs = []
    for nested_insert, (expected_x, expected_state) in zip(
        nested_inserts,
        ((40.0, "STATE_A"), (80.0, "STATE_B")),
    ):
        nested_base = get_dynamic_block_definition(nested_insert)
        nested_ref = get_dynamic_block_reference(nested_insert)

        assert nested_base is not None
        assert nested_ref is not None
        assert round(float(nested_insert.dxf.insert.x), 3) == expected_x
        assert (
            nested_base.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
            == child_public_name
        )
        assert nested_insert.has_extension_dict is True
        assert get_dynamic_block_visibility_state(nested_insert) == expected_state
        refs.append(nested_ref.name)
    assert len(set(refs)) == 2


def assert_nested_working_oracle_replay_doc(doc: ezdxf.document.Drawing) -> None:
    inner_base = doc.blocks.get("*U0")
    outer_base = doc.blocks.get("*U2")
    inner_ref = doc.blocks.get("*U15")
    outer_ref = doc.blocks.get("*U16")

    assert inner_base is not None
    assert outer_base is not None
    assert inner_ref is not None
    assert outer_ref is not None
    assert inner_base.block_record.get_xdata("AcDbDynamicBlockTrueName").get_first_value(1000, "") == "AUTHORED_SIMPLE_DYN_VIS_A"
    assert outer_base.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "") == "AUTHORED_SIMPLE_DYN_LINEAR_B"

    outer_base_nested = [entity for entity in outer_base if entity.dxftype() == "INSERT"]
    outer_ref_nested = [entity for entity in outer_ref if entity.dxftype() == "INSERT"]

    assert len(outer_base_nested) == 1
    assert len(outer_ref_nested) == 1
    for nested_insert in (outer_base_nested[0], outer_ref_nested[0]):
        assert nested_insert.has_extension_dict is True
        assert nested_insert.dxf.name == "*U15"
        assert get_dynamic_block_definition(nested_insert) == inner_base
        assert get_dynamic_block_reference(nested_insert) == inner_ref
        assert get_dynamic_block_visibility_state(nested_insert) == "STATE_B"
        rep = nested_insert.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
        cache = rep.get("AppDataCache")
        enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")
        assert rep._value_code == 360
        assert cache._value_code == 360
        assert enhanced._value_code == 360
        assert set(enhanced.keys()) >= {"6"}

    assert set(inner_ref.block_record.blkref_handles) == {
        outer_base_nested[0].dxf.handle,
        outer_ref_nested[0].dxf.handle,
    }

    modelspace_inserts = list(doc.modelspace().query("INSERT"))
    outer_model_insert = next(insert for insert in modelspace_inserts if insert.dxf.name == "*U16")
    assert get_dynamic_block_visibility_state(outer_model_insert) == "STATE_A"


def assert_nested_richer_child_oracle_replay_doc(doc: ezdxf.document.Drawing) -> None:
    assert_nested_parent_insert_states(
        doc,
        insert_x=200.0,
        outer_state="SHOW",
        child_public_name="DYN_PROP_BASEPOINT_LINEAR_REPLAY",
        nested_count=1,
        nested_state="STATE_B",
    )


def assert_nested_two_children_oracle_replay_doc(doc: ezdxf.document.Drawing) -> None:
    assert_nested_parent_insert_states(
        doc,
        insert_x=260.0,
        outer_state="SHOW_BOTH",
        child_public_name="DYN_PROP_BASEPOINT_LINEAR_REPLAY",
        nested_count=2,
        nested_state="STATE_B",
    )


def assert_nested_two_children_mixed_oracle_replay_doc(doc: ezdxf.document.Drawing) -> None:
    assert_nested_parent_insert_mixed_states(
        doc,
        insert_x=340.0,
        outer_state="SHOW_MIXED",
        child_public_name="DYN_PROP_BASEPOINT_LINEAR_REPLAY",
        expected_states=((40.0, "STATE_A"), (80.0, "STATE_B")),
    )


def assert_nested_three_level_mixed_oracle_replay_doc(doc: ezdxf.document.Drawing) -> None:
    assert_three_level_nested_parent_insert_mixed_states(
        doc,
        insert_x=420.0,
        child_public_name="DYN_PROP_BASEPOINT_LINEAR_REPLAY",
    )


def nested_oracle_cases():
    return (
        pytest.param(
            NESTED_WORKING_ORACLE,
            assert_nested_working_oracle_replay_doc,
            id="working-minimal",
        ),
        pytest.param(
            NESTED_RICHER_CHILD_ORACLE,
            assert_nested_richer_child_oracle_replay_doc,
            id="richer-child",
        ),
        pytest.param(
            NESTED_TWO_CHILDREN_ORACLE,
            assert_nested_two_children_oracle_replay_doc,
            id="two-children-same-state",
        ),
        pytest.param(
            NESTED_TWO_CHILDREN_MIXED_ORACLE,
            assert_nested_two_children_mixed_oracle_replay_doc,
            id="two-children-mixed-states",
        ),
        pytest.param(
            NESTED_THREE_LEVEL_MIXED_ORACLE,
            assert_nested_three_level_mixed_oracle_replay_doc,
            id="three-level-mixed",
        ),
    )


def test_dynamic_visibility_blocks_to_code():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    base = source_doc.blocks.new("DYN_VIS_DXF2CODE")
    common1 = base.add_line((0, 0), (1, 0))
    common2 = base.add_line((0, 1), (1, 1))
    state_a = base.add_circle((1, 1), radius=0.5)
    state_b = base.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
    state_c1 = base.add_line((0, 0), (1, 1))
    state_c2 = base.add_line((0, 1), (1, 0))
    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility State",
        parameter_name="Visibility1Param",
        location=(0.0, 14.0, 0.0),
        states=(
            DynamicBlockVisibilityState(
                "STATE_A",
                (common1.dxf.handle, common2.dxf.handle, state_a.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_B",
                (common1.dxf.handle, common2.dxf.handle, state_b.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_C",
                (
                    common1.dxf.handle,
                    common2.dxf.handle,
                    state_c1.dxf.handle,
                    state_c2.dxf.handle,
                ),
            ),
        ),
    )
    set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}")

    def add_reference_block_and_insert(state: str, insert_point: tuple[float, float]):
        anon = source_doc.blocks.new_anonymous_block(type_char="U")
        anon.add_line((0, 0), (1, 0))
        anon.add_line((0, 1), (1, 1))
        anon.add_circle((1, 1), radius=0.5)
        anon.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
        anon.add_line((0, 0), (1, 1))
        anon.add_line((0, 1), (1, 0))
        set_dynamic_block_reference(anon, base)
        insert = source_msp.add_blockref(anon.name, insert_point)
        set_dynamic_block_visibility_state(insert, base, state=state)
        return insert

    insert_a = add_reference_block_and_insert("STATE_A", (0, 0))
    insert_c = add_reference_block_and_insert("STATE_C", (3, 0))

    target_doc = ezdxf.new("R2018")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(base, drawing="doc"), namespace)
    execute_code_in_namespace(
        block_to_code(get_dynamic_block_reference(insert_a), drawing="doc"),
        namespace,
    )
    execute_code_in_namespace(
        block_to_code(get_dynamic_block_reference(insert_c), drawing="doc"),
        namespace,
    )
    execute_code_in_namespace(entities_to_code([insert_a, insert_c], layout="msp"), namespace)

    new_doc = namespace["doc"]
    new_inserts = list(namespace["msp"].query("INSERT"))

    assert get_dynamic_block_visibility_states(new_inserts[0]) == (
        "STATE_A",
        "STATE_B",
        "STATE_C",
    )
    assert get_dynamic_block_visibility_state(new_inserts[0]) == "STATE_A"
    assert get_dynamic_block_visibility_state(new_inserts[1]) == "STATE_C"
    ref_a = get_dynamic_block_reference(new_inserts[0])
    ref_c = get_dynamic_block_reference(new_inserts[1])
    assert ref_a is not None
    assert ref_c is not None
    assert all(entity.has_xdata("AcDbBlockRepETag") for entity in ref_a)
    assert all(entity.has_xdata("AcDbBlockRepETag") for entity in ref_c)
    assert new_doc.blocks.get("DYN_VIS_DXF2CODE") is not None


def test_dynamic_visibility_blocks_to_code_preserves_sparse_rep_indices():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    base = source_doc.blocks.new("DYN_VIS_SPARSE_REP")
    common1 = base.add_line((0, 0), (1, 0))
    common2 = base.add_line((0, 1), (1, 1))
    state_b = base.add_circle((1, 1), radius=0.5)
    base_entities = list(base)
    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility State",
        parameter_name="Visibility1Param",
        location=(0.0, 14.0, 0.0),
        states=(
            DynamicBlockVisibilityState(
                "STATE_A",
                (common1.dxf.handle, common2.dxf.handle),
            ),
            DynamicBlockVisibilityState("STATE_B", (state_b.dxf.handle,)),
        ),
    )
    set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}")
    sparse_indices = (0, 1, 3)
    for entity, index in zip(base_entities, sparse_indices):
        entity.set_xdata(
            "AcDbBlockRepETag",
            [(1070, 1), (1071, index), (1005, entity.dxf.handle)],
        )
    base.block_record.set_xdata("AcDbBlockRepETag", [(1070, 1), (1071, 4)])

    anon = source_doc.blocks.new_anonymous_block(type_char="U")
    anon.add_line((0, 0), (1, 0))
    anon.add_line((0, 1), (1, 1))
    anon.add_circle((1, 1), radius=0.5)
    set_dynamic_block_reference(anon, base)
    anon_entities = list(anon)
    for entity, index in zip(anon_entities, sparse_indices):
        entity.set_xdata(
            "AcDbBlockRepETag",
            [(1070, 1), (1071, index), (1005, entity.dxf.handle)],
        )
    insert = source_msp.add_blockref(anon.name, (0, 0))
    set_dynamic_block_visibility_state(insert, base, state="STATE_A")

    target_doc = ezdxf.new("R2018")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(base, drawing="doc"), namespace)
    execute_code_in_namespace(block_to_code(anon, drawing="doc"), namespace)
    execute_code_in_namespace(entities_to_code([insert], layout="msp"), namespace)

    new_doc = namespace["doc"]
    new_base = new_doc.blocks.get("DYN_VIS_SPARSE_REP")
    new_insert = list(namespace["msp"].query("INSERT"))[0]
    new_ref = get_dynamic_block_reference(new_insert)

    assert new_base is not None
    assert new_ref is not None
    assert list(new_base.block_record.get_xdata("AcDbBlockRepETag")) == [(1070, 1), (1071, 4)]
    assert [list(entity.get_xdata("AcDbBlockRepETag"))[1][1] for entity in new_base] == [0, 1, 3]
    assert [list(entity.get_xdata("AcDbBlockRepETag"))[1][1] for entity in new_ref] == [0, 1, 3]
    assert [list(entity.get_xdata("AcDbBlockRepETag"))[2][1] for entity in new_base] == [entity.dxf.handle for entity in new_base]
    assert [list(entity.get_xdata("AcDbBlockRepETag"))[2][1] for entity in new_ref] == [entity.dxf.handle for entity in new_ref]


def test_dynamic_block_properties_to_code():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    base = source_doc.blocks.new("DYN_PROP_DXF2CODE")
    common1 = base.add_line((0, 0), (1, 0))
    common2 = base.add_line((0, 1), (1, 1))
    state_a = base.add_circle((1, 1), radius=0.5)
    state_b = base.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
    state_c1 = base.add_line((0, 0), (1, 1))
    state_c2 = base.add_line((0, 1), (1, 0))
    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility State",
        parameter_name="Visibility1Param",
        location=(0.0, 14.0, 0.0),
        states=(
            DynamicBlockVisibilityState(
                "STATE_A",
                (common1.dxf.handle, common2.dxf.handle, state_a.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_B",
                (common1.dxf.handle, common2.dxf.handle, state_b.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_C",
                (
                    common1.dxf.handle,
                    common2.dxf.handle,
                    state_c1.dxf.handle,
                    state_c2.dxf.handle,
                ),
            ),
        ),
    )
    set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}")
    props = DynamicBlockPropertiesTable(
        handle="",
        label="Block Table",
        table_name="Block Table1",
        description="",
        location=(32.0, 20.0, 0.0),
        grip_location=(32.0, 20.0, 0.0),
        columns=(
            DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_1", "Block Table1"),
            DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_2", "Block Table1"),
            DynamicBlockPropertyColumn("", "BLOCKVISIBILITYPARAMETER", "VisibilityState", "VisibilityState"),
        ),
        rows=(
            DynamicBlockPropertyRow(0, ("A", "X", "STATE_A")),
            DynamicBlockPropertyRow(1, ("A", "Y", "STATE_B")),
            DynamicBlockPropertyRow(2, ("B", "Z", "STATE_C")),
        ),
    )
    set_dynamic_block_properties_table(base, props)

    def add_reference_block_and_insert(state: str, insert_point: tuple[float, float]):
        anon = source_doc.blocks.new_anonymous_block(type_char="U")
        anon.add_line((0, 0), (1, 0))
        anon.add_line((0, 1), (1, 1))
        anon.add_circle((1, 1), radius=0.5)
        anon.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
        anon.add_line((0, 0), (1, 1))
        anon.add_line((0, 1), (1, 0))
        set_dynamic_block_reference(anon, base)
        insert = source_msp.add_blockref(anon.name, insert_point)
        set_dynamic_block_visibility_state(insert, base, state=state)
        return insert

    insert_a = add_reference_block_and_insert("STATE_A", (0, 0))
    insert_c = add_reference_block_and_insert("STATE_C", (3, 0))

    target_doc = ezdxf.new("R2018")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(base, drawing="doc"), namespace)
    execute_code_in_namespace(
        block_to_code(get_dynamic_block_reference(insert_a), drawing="doc"),
        namespace,
    )
    execute_code_in_namespace(
        block_to_code(get_dynamic_block_reference(insert_c), drawing="doc"),
        namespace,
    )
    execute_code_in_namespace(entities_to_code([insert_a, insert_c], layout="msp"), namespace)

    new_doc = namespace["doc"]
    new_inserts = list(namespace["msp"].query("INSERT"))
    new_base = new_doc.blocks.get("DYN_PROP_DXF2CODE")
    new_props = get_dynamic_block_properties_table(new_base)

    assert new_props is not None
    assert new_props.table_name == "Block Table1"
    assert [column.name for column in new_props.columns] == [
        "PARAM_1",
        "PARAM_2",
        "VisibilityState",
    ]
    assert [row.values for row in new_props.rows] == [
        ("A", "X", "STATE_A"),
        ("A", "Y", "STATE_B"),
        ("B", "Z", "STATE_C"),
    ]
    assert get_dynamic_block_visibility_state(new_inserts[0]) == "STATE_A"
    assert get_dynamic_block_visibility_state(new_inserts[1]) == "STATE_C"


def test_dynamic_block_linear_parameter_to_code():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    base = source_doc.blocks.new("DYN_PROP_LINEAR_DXF2CODE")
    common1 = base.add_line((0, 0), (1, 0))
    common2 = base.add_line((0, 1), (1, 1))
    state_a = base.add_circle((1, 1), radius=0.5)
    state_b = base.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
    state_c1 = base.add_line((0, 0), (1, 1))
    state_c2 = base.add_line((0, 1), (1, 0))
    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility State",
        parameter_name="Visibility1Param",
        location=(0.0, 14.0, 0.0),
        states=(
            DynamicBlockVisibilityState(
                "STATE_A",
                (common1.dxf.handle, common2.dxf.handle, state_a.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_B",
                (common1.dxf.handle, common2.dxf.handle, state_b.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_C",
                (
                    common1.dxf.handle,
                    common2.dxf.handle,
                    state_c1.dxf.handle,
                    state_c2.dxf.handle,
                ),
            ),
        ),
    )
    set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}")
    props = DynamicBlockPropertiesTable(
        handle="",
        label="Block Table",
        table_name="Block Table1",
        description="",
        location=(32.0, 20.0, 0.0),
        grip_location=(32.0, 20.0, 0.0),
        columns=(
            DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_1", "Block Table1"),
            DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_2", "Block Table1"),
            DynamicBlockPropertyColumn("", "BLOCKVISIBILITYPARAMETER", "VisibilityState", "VisibilityState"),
        ),
        rows=(
            DynamicBlockPropertyRow(0, ("A", "X", "STATE_A")),
            DynamicBlockPropertyRow(1, ("A", "Y", "STATE_B")),
            DynamicBlockPropertyRow(2, ("B", "Z", "STATE_C")),
        ),
    )
    props = set_dynamic_block_properties_table(base, props)
    grip = next(obj for obj in source_doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")
    base_attdefs = {entity.dxf.tag: entity for entity in base if entity.dxftype() == "ATTDEF"}
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
        end_grip_location=(0.25, 2.0, 0.0),
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
            props.handle,
            base_attdefs["PARAM_2"].dxf.handle,
            base_attdefs["PARAM_1"].dxf.handle,
            common1.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(common1.dxf.handle, 2, (1, 2)),
            DynamicBlockStretchActionTarget(base_attdefs["PARAM_1"].dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(base_attdefs["PARAM_2"].dxf.handle, 1, (0,)),
        ),
    )
    set_dynamic_block_linear_parameter(base, linear, stretch)

    def add_reference_block_and_insert(state: str, insert_point: tuple[float, float]):
        anon = source_doc.blocks.new_anonymous_block(type_char="U")
        anon.add_line((0, 0), (1, 0))
        anon.add_line((0, 1), (1, 1))
        anon.add_circle((1, 1), radius=0.5)
        anon.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
        anon.add_line((0, 0), (1, 1))
        anon.add_line((0, 1), (1, 0))
        set_dynamic_block_reference(anon, base)
        insert = source_msp.add_blockref(anon.name, insert_point)
        set_dynamic_block_visibility_state(insert, base, state=state)
        return insert

    insert_a = add_reference_block_and_insert("STATE_A", (0, 0))
    insert_c = add_reference_block_and_insert("STATE_C", (3, 0))

    target_doc = ezdxf.new("R2018")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(base, drawing="doc"), namespace)
    execute_code_in_namespace(
        block_to_code(get_dynamic_block_reference(insert_a), drawing="doc"),
        namespace,
    )
    execute_code_in_namespace(
        block_to_code(get_dynamic_block_reference(insert_c), drawing="doc"),
        namespace,
    )
    execute_code_in_namespace(entities_to_code([insert_a, insert_c], layout="msp"), namespace)

    new_doc = namespace["doc"]
    new_inserts = list(namespace["msp"].query("INSERT"))
    new_base = new_doc.blocks.get("DYN_PROP_LINEAR_DXF2CODE")
    new_linear = get_dynamic_block_linear_parameters(new_base)
    new_actions = get_dynamic_block_stretch_actions(new_base)

    assert len(new_linear) == 1
    assert new_linear[0].parameter_name == "Distance1"
    assert new_linear[0].base_grip_label == "Base Grip"
    assert new_linear[0].end_grip_label == "End Grip"
    assert new_linear[0].end_point == (1.0, 0.0, 0.0)
    assert new_linear[0].end_grip_location == (0.25, 2.0, 0.0)
    assert len(new_actions) == 1
    assert new_actions[0].label == "Stretch1"
    assert new_actions[0].selection_window == ((2.0, 1.0, 0.0), (0.5, -0.5, 0.0))
    assert get_dynamic_block_visibility_state(new_inserts[0]) == "STATE_A"
    assert get_dynamic_block_visibility_state(new_inserts[1]) == "STATE_C"
    ref_a = get_dynamic_block_reference(new_inserts[0])
    ref_c = get_dynamic_block_reference(new_inserts[1])
    assert ref_a is not None
    assert ref_c is not None
    assert all(entity.has_xdata("AcDbBlockRepETag") for entity in ref_a)
    assert all(entity.has_xdata("AcDbBlockRepETag") for entity in ref_c)


def test_dynamic_block_basepoint_linear_full_replay_preserves_supported_path():
    source_doc, public_name = build_supported_linear_visibility_replay_doc()
    source_base = _dynamic_block_by_public_name(source_doc, public_name)
    source_base.block_record.preview_data = bytes.fromhex("01020304")
    source_base.block_record.dxf.units = 1
    new_doc = replay_doc_to_new_doc(source_doc)
    new_base = _dynamic_block_by_public_name(new_doc, public_name)

    assert_supported_linear_visibility_replay_doc(new_doc, public_name)
    assert source_base.block_record.has_extension_dict is True
    assert new_base.block_record.has_extension_dict is True
    assert new_base.block_record.preview_data == source_base.block_record.preview_data
    assert new_base.block_record.dxf.units == source_base.block_record.dxf.units
    assert list(source_base.block_record.xdata.data.keys()) == list(
        new_base.block_record.xdata.data.keys()
    )
    assert list(source_base.block_record.get_extension_dict().dictionary.keys()) == list(
        new_base.block_record.get_extension_dict().dictionary.keys()
    )


def test_dynamic_block_basepoint_only_replay_preserves_supported_path():
    source_doc, public_name = build_basepoint_only_replay_doc()
    source_base = _dynamic_block_by_public_name(source_doc, public_name)
    source_base.block_record.preview_data = bytes.fromhex("01020304")
    source_base.block_record.dxf.units = 1
    new_doc = replay_doc_to_new_doc(source_doc)
    new_base = _dynamic_block_by_public_name(new_doc, public_name)
    new_basepoint = get_dynamic_block_base_point_parameter(new_base)

    assert new_basepoint is not None
    assert new_basepoint.location == (5.0, 6.0, 0.0)
    assert source_base.block_record.has_extension_dict is True
    assert new_base.block_record.has_extension_dict is True
    assert new_base.block_record.preview_data == source_base.block_record.preview_data
    assert new_base.block_record.dxf.units == source_base.block_record.dxf.units
    assert list(source_base.block_record.xdata.data.keys()) == list(
        new_base.block_record.xdata.data.keys()
    )
    assert list(source_base.block_record.get_extension_dict().dictionary.keys()) == list(
        new_base.block_record.get_extension_dict().dictionary.keys()
    )


def test_plain_wrapper_nested_dynamic_replay_preserves_blkref_handles():
    source_doc, wrapper_name = build_plain_wrapper_nested_dynamic_replay_doc()
    new_doc = replay_doc_to_new_doc(source_doc)
    wrapper = new_doc.blocks.get(wrapper_name)

    assert wrapper is not None
    wrapper_insert = next(
        insert
        for insert in new_doc.modelspace().query("INSERT")
        if insert.dxf.name == wrapper_name
    )
    assert list(wrapper.block_record.blkref_handles) == [wrapper_insert.dxf.handle]


def test_raw_dynamic_layout_fallback_preserves_nested_insert_handles(tmp_path):
    source_doc = ezdxf.new("R2018")
    child = source_doc.blocks.new("RAW_LAYOUT_CHILD")
    child.add_line((0, 0), (1, 0))
    base = source_doc.blocks.new("RAW_LAYOUT_UNSUPPORTED")
    line = base.add_line((0, 0), (10, 0))
    attdef = base.add_attdef("PARAM_1", insert=(0, 2), text="A")
    child_insert = base.add_blockref(child.name, (5, 0))
    table = base.add_table((0, 4), [["T"]])
    table_geometry = "*T900"
    source_doc.blocks.rename_block(table.dxf.geometry, table_geometry)
    table.dxf.geometry = table_geometry
    assert source_doc.entitydb.reset_handle(child_insert, "ABCD")
    child_xdict = child_insert.new_extension_dict().dictionary
    assert source_doc.entitydb.reset_handle(child_xdict, "ABCE")
    child_data = child_xdict.add_new_dict("TEST")
    assert source_doc.entitydb.reset_handle(child_data, "ABCF")
    child_value = child_data.add_xrecord("VALUE")
    child_value.tags.extend([dxftag(1, "PAYLOAD")])
    assert source_doc.entitydb.reset_handle(child_value, "ABD0")
    set_dynamic_block_visibility_parameter(
        base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="Visibility1",
            location=(0.0, 10.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "STATE_A",
                    (line.dxf.handle, attdef.dxf.handle, child_insert.dxf.handle),
                ),
            ),
        ),
        guid="{GUID}",
    )
    set_dynamic_block_properties_table(
        base,
        DynamicBlockPropertiesTable(
            handle="",
            label="Block Table",
            table_name="Block Table1",
            description="",
            location=(10.0, 10.0, 0.0),
            grip_location=(10.0, 10.0, 0.0),
            columns=(
                DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_1", "Block Table1"),
                DynamicBlockPropertyColumn(
                    "", "BLOCKVISIBILITYPARAMETER", "VisibilityState", "VisibilityState"
                ),
            ),
            rows=(DynamicBlockPropertyRow(0, ("A", "STATE_A")),),
        ),
    )
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

    assert "restore_raw_dynamic_block_layout" in str(block_to_code(base, drawing="doc"))
    source_blocks = [block for block in source_doc.blocks if not block.is_any_layout]
    assert table_geometry in _block_dependencies(source_blocks)[base.name]

    new_doc = replay_doc_to_new_doc(source_doc)
    new_base = new_doc.blocks.get(base.name)

    assert new_base is not None
    new_child_insert = next(
        entity for entity in new_base.query("INSERT") if entity.dxf.name == child.name
    )
    assert new_child_insert.dxf.handle == child_insert.dxf.handle
    assert new_child_insert.has_extension_dict is True
    new_child_xdict = new_child_insert.get_extension_dict().dictionary
    assert new_child_xdict.dxf.handle == child_xdict.dxf.handle
    new_child_data = new_child_xdict.get("TEST")
    assert new_child_data is not None
    assert new_child_data.dxf.handle == child_data.dxf.handle
    new_child_value = new_child_data.get("VALUE")
    assert new_child_value is not None
    assert new_child_value.dxf.handle == child_value.dxf.handle
    new_table = next(entity for entity in new_base if entity.dxftype() == "ACAD_TABLE")
    new_table_geometry = new_doc.blocks.get(table_geometry)

    assert new_table_geometry is not None
    assert new_table.dxf.geometry == table_geometry
    assert new_table.dxf.block_record_handle == new_table_geometry.block_record_handle

    stream = StringIO()
    new_table.export_dxf(TagWriter(stream, dxfversion=new_doc.dxfversion))
    lines = stream.getvalue().splitlines()
    raw_btr_handles = [
        lines[index + 1].strip()
        for index in range(0, len(lines) - 1, 2)
        if lines[index].strip() == "343"
    ]
    assert raw_btr_handles == [new_table_geometry.block_record_handle]

    source_path = tmp_path / "raw_dynamic_table_source.dxf"
    script_path = tmp_path / "raw_dynamic_table_replay.py"
    output_path = tmp_path / "raw_dynamic_table_replay.dxf"
    source_doc.saveas(source_path)
    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    generated_doc = ezdxf.readfile(output_path)
    comparison = compare_replay_documents(source_doc, generated_doc)
    assert comparison.replay_bad_acad_table_btrs == ()


def test_dynamic_block_visibility_unresolved_state_handle_uses_raw_layout_fallback():
    source_doc = ezdxf.new("R2018")
    base = source_doc.blocks.new("RAW_LAYOUT_UNRESOLVED_VISIBILITY")
    line = base.add_line((0, 0), (1, 0))
    set_dynamic_block_visibility_parameter(
        base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="Visibility1",
            location=(0.0, 10.0, 0.0),
            states=(
                DynamicBlockVisibilityState(
                    "STATE_A",
                    (line.dxf.handle, "DEADBEEF"),
                ),
            ),
        ),
        guid="{GUID}",
    )

    code = block_to_code(base, drawing="doc")
    script = code.import_str() + "\n" + str(code)

    assert "restore_raw_dynamic_block_layout" in script
    assert "_dyn_states = (" not in script
    compile(script, "<dxf2code>", "exec")


def test_dynamic_block_rep_etag_dangling_handle_emits_null_handle():
    from ezdxf.dynblkhelper import set_dynamic_block_definition_metadata

    source_doc = ezdxf.new("R2018")
    base = source_doc.blocks.new("DYN_DANGLING_REP_HANDLE")
    line = base.add_line((0, 0), (1, 0))
    set_dynamic_block_definition_metadata(
        base,
        guid="{GUID}",
        true_name=base.name,
    )
    set_dynamic_block_base_point_parameter(
        base,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0, 0, 0),
            base_point=(0, 0, 0),
            second_point=(0, 0, 0),
            expr_id=0,
        ),
    )
    line.set_xdata("AcDbBlockRepETag", [(1070, 1), (1071, 3), (1005, "DEADBEEF")])

    code = block_to_code(base, drawing="doc")

    assert '(1005, "0")' in str(code)


def test_dynamic_block_basepoint_linear_two_generation_replay_preserves_supported_path():
    source_doc, public_name = build_supported_linear_visibility_replay_doc()
    gen1_doc = replay_doc_to_new_doc(source_doc)
    gen2_doc = replay_doc_to_new_doc(gen1_doc)

    assert_supported_linear_visibility_replay_doc(gen1_doc, public_name)
    assert_supported_linear_visibility_replay_doc(gen2_doc, public_name)


def test_dynamic_block_basepoint_linear_replay_does_not_duplicate_helper_objects():
    source_doc, _public_name = build_supported_linear_visibility_replay_doc()
    new_doc = replay_doc_to_new_doc(source_doc)

    source_counts = Counter(obj.dxftype() for obj in source_doc.objects)
    new_counts = Counter(obj.dxftype() for obj in new_doc.objects)

    for dxftype in (
        "BLOCKBASEPOINTPARAMETER",
        "BLOCKVISIBILITYPARAMETER",
        "BLOCKVISIBILITYGRIP",
        "BLOCKGRIPLOCATIONCOMPONENT",
        "ACAD_EVALUATION_GRAPH",
    ):
        assert new_counts[dxftype] == source_counts[dxftype]


def test_dynamic_block_basepoint_linear_replay_preserves_nested_dynamic_insert_state():
    source_doc, child_public_name = build_nested_supported_linear_visibility_replay_doc()
    new_doc = replay_doc_to_new_doc(source_doc)

    parent_insert = next(
        insert
        for insert in new_doc.modelspace().query("INSERT")
        if round(float(insert.dxf.insert.x), 3) == 200.0
    )
    parent_ref = get_dynamic_block_reference(parent_insert)

    assert parent_ref is not None
    assert get_dynamic_block_visibility_state(parent_insert) == "SHOW"
    nested_insert = list(parent_ref.query("INSERT"))[0]
    nested_base = get_dynamic_block_definition(nested_insert)

    assert nested_base is not None
    assert (
        nested_base.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
        == child_public_name
    )
    assert nested_insert.has_extension_dict is True
    assert get_dynamic_block_visibility_state(nested_insert) == "STATE_B"
    rep = nested_insert.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
    cache = rep.get("AppDataCache")
    enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")

    assert set(enhanced.keys()) >= {"1", "5", "16", "20"}
    assert "6" not in set(enhanced.keys())


def test_dynamic_block_basepoint_linear_nested_replay_survives_write_read_cycle():
    source_doc, child_public_name = build_nested_supported_linear_visibility_replay_doc()
    replayed_doc = replay_doc_to_new_doc(source_doc)
    stream = StringIO()
    replayed_doc.write(stream)
    stream.seek(0)
    reloaded_doc = ezdxf.read(stream)

    parent_insert = next(
        insert
        for insert in reloaded_doc.modelspace().query("INSERT")
        if round(float(insert.dxf.insert.x), 3) == 200.0
    )
    parent_ref = get_dynamic_block_reference(parent_insert)

    assert parent_ref is not None
    assert get_dynamic_block_visibility_state(parent_insert) == "SHOW"
    nested_insert = list(parent_ref.query("INSERT"))[0]
    nested_base = get_dynamic_block_definition(nested_insert)

    assert nested_base is not None
    assert (
        nested_base.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
        == child_public_name
    )
    assert nested_insert.has_extension_dict is True
    assert get_dynamic_block_visibility_state(nested_insert) == "STATE_B"
    rep = nested_insert.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
    cache = rep.get("AppDataCache")
    enhanced = cache.get("ACAD_ENHANCEDBLOCKDATA")

    assert rep._value_code == 360
    assert cache._value_code == 360
    assert enhanced._value_code == 360
    assert cache.get_reactors() == []
    assert enhanced.get_reactors() == []
    assert set(enhanced.keys()) >= {"1", "5", "16", "20"}
    assert "6" not in set(enhanced.keys())


def test_dynamic_block_basepoint_linear_replay_preserves_multiple_nested_dynamic_insert_states():
    source_doc, child_public_name = build_multi_nested_supported_linear_visibility_replay_doc()
    new_doc = replay_doc_to_new_doc(source_doc)

    assert_nested_parent_insert_states(
        new_doc,
        insert_x=260.0,
        outer_state="SHOW_BOTH",
        child_public_name=child_public_name,
        nested_count=2,
        nested_state="STATE_B",
    )


def test_dynamic_block_basepoint_linear_multi_nested_replay_survives_write_read_cycle():
    source_doc, child_public_name = build_multi_nested_supported_linear_visibility_replay_doc()
    replayed_doc = replay_doc_to_new_doc(source_doc)
    stream = StringIO()
    replayed_doc.write(stream)
    stream.seek(0)
    reloaded_doc = ezdxf.read(stream)

    assert_nested_parent_insert_states(
        reloaded_doc,
        insert_x=260.0,
        outer_state="SHOW_BOTH",
        child_public_name=child_public_name,
        nested_count=2,
        nested_state="STATE_B",
    )


def test_dynamic_block_basepoint_linear_replay_preserves_multiple_nested_dynamic_insert_mixed_states():
    source_doc, child_public_name = build_multi_nested_mixed_state_replay_doc()
    new_doc = replay_doc_to_new_doc(source_doc)

    assert_nested_parent_insert_mixed_states(
        new_doc,
        insert_x=340.0,
        outer_state="SHOW_MIXED",
        child_public_name=child_public_name,
        expected_states=((40.0, "STATE_A"), (80.0, "STATE_B")),
    )


def test_dynamic_block_basepoint_linear_multi_nested_mixed_state_replay_survives_write_read_cycle():
    source_doc, child_public_name = build_multi_nested_mixed_state_replay_doc()
    replayed_doc = replay_doc_to_new_doc(source_doc)
    stream = StringIO()
    replayed_doc.write(stream)
    stream.seek(0)
    reloaded_doc = ezdxf.read(stream)

    assert_nested_parent_insert_mixed_states(
        reloaded_doc,
        insert_x=340.0,
        outer_state="SHOW_MIXED",
        child_public_name=child_public_name,
        expected_states=((40.0, "STATE_A"), (80.0, "STATE_B")),
    )


def test_dynamic_block_basepoint_linear_replay_preserves_three_level_nested_mixed_states():
    source_doc, child_public_name = build_three_level_nested_mixed_state_replay_doc()
    new_doc = replay_doc_to_new_doc(source_doc)

    assert_three_level_nested_parent_insert_mixed_states(
        new_doc,
        insert_x=420.0,
        child_public_name=child_public_name,
    )


def test_dynamic_block_basepoint_linear_three_level_nested_mixed_state_replay_survives_write_read_cycle():
    source_doc, child_public_name = build_three_level_nested_mixed_state_replay_doc()
    replayed_doc = replay_doc_to_new_doc(source_doc)
    stream = StringIO()
    replayed_doc.write(stream)
    stream.seek(0)
    reloaded_doc = ezdxf.read(stream)

    assert_three_level_nested_parent_insert_mixed_states(
        reloaded_doc,
        insert_x=420.0,
        child_public_name=child_public_name,
    )


def test_dynamic_block_basepoint_linear_replay_preserves_multi_richer_child_mixed_states():
    source_doc, child_public_name = build_multi_richer_child_mixed_state_replay_doc()
    new_doc = replay_doc_to_new_doc(source_doc)

    assert_nested_parent_insert_mixed_states(
        new_doc,
        insert_x=520.0,
        outer_state="SHOW_MIXED",
        child_public_name=child_public_name,
        expected_states=((40.0, "STATE_A"), (90.0, "STATE_B")),
    )


def test_dynamic_block_basepoint_linear_multi_richer_child_mixed_state_replay_survives_write_read_cycle():
    source_doc, child_public_name = build_multi_richer_child_mixed_state_replay_doc()
    replayed_doc = replay_doc_to_new_doc(source_doc)
    stream = StringIO()
    replayed_doc.write(stream)
    stream.seek(0)
    reloaded_doc = ezdxf.read(stream)

    assert_nested_parent_insert_mixed_states(
        reloaded_doc,
        insert_x=520.0,
        outer_state="SHOW_MIXED",
        child_public_name=child_public_name,
        expected_states=((40.0, "STATE_A"), (90.0, "STATE_B")),
    )


@pytest.mark.parametrize("oracle, checker", nested_oracle_cases())
def test_autocad_nested_oracle_replay_survives_write_read_cycle(oracle, checker):
    source_doc = ezdxf.readfile(oracle)
    replayed_doc = replay_doc_to_new_doc(source_doc)
    stream = StringIO()
    replayed_doc.write(stream)
    stream.seek(0)
    reloaded_doc = ezdxf.read(stream)

    checker(reloaded_doc)


@pytest.mark.parametrize("oracle, checker", nested_oracle_cases())
def test_autocad_nested_oracle_two_generation_replay_survives_write_read_cycle(
    oracle, checker
):
    source_doc = ezdxf.readfile(oracle)
    gen1_doc = replay_doc_to_new_doc(source_doc)
    gen2_doc = replay_doc_to_new_doc(gen1_doc)

    for doc in (gen1_doc, gen2_doc):
        stream = StringIO()
        doc.write(stream)
        stream.seek(0)
        reloaded_doc = ezdxf.read(stream)
        checker(reloaded_doc)


def test_autocad_nested_working_oracle_block_dependencies_include_dynamic_reference_targets():
    source_doc = ezdxf.readfile(NESTED_WORKING_ORACLE)
    blocks = [block for block in source_doc.blocks if not block.is_any_layout]

    dependencies = _block_dependencies(blocks)

    assert dependencies["*U1"] == {"*U0"}
    assert dependencies["*U15"] == {"*U0"}
    assert dependencies["*U16"] == {"*U2", "*U15"}


def test_autocad_nested_working_oracle_sort_blocks_orders_dynamic_bases_before_refs():
    source_doc = ezdxf.readfile(NESTED_WORKING_ORACLE)
    ordered = _sort_blocks([block for block in source_doc.blocks if not block.is_any_layout])
    order = {block.name: index for index, block in enumerate(ordered)}

    assert order["*U0"] < order["*U1"]
    assert order["*U0"] < order["*U15"]
    assert order["*U2"] < order["*U16"]
    assert order["*U15"] < order["*U16"]


def test_dynamic_block_linear_descendant_authoring_is_rejected():
    source_doc, child_public_name = build_supported_linear_visibility_replay_doc()
    child_base = next(
        block
        for block in source_doc.blocks
        if block.block_record.has_xdata("AcDbDynamicBlockTrueName2")
        and block.block_record.get_xdata("AcDbDynamicBlockTrueName2").get_first_value(1000, "")
        == child_public_name
    )
    child_ref = _add_supported_linear_visibility_reference_block(source_doc, child_base)
    child_line = next(entity for entity in child_ref if entity.dxftype() == "LINE")
    base = source_doc.blocks.new("PARENT_NESTED_DESC_LINEAR")
    parent_line = base.add_line((0, 0), (24, 0))
    base.add_blockref(child_ref.name, (40, 0))
    set_dynamic_block_visibility_parameter(
        base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="Visibility1",
            location=(0.0, 30.0, 0.0),
            states=(DynamicBlockVisibilityState("STATE_A", (parent_line.dxf.handle,)),),
        ),
        guid="{GUID}",
    )
    props = DynamicBlockPropertiesTable(
        handle="",
        label="Block Table",
        table_name="Block Table1",
        description="",
        location=(36.0, 24.0, 0.0),
        grip_location=(36.0, 24.0, 0.0),
        columns=(
            DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_1", "Block Table1"),
            DynamicBlockPropertyColumn("", "BLOCKVISIBILITYPARAMETER", "VisibilityState", "VisibilityState"),
        ),
        rows=(DynamicBlockPropertyRow(0, ("A", "STATE_A")),),
    )
    props = set_dynamic_block_properties_table(base, props)
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
    attdef = next(entity for entity in base if entity.dxftype() == "ATTDEF" and entity.dxf.tag == "PARAM_1")
    with pytest.raises(
        ezdxf.lldxf.const.DXFValueError,
        match="nested dynamic block linear descendant targets are not supported",
    ):
        set_dynamic_block_linear_parameter(
            base,
            DynamicBlockLinearParameter(
                handle="",
                label="Linear",
                parameter_name="Distance1",
                description="",
                base_point=(0.0, 0.0, 0.0),
                end_point=(12.0, 0.0, 0.0),
                distance=12.0,
                expr_id=0,
                end_grip_label="End Grip",
            ),
            DynamicBlockStretchAction(
                handle="",
                label="Stretch1",
                action_location=(12.0, -6.0, 0.0),
                x_expr_id=0,
                x_name="EndXDelta",
                y_expr_id=0,
                y_name="EndYDelta",
                selection_window=((26.0, 20.0, 0.0), (8.0, -6.0, 0.0)),
                dependency_handles=(attdef.dxf.handle, parent_line.dxf.handle, child_line.dxf.handle),
                targets=(
                    DynamicBlockStretchActionTarget(parent_line.dxf.handle, 1, (1,)),
                    DynamicBlockStretchActionTarget(child_line.dxf.handle, 1, (1,)),
                    DynamicBlockStretchActionTarget(attdef.dxf.handle, 1, (0,)),
                ),
            ),
        )


def test_dynamic_block_lookup_parameter_to_code():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    base = source_doc.blocks.new("DYN_PROP_LOOKUP_DXF2CODE")
    common1 = base.add_line((0, 0), (1, 0))
    common2 = base.add_line((0, 1), (1, 1))
    state_a = base.add_circle((1, 1), radius=0.5)
    state_b = base.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
    state_c1 = base.add_line((0, 0), (1, 1))
    state_c2 = base.add_line((0, 1), (1, 0))
    parameter = DynamicBlockVisibilityParameter(
        handle="",
        label="Visibility State",
        parameter_name="Visibility1Param",
        location=(0.0, 14.0, 0.0),
        states=(
            DynamicBlockVisibilityState(
                "STATE_A",
                (common1.dxf.handle, common2.dxf.handle, state_a.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_B",
                (common1.dxf.handle, common2.dxf.handle, state_b.dxf.handle),
            ),
            DynamicBlockVisibilityState(
                "STATE_C",
                (
                    common1.dxf.handle,
                    common2.dxf.handle,
                    state_c1.dxf.handle,
                    state_c2.dxf.handle,
                ),
            ),
        ),
    )
    set_dynamic_block_visibility_parameter(base, parameter, guid="{GUID}")
    props = DynamicBlockPropertiesTable(
        handle="",
        label="Block Table",
        table_name="Block Table1",
        description="",
        location=(32.0, 20.0, 0.0),
        grip_location=(32.0, 20.0, 0.0),
        columns=(
            DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_1", "Block Table1"),
            DynamicBlockPropertyColumn("", "ATTDEF", "PARAM_2", "Block Table1"),
            DynamicBlockPropertyColumn("", "BLOCKVISIBILITYPARAMETER", "VisibilityState", "VisibilityState"),
        ),
        rows=(
            DynamicBlockPropertyRow(0, ("A", "X", "STATE_A")),
            DynamicBlockPropertyRow(1, ("A", "Y", "STATE_B")),
            DynamicBlockPropertyRow(2, ("B", "Z", "STATE_C")),
        ),
    )
    props = set_dynamic_block_properties_table(base, props)
    grip = next(obj for obj in source_doc.objects if obj.dxftype() == "BLOCKPROPERTIESTABLEGRIP")
    base_attdefs = {entity.dxf.tag: entity for entity in base if entity.dxftype() == "ATTDEF"}
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
            props.handle,
            base_attdefs["PARAM_2"].dxf.handle,
            base_attdefs["PARAM_1"].dxf.handle,
            common1.dxf.handle,
        ),
        targets=(
            DynamicBlockStretchActionTarget(common1.dxf.handle, 2, (1, 2)),
            DynamicBlockStretchActionTarget(base_attdefs["PARAM_1"].dxf.handle, 1, (0,)),
            DynamicBlockStretchActionTarget(base_attdefs["PARAM_2"].dxf.handle, 1, (0,)),
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
    set_dynamic_block_lookup_parameter(base, lookup, (helper_action, public_action))

    def add_reference_block_and_insert(state: str, insert_point: tuple[float, float]):
        anon = source_doc.blocks.new_anonymous_block(type_char="U")
        anon.add_line((0, 0), (1, 0))
        anon.add_line((0, 1), (1, 1))
        anon.add_circle((1, 1), radius=0.5)
        anon.add_lwpolyline([(0, 0), (1, 0), (0.5, 1)], close=True)
        anon.add_line((0, 0), (1, 1))
        anon.add_line((0, 1), (1, 0))
        set_dynamic_block_reference(anon, base)
        insert = source_msp.add_blockref(anon.name, insert_point)
        set_dynamic_block_visibility_state(insert, base, state=state)
        return insert

    insert_a = add_reference_block_and_insert("STATE_A", (0, 0))
    insert_c = add_reference_block_and_insert("STATE_C", (3, 0))

    target_doc = ezdxf.new("R2018")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(base, drawing="doc"), namespace)
    execute_code_in_namespace(
        block_to_code(get_dynamic_block_reference(insert_a), drawing="doc"),
        namespace,
    )
    execute_code_in_namespace(
        block_to_code(get_dynamic_block_reference(insert_c), drawing="doc"),
        namespace,
    )
    execute_code_in_namespace(entities_to_code([insert_a, insert_c], layout="msp"), namespace)

    new_doc = namespace["doc"]
    new_inserts = list(namespace["msp"].query("INSERT"))
    new_base = new_doc.blocks.get("DYN_PROP_LOOKUP_DXF2CODE")
    new_linear = get_dynamic_block_linear_parameters(new_base)
    new_lookup = get_dynamic_block_lookup_parameters(new_base)
    new_lookup_actions = get_dynamic_block_lookup_actions(new_base)

    assert len(new_linear) == 1
    assert new_linear[0].allowed_values == (10.0, 20.0, 32.0, 40.0, 50.0)
    assert len(new_lookup) == 1
    assert new_lookup[0].parameter_name == "Lookup1"
    assert new_lookup[0].grip_label == "Grip"
    assert len(new_lookup_actions) == 2
    assert {action.label for action in new_lookup_actions} == {"Lookup1", "Lookup3"}
    assert get_dynamic_block_visibility_state(new_inserts[0]) == "STATE_A"
    assert get_dynamic_block_visibility_state(new_inserts[1]) == "STATE_C"


def test_reference_block_to_code_preserves_attdef_reactors_per_entity():
    source_doc = ezdxf.new("R2018")
    base = source_doc.blocks.new("ATTDEF_REACTOR_BASE")
    line = base.add_line((0, 0), (1, 0))
    attdef_a = base.add_attdef("PARAM_A", insert=(0, 0), text="A")
    attdef_b = base.add_attdef("PARAM_B", insert=(0, -10), text="B")
    set_dynamic_block_visibility_parameter(
        base,
        DynamicBlockVisibilityParameter(
            handle="",
            label="Visibility State",
            parameter_name="Visibility1",
            location=(0.0, 10.0, 0.0),
            states=(DynamicBlockVisibilityState("STATE_A", (line.dxf.handle,)),),
        ),
        guid="{GUID}",
    )
    props = DynamicBlockPropertiesTable(
        handle="",
        label="Block Table",
        table_name="Block Table1",
        description="",
        location=(10.0, 10.0, 0.0),
        grip_location=(10.0, 10.0, 0.0),
        columns=(
            DynamicBlockPropertyColumn(attdef_a.dxf.handle, "ATTDEF", "PARAM_A", "Block Table1"),
            DynamicBlockPropertyColumn(attdef_b.dxf.handle, "ATTDEF", "PARAM_B", "Block Table1"),
        ),
        rows=(DynamicBlockPropertyRow(0, ("A", "B")),),
    )
    set_dynamic_block_properties_table(base, props)
    set_dynamic_block_properties_editor_support(base, props)

    ref = source_doc.blocks.new_anonymous_block(type_char="U")
    ref.add_line((0, 0), (1, 0))
    set_dynamic_block_reference(ref, base)
    ref_attdefs = [entity for entity in ref if entity.dxftype() == "ATTDEF"]
    assert len(ref_attdefs) == 2
    ref_attdefs[1].set_reactors([])

    target_doc = ezdxf.new("R2018")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(base, drawing="doc"), namespace)
    execute_code_in_namespace(block_to_code(ref, drawing="doc"), namespace)

    new_ref = target_doc.blocks.get(ref.name)
    assert new_ref is not None
    new_ref_attdefs = [entity for entity in new_ref if entity.dxftype() == "ATTDEF"]

    assert len(new_ref_attdefs[0].get_reactors()) == 1
    assert new_ref_attdefs[1].get_reactors() == []


def test_dynamic_insert_extension_subtree_handle_map_uses_stable_entity_map_target():
    source_doc, _public_name = build_supported_linear_visibility_replay_doc()
    insert = next(entity for entity in source_doc.modelspace().query("INSERT"))

    code = entities_to_code([insert], layout="msp")
    text = str(code)

    assert (
        f'map_extension_subtree_handles(_entity_map["{insert.dxf.handle}"]'
        in text
    )


if __name__ == "__main__":
    pytest.main([__file__])
