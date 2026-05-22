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
    table_entries_to_code,
    block_to_code,
    _SourceCodeGenerator,
)
from ezdxf.addons.dxf2code import (
    _fmt_mapping,
    _fmt_list,
    _fmt_api_call,
    _fmt_dxf_tags,
)
from ezdxf.fidelity import finalize_document_fidelity, prepare_document_fidelity
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
    get_dynamic_block_record_handle,
    get_dynamic_block_reference,
    get_dynamic_block_stretch_actions,
    get_dynamic_block_visibility_entities,
    get_dynamic_block_visibility_state,
    get_dynamic_block_visibility_states,
    register_source_entity_handle_mapping,
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
from ezdxf.lldxf.types import dxftag, is_pointer_code
from ezdxf.lldxf.tags import Tags  # required by exec() or eval()
from ezdxf.entities.ltype import LinetypePattern  # required by exec() or eval()
from ezdxf.math import Vec2, Vec3

doc = ezdxf.new("R2010")
msp = doc.modelspace()
NESTED_WORKING_ORACLE = Path(__file__).parent / "autocad_nested_working_minimal_v1_edited.dxf"
NESTED_RICHER_CHILD_ORACLE = Path(__file__).parent / "autocad_nested_richer_child_gen2_v1.dxf"
NESTED_TWO_CHILDREN_ORACLE = Path(__file__).parent / "autocad_nested_two_children_candidate_gen2.dxf"
NESTED_TWO_CHILDREN_MIXED_ORACLE = Path(__file__).parent / "autocad_nested_two_children_mixed_states_gen2_v2.dxf"
NESTED_THREE_LEVEL_MIXED_ORACLE = Path(__file__).parent / "autocad_nested_three_level_mixed_gen2_v3.dxf"
def test_fmt_mapping():
    d = {"a": 1, "b": "str", "c": Vec3(), "d": "xxx \"yyy\" 'zzz'"}
    r = list(_fmt_mapping(d))
    assert r[0] == "'a': 1,"
    assert r[1] == "'b': \"str\","
    assert r[2] == "'c': (0.0, 0.0, 0.0),"
    assert r[3] == "'d': \"xxx \\\"yyy\\\" 'zzz'\","


def test_fmt_int_list():
    l = [1, 2, 3]
    r = list(_fmt_list(l))
    assert r[0] == "1,"
    assert r[1] == "2,"
    assert r[2] == "3,"


def test_fmt_float_list():
    l = [1.0, 2.0, 3.0]
    r = list(_fmt_list(l))
    assert r[0] == "1.0,"
    assert r[1] == "2.0,"
    assert r[2] == "3.0,"


def test_fmt_vector_list():
    from ezdxf.math import Vec3

    l = [Vec3(), (1.0, 2.0, 3.0)]
    r = list(_fmt_list(l))
    assert r[0] == "(0.0, 0.0, 0.0),"
    assert r[1] == "(1.0, 2.0, 3.0),"


def test_fmt_api_call():
    r = _fmt_api_call(
        "msp.add_line(",
        ["start", "end"],
        dxfattribs={"start": (0, 0), "end": (1, 0), "color": 7},
    )
    assert r[0] == "msp.add_line("
    assert r[1] == "    start=(0, 0),"
    assert r[2] == "    end=(1, 0),"
    assert r[3] == "    dxfattribs={"
    assert r[4] == "        'color': 7,"
    assert r[5] == "    },"
    assert r[6] == ")"


def test_fmt_dxf_tags():
    tags = [dxftag(1, "TEXT"), dxftag(10, (1, 2, 3))]
    code = "[{}]".format("".join(_fmt_dxf_tags(tags)))
    r = eval(code, globals())
    assert r == tags


def translate_to_code_and_execute(entity):
    code = entities_to_code([entity], layout="msp")
    exec(code.import_str() + "\n" + str(code), globals())
    return msp[-1]


def translate_entities_to_new_layout(entities):
    target_doc = ezdxf.new("R2010")
    return execute_entities_code_in_doc(entities, target_doc)


def execute_entities_code_in_doc(entities, target_doc):
    target_msp = target_doc.modelspace()
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_msp}
    code = entities_to_code(entities, layout="msp")
    execute_code_in_namespace(code, namespace)
    return target_doc, target_msp


def execute_code_in_namespace(code, namespace):
    exec(code.import_str() + "\n" + str(code), namespace)


def _normalize_handle_refs_in_text(text: str) -> str:
    lines = text.replace("\r\n", "\n").split("\n")
    normalized: list[str] = []
    index = 0
    while index < len(lines):
        code_line = lines[index]
        normalized.append(code_line)
        if index + 1 >= len(lines):
            break
        value_line = lines[index + 1]
        try:
            code = int(code_line.strip())
        except ValueError:
            normalized.append(value_line)
            index += 2
            continue
        if code in (5, 105, 1005) or is_pointer_code(code):
            normalized.append("<REF>")
        else:
            normalized.append(value_line)
        index += 2
    return "\n".join(normalized)


def _export_text(entity, dxfversion: str) -> str:
    stream = StringIO()
    entity.export_dxf(TagWriter(stream, dxfversion=dxfversion))
    return stream.getvalue()


def _names(table) -> set[str]:
    return {entry.dxf.name for entry in table}


def _maybe_get(table, name: str):
    try:
        return table.get(name)
    except Exception:
        return None


def _resource_entities(doc: ezdxf.document.Drawing) -> list:
    default_doc = ezdxf.new(doc.dxfversion)
    entities: list = []

    active_viewports = doc.viewports.get("*Active")
    if active_viewports:
        entities.append(active_viewports[0])

    for name in sorted(_names(doc.layers) - _names(default_doc.layers)):
        entity = _maybe_get(doc.layers, name)
        if entity is not None:
            entities.append(entity)
    for name in sorted(_names(doc.linetypes) - _names(default_doc.linetypes)):
        entity = _maybe_get(doc.linetypes, name)
        if entity is not None:
            entities.append(entity)
    for name in sorted(_names(doc.styles) - _names(default_doc.styles)):
        entity = _maybe_get(doc.styles, name)
        if entity is not None:
            entities.append(entity)
    for name in sorted(_names(doc.dimstyles) - _names(default_doc.dimstyles)):
        entity = _maybe_get(doc.dimstyles, name)
        if entity is not None:
            entities.append(entity)
    for name in sorted(_names(doc.appids) - _names(default_doc.appids)):
        entity = _maybe_get(doc.appids, name)
        if entity is not None:
            entities.append(entity)
    for name in sorted(
        set(doc.mleader_styles.object_dict.keys())
        - set(default_doc.mleader_styles.object_dict.keys())
    ):
        entity = doc.mleader_styles.get(name)
        if entity is not None:
            entities.append(entity)
    for name in sorted(
        set(doc.table_styles.object_dict.keys())
        - set(default_doc.table_styles.object_dict.keys())
    ):
        entity = doc.table_styles.get(name)
        if entity is not None:
            entities.append(entity)
    return entities


def _block_dependencies(blocks) -> dict[str, set[str]]:
    block_by_name = {block.name: block for block in blocks}
    block_by_record_handle = {
        block.block_record_handle: block
        for block in blocks
        if block.block_record_handle
    }
    dependencies: dict[str, set[str]] = {block.name: set() for block in blocks}
    for block in blocks:
        deps = dependencies[block.name]
        base_handle = get_dynamic_block_record_handle(block.block_record)
        if base_handle:
            base_block = block_by_record_handle.get(base_handle)
            if base_block is not None and base_block.name != block.name:
                deps.add(base_block.name)
        for entity in block:
            if entity.dxftype() != "INSERT":
                continue
            name = entity.dxf.name
            if name in block_by_name and name != block.name:
                deps.add(name)
    return dependencies


def _sort_blocks(blocks):
    dependencies = _block_dependencies(blocks)
    block_by_name = {block.name: block for block in blocks}
    ordered: list = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited or name in visiting:
            return
        visiting.add(name)
        for dep in dependencies.get(name, ()): 
            visit(dep)
        visiting.remove(name)
        visited.add(name)
        ordered.append(block_by_name[name])

    for block in blocks:
        visit(block.name)
    return ordered


def replay_doc_to_new_doc(source_doc: ezdxf.document.Drawing) -> ezdxf.document.Drawing:
    target_doc = ezdxf.new(source_doc.dxfversion)
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    resources = _resource_entities(source_doc)
    if resources:
        execute_code_in_namespace(table_entries_to_code(resources, drawing="doc"), namespace)
    prepare_document_fidelity(source_doc, target_doc)
    blocks = _sort_blocks([block for block in source_doc.blocks if not block.is_any_layout])
    for block in blocks:
        target_block = target_doc.blocks.get(block.name)
        if target_block is not None:
            target_doc.blocks.delete_block(block.name, safe=False)
            target_block = None
        execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)
        target_block = target_doc.blocks.get(block.name)
        if target_block is None:
            continue
        register_source_entity_handle_mapping(block.block_record, target_block.block_record)
        if block.block is not None and target_block.block is not None:
            register_source_entity_handle_mapping(block.block, target_block.block)
        if block.endblk is not None and target_block.endblk is not None:
            register_source_entity_handle_mapping(block.endblk, target_block.endblk)
    execute_code_in_namespace(entities_to_code(source_doc.modelspace(), layout="msp"), namespace)
    finalize_document_fidelity(source_doc, target_doc)
    return target_doc


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


def test_insert_xdata_replay_preserves_nonhandle_payload():
    source_doc = ezdxf.new("R2018")
    block = source_doc.blocks.new("XDATA_BLOCK")
    block.add_line((0, 0), (1, 0))
    insert = source_doc.modelspace().add_blockref(block.name, (0, 0))
    insert.set_xdata(
        "AcadAnnotativeAttributeDecomposition",
        [
            (1000, "AnnotativeData"),
            (1002, "{"),
            (1070, 1),
            (1070, 1),
            (1002, "}"),
        ],
    )

    new_doc = replay_doc_to_new_doc(source_doc)
    new_insert = list(new_doc.modelspace().query("INSERT"))[0]

    assert list(new_insert.get_xdata("AcadAnnotativeAttributeDecomposition")) == [
        (1000, "AnnotativeData"),
        (1002, "{"),
        (1070, 1),
        (1070, 1),
        (1002, "}"),
    ]


def test_header_material_handle_replay_maps_by_material_name():
    source_doc = ezdxf.new("R2010")
    material = source_doc.materials.get("ByLayer")
    source_doc.header["$CMATERIAL"] = material.dxf.handle

    new_doc = replay_doc_to_new_doc(source_doc)

    assert new_doc.header["$CMATERIAL"] == new_doc.materials.get("ByLayer").dxf.handle


def test_layer_material_handle_replay_maps_by_material_name():
    source_doc = ezdxf.new("R2010")
    source_doc.layers.new("MATERIAL_LAYER")

    new_doc = replay_doc_to_new_doc(source_doc)

    layer = new_doc.layers.get("MATERIAL_LAYER")
    assert layer is not None
    assert layer.dxf.material_handle == new_doc.materials.get("Global").dxf.handle


def test_layer_extension_subtree_replay_remaps_external_handles():
    source_doc = ezdxf.new("R2018")
    ref_layer = source_doc.layers.new("U-MISC")
    annotated_layer = source_doc.layers.new("U-MISC @ 1")
    material = source_doc.materials.get("Global")
    assert source_doc.entitydb.reset_handle(ref_layer, "1A2C") is True
    assert source_doc.entitydb.reset_handle(material, "1A2D") is True
    xdict = annotated_layer.new_extension_dict().dictionary
    xrecord = xdict.add_xrecord("ASDK_XREC_ANNO_SCALE_INFO")
    xrecord.set_reactors([xdict.dxf.handle])
    xrecord.reset(
        [
            (70, 1),
            (340, material.dxf.handle),
            (340, ref_layer.dxf.handle),
            (70, -1),
        ]
    )

    new_doc = replay_doc_to_new_doc(source_doc)

    replayed_layer = new_doc.layers.get("U-MISC @ 1")
    replayed_ref = new_doc.layers.get("U-MISC")
    replayed_material = new_doc.materials.get("Global")
    assert replayed_layer is not None
    assert replayed_ref is not None
    assert replayed_material is not None
    assert replayed_ref.dxf.handle != ref_layer.dxf.handle
    assert replayed_material.dxf.handle != material.dxf.handle

    snapshot = snapshot_raw_extension_subtree(replayed_layer)
    pointer_values = [value for code, value in snapshot[1] if code == 340]

    assert pointer_values == [replayed_material.dxf.handle, replayed_ref.dxf.handle]


def test_dimstyle_raw_replay_aligns_runtime_handle_with_raw_export_handle():
    source_doc = ezdxf.new("R2018")
    dimstyle = source_doc.dimstyles.new("RAW_HANDLE_STYLE")

    assert source_doc.entitydb.reset_handle(dimstyle, "1FE") is True

    new_doc = replay_doc_to_new_doc(source_doc)

    replayed = new_doc.dimstyles.get("RAW_HANDLE_STYLE")
    assert replayed is not None
    assert replayed.dxf.handle == "1FE"
    assert new_doc.entitydb.get("1FE") is replayed


def test_restore_raw_dimstyle_export_remaps_handle_105_on_collision():
    source_doc = ezdxf.new("R2018")
    source_dimstyle = source_doc.dimstyles.new("RAW_HANDLE_STYLE")
    assert source_doc.entitydb.reset_handle(source_dimstyle, "1FE") is True
    snapshot = snapshot_raw_entity_export(source_dimstyle)

    target_doc = ezdxf.new("R2018")
    blocker = target_doc.modelspace().add_circle((0, 0), 1)
    assert target_doc.entitydb.reset_handle(blocker, "1FE") is True
    target_dimstyle = target_doc.dimstyles.new("RAW_HANDLE_STYLE")

    restore_raw_entity_export(target_dimstyle, snapshot)
    exported = ExtendedTags.from_text(snapshot_raw_entity_export(target_dimstyle)[0])

    assert target_dimstyle.dxf.handle != "1FE"
    assert exported.get_handle() == target_dimstyle.dxf.handle


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


def test_line_to_code():
    from ezdxf.entities.line import Line

    entity = Line.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "start": (1, 2, 3),
            "end": (4, 5, 6),
        },
    )

    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "start", "end"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_point_to_code():
    from ezdxf.entities.point import Point

    entity = Point.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "location": (1, 2, 3),
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "location"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_circle_to_code():
    from ezdxf.entities.circle import Circle

    entity = Circle.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "center": (1, 2, 3),
            "radius": 2,
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "center", "radius"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_arc_to_code():
    from ezdxf.entities.arc import Arc

    entity = Arc.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "center": (1, 2, 3),
            "radius": 2,
            "start_angle": 30,
            "end_angle": 60,
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "center", "radius", "start_angle", "end_angle"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_text_to_code():
    from ezdxf.entities.text import Text

    entity = Text.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "text": "xyz",
            "insert": (2, 3, 4),
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "text", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_solid_to_code():
    from ezdxf.entities.solid import Solid

    entity = Solid.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "vtx0": (1, 2, 3),
            "vtx1": (4, 5, 6),
            "vtx2": (7, 8, 9),
            "vtx3": (3, 2, 1),
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("vtx0", "vtx1", "vtx2", "vtx3"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_shape_to_code():
    from ezdxf.entities.shape import Shape

    entity = Shape.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "name": "shape_name",
            "insert": (2, 3, 4),
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "name", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_ellipse_to_code():
    from ezdxf.entities.ellipse import Ellipse

    entity = Ellipse.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "center": (1, 2, 3),
            "major_axis": (2, 0, 0),
            "ratio": 0.5,
            "start_param": 1,
            "end_param": 3,
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in (
        "color",
        "center",
        "major_axis",
        "ratio",
        "start_param",
        "end_param",
    ):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_insert_to_code():
    from ezdxf.entities.insert import Insert

    entity = Insert.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "name": "block1",
            "insert": (2, 3, 4),
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("name", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_insert_with_attrib_to_code():
    source_doc = ezdxf.new("R2010")
    source_doc.blocks.new("ATTRIB_BLOCK")
    source_msp = source_doc.modelspace()
    insert = source_msp.add_blockref("ATTRIB_BLOCK", (2, 3, 4))
    insert.add_attrib("TAG1", "Text1", (5, 6, 7))

    _, new_msp = translate_entities_to_new_layout([insert])
    new_insert = next(entity for entity in new_msp if entity.dxftype() == "INSERT")

    assert len(new_insert.attribs) == 1
    assert len([entity for entity in new_msp if entity.dxftype() == "ATTRIB"]) == 0
    assert new_insert.attribs[0].dxf.tag == "TAG1"
    assert new_insert.attribs[0].dxf.text == "Text1"


def test_attdef_to_code():
    from ezdxf.entities.attrib import AttDef

    entity = AttDef.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "tag": "TAG1",
            "text": "Text1",
            "insert": (2, 3, 4),
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("tag", "text", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_mtext_to_code():
    from ezdxf.entities.mtext import MText

    entity = MText.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "insert": (2, 3, 4),
        },
    )
    text = "xxx \"yyy\" 'zzz'"
    entity.text = text
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)
    assert new_entity.text == "xxx \"yyy\" 'zzz'"


def test_mtext_to_code_preserves_explicit_optional_line_spacing_style():
    from ezdxf.entities.mtext import MText

    entity = MText.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "insert": (2, 3, 4),
            "line_spacing_style": 1,
        },
    )

    new_entity = translate_to_code_and_execute(entity)
    stream = StringIO()
    new_entity.export_dxf(TagWriter(stream, dxfversion=new_entity.doc.dxfversion))
    tags = ExtendedTags.from_text(stream.getvalue())

    assert any(tag.code == 73 and tag.value == 1 for tag in tags)


def test_mtext_to_code_preserves_explicit_optional_line_spacing_factor():
    from ezdxf.entities.mtext import MText

    entity = MText.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "insert": (2, 3, 4),
            "line_spacing_factor": 1.0,
        },
    )

    new_entity = translate_to_code_and_execute(entity)
    stream = StringIO()
    new_entity.export_dxf(TagWriter(stream, dxfversion=new_entity.doc.dxfversion))
    tags = ExtendedTags.from_text(stream.getvalue())

    assert any(tag.code == 44 and tag.value == 1.0 for tag in tags)


def test_wipeout_to_code_preserves_proxy_graphic_payload():
    source_doc = ezdxf.new("R2010")
    wipeout = source_doc.modelspace().add_wipeout([(0, 0), (2, 0), (2, 1), (0, 1)])
    wipeout.proxy_graphic = b"\x01\x02\x03\x04"

    _, new_msp = translate_entities_to_new_layout([wipeout])
    new_entity = new_msp[0]
    stream = StringIO()
    new_entity.export_dxf(TagWriter(stream, dxfversion=new_entity.doc.dxfversion))
    text = stream.getvalue().replace("\r\n", "\n")

    assert new_entity.proxy_graphic == wipeout.proxy_graphic
    assert "\n 92\n4\n310\n01020304\n" in text


def test_insert_attrib_to_code_preserves_explicit_attrib_layer():
    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("ATTRIB_LAYER_BLOCK")
    insert = block.add_blockref(
        "TEST_REF", (0, 0), dxfattribs={"layer": "INSERT_LAYER"}
    )
    insert.add_attrib(
        "TAG",
        "TEXT",
        insert=(1, 2),
        dxfattribs={"layer": "ATTRIB_LAYER"},
    )

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)

    new_insert = next(
        e
        for e in namespace["doc"].blocks.get("ATTRIB_LAYER_BLOCK")
        if e.dxftype() == "INSERT"
    )

    assert new_insert.attribs[0].dxf.layer == "ATTRIB_LAYER"


def test_insert_attrib_to_code_preserves_context_data_subtree():
    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("ATTRIB_CONTEXT_BLOCK")
    insert = block.add_blockref("TEST_REF", (0, 0))
    attrib = insert.add_attrib("TAG", "TEXT", insert=(1, 2))
    xdict = attrib.new_extension_dict()
    mgr = xdict.dictionary.add_new_dict("AcDbContextDataManager")
    mgr.add_new_dict("ACDB_ANNOTATIONSCALES")

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)

    new_insert = next(
        e
        for e in namespace["doc"].blocks.get("ATTRIB_CONTEXT_BLOCK")
        if e.dxftype() == "INSERT"
    )
    new_attrib = new_insert.attribs[0]

    assert new_attrib.has_extension_dict is True
    assert new_attrib.get_extension_dict().dictionary.dxf.owner == new_attrib.dxf.handle
    new_mgr = new_attrib.get_extension_dict().dictionary.get("AcDbContextDataManager")
    assert new_mgr is not None
    assert new_mgr.dxf.owner == new_attrib.get_extension_dict().dictionary.dxf.handle
    assert new_mgr.get("ACDB_ANNOTATIONSCALES") is not None


def test_block_to_code_preserves_block_record_preview_data():
    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("BLOCK_PREVIEW_DATA")
    block.add_line((0, 0), (1, 0))
    block.block_record.preview_data = bytes.fromhex("01020304")

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)

    new_block = namespace["doc"].blocks.get("BLOCK_PREVIEW_DATA")

    assert new_block.block_record.preview_data == block.block_record.preview_data


def test_lwpolyline_to_code():
    from ezdxf.entities.lwpolyline import LWPolyline

    entity = LWPolyline.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
        },
    )
    entity.set_points(
        [
            (1, 2, 0, 0, 0),
            (4, 3, 0, 0, 0),
            (7, 8, 0, 0, 0),
        ]
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "count"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)
    for np, ep in zip(new_entity.get_points(), entity.get_points()):
        assert np == ep


def test_polyline_to_code():
    # POLYLINE does not work without an entity space
    polyline = msp.add_polyline3d(
        [
            (1, 2, 3),
            (2, 3, 7),
            (9, 3, 1),
            (4, 4, 4),
            (0, 5, 8),
        ]
    )

    new_entity = translate_to_code_and_execute(polyline)
    # Are the last two entities POLYLINE entities?
    assert msp[-2].dxftype() == msp[-1].dxftype()
    assert len(new_entity) == len(polyline)
    assert new_entity.dxf.flags == polyline.dxf.flags
    for np, ep in zip(new_entity.points(), polyline.points()):
        assert np == ep


def cmp_vertices(a, b):
    return all(Vec3(v0).isclose(v1) for v0, v1 in zip(a, b))


def test_spline_to_code():
    from ezdxf.entities.spline import Spline

    entity = Spline.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "degree": 3,
        },
    )
    entity.fit_points = [(1, 2, 0), (4, 3, 0), (7, 8, 0)]
    entity.control_points = [(1, 2, 0), (4, 3, 0), (7, 8, 0)]
    entity.knots = [1, 2, 3, 4, 5, 6, 7]
    entity.weights = [1.0, 2.0, 3.0]
    new_entity = translate_to_code_and_execute(entity)
    for name in (
        "color",
        "n_knots",
        "n_control_points",
        "n_fit_points",
        "degree",
    ):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)

    assert new_entity.knots == entity.knots
    assert cmp_vertices(new_entity.control_points, entity.control_points) is True
    assert cmp_vertices(new_entity.fit_points, entity.fit_points) is True
    assert new_entity.weights == entity.weights


def test_leader_to_code():
    from ezdxf.entities.leader import Leader

    entity = Leader.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
        },
    )
    entity.set_vertices(
        [
            (1, 2, 0),
            (4, 3, 0),
            (7, 8, 0),
        ]
    )
    new_entity = translate_to_code_and_execute(entity)
    assert new_entity.dxf.color == entity.dxf.color
    for np, ep in zip(new_entity.vertices, entity.vertices):
        assert np == ep


def test_mesh_to_code():
    from ezdxf.entities.mesh import Mesh
    from ezdxf.render.forms import cube

    entity = Mesh.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
        },
    )
    c = cube()
    entity.vertices = c.vertices
    entity.faces = c.faces

    assert len(entity.vertices) == 8
    new_entity = translate_to_code_and_execute(entity)
    assert cmp_vertices(entity.vertices, new_entity.vertices) is True
    assert list(entity.faces) == list(new_entity.faces)


def test_layer_entry():
    from ezdxf.entities.layer import Layer

    layer = Layer.new("LAYER", dxfattribs={"name": "TestTest", "color": 3})
    code = table_entries_to_code([layer], drawing="doc")
    exec(str(code), globals())
    layer = doc.layers.get("TestTest")
    assert layer.dxf.color == 3


def test_ltype_entry():
    from ezdxf.entities.ltype import Linetype

    ltype = Linetype.new(
        "FFFF",
        dxfattribs={
            "name": "TEST",
            "description": "TESTDESC",
        },
    )
    ltype.setup_pattern([0.2, 0.1, -0.1])
    code = table_entries_to_code([ltype], drawing="doc")
    exec(str(code), globals())
    new_ltype = doc.linetypes.get("TEST")
    assert new_ltype.dxf.description == ltype.dxf.description
    assert new_ltype.pattern_tags.tags == ltype.pattern_tags.tags
    # all imports added
    assert any(line.endswith("Tags") for line in code.imports)
    assert any(line.endswith("dxftag") for line in code.imports)
    assert any(line.endswith("LinetypePattern") for line in code.imports)


def test_mleaderstyle_entry():
    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "TEST_STYLE")
    style.dxf.default_text_content = "STYLE_TEXT"
    style.dxf.char_height = 3.5
    style.set_arrow_head("DOT")

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc}
    code = table_entries_to_code([style], drawing="doc")
    execute_code_in_namespace(code, namespace)
    new_style = target_doc.mleader_styles.get("TEST_STYLE")

    assert new_style is not None
    assert new_style.dxf.default_text_content == "STYLE_TEXT"
    assert new_style.dxf.char_height == 3.5
    assert target_doc.entitydb.get(new_style.dxf.arrow_head_handle).dxf.name == "_DOT"


def test_mleaderstyle_entry_missing_block_handle_is_safe():
    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "TEST_STYLE")
    source_doc.blocks.new("STYLE_BLOCK")
    style.dxf.block_record_handle = source_doc.blocks.get(
        "STYLE_BLOCK"
    ).block_record_handle

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc}
    code = table_entries_to_code([style], drawing="doc")
    execute_code_in_namespace(code, namespace)
    new_style = target_doc.mleader_styles.get("TEST_STYLE")

    assert new_style is not None
    assert new_style.dxf.hasattr("block_record_handle") is False


def test_mleaderstyle_entry_uses_object_dict_key_when_entity_name_diverges():
    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "TEST_STYLE")
    style.dxf.name = "Standard"
    style.dxf.default_text_content = "STYLE_TEXT"

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc}
    code = table_entries_to_code([style], drawing="doc")
    execute_code_in_namespace(code, namespace)
    new_style = target_doc.mleader_styles.get("TEST_STYLE")

    assert new_style is not None
    assert new_style.dxf.default_text_content == "STYLE_TEXT"


def test_dimstyle_replay_preserves_normalized_raw_export():
    source_doc = ezdxf.new("R2010")
    source_doc.styles.new("DIM_TXT", dxfattribs={"font": "txt"})
    ltype = source_doc.linetypes.new("DIM_LT", dxfattribs={"description": "DIM_LT"})
    ltype.setup_pattern([0.2, 0.1, -0.1])
    arrow = source_doc.blocks.new("DIM_ARROW")
    arrow.add_line((0, 0), (1, 0))

    dimstyle = source_doc.dimstyles.new("TEST_DIMSTYLE")
    dimstyle.dxf.dimtxsty = "DIM_TXT"
    dimstyle.dxf.dimblk = "DIM_ARROW"
    dimstyle.dxf.dimldrblk = "DIM_ARROW"
    dimstyle.dxf.dimltype = "DIM_LT"
    dimstyle.dxf.dimltex1 = "DIM_LT"
    dimstyle.dxf.dimltex2 = "DIM_LT"
    dimstyle.set_xdata(
        "ACAD_DSTYLE_DIMBREAK",
        [(1070, 391), (1040, 0.125)],
    )

    new_doc = replay_doc_to_new_doc(source_doc)
    new_dimstyle = new_doc.dimstyles.get("TEST_DIMSTYLE")

    assert new_dimstyle is not None
    assert new_dimstyle.dxf.dimtxsty == "DIM_TXT"
    assert new_dimstyle.dxf.dimblk == "DIM_ARROW"
    assert new_dimstyle.dxf.dimldrblk == "DIM_ARROW"
    assert new_dimstyle.dxf.dimltype == "DIM_LT"
    assert new_dimstyle.dxf.dimltex1 == "DIM_LT"
    assert new_dimstyle.dxf.dimltex2 == "DIM_LT"
    assert _normalize_handle_refs_in_text(
        _export_text(new_dimstyle, new_doc.dxfversion)
    ) == _normalize_handle_refs_in_text(_export_text(dimstyle, source_doc.dxfversion))


def test_block_to_code():
    testdoc = ezdxf.new()
    block = testdoc.blocks.new("TestBlock", dxfattribs={"description": "test"})
    block.add_line((1, 1), (2, 2))
    code = block_to_code(block, drawing="doc")
    exec(str(code), globals())
    new_block = doc.blocks.get("TestBlock")
    assert new_block.block.dxf.description == block.block.dxf.description
    assert new_block[0].dxftype() == block[0].dxftype()


def test_hatch_to_code():
    from ezdxf.entities import Hatch

    hatch = Hatch()
    hatch.set_pattern_fill(name="ANGLE")
    hatch.paths.add_polyline_path(
        [(0, 0), (100, 0), (100, 100), (0, 100)], is_closed=True
    )

    new_hatch = translate_to_code_and_execute(hatch)
    assert isinstance(new_hatch, Hatch)
    assert new_hatch.has_pattern_fill
    assert len(new_hatch.pattern.lines) == len(hatch.pattern.lines)


def test_text_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    text = source_msp.add_text("----")
    child, _ = text.new_acvar_field(
        "Author", text="----", register_field_list=True
    )

    new_doc, new_msp = translate_entities_to_new_layout([text])
    new_text = new_msp[-1]
    new_child = new_text.get_primary_field("TEXT")

    assert new_text.dxf.text == text.dxf.text
    assert new_child.field_code == child.field_code
    assert new_doc.objects.get_field_list() is not None


def test_mtext_object_property_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (2, 0))
    mtext = source_msp.add_mtext("0")
    child, _ = mtext.new_acobjprop_field(
        line, "Length", register_field_list=True
    )

    _, new_msp = translate_entities_to_new_layout([line, mtext])
    new_line = new_msp[0]
    new_mtext = new_msp[1]
    new_child = new_mtext.get_primary_field("TEXT")

    assert new_child.field_code == child.field_code
    assert new_child.object_handles == [new_line.dxf.handle]


def test_text_acexpr_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (10, 0))
    circle = source_msp.add_circle((5, 0), radius=2.5)
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    txt = source_msp.add_text_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    _, new_msp = translate_entities_to_new_layout([line, circle, txt])
    new_line = new_msp[0]
    new_circle = new_msp[1]
    new_text = new_msp[2]
    new_expr = new_text.get_primary_field("TEXT")

    assert new_expr is not None
    assert new_expr.evaluator_id == "AcExpr"
    assert new_expr.field_code == "\\AcExpr (%<\\_FldIdx 0>%*%<\\_FldIdx 1>%) \\f \"%lu2\""
    children = new_expr.get_child_fields()
    assert len(children) == 2
    assert children[0].object_handles == [new_line.dxf.handle]
    assert children[1].object_handles == [new_circle.dxf.handle]


def test_document_to_code_file_generates_executable_full_doc_script(tmp_path):
    source_doc = ezdxf.new("R2010")
    line = source_doc.modelspace().add_line((0, 0), (1, 0))
    source_doc.header["$LASTSAVEDBY"] = "tester"
    source_doc.header.custom_vars.append("CustomTag", "CustomValue")
    xrecord = source_doc.objects.add_xrecord(owner=source_doc.rootdict.dxf.handle)
    xrecord.set_reactors([source_doc.rootdict.dxf.handle])
    xrecord.tags.extend([(90, 1), (330, line.dxf.handle)])
    source_doc.rootdict.add("ACDB_RECOMPOSE_DATA", xrecord)

    source_path = tmp_path / "source_doc.dxf"
    script_path = tmp_path / "generated_doc.py"
    output_path = tmp_path / "generated_doc.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    script_text = script_path.read_text(encoding="utf-8")

    assert "from ezdxf.addons._dxf2code_runtime import DocumentCodegenRuntime" in script_text
    assert "rt = DocumentCodegenRuntime(doc)" in script_text
    assert "def _add_raw_object(" not in script_text
    assert "def _swap_raw_graphic_entity(" not in script_text

    exec(script_text, {})

    out_doc = ezdxf.readfile(output_path)
    out_line = out_doc.modelspace()[0]
    restored = out_doc.rootdict.get("ACDB_RECOMPOSE_DATA")

    assert script_path.exists()
    assert output_path.exists()
    assert out_doc.header["$LASTSAVEDBY"] == "tester"
    assert list(out_doc.header.custom_vars) == [("CustomTag", "CustomValue")]
    assert restored is not None
    assert f"330\n{out_line.dxf.handle}\n" in _export_text(restored, out_doc.dxfversion)


def test_document_codegen_runtime_remaps_dangling_fieldlist_handles_once():
    from ezdxf.addons._dxf2code_runtime import DocumentCodegenRuntime

    runtime_doc = ezdxf.new("R2010")
    line = runtime_doc.modelspace().add_line((0, 0), (1, 0))
    rt = DocumentCodegenRuntime(runtime_doc)
    rt.source_entity_map["LINE_SRC"] = line

    mapped = rt.remap_fieldlist_handles(["LINE_SRC", "DANGLE", "DANGLE"], {"DANGLE"})

    assert mapped[0] == line.dxf.handle
    assert mapped[1] == mapped[2]
    assert mapped[1] != "DANGLE"


def test_capture_document_codegen_inputs_returns_typed_specs(tmp_path):
    from ezdxf.addons._dxf2code_capture import capture_document_codegen_inputs
    from ezdxf.addons._dxf2code_specs import MLeaderStyleSpec, VisualStyleEntry

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "TEST_STYLE")
    style.set_xdata("ACAD_MLEADERVER", [(1070, 2)])
    source_doc.rootdict.get_required_dict("ACAD_VISUALSTYLE")

    source_path = tmp_path / "capture_source.dxf"
    source_doc.saveas(source_path)
    loaded = ezdxf.readfile(source_path)

    captured = capture_document_codegen_inputs(loaded, source_path)

    assert "mleader_style_specs" in captured
    assert all(isinstance(spec, MLeaderStyleSpec) for spec in captured["mleader_style_specs"])
    assert all(isinstance(entry, VisualStyleEntry) for entry in captured["visualstyle_entries"])


def test_mtext_acexpr_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (10, 0))
    circle = source_msp.add_circle((5, 0), radius=2.5)
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    mtext = source_msp.add_mtext_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    _, new_msp = translate_entities_to_new_layout([line, circle, mtext])
    new_line = new_msp[0]
    new_circle = new_msp[1]
    new_mtext = new_msp[2]
    new_expr = new_mtext.get_primary_field("TEXT")

    assert new_expr is not None
    assert new_expr.evaluator_id == "AcExpr"
    children = new_expr.get_child_fields()
    assert len(children) == 2
    assert children[0].object_handles == [new_line.dxf.handle]
    assert children[1].object_handles == [new_circle.dxf.handle]


def test_insert_attrib_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    insert = source_msp.add_blockref("TEST", (0, 0))
    attrib = insert.add_attrib("TAG", "VALUE", (0, 0))
    child, _ = attrib.new_dwgprops_field(
        "ProjectCode",
        value="VALUE-123",
        text="VALUE-123",
        register_field_list=True,
    )

    new_doc, new_msp = translate_entities_to_new_layout([insert])
    new_insert = next(entity for entity in new_msp if entity.dxftype() == "INSERT")
    new_attrib = new_insert.attribs[0]
    new_child = new_attrib.get_primary_field("TEXT")

    assert new_child.field_code == child.field_code
    assert new_doc.header.custom_vars.get("ProjectCode") == "VALUE-123"


def test_multileader_mtext_to_code():
    from ezdxf.render.mleader import ConnectionSide, TextAlignment

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content(
        "note", color=3, char_height=2.5, alignment=TextAlignment.right
    )
    builder.set_connection_properties(landing_gap=2.0, dogleg_length=4.0)
    builder.set_overall_scaling(1.25)
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    _, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]

    assert new_ml.dxftype() == "MULTILEADER"
    assert new_ml.context.mtext is not None
    assert new_ml.context.mtext.default_content == "note"
    assert new_ml.context.mtext.alignment == 3
    assert new_ml.context.char_height == builder.multileader.context.char_height
    assert len(new_ml.context.leaders) == 1
    assert len(new_ml.context.leaders[0].lines) == 1
    assert cmp_vertices(
        new_ml.context.leaders[0].lines[0].vertices,
        builder.multileader.context.leaders[0].lines[0].vertices,
    ) is True
    assert len(list(new_ml.virtual_entities())) == len(
        list(builder.multileader.virtual_entities())
    )


def test_multileader_field_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    child, _ = builder.set_acvar_field(
        "Author", text="----", register_field_list=True
    )
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_child = new_ml.get_primary_field("TEXT")

    assert new_ml.context.mtext is not None
    assert new_ml.context.mtext.default_content == "----"
    assert new_child is not None
    assert new_child.field_code == child.field_code
    assert new_doc.objects.get_field_list() is not None


def test_multileader_to_code_preserves_proxy_graphic_payload():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    builder.multileader.proxy_graphic = b"\x01\x02\x03\x04"

    _, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    stream = StringIO()
    new_ml.export_dxf(TagWriter(stream, dxfversion=new_ml.doc.dxfversion))
    text = stream.getvalue().replace("\r\n", "\n")

    assert new_ml.proxy_graphic == builder.multileader.proxy_graphic
    assert "\n 92\n4\n310\n01020304\n" in text


def test_multileader_to_code_does_not_inject_version_tag_when_source_omits_it():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    _, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    stream = StringIO()
    new_ml.export_dxf(TagWriter(stream, dxfversion=new_ml.doc.dxfversion))
    text = stream.getvalue().replace("\r\n", "\n")

    assert new_ml.dxf.hasattr("version") is False
    assert "\n270\n2\n" not in text


def test_multileader_to_code_tolerates_unresolved_leader_linetype_handle():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "BROKEN_LT_STYLE")
    style.dxf.leader_linetype_handle = "25"
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("BROKEN_LT_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    builder.multileader.dxf.leader_linetype_handle = "25"

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_style = new_doc.mleader_styles.get("BROKEN_LT_STYLE")

    assert new_ml.dxftype() == "MULTILEADER"
    assert new_style is not None
    assert new_ml.dxf.style_handle == new_style.dxf.handle


def test_multileader_acexpr_field_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (10, 0))
    circle = source_msp.add_circle((5, 0), radius=2.5)
    builder = source_msp.add_multileader_mtext()
    builder.set_content("TEXT")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    ml = builder.multileader
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    ml.new_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    _, new_msp = translate_entities_to_new_layout([line, circle, ml])
    new_line = new_msp[0]
    new_circle = new_msp[1]
    new_ml = new_msp[2]
    new_expr = new_ml.get_primary_field("TEXT")

    assert new_ml.get_mtext_content() == "25.0000"
    assert new_expr is not None
    assert new_expr.evaluator_id == "AcExpr"
    children = new_expr.get_child_fields()
    assert len(children) == 2
    assert children[0].object_handles == [new_line.dxf.handle]
    assert children[1].object_handles == [new_circle.dxf.handle]


def test_unsupported_translator_does_not_register_entity_handle(monkeypatch):
    class DummyDXF:
        def __init__(self, handle: str):
            self.handle = handle

        def get(self, key: str, default=None):
            if key == "handle":
                return self.handle
            return default

    class DummyEntity:
        def __init__(self, handle: str):
            self.dxf = DummyDXF(handle)

        def dxftype(self):
            return "FAKE"

    generator = _SourceCodeGenerator(layout="msp", doc="doc")
    monkeypatch.setattr(
        _SourceCodeGenerator,
        "_fake",
        lambda self, entity: False,
        raising=False,
    )

    generator.translate_entities([DummyEntity("ABBA")])

    assert '_entity_map["ABBA"]' not in str(generator.code)


def test_multileader_custom_style_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "MY_STYLE")
    style.dxf.default_text_content = "STYLE_TEXT"
    style.dxf.char_height = 3.5
    style.dxf.text_alignment_type = 1
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("MY_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_style = new_doc.mleader_styles.get("MY_STYLE")

    assert new_style is not None
    assert new_style.dxf.default_text_content == "STYLE_TEXT"
    assert new_style.dxf.char_height == 3.5
    assert new_style.dxf.text_alignment_type == 1
    assert new_ml.dxf.style_handle == new_style.dxf.handle


def test_multileader_custom_style_to_code_does_not_inherit_standard_extension_dict():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    standard = source_doc.mleader_styles.get("Standard")
    assert standard is not None
    if not standard.has_extension_dict:
        xdict = standard.new_extension_dict()
        xdict.dictionary.add_xrecord("ACAD_XREC_ROUNDTRIP")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "CUSTOM_NO_XDICT")
    if style.has_extension_dict:
        style.discard_extension_dict()
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("CUSTOM_NO_XDICT")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_style = new_doc.mleader_styles.get("CUSTOM_NO_XDICT")

    assert new_ml.dxftype() == "MULTILEADER"
    assert new_style is not None
    assert new_style.has_extension_dict is False


def test_multileader_custom_style_arrow_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "ARROW_STYLE")
    style.set_arrow_head("DOT")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("ARROW_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_style = new_doc.mleader_styles.get("ARROW_STYLE")

    assert new_style is not None
    assert new_style.dxf.arrow_head_handle is not None
    assert new_doc.entitydb.get(new_style.dxf.arrow_head_handle).dxf.name == "_DOT"
    assert new_ml.dxf.style_handle == new_style.dxf.handle


def test_multileader_arrow_override_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note")
    builder.set_arrow_properties(name="DOT", size=2.0)
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]

    assert new_ml.dxf.arrow_head_handle is not None
    assert new_doc.entitydb.get(new_ml.dxf.arrow_head_handle).dxf.name == "_DOT"


def test_multileader_arrow_heads_to_code():
    from ezdxf.entities.mleader import ArrowHeadData
    from ezdxf.render.arrows import ARROWS
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    multileader = builder.multileader
    multileader.arrow_heads = [
        ArrowHeadData(0, ARROWS.arrow_handle(source_doc.blocks, "DOT")),
        ArrowHeadData(1, ARROWS.arrow_handle(source_doc.blocks, "OPEN")),
    ]

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    arrow0, arrow1 = new_ml.arrow_heads

    assert len(new_ml.arrow_heads) == 2
    assert arrow0.index == 0
    assert arrow1.index == 1
    assert new_doc.entitydb.get(arrow0.handle).dxf.name == "_DOT"
    assert new_doc.entitydb.get(arrow1.handle).dxf.name == "_OPEN"


def test_multileader_custom_style_block_reference_missing_is_safe():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "STYLE_BLOCK_STYLE")
    source_doc.blocks.new("STYLE_BLOCK")
    style.dxf.block_record_handle = source_doc.blocks.get(
        "STYLE_BLOCK"
    ).block_record_handle
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("STYLE_BLOCK_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_style = new_doc.mleader_styles.get("STYLE_BLOCK_STYLE")

    assert new_style is not None
    assert new_style.dxf.hasattr("block_record_handle") is False
    assert new_msp[-1].dxftype() == "MULTILEADER"


def test_multileader_custom_style_block_reference_preserved_if_available():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "STYLE_BLOCK_STYLE")
    source_doc.blocks.new("STYLE_BLOCK")
    style.dxf.block_record_handle = source_doc.blocks.get(
        "STYLE_BLOCK"
    ).block_record_handle
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("STYLE_BLOCK_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    target_doc = ezdxf.new("R2010")
    target_doc.blocks.new("STYLE_BLOCK")
    new_doc, _ = execute_entities_code_in_doc(source_msp, target_doc)
    new_style = new_doc.mleader_styles.get("STYLE_BLOCK_STYLE")

    assert new_style is not None
    assert (
        new_style.dxf.block_record_handle
        == new_doc.blocks.get("STYLE_BLOCK").block_record_handle
    )


def test_multileader_block_content_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("TEST_BLOCK")
    block.add_lwpolyline([(0, 0), (1, 0), (1, 1), (0, 1)], close=True)
    block.add_attdef("ONE", insert=(0, 0), text="ONE")
    block.add_attdef("TWO", insert=(1, 1), text="TWO")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "BLOCK_STYLE")
    style.dxf.block_record_handle = block.block_record_handle
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_block("BLOCK_STYLE")
    builder.set_content(name="TEST_BLOCK")
    builder.set_attribute("ONE", "Data1")
    builder.set_attribute("TWO", "Data2")
    builder.add_leader_line(ConnectionSide.right, [Vec2(5, 0)])
    builder.build(insert=Vec2(0, 0))

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)
    execute_code_in_namespace(entities_to_code(source_msp, layout="msp"), namespace)

    new_doc = namespace["doc"]
    new_msp = namespace["msp"]
    new_ml = new_msp[-1]
    new_block = new_doc.blocks.get("TEST_BLOCK")
    new_style = new_doc.mleader_styles.get("BLOCK_STYLE")
    attdef0, attdef1 = list(new_block.attdefs())
    block_attrib0, block_attrib1 = new_ml.block_attribs

    assert new_ml.dxftype() == "MULTILEADER"
    assert new_style is not None
    assert new_style.dxf.block_record_handle == new_block.block_record_handle
    assert new_ml.dxf.block_record_handle == new_block.block_record_handle
    assert new_ml.context.block is not None
    assert new_ml.context.block.block_record_handle == new_block.block_record_handle
    assert block_attrib0.handle == attdef0.dxf.handle
    assert block_attrib1.handle == attdef1.dxf.handle
    assert block_attrib0.text == "Data1"
    assert block_attrib1.text == "Data2"


def test_acad_table_text_surface_to_code():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    table = source_msp.add_table(
        (1, 2),
        [["TITLE", "STATUS"], ["HEADER", "VALUE"], ["DATA", "OK"]],
        row_heights=[11.0, 9.0, 9.0],
        col_widths=[38.0, 28.0],
    )
    table.set_row_height(0, 20.0)
    table.set_col_width(1, 30.0)
    table.set_title_suppressed(True)
    table.set_cell_text(1, 1, "VALUE-LONG")
    table.set_cell_text_height(0, 0, 20.0)
    table.set_cell_alignment(0, 1, 4)
    table.set_cell_content_color(1, 0, 215, 10507177)
    table.set_cell_fill_color(0, 1, 177, 3811732)
    table.clear_cell_fill(0, 1)

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_table = next(entity for entity in new_msp if entity.dxftype() == "ACAD_TABLE")

    assert new_table.data is not None
    assert new_table.dxf.insert == table.dxf.insert
    assert new_table.data.row_heights == table.data.row_heights
    assert new_table.data.col_widths == table.data.col_widths
    assert new_table.data.suppress_title == table.data.suppress_title
    assert new_table.data.suppress_column_header == table.data.suppress_column_header
    assert [cell.text for cell in new_table.data.cells] == [cell.text for cell in table.data.cells]

    src_cells = table.data.cells
    dst_cells = new_table.data.cells
    assert dst_cells[0].text_height == src_cells[0].text_height
    assert dst_cells[1].alignment == src_cells[1].alignment
    assert dst_cells[1].fill_enabled == 1
    assert dst_cells[1].fill_color == 0
    assert dst_cells[2].text == src_cells[2].text

    assert len(list(new_table.virtual_entities())) == len(list(table.virtual_entities()))
    assert new_doc.table_styles.get("Standard") is not None


def test_acad_table_minimal_block_cell_to_code():
    source_doc = ezdxf.new("R2018")
    block = source_doc.blocks.new("TABLE_BLOCK_CELL_MIN", base_point=(0, 0))
    block.add_lwpolyline([(0, 0), (2, 0), (2, 2), (0, 2)], close=True)
    source_msp = source_doc.modelspace()
    table = source_msp.add_table((0, 0), [["T"], ["H"], [""]])
    table.set_cell_block(2, 0, "TABLE_BLOCK_CELL_MIN", block_scale=1.0, alignment=1)

    target_doc = ezdxf.new("R2018")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)
    execute_code_in_namespace(entities_to_code(source_msp, layout="msp"), namespace)

    new_doc = namespace["doc"]
    new_msp = namespace["msp"]
    new_table = next(entity for entity in new_msp if entity.dxftype() == "ACAD_TABLE")
    new_cell = new_table.get_cell(2, 0)

    assert new_cell.is_block_cell is True
    assert new_cell.block_scale == 1.0
    assert new_cell.alignment == 1
    assert new_table.get_cell_block_name(2, 0) == "TABLE_BLOCK_CELL_MIN"
    inserts = [entity for entity in new_table.virtual_entities() if entity.dxftype() == "INSERT"]
    assert len(inserts) == 1
    assert inserts[0].dxf.name == "TABLE_BLOCK_CELL_MIN"


def test_acad_table_acexpr_field_to_code():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (10, 0))
    circle = source_msp.add_circle((5, 0), radius=2.5)
    table = source_msp.add_table(
        (0, 0),
        [["FIELD EXPR", "AUTHORED"], ["LABEL", "VALUE"], ["Length", "10.0000"], ["Radius", "2.5000"], ["Result", "25.0000"]],
        col_widths=[30.0, 38.0],
    )
    table.new_cell_acobjprop_field(2, 1, line, "Length", text="10.0000", register_field_list=True)
    table.new_cell_acobjprop_field(3, 1, circle, "Radius", text="2.5000", register_field_list=True)
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    table.new_cell_acexpr_field(
        4,
        1,
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    new_doc, new_msp = translate_entities_to_new_layout([line, circle, table])
    new_line = new_msp[0]
    new_circle = new_msp[1]
    new_table = new_msp[2]
    new_expr = new_table.get_cell_primary_field(4, 1)

    assert new_expr is not None
    assert new_expr.evaluator_id == "AcExpr"
    children = new_expr.get_child_fields()
    assert len(children) == 2
    assert children[0].object_handles == [new_line.dxf.handle]
    assert children[1].object_handles == [new_circle.dxf.handle]
    assert new_table.get_cell_field(4, 1) is not None


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


def test_replay_block_multileader_external_handles_remap_to_target_resources():
    from ezdxf.render.mleader import ConnectionSide
    from ezdxf.lldxf.extendedtags import ExtendedTags

    source_doc = ezdxf.new("R2010")
    source_doc.blocks.new("_ClosedBlank")
    style = source_doc.mleader_styles.duplicate_entry(
        "Standard", "RAE SLD Leader (Model Only)"
    )
    style.dxf.name = "Standard"
    style.dxf.block_record_handle = source_doc.blocks.get(
        "_ClosedBlank"
    ).block_record_handle
    block = source_doc.blocks.new("MLEADER_BLOCK_SOURCE")
    builder = block.add_multileader_mtext("RAE SLD Leader (Model Only)")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    source_doc.modelspace().add_blockref(block.name, (0, 0))

    new_doc = replay_doc_to_new_doc(source_doc)
    new_block = new_doc.blocks.get("MLEADER_BLOCK_SOURCE")
    assert new_block is not None
    new_entity = next(entity for entity in new_block if entity.dxftype() == "MULTILEADER")
    text = _export_text(new_entity, new_doc.dxfversion)
    refs = []
    for tag in ExtendedTags.from_text(text):
        if tag.code not in (340, 342):
            continue
        target = new_doc.entitydb.get(str(tag.value))
        if target is None:
            continue
        name = target.dxf.name if target.dxf.hasattr("name") else ""
        refs.append((tag.code, target.dxftype(), name))

    assert (340, "MLEADERSTYLE", "Standard") in refs
    new_style = new_doc.mleader_styles.get("RAE SLD Leader (Model Only)")
    assert new_style is not None
    assert new_style.dxf.block_record_handle == new_doc.blocks.get(
        "_ClosedBlank"
    ).block_record_handle


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


if __name__ == "__main__":
    pytest.main([__file__])
