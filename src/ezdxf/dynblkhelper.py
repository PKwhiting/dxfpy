#  Copyright (c) 2023, Manfred Moitzi
#  License: MIT License
"""
This module provides helper tools to work with dynamic blocks.

The current state supports only reading information from dynamic blocks, it does not
support the creation of new dynamic blocks nor the modification of them.

"""
from __future__ import annotations
from dataclasses import dataclass
import uuid
from typing import TYPE_CHECKING, Any, Iterator, Optional, Sequence, Union
from ezdxf.entities import Insert, DXFTagStorage, XRecord, Dictionary
from ezdxf.lldxf import const

if TYPE_CHECKING:
    from ezdxf.document import Drawing
    from ezdxf.layouts import BlockLayout
    from ezdxf.entities import BlockRecord, DXFEntity

__all__ = [
    "DynamicBlockVisibilityState",
    "DynamicBlockVisibilityParameter",
    "DynamicBlockBasePointParameter",
    "DynamicBlockLinearGrip",
    "DynamicBlockLinearParameter",
    "DynamicBlockLookupGrip",
    "DynamicBlockLookupParameter",
    "DynamicBlockLookupActionBinding",
    "DynamicBlockLookupAction",
    "DynamicBlockStretchActionTarget",
    "DynamicBlockStretchAction",
    "DynamicBlockPropertyColumn",
    "DynamicBlockPropertyRow",
    "DynamicBlockPropertiesTable",
    "DynamicBlockAssocVariable",
    "DynamicBlockAssocNetwork",
    "DynamicBlockPropertyCarrier",
    "DynamicBlockPropertyRepresentation",
    "get_dynamic_block_definition",
    "get_dynamic_block_reference",
    "is_dynamic_block_definition",
    "get_dynamic_block_record_handle",
    "get_dynamic_block_visibility_parameter",
    "get_dynamic_block_visibility_states",
    "get_dynamic_block_visibility_state",
    "get_dynamic_block_visibility_state_handles",
    "get_dynamic_block_visibility_entities",
    "get_dynamic_block_base_point_parameter",
    "get_dynamic_block_linear_grips",
    "get_dynamic_block_linear_parameters",
    "get_dynamic_block_lookup_grips",
    "get_dynamic_block_lookup_parameters",
    "get_dynamic_block_lookup_actions",
    "get_dynamic_block_stretch_actions",
    "get_dynamic_block_properties_table",
    "get_dynamic_block_property_columns",
    "get_dynamic_block_property_rows",
    "get_dynamic_block_property_assoc_networks",
    "get_dynamic_block_property_representations",
    "get_dynamic_block_property_representation_families",
    "set_dynamic_block_definition_metadata",
    "setup_dynamic_block_property_attdef_support",
    "set_dynamic_block_linear_parameter",
    "set_dynamic_block_base_point_parameter",
    "set_dynamic_block_insert_appdata_record",
    "set_dynamic_block_insert_cache_record",
    "set_dynamic_block_insert_cache",
    "set_dynamic_block_lookup_parameter",
    "set_dynamic_block_properties_editor_support",
    "set_dynamic_block_properties_table",
    "set_dynamic_block_visibility_parameter",
    "set_dynamic_block_reference",
    "set_dynamic_block_visibility_state",
]

AcDbDynamicBlockGUID = "AcDbDynamicBlockGUID"
AcDbBlockRepBTag = "AcDbBlockRepBTag"
AcDbDynamicBlockTrueName = "AcDbDynamicBlockTrueName"
AcDbDynamicBlockTrueName2 = "AcDbDynamicBlockTrueName2"
AcDbBlockRepETag = "AcDbBlockRepETag"
AcadBPTGraphNodeId = "AcadBPTGraphNodeId"


def _ensure_dynamic_block_appids(doc: Drawing) -> None:
    for name in (
        AcDbDynamicBlockGUID,
        AcDbDynamicBlockTrueName,
        AcDbBlockRepETag,
        AcDbBlockRepBTag,
    ):
        if name not in doc.appids:
            doc.appids.new(name)


def _ensure_dynamic_block_properties_appids(doc: Drawing) -> None:
    for name in (AcDbDynamicBlockTrueName2, AcadBPTGraphNodeId):
        if name not in doc.appids:
            doc.appids.new(name)


def _ensure_annotative_appid(doc: Drawing) -> None:
    if "AcadAnnotative" not in doc.appids:
        doc.appids.new("AcadAnnotative")


def _tag_block_representation_entities(block: BlockLayout) -> None:
    for index, entity in enumerate(block):
        if entity.dxftype() == "ATTDEF" and entity.has_xdata(AcDbBlockRepETag):
            continue
        _set_entity_rep_etag(entity, index)


def _set_entity_rep_etag(entity, rep_index: int, rep_handle: Optional[str] = None) -> None:
    if rep_handle is None:
        rep_handle = entity.dxf.handle
    entity.set_xdata(AcDbBlockRepETag, [(1070, 1), (1071, rep_index), (1005, rep_handle)])


def _default_annotation_scale_handle(doc: Drawing) -> str:
    scale_root = doc.rootdict.get_required_dict("ACAD_SCALELIST")
    scale = scale_root.get("A0")
    if scale is None:
        scale = _new_tag_storage_object(
            doc,
            "SCALE",
            scale_root.dxf.handle,
            [[(100, "AcDbScale"), (70, 0), (300, "1:1"), (140, 1.0), (141, 1.0), (290, 1)]],
        )
        scale.set_reactors([scale_root.dxf.handle])
        scale_root.add("A0", scale)
    if scale is None:
        for _, entity in scale_root.items():
            scale = entity
            break
    if scale is None:
        raise const.DXFStructureError("ACAD_SCALELIST requires at least one SCALE entry")
    return scale.dxf.handle


def _set_property_attdef_rep_etag(attdef, rep_index: int) -> None:
    _set_entity_rep_etag(attdef, rep_index, "0")


def _ensure_property_attdef_annotative_metadata(
    attdef, *, create_context_record: bool = True
) -> None:
    doc = attdef.doc
    if doc is None:
        raise const.DXFStructureError("valid DXF document required")
    _ensure_annotative_appid(doc)

    attdef.set_xdata(
        "AcadAnnotative",
        [
            (1000, "AnnotativeData"),
            (1002, "{"),
            (1070, 1),
            (1070, 1 if create_context_record else 0),
            (1002, "}"),
        ],
    )

    xdict = attdef.get_extension_dict() if attdef.has_extension_dict else attdef.new_extension_dict()
    root = xdict.dictionary
    context_manager = root.get("AcDbContextDataManager")
    if not isinstance(context_manager, Dictionary):
        context_manager = root.add_new_dict("AcDbContextDataManager")
    annot_scales = context_manager.get("ACDB_ANNOTATIONSCALES")
    if not isinstance(annot_scales, Dictionary):
        annot_scales = context_manager.add_new_dict("ACDB_ANNOTATIONSCALES")
    context_manager.set_reactors([root.dxf.handle])
    annot_scales.set_reactors([context_manager.dxf.handle])

    if create_context_record:
        context_data = annot_scales.get("*A1")
        if not isinstance(context_data, DXFTagStorage):
            context_data = _new_tag_storage_object(
                doc,
                "ACDB_MTEXTATTRIBUTEOBJECTCONTEXTDATA_CLASS",
                annot_scales.dxf.handle,
                [
                    [(100, "AcDbObjectContextData"), (70, 4), (290, 1)],
                    [
                        (100, "AcDbAnnotScaleObjectContextData"),
                        (340, _default_annotation_scale_handle(doc)),
                        (70, 0),
                        (50, 0.0),
                        (10, (attdef.dxf.insert.x, attdef.dxf.insert.y)),
                        (11, (0.0, 0.0)),
                        (290, 0),
                    ],
                ],
            )
            _set_owner_reactor(context_data, annot_scales.dxf.handle)
            annot_scales.add("*A1", context_data)


def _ensure_property_attdef_metadata(attdef, rep_index: int) -> None:
    _set_property_attdef_rep_etag(attdef, rep_index)
    _ensure_property_attdef_annotative_metadata(attdef)


def _attdef_has_context_record(attdef) -> bool:
    return bool(
        attdef.has_extension_dict
        and isinstance(attdef.get_extension_dict().dictionary.get("AcDbContextDataManager"), Dictionary)
        and isinstance(
            attdef.get_extension_dict().dictionary.get("AcDbContextDataManager").get("ACDB_ANNOTATIONSCALES"),
            Dictionary,
        )
        and "*A1"
        in attdef.get_extension_dict().dictionary.get("AcDbContextDataManager").get("ACDB_ANNOTATIONSCALES")
    )


def _attdef_rep_index(attdef) -> Optional[int]:
    try:
        return int(attdef.get_xdata(AcDbBlockRepETag).get_first_value(1071, -1))
    except const.DXFValueError:
        return None


@dataclass(frozen=True)
class _PropertyAttdefState:
    annotative: bool
    invisible: int
    has_extension_dict: bool
    has_context_record: bool
    rep_index: Optional[int]


def _property_attdef_state(attdef) -> _PropertyAttdefState:
    return _PropertyAttdefState(
        annotative=attdef.has_xdata("AcadAnnotative"),
        invisible=int(attdef.dxf.get("invisible", 0)),
        has_extension_dict=attdef.has_extension_dict,
        has_context_record=_attdef_has_context_record(attdef),
        rep_index=_attdef_rep_index(attdef),
    )


def setup_dynamic_block_property_attdef_support(
    attdef,
    rep_index: int,
    *,
    annotative: bool = False,
    create_context_record: bool = True,
) -> None:
    _set_property_attdef_rep_etag(attdef, rep_index)
    if annotative:
        _ensure_property_attdef_annotative_metadata(
            attdef, create_context_record=create_context_record
        )


def set_dynamic_block_definition_metadata(
    block: BlockLayout,
    *,
    guid: str = "",
    true_name: str = "",
    rep_index: Optional[int] = None,
    annotative: bool = False,
) -> None:
    doc = block.doc
    if doc is None:
        raise const.DXFStructureError("valid DXF document required")
    _ensure_dynamic_block_appids(doc)
    if annotative:
        _ensure_annotative_appid(doc)
        block.block_record.set_xdata(
            "AcadAnnotative",
            [
                (1000, "AnnotativeData"),
                (1002, "{"),
                (1070, 1),
                (1070, 0),
                (1002, "}"),
            ],
        )
    if not guid:
        guid = "{" + str(uuid.uuid4()).upper() + "}"
    if not true_name:
        true_name = block.name
    if rep_index is None:
        rep_index = len(block)
    block.block_record.set_xdata(AcDbDynamicBlockGUID, [(1000, guid)])
    block.block_record.set_xdata(AcDbDynamicBlockTrueName, [(1000, true_name)])
    block.block_record.set_xdata(AcDbBlockRepETag, [(1070, 1), (1071, rep_index)])
    xdict = _ensure_dynamic_block_extension_dict(block.block_record)
    purge = xdict.get("AcDbDynamicBlockRoundTripPurgePreventer")
    if not isinstance(purge, DXFTagStorage):
        purge = _new_tag_storage_object(
            doc,
            "ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION",
            xdict.dxf.handle,
            [[(100, "AcDbDynamicBlockPurgePreventer"), (70, 1)]],
        )
        _set_owner_reactor(purge, xdict.dxf.handle)
        xdict.add("AcDbDynamicBlockRoundTripPurgePreventer", purge)


def _get_property_attdefs(block: BlockLayout) -> tuple:
    return tuple(entity for entity in block if entity.dxftype() == "ATTDEF")


def _clone_property_attdefs_to_reference(reference: BlockLayout, dynamic_block: BlockLayout) -> None:
    existing_tags = {entity.dxf.tag for entity in reference if entity.dxftype() == "ATTDEF"}
    for attdef in _get_property_attdefs(dynamic_block):
        if attdef.dxf.tag in existing_tags:
            continue
        clone = reference.add_attdef(
            attdef.dxf.tag,
            insert=attdef.dxf.insert,
            text=attdef.dxf.text,
            height=attdef.dxf.height,
            rotation=attdef.dxf.get("rotation", 0.0),
            dxfattribs={
                "layer": attdef.dxf.layer,
                "color": attdef.dxf.color,
                "style": attdef.dxf.style,
                "flags": attdef.dxf.flags,
                "lock_position": attdef.dxf.get("lock_position", 1),
            },
        )
        clone.dxf.prompt = attdef.dxf.prompt
        if attdef.dxf.get("invisible", 0):
            clone.dxf.invisible = 1



def _apply_visibility_state_to_block(
    block: BlockLayout,
    parameter: DynamicBlockVisibilityParameter,
    state: str,
    *,
    dynamic_block: Optional[BlockLayout] = None,
) -> None:
    if dynamic_block is None:
        dynamic_block = block

    visible_handles: tuple[str, ...] = ()
    for visibility_state in parameter.states:
        if visibility_state.name == state:
            visible_handles = visibility_state.entity_handles
            break
    if not visible_handles:
        return

    if block is dynamic_block:
        visible = set(visible_handles)
        for entity in block:
            if entity.dxf.handle in visible:
                entity.dxf.discard("invisible")
            else:
                entity.dxf.invisible = 1
        return

    base_entities = list(dynamic_block)
    ref_entities = list(block)
    handle_to_index = {
        entity.dxf.handle: index
        for index, entity in enumerate(base_entities)
        if entity.dxf.handle is not None
    }
    visible_indices = {handle_to_index[handle] for handle in visible_handles if handle in handle_to_index}
    for index, entity in enumerate(ref_entities):
        if index in visible_indices:
            entity.dxf.discard("invisible")
        else:
            entity.dxf.invisible = 1


def _apply_property_attdef_visibility(
    block: BlockLayout,
    dynamic_block: BlockLayout,
    state: str,
    first_state_name: str,
) -> None:
    property_tags = {attdef.dxf.tag for attdef in _get_property_attdefs(dynamic_block)}
    if not property_tags:
        return
    if get_dynamic_block_linear_parameters(dynamic_block):
        source_invisible = {
            attdef.dxf.tag: int(attdef.dxf.get("invisible", 0))
            for attdef in _get_property_attdefs(dynamic_block)
        }
        for entity in block:
            if entity.dxftype() != "ATTDEF":
                continue
            if entity.dxf.tag in property_tags:
                if source_invisible.get(entity.dxf.tag, 0):
                    entity.dxf.invisible = 1
                else:
                    entity.dxf.discard("invisible")
        return
    visible = state == first_state_name
    for entity in block:
        if entity.dxftype() != "ATTDEF":
            continue
        if entity.dxf.tag not in property_tags:
            continue
        if visible:
            entity.dxf.discard("invisible")
        else:
            entity.dxf.invisible = 1


@dataclass(frozen=True)
class DynamicBlockVisibilityState:
    name: str
    entity_handles: tuple[str, ...] = ()


@dataclass(frozen=True)
class DynamicBlockVisibilityParameter:
    handle: str
    label: str
    parameter_name: str
    location: tuple[float, float, float]
    states: tuple[DynamicBlockVisibilityState, ...]
    all_entity_handles: tuple[str, ...] = ()


@dataclass(frozen=True)
class DynamicBlockBasePointParameter:
    handle: str
    label: str
    location: tuple[float, float, float]
    base_point: tuple[float, float, float]
    second_point: tuple[float, float, float]
    expr_id: int


@dataclass(frozen=True)
class DynamicBlockLinearGrip:
    handle: str
    label: str
    location: tuple[float, float, float]
    offset: tuple[float, float, float]
    expr_id: int
    x_expr_id: int
    y_expr_id: int


@dataclass(frozen=True)
class DynamicBlockLinearParameter:
    handle: str
    label: str
    parameter_name: str
    description: str
    base_point: tuple[float, float, float]
    end_point: tuple[float, float, float]
    distance: float
    expr_id: int
    base_grip_handle: str = ""
    end_grip_handle: str = ""
    base_grip_label: str = ""
    end_grip_label: str = ""
    base_grip_location: Optional[tuple[float, float, float]] = None
    end_grip_location: Optional[tuple[float, float, float]] = None
    value_set_type: int = 0
    value_count: int = 0
    allowed_values: tuple[float, ...] = ()


@dataclass(frozen=True)
class DynamicBlockLookupGrip:
    handle: str
    label: str
    location: tuple[float, float, float]
    expr_id: int
    x_expr_id: int
    y_expr_id: int
    parameter_expr_id: int = -1


@dataclass(frozen=True)
class DynamicBlockLookupParameter:
    handle: str
    label: str
    parameter_name: str
    description: str
    location: tuple[float, float, float]
    expr_id: int
    action_expr_id: int
    grip_handle: str = ""
    grip_label: str = ""


@dataclass(frozen=True)
class DynamicBlockLookupActionBinding:
    group_label: str
    expr_id: int
    value_code: int
    value_type: int
    flag282: int
    display_name: str
    flag281: int
    property_name: str


@dataclass(frozen=True)
class DynamicBlockLookupAction:
    handle: str
    label: str
    action_location: tuple[float, float, float]
    expr_id: int
    row_count: int
    column_count: int
    entries: tuple[tuple[str, ...], ...]
    bindings: tuple[DynamicBlockLookupActionBinding, ...]
    enabled: int


@dataclass(frozen=True)
class DynamicBlockStretchActionTarget:
    entity_handle: str
    mode: int
    components: tuple[int, ...] = ()


@dataclass(frozen=True)
class DynamicBlockStretchAction:
    handle: str
    label: str
    action_location: tuple[float, float, float]
    x_expr_id: int
    x_name: str
    y_expr_id: int
    y_name: str
    selection_window: tuple[tuple[float, float, float], ...]
    dependency_handles: tuple[str, ...]
    targets: tuple[DynamicBlockStretchActionTarget, ...]


@dataclass(frozen=True)
class DynamicBlockPropertyColumn:
    source_handle: str
    source_dxftype: str
    name: str
    display_name: str = ""


@dataclass(frozen=True)
class DynamicBlockPropertyRow:
    index: int
    values: tuple[Any, ...]


@dataclass(frozen=True)
class DynamicBlockPropertiesTable:
    handle: str
    label: str
    table_name: str
    description: str
    location: tuple[float, float, float]
    grip_location: Optional[tuple[float, float, float]]
    columns: tuple[DynamicBlockPropertyColumn, ...]
    rows: tuple[DynamicBlockPropertyRow, ...]


@dataclass(frozen=True)
class DynamicBlockAssocVariable:
    handle: str
    name: str
    value: str
    evaluator_id: str
    expression: str
    raw_ints: tuple[int, ...] = ()


@dataclass(frozen=True)
class DynamicBlockAssocNetwork:
    handle: str
    block_record_handle: str
    block_name: str
    dictionary_handle: str
    variables: tuple[DynamicBlockAssocVariable, ...]


@dataclass(frozen=True)
class DynamicBlockPropertyCarrier:
    handle: str
    tag: str
    text: str
    invisible: int


@dataclass(frozen=True)
class DynamicBlockPropertyRepresentation:
    block_record_handle: str
    block_name: str
    is_active: bool
    invisible_flags: tuple[int, ...]
    carriers: tuple[DynamicBlockPropertyCarrier, ...]
    assoc_network: Optional[DynamicBlockAssocNetwork] = None


@dataclass(frozen=True)
class DynamicBlockPropertyRepresentationFamily:
    invisible_flags: tuple[int, ...]
    carrier_count: int
    carrier_texts: tuple[str, ...]
    carrier_visibility: tuple[int, ...]
    assoc_signature: tuple[tuple[str, str], ...]
    block_names: tuple[str, ...]


def get_dynamic_block_definition(
    insert: Insert, doc: Optional[Drawing] = None
) -> Optional[BlockLayout]:
    """Returns the dynamic block definition if the given block reference is
    referencing a dynamic block direct or indirect via an anonymous block.
    Returns ``None`` otherwise.
    """
    if doc is None:
        doc = insert.doc
        if doc is None:
            return None

    block = doc.blocks.get(insert.dxf.name)
    if block is None:
        return None

    block_record = block.block_record
    if is_dynamic_block_definition(block_record):
        return block  # direct dynamic block reference

    # is indirect dynamic block reference?
    handle = get_dynamic_block_record_handle(block_record)
    if not handle:
        return None  # lost reference to dynamic block definition
    dyn_block_record = doc.entitydb.get(handle)
    if dyn_block_record:
        return doc.blocks.get(dyn_block_record.dxf.name)
    return None


def get_dynamic_block_reference(
    insert: Insert, doc: Optional[Drawing] = None
) -> Optional[BlockLayout]:
    """Returns the anonymous block referenced by `insert` for a dynamic block.

    Returns ``None`` if the referenced block can not be resolved.
    """
    if doc is None:
        doc = insert.doc
        if doc is None:
            return None
    return doc.blocks.get(insert.dxf.name)


def is_dynamic_block_definition(block_record: BlockRecord) -> bool:
    """Return ``True`` if the given block record is a dynamic block definition."""
    return block_record.has_xdata(AcDbDynamicBlockGUID)


def get_dynamic_block_record_handle(block_record: BlockRecord) -> str:
    """Returns handle of the dynamic block record for an indirect dynamic block
    reference. Returns an empty string if the block record do not reference a dynamic
    block or the handle was not found.

    """
    try:  # check for indirect dynamic block reference
        xdata = block_record.get_xdata(AcDbBlockRepBTag)
    except const.DXFValueError:
        return ""  # not a dynamic block reference
    # get handle of dynamic block definition
    return xdata.get_first_value(1005, "")


def _get_enhanced_block_graph(block_record: BlockRecord) -> Optional[DXFTagStorage]:
    if not block_record.has_extension_dict:
        return None
    graph = block_record.get_extension_dict().dictionary.get("ACAD_ENHANCEDBLOCK")
    if isinstance(graph, DXFTagStorage) and graph.dxftype() == "ACAD_EVALUATION_GRAPH":
        return graph
    return None


def _iter_graph_owned_objects(graph: DXFTagStorage) -> Iterator[DXFTagStorage]:
    doc = graph.doc
    handle = graph.dxf.handle
    if doc is None or not handle:
        return iter(())
    return (
        entity
        for entity in doc.objects
        if isinstance(entity, DXFTagStorage) and entity.dxf.owner == handle
    )


def _parse_visibility_parameter(entity: DXFTagStorage) -> Optional[DynamicBlockVisibilityParameter]:
    if entity.dxftype() != "BLOCKVISIBILITYPARAMETER":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        location_tags = entity.xtags.get_subclass("AcDbBlock1PtParameter")
        visibility_tags = entity.xtags.get_subclass("AcDbBlockVisibilityParameter")
    except const.DXFKeyError:
        return None

    label = str(element_tags.get_first_value(300, ""))
    location = location_tags.get_first_value(1010, (0.0, 0.0, 0.0))
    parameter_name = str(visibility_tags.get_first_value(301, ""))
    all_entity_handles = tuple(str(value) for code, value in visibility_tags if code == 331)
    tags = list(visibility_tags)
    states: list[DynamicBlockVisibilityState] = []
    index = 0
    while index < len(tags):
        tag = tags[index]
        if tag.code != 303:
            index += 1
            continue
        state_name = str(tag.value)
        index += 1
        entity_handles: list[str] = []
        if index < len(tags) and tags[index].code == 94:
            index += 1
        while index < len(tags) and tags[index].code == 332:
            entity_handles.append(str(tags[index].value))
            index += 1
        if index < len(tags) and tags[index].code == 95:
            index += 1
        states.append(
            DynamicBlockVisibilityState(state_name, tuple(entity_handles))
        )
    return DynamicBlockVisibilityParameter(
        handle=entity.dxf.handle or "",
        label=label,
        parameter_name=parameter_name,
        location=(float(location[0]), float(location[1]), float(location[2])),
        states=tuple(states),
        all_entity_handles=all_entity_handles,
    )


def _point3d(value: Any) -> tuple[float, float, float]:
    if len(value) == 2:
        return (float(value[0]), float(value[1]), 0.0)
    return (float(value[0]), float(value[1]), float(value[2]))


def _eval_expr_id(entity: DXFTagStorage) -> int:
    try:
        return int(entity.xtags.get_subclass("AcDbEvalExpr").get_first_value(90, -1))
    except const.DXFKeyError:
        return -1


def _get_subclass(entity: DXFTagStorage, *names: str):
    for name in names:
        try:
            return entity.xtags.get_subclass(name)
        except const.DXFKeyError:
            continue
    raise const.DXFKeyError(names[0])


def _parse_linear_grip(entity: DXFTagStorage) -> Optional[DynamicBlockLinearGrip]:
    if entity.dxftype() != "BLOCKLINEARGRIP":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        grip_tags = entity.xtags.get_subclass("AcDbBlockGrip")
        linear_tags = entity.xtags.get_subclass("AcDbBlockLinearGrip")
    except const.DXFKeyError:
        return None
    location = grip_tags.get_first_value(1010, None)
    if location is None:
        return None
    return DynamicBlockLinearGrip(
        handle=entity.dxf.handle or "",
        label=str(element_tags.get_first_value(300, "")),
        location=_point3d(location),
        offset=(
            float(linear_tags.get_first_value(140, 0.0)),
            float(linear_tags.get_first_value(141, 0.0)),
            float(linear_tags.get_first_value(142, 0.0)),
        ),
        expr_id=_eval_expr_id(entity),
        x_expr_id=int(grip_tags.get_first_value(91, -1)),
        y_expr_id=int(grip_tags.get_first_value(92, -1)),
    )


def _parse_base_point_parameter(entity: DXFTagStorage) -> Optional[DynamicBlockBasePointParameter]:
    if entity.dxftype() != "BLOCKBASEPOINTPARAMETER":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        point_tags = entity.xtags.get_subclass("AcDbBlock1PtParameter")
        basepoint_tags = entity.xtags.get_subclass("AcDbBlockBasepointParameter")
    except const.DXFKeyError:
        return None
    location = point_tags.get_first_value(1010, None)
    base_point = basepoint_tags.get_first_value(1011, None)
    second_point = basepoint_tags.get_first_value(1012, None)
    if location is None or base_point is None or second_point is None:
        return None
    return DynamicBlockBasePointParameter(
        handle=entity.dxf.handle or "",
        label=str(element_tags.get_first_value(300, "")),
        location=_point3d(location),
        base_point=_point3d(base_point),
        second_point=_point3d(second_point),
        expr_id=_eval_expr_id(entity),
    )


def _parse_linear_parameter(
    entity: DXFTagStorage,
    grips_by_expr: dict[int, DynamicBlockLinearGrip],
) -> Optional[DynamicBlockLinearParameter]:
    if entity.dxftype() != "BLOCKLINEARPARAMETER":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        point_tags = entity.xtags.get_subclass("AcDbBlock2PtParameter")
        linear_tags = entity.xtags.get_subclass("AcDbBlockLinearParameter")
    except const.DXFKeyError:
        return None
    base_point = point_tags.get_first_value(1010, None)
    end_point = point_tags.get_first_value(1011, None)
    if base_point is None or end_point is None:
        return None
    grip_expr_ids = [int(tag.value) for tag in point_tags if tag.code == 91]
    base_grip = grips_by_expr.get(grip_expr_ids[0], None) if len(grip_expr_ids) > 0 else None
    end_grip = grips_by_expr.get(grip_expr_ids[1], None) if len(grip_expr_ids) > 1 else None
    allowed_values = tuple(float(tag.value) for tag in linear_tags if tag.code == 144)
    return DynamicBlockLinearParameter(
        handle=entity.dxf.handle or "",
        label=str(element_tags.get_first_value(300, "")),
        parameter_name=str(linear_tags.get_first_value(305, "")),
        description=str(linear_tags.get_first_value(306, "")),
        base_point=_point3d(base_point),
        end_point=_point3d(end_point),
        distance=float(linear_tags.get_first_value(140, 0.0)),
        expr_id=_eval_expr_id(entity),
        base_grip_handle=base_grip.handle if base_grip is not None else "",
        end_grip_handle=end_grip.handle if end_grip is not None else "",
        base_grip_label=base_grip.label if base_grip is not None else "",
        end_grip_label=end_grip.label if end_grip is not None else "",
        base_grip_location=base_grip.location if base_grip is not None else None,
        end_grip_location=end_grip.location if end_grip is not None else None,
        value_set_type=int(linear_tags.get_first_value(96, 0)),
        value_count=int(linear_tags.get_first_value(175, 0)),
        allowed_values=allowed_values,
    )


def _parse_grip_component(entity: DXFTagStorage) -> Optional[tuple[int, int, str]]:
    if entity.dxftype() != "BLOCKGRIPLOCATIONCOMPONENT":
        return None
    try:
        eval_tags = entity.xtags.get_subclass("AcDbEvalExpr")
        grip_expr_tags = entity.xtags.get_subclass("AcDbBlockGripExpr")
    except const.DXFKeyError:
        return None
    return (
        int(eval_tags.get_first_value(90, -1)),
        int(grip_expr_tags.get_first_value(91, -1)),
        str(grip_expr_tags.get_first_value(300, "")),
    )


def _parse_lookup_grip(entity: DXFTagStorage) -> Optional[DynamicBlockLookupGrip]:
    if entity.dxftype() != "BLOCKLOOKUPGRIP":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        grip_tags = entity.xtags.get_subclass("AcDbBlockGrip")
        _get_subclass(entity, "AcDbBlockLookUpGrip", "AcDbBlockLookupGrip")
    except const.DXFKeyError:
        return None
    location = grip_tags.get_first_value(1010, None)
    if location is None:
        return None
    return DynamicBlockLookupGrip(
        handle=entity.dxf.handle or "",
        label=str(element_tags.get_first_value(300, "")),
        location=_point3d(location),
        expr_id=_eval_expr_id(entity),
        x_expr_id=int(grip_tags.get_first_value(91, -1)),
        y_expr_id=int(grip_tags.get_first_value(92, -1)),
    )


def _parse_lookup_parameter(
    entity: DXFTagStorage,
    grips_by_param_expr: dict[int, DynamicBlockLookupGrip],
) -> Optional[DynamicBlockLookupParameter]:
    if entity.dxftype() != "BLOCKLOOKUPPARAMETER":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        point_tags = entity.xtags.get_subclass("AcDbBlock1PtParameter")
        lookup_tags = _get_subclass(entity, "AcDbBlockLookUpParameter", "AcDbBlockLookupParameter")
    except const.DXFKeyError:
        return None
    location = point_tags.get_first_value(1010, None)
    if location is None:
        return None
    expr_id = _eval_expr_id(entity)
    grip = grips_by_param_expr.get(expr_id, None)
    return DynamicBlockLookupParameter(
        handle=entity.dxf.handle or "",
        label=str(element_tags.get_first_value(300, "")),
        parameter_name=str(lookup_tags.get_first_value(303, "")),
        description=str(lookup_tags.get_first_value(304, "")),
        location=_point3d(location),
        expr_id=expr_id,
        action_expr_id=int(lookup_tags.get_first_value(94, -1)),
        grip_handle=grip.handle if grip is not None else "",
        grip_label=grip.label if grip is not None else "",
    )


def _parse_lookup_action(entity: DXFTagStorage) -> Optional[DynamicBlockLookupAction]:
    if entity.dxftype() != "BLOCKLOOKUPACTION":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        action_tags = entity.xtags.get_subclass("AcDbBlockAction")
        lookup_tags = list(entity.xtags.get_subclass("AcDbBlockLookupAction"))
    except const.DXFKeyError:
        return None
    action_location = action_tags.get_first_value(1010, None)
    if action_location is None:
        return None

    row_count = int(next((tag.value for tag in lookup_tags if tag.code == 92), 0))
    column_count = int(next((tag.value for tag in lookup_tags if tag.code == 93), 0))
    raw_values: list[str] = []
    bindings: list[DynamicBlockLookupActionBinding] = []
    index = 0
    while index < len(lookup_tags):
        code = lookup_tags[index].code
        if code == 301:
            index += 1
            while index < len(lookup_tags) and lookup_tags[index].code == 302:
                raw_values.append(str(lookup_tags[index].value))
                index += 1
            continue
        if code == 303:
            group_label = str(lookup_tags[index].value)
            index += 1
            binding_tags = []
            while index < len(lookup_tags) and lookup_tags[index].code not in (303, 280):
                binding_tags.append(lookup_tags[index])
                index += 1
            bindings.append(
                DynamicBlockLookupActionBinding(
                    group_label=group_label,
                    expr_id=int(next((tag.value for tag in binding_tags if tag.code == 94), -1)),
                    value_code=int(next((tag.value for tag in binding_tags if tag.code == 95), -1)),
                    value_type=int(next((tag.value for tag in binding_tags if tag.code == 96), -1)),
                    flag282=int(next((tag.value for tag in binding_tags if tag.code == 282), -1)),
                    display_name=str(next((tag.value for tag in binding_tags if tag.code == 305), "")),
                    flag281=int(next((tag.value for tag in binding_tags if tag.code == 281), -1)),
                    property_name=str(next((tag.value for tag in binding_tags if tag.code == 304), "")),
                )
            )
            continue
        if code == 280:
            break
        index += 1

    if column_count > 0:
        entries = tuple(
            tuple(raw_values[row * column_count : (row + 1) * column_count])
            for row in range(max(row_count, len(raw_values) // column_count))
            if raw_values[row * column_count : (row + 1) * column_count]
        )
    else:
        entries = ()
    return DynamicBlockLookupAction(
        handle=entity.dxf.handle or "",
        label=str(element_tags.get_first_value(300, "")),
        action_location=_point3d(action_location),
        expr_id=_eval_expr_id(entity),
        row_count=row_count,
        column_count=column_count,
        entries=entries,
        bindings=tuple(bindings),
        enabled=int(next((tag.value for tag in reversed(lookup_tags) if tag.code == 280), 0)),
    )


def _parse_stretch_action(entity: DXFTagStorage) -> Optional[DynamicBlockStretchAction]:
    if entity.dxftype() != "BLOCKSTRETCHACTION":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        action_tags = entity.xtags.get_subclass("AcDbBlockAction")
        stretch_tags = list(entity.xtags.get_subclass("AcDbBlockStretchAction"))
    except const.DXFKeyError:
        return None
    action_location = action_tags.get_first_value(1010, None)
    if action_location is None:
        return None
    selection_window = tuple(_point3d(tag.value) for tag in stretch_tags if tag.code == 1011)
    dependency_handles = tuple(str(tag.value) for tag in action_tags if tag.code == 330)
    x_expr_id = int(next((tag.value for tag in stretch_tags if tag.code == 92), -1))
    y_expr_id = int(next((tag.value for tag in stretch_tags if tag.code == 93), -1))
    x_name = str(next((tag.value for tag in stretch_tags if tag.code == 301), ""))
    y_name = str(next((tag.value for tag in stretch_tags if tag.code == 302), ""))
    targets: list[DynamicBlockStretchActionTarget] = []
    index = 0
    while index < len(stretch_tags):
        if stretch_tags[index].code != 331:
            index += 1
            continue
        entity_handle = str(stretch_tags[index].value)
        index += 1
        mode = 0
        if index < len(stretch_tags) and stretch_tags[index].code == 74:
            mode = int(stretch_tags[index].value)
            index += 1
        components: list[int] = []
        while index < len(stretch_tags) and stretch_tags[index].code == 94:
            components.append(int(stretch_tags[index].value))
            index += 1
        targets.append(
            DynamicBlockStretchActionTarget(
                entity_handle=entity_handle,
                mode=mode,
                components=tuple(components),
            )
        )
    return DynamicBlockStretchAction(
        handle=entity.dxf.handle or "",
        label=str(element_tags.get_first_value(300, "")),
        action_location=_point3d(action_location),
        x_expr_id=x_expr_id,
        x_name=x_name,
        y_expr_id=y_expr_id,
        y_name=y_name,
        selection_window=selection_window,
        dependency_handles=dependency_handles,
        targets=tuple(targets),
    )


def _parse_block_properties_table_grip(entity: DXFTagStorage) -> Optional[tuple[float, float, float]]:
    if entity.dxftype() != "BLOCKPROPERTIESTABLEGRIP":
        return None
    try:
        grip_tags = entity.xtags.get_subclass("AcDbBlockGrip")
    except const.DXFKeyError:
        return None
    location = grip_tags.get_first_value(1010, None)
    if location is None:
        return None
    return (float(location[0]), float(location[1]), float(location[2]))


def _resolve_property_column(table: DXFTagStorage, source_handle: str, column_name: str) -> DynamicBlockPropertyColumn:
    doc = table.doc
    source = doc.entitydb.get(source_handle) if doc is not None else None
    source_dxftype = source.dxftype() if source is not None else "UNKNOWN"
    display_name = column_name
    name = column_name
    if source_dxftype == "ATTDEF":
        name = source.dxf.get("tag", "")
        if not display_name:
            display_name = source.dxf.get("text", "")
    elif source_dxftype == "BLOCKVISIBILITYPARAMETER":
        visibility = _parse_visibility_parameter(source) if isinstance(source, DXFTagStorage) else None
        if not name and visibility is not None:
            name = visibility.parameter_name
        if not display_name and visibility is not None:
            display_name = visibility.label
    if not name:
        name = source_handle
    return DynamicBlockPropertyColumn(
        source_handle=source_handle,
        source_dxftype=source_dxftype,
        name=name,
        display_name=display_name,
    )


def _convert_property_cell_value(tag) -> Any:
    if tag.code in (300, 301, 302, 303, 1):
        return str(tag.value)
    if tag.code in (40, 41, 42, 43, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149):
        return float(tag.value)
    if 60 <= tag.code <= 99 or 170 <= tag.code <= 299 or 1070 <= tag.code <= 1071:
        return int(tag.value)
    return tag.value


def _parse_block_properties_table(entity: DXFTagStorage) -> Optional[DynamicBlockPropertiesTable]:
    if entity.dxftype() != "BLOCKPROPERTIESTABLE":
        return None
    try:
        element_tags = entity.xtags.get_subclass("AcDbBlockElement")
        location_tags = entity.xtags.get_subclass("AcDbBlock1PtParameter")
        table_tags = list(entity.xtags.get_subclass("AcDbBlockPropertiesTable"))[1:]
    except const.DXFKeyError:
        return None

    label = str(element_tags.get_first_value(300, ""))
    location = location_tags.get_first_value(1010, (0.0, 0.0, 0.0))
    index = 0
    if index >= len(table_tags) or table_tags[index].code != 90:
        return None
    index += 1  # table version marker
    table_name = str(table_tags[index].value) if index < len(table_tags) and table_tags[index].code == 300 else ""
    index += 1
    description = str(table_tags[index].value) if index < len(table_tags) and table_tags[index].code == 301 else ""
    index += 1
    if index >= len(table_tags) or table_tags[index].code != 91:
        return None
    column_count = int(table_tags[index].value)
    index += 1

    columns: list[DynamicBlockPropertyColumn] = []
    for _ in range(column_count):
        if index >= len(table_tags) or table_tags[index].code != 340:
            return None
        source_handle = str(table_tags[index].value)
        index += 1
        column_name = ""
        while index < len(table_tags):
            tag = table_tags[index]
            index += 1
            if tag.code == 301:
                column_name = str(tag.value)
            if tag.code == 340 and str(tag.value) == "0":
                break
        columns.append(_resolve_property_column(entity, source_handle, column_name))

    if index >= len(table_tags) or table_tags[index].code != 92:
        return None
    row_count = int(table_tags[index].value)
    index += 1

    rows: list[DynamicBlockPropertyRow] = []
    for _ in range(row_count):
        if index >= len(table_tags) or table_tags[index].code != 90:
            break
        row_index = int(table_tags[index].value)
        index += 1
        values: list[Any] = []
        for _column in range(column_count):
            if index >= len(table_tags) or table_tags[index].code != 170:
                break
            value_marker = int(table_tags[index].value)
            index += 1
            if index >= len(table_tags):
                break
            if value_marker == -9999 and table_tags[index].code in (170, 90, 92, 93):
                values.append(None)
                continue
            value_tag = table_tags[index]
            index += 1
            values.append(_convert_property_cell_value(value_tag))
        rows.append(DynamicBlockPropertyRow(index=row_index, values=tuple(values)))

    grip_location = None
    graph = entity.doc.entitydb.get(entity.dxf.owner) if entity.doc is not None else None
    if isinstance(graph, DXFTagStorage):
        for owned in _iter_graph_owned_objects(graph):
            grip_location = _parse_block_properties_table_grip(owned)
            if grip_location is not None:
                break

    return DynamicBlockPropertiesTable(
        handle=entity.dxf.handle or "",
        label=label,
        table_name=table_name,
        description=description,
        location=(float(location[0]), float(location[1]), float(location[2])),
        grip_location=grip_location,
        columns=tuple(columns),
        rows=tuple(rows),
    )


def _resolve_dynamic_block_record(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> Optional[BlockRecord]:
    if isinstance(source, Insert):
        block = get_dynamic_block_definition(source, doc)
        return block.block_record if block is not None else None
    if hasattr(source, "block_record"):
        return source.block_record  # BlockLayout
    return source


def get_dynamic_block_visibility_parameter(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> Optional[DynamicBlockVisibilityParameter]:
    block_record = _resolve_dynamic_block_record(source, doc)
    if block_record is None:
        return None
    graph = _get_enhanced_block_graph(block_record)
    if graph is None:
        return None
    for entity in _iter_graph_owned_objects(graph):
        parameter = _parse_visibility_parameter(entity)
        if parameter is not None:
            return parameter
    return None


def get_dynamic_block_visibility_states(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[str, ...]:
    parameter = get_dynamic_block_visibility_parameter(source, doc)
    if parameter is None:
        return ()
    return tuple(state.name for state in parameter.states)


def _iter_visibility_state_xrecords(insert: Insert) -> Iterator[XRecord]:
    if not insert.has_extension_dict:
        return iter(())
    rep = insert.get_extension_dict().dictionary.get("AcDbBlockRepresentation")
    if not isinstance(rep, Dictionary):
        return iter(())
    appdata_cache = rep.get("AppDataCache")
    if not isinstance(appdata_cache, Dictionary):
        return iter(())
    enhanced = appdata_cache.get("ACAD_ENHANCEDBLOCKDATA")
    if not isinstance(enhanced, Dictionary):
        return iter(())

    def iter_items(dictionary: Dictionary) -> Iterator[XRecord]:
        for _, value in dictionary.items():
            if isinstance(value, XRecord):
                yield value
            elif isinstance(value, Dictionary):
                yield from iter_items(value)

    return iter_items(enhanced)


def get_dynamic_block_visibility_state(
    insert: Insert, doc: Optional[Drawing] = None
) -> str:
    names = set(get_dynamic_block_visibility_states(insert, doc))
    if not names:
        return ""
    for xrecord in _iter_visibility_state_xrecords(insert):
        state_name = xrecord.tags.get_first_value(1, "")
        if state_name in names:
            return str(state_name)
    return ""


def get_dynamic_block_visibility_state_handles(
    source: Union[Insert, BlockLayout, BlockRecord],
    state: str = "",
    doc: Optional[Drawing] = None,
) -> tuple[str, ...]:
    parameter = get_dynamic_block_visibility_parameter(source, doc)
    if parameter is None or not parameter.states:
        return ()
    if not state and isinstance(source, Insert):
        state = get_dynamic_block_visibility_state(source, doc)
    for visibility_state in parameter.states:
        if visibility_state.name == state:
            return visibility_state.entity_handles
    return ()


def _resolve_block_layout(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> Optional[BlockLayout]:
    if isinstance(source, Insert):
        return get_dynamic_block_reference(source, doc)
    if hasattr(source, "block_record"):
        return source
    if doc is None:
        doc = source.doc
    if doc is None:
        return None
    return doc.blocks.get(source.dxf.name)


def get_dynamic_block_visibility_entities(
    source: Union[Insert, BlockLayout, BlockRecord],
    state: str = "",
    doc: Optional[Drawing] = None,
) -> tuple[DXFEntity, ...]:
    handles = get_dynamic_block_visibility_state_handles(source, state, doc)
    if not handles:
        return ()
    if isinstance(source, Insert):
        base_block = get_dynamic_block_definition(source, doc)
        ref_block = get_dynamic_block_reference(source, doc)
        if base_block is None or ref_block is None:
            return ()
        base_entities = list(base_block)
        ref_entities = list(ref_block)
        handle_to_index = {
            entity.dxf.handle: index
            for index, entity in enumerate(base_entities)
            if entity.dxf.handle is not None
        }
        result: list[DXFEntity] = []
        for handle in handles:
            index = handle_to_index.get(handle)
            if index is None or index >= len(ref_entities):
                continue
            result.append(ref_entities[index])
        return tuple(result)

    block = _resolve_block_layout(source, doc)
    if block is None:
        return ()
    entitydb = block.doc.entitydb if block.doc is not None else None
    if entitydb is None:
        return ()
    result: list[DXFEntity] = []
    for handle in handles:
        entity = entitydb.get(handle)
        if entity is not None:
            result.append(entity)
    return tuple(result)


def _get_dynamic_graph_owned_objects(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DXFTagStorage, ...]:
    block_record = _resolve_dynamic_block_record(source, doc)
    if block_record is None:
        return ()
    graph = _get_enhanced_block_graph(block_record)
    if graph is None:
        return ()
    return tuple(_iter_graph_owned_objects(graph))


def get_dynamic_block_linear_grips(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockLinearGrip, ...]:
    result: list[DynamicBlockLinearGrip] = []
    for entity in _get_dynamic_graph_owned_objects(source, doc):
        grip = _parse_linear_grip(entity)
        if grip is not None:
            result.append(grip)
    return tuple(result)


def get_dynamic_block_base_point_parameter(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> Optional[DynamicBlockBasePointParameter]:
    for entity in _get_dynamic_graph_owned_objects(source, doc):
        parameter = _parse_base_point_parameter(entity)
        if parameter is not None:
            return parameter
    return None


def get_dynamic_block_linear_parameters(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockLinearParameter, ...]:
    grips_by_expr = {grip.expr_id: grip for grip in get_dynamic_block_linear_grips(source, doc)}
    result: list[DynamicBlockLinearParameter] = []
    for entity in _get_dynamic_graph_owned_objects(source, doc):
        parameter = _parse_linear_parameter(entity, grips_by_expr)
        if parameter is not None:
            result.append(parameter)
    return tuple(result)


def get_dynamic_block_lookup_grips(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockLookupGrip, ...]:
    components = {
        component_expr_id: parameter_expr_id
        for entity in _get_dynamic_graph_owned_objects(source, doc)
        for component in [_parse_grip_component(entity)]
        if component is not None
        for component_expr_id, parameter_expr_id, _label in [component]
    }
    result: list[DynamicBlockLookupGrip] = []
    for entity in _get_dynamic_graph_owned_objects(source, doc):
        grip = _parse_lookup_grip(entity)
        if grip is None:
            continue
        parameter_expr_id = components.get(grip.x_expr_id, components.get(grip.y_expr_id, -1))
        result.append(
            DynamicBlockLookupGrip(
                handle=grip.handle,
                label=grip.label,
                location=grip.location,
                expr_id=grip.expr_id,
                x_expr_id=grip.x_expr_id,
                y_expr_id=grip.y_expr_id,
                parameter_expr_id=parameter_expr_id,
            )
        )
    return tuple(result)


def get_dynamic_block_lookup_parameters(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockLookupParameter, ...]:
    grips_by_param_expr = {
        grip.parameter_expr_id: grip
        for grip in get_dynamic_block_lookup_grips(source, doc)
        if grip.parameter_expr_id >= 0
    }
    result: list[DynamicBlockLookupParameter] = []
    for entity in _get_dynamic_graph_owned_objects(source, doc):
        parameter = _parse_lookup_parameter(entity, grips_by_param_expr)
        if parameter is not None:
            result.append(parameter)
    return tuple(result)


def get_dynamic_block_lookup_actions(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockLookupAction, ...]:
    result: list[DynamicBlockLookupAction] = []
    for entity in _get_dynamic_graph_owned_objects(source, doc):
        action = _parse_lookup_action(entity)
        if action is not None:
            result.append(action)
    return tuple(result)


def get_dynamic_block_stretch_actions(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockStretchAction, ...]:
    result: list[DynamicBlockStretchAction] = []
    for entity in _get_dynamic_graph_owned_objects(source, doc):
        action = _parse_stretch_action(entity)
        if action is not None:
            result.append(action)
    return tuple(result)


def get_dynamic_block_properties_table(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> Optional[DynamicBlockPropertiesTable]:
    for entity in _get_dynamic_graph_owned_objects(source, doc):
        table = _parse_block_properties_table(entity)
        if table is not None:
            return table
    return None


def get_dynamic_block_property_columns(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockPropertyColumn, ...]:
    table = get_dynamic_block_properties_table(source, doc)
    if table is None:
        return ()
    return table.columns


def get_dynamic_block_property_rows(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockPropertyRow, ...]:
    table = get_dynamic_block_properties_table(source, doc)
    if table is None:
        return ()
    return table.rows


def _iter_dynamic_reference_block_records(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> Iterator[BlockRecord]:
    block_record = _resolve_dynamic_block_record(source, doc)
    if block_record is None:
        return iter(())
    doc = block_record.doc
    handle = block_record.dxf.handle
    if doc is None or not handle:
        return iter(())

    def iterator() -> Iterator[BlockRecord]:
        for candidate in doc.block_records:
            if candidate is block_record:
                continue
            if get_dynamic_block_record_handle(candidate) == handle:
                yield candidate

    return iterator()


def _iter_assoc_network_dictionaries(block_record: BlockRecord) -> Iterator[Dictionary]:
    doc = block_record.doc
    handle = block_record.dxf.handle
    if doc is None or not handle:
        return iter(())

    def iterator() -> Iterator[Dictionary]:
        for obj in doc.objects:
            if not isinstance(obj, Dictionary) or obj.dxf.owner != handle:
                continue
            if "ACAD_ASSOCNETWORK" in obj:
                yield obj

    return iterator()


def _resolve_assoc_network(dictionary: Dictionary):
    target = dictionary.get("ACAD_ASSOCNETWORK")
    if target is None:
        return None
    if isinstance(target, Dictionary):
        target = target.get("ACAD_ASSOCNETWORK")
    return target if isinstance(target, DXFTagStorage) and target.dxftype() == "ACDBASSOCNETWORK" else None


def _parse_assoc_variable(entity: DXFTagStorage) -> Optional[DynamicBlockAssocVariable]:
    if entity.dxftype() != "ACDBASSOCVARIABLE":
        return None
    try:
        tags = entity.xtags.get_subclass("AcDbAssocVariable")
    except const.DXFKeyError:
        return None
    strings = [str(tag.value) for tag in tags if tag.code == 1]
    ints = tuple(int(tag.value) for tag in tags if tag.code == 90)
    name = strings[0] if len(strings) else ""
    value = strings[1] if len(strings) > 1 else ""
    evaluator_id = strings[2] if len(strings) > 2 else ""
    expression = strings[3] if len(strings) > 3 else ""
    return DynamicBlockAssocVariable(
        handle=entity.dxf.handle or "",
        name=name,
        value=value,
        evaluator_id=evaluator_id,
        expression=expression,
        raw_ints=ints,
    )


def get_dynamic_block_property_assoc_networks(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockAssocNetwork, ...]:
    result: list[DynamicBlockAssocNetwork] = []
    for block_record in _iter_dynamic_reference_block_records(source, doc):
        for dictionary in _iter_assoc_network_dictionaries(block_record):
            network = _resolve_assoc_network(dictionary)
            if network is None:
                continue
            variables: list[DynamicBlockAssocVariable] = []
            if len(network.xtags.subclasses) > 2:
                for code, value in network.xtags.subclasses[2]:
                    if code != 360:
                        continue
                    child = network.doc.entitydb.get(str(value)) if network.doc is not None else None
                    if not isinstance(child, DXFTagStorage):
                        continue
                    variable = _parse_assoc_variable(child)
                    if variable is not None:
                        variables.append(variable)
            result.append(
                DynamicBlockAssocNetwork(
                    handle=network.dxf.handle or "",
                    block_record_handle=block_record.dxf.handle or "",
                    block_name=block_record.dxf.name,
                    dictionary_handle=dictionary.dxf.handle or "",
                    variables=tuple(variables),
                )
            )
    return tuple(result)


def get_dynamic_block_property_representations(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockPropertyRepresentation, ...]:
    assoc_by_block = {
        network.block_record_handle: network
        for network in get_dynamic_block_property_assoc_networks(source, doc)
    }
    active_names: set[str] = set()
    block_record = _resolve_dynamic_block_record(source, doc)
    if block_record is not None and block_record.doc is not None:
        doc = block_record.doc
        for ins in doc.modelspace().query("INSERT"):
            base = get_dynamic_block_definition(ins, doc)
            if base is not None and base.block_record is block_record:
                active_names.add(ins.dxf.name)
    result: list[DynamicBlockPropertyRepresentation] = []
    for block_record in _iter_dynamic_reference_block_records(source, doc):
        block = _resolve_block_layout(block_record, doc)
        if block is None:
            continue
        carriers = tuple(
            DynamicBlockPropertyCarrier(
                handle=entity.dxf.handle or "",
                tag=entity.dxf.tag,
                text=entity.dxf.text,
                invisible=int(entity.dxf.get("invisible", 0)),
            )
            for entity in block
            if entity.dxftype() == "ATTDEF"
        )
        if not carriers and block_record.dxf.handle not in assoc_by_block:
            continue
        result.append(
            DynamicBlockPropertyRepresentation(
                block_record_handle=block_record.dxf.handle or "",
                block_name=block_record.dxf.name,
                is_active=block_record.dxf.name in active_names,
                invisible_flags=tuple(int(entity.dxf.get("invisible", 0)) for entity in block),
                carriers=carriers,
                assoc_network=assoc_by_block.get(block_record.dxf.handle or ""),
            )
        )
    return tuple(result)


def get_dynamic_block_property_representation_families(
    source: Union[Insert, BlockLayout, BlockRecord], doc: Optional[Drawing] = None
) -> tuple[DynamicBlockPropertyRepresentationFamily, ...]:
    families: dict[
        tuple[tuple[int, ...], int, tuple[str, ...], tuple[int, ...], tuple[tuple[str, str], ...]],
        list[str],
    ] = {}
    for rep in get_dynamic_block_property_representations(source, doc):
        assoc_signature: tuple[tuple[str, str], ...] = ()
        if rep.assoc_network is not None:
            assoc_signature = tuple((var.name, var.value) for var in rep.assoc_network.variables)
        key = (
            rep.invisible_flags,
            len(rep.carriers),
            tuple(carrier.text for carrier in rep.carriers),
            tuple(carrier.invisible for carrier in rep.carriers),
            assoc_signature,
        )
        families.setdefault(key, []).append(rep.block_name)

    result: list[DynamicBlockPropertyRepresentationFamily] = []
    for key, names in families.items():
        invisible_flags, carrier_count, carrier_texts, carrier_visibility, assoc_signature = key
        result.append(
            DynamicBlockPropertyRepresentationFamily(
                invisible_flags=invisible_flags,
                carrier_count=carrier_count,
                carrier_texts=carrier_texts,
                carrier_visibility=carrier_visibility,
                assoc_signature=assoc_signature,
                block_names=tuple(names),
            )
        )
    return tuple(result)


def _delete_graph_stack(block_record: BlockRecord) -> None:
    graph = _get_enhanced_block_graph(block_record)
    if graph is None:
        return
    doc = block_record.doc
    if doc is None:
        return
    xdict = block_record.get_extension_dict().dictionary
    for entity in list(_iter_graph_owned_objects(graph)):
        doc.objects.delete_entity(entity)
    xdict.discard("ACAD_ENHANCEDBLOCK")
    doc.objects.delete_entity(graph)
    purge = xdict.get("AcDbDynamicBlockRoundTripPurgePreventer")
    if isinstance(purge, DXFTagStorage):
        xdict.discard("AcDbDynamicBlockRoundTripPurgePreventer")
        doc.objects.delete_entity(purge)


def _delete_assoc_networks(block_record: BlockRecord) -> None:
    doc = block_record.doc
    if doc is None:
        return
    for obj in list(doc.objects):
        if isinstance(obj, Dictionary) and obj.dxf.owner == block_record.dxf.handle:
            if "ACAD_ASSOCNETWORK" in obj:
                doc.objects.delete_entity(obj)


def _delete_owned_object_tree(doc: Drawing, owner_handle: str) -> None:
    if not owner_handle:
        return
    children = [entity for entity in doc.objects if entity.dxf.owner == owner_handle]
    for entity in children:
        handle = entity.dxf.handle or ""
        if isinstance(entity, Dictionary) and entity.is_hard_owner:
            doc.objects.delete_entity(entity)
            continue
        _delete_owned_object_tree(doc, handle)
        if entity.is_alive:
            doc.objects.delete_entity(entity)


def _delete_hidden_dynamic_support_blocks(block_record: BlockRecord) -> None:
    doc = block_record.doc
    if doc is None:
        return
    to_delete: list[str] = []
    for candidate in _iter_dynamic_reference_block_records(block_record, doc):
        if candidate.blkref_handles:
            continue
        _delete_owned_object_tree(doc, candidate.dxf.handle or "")
        to_delete.append(candidate.dxf.name)
    for name in to_delete:
        if name in doc.blocks:
            doc.blocks.delete_block(name, safe=False)


def _clone_non_attdef_entities(source_block: BlockLayout, target_block: BlockLayout) -> None:
    for entity in source_block:
        if entity.dxftype() == "ATTDEF":
            continue
        target_block.add_entity(entity.copy())


def _clone_property_attdef(source_attdef, target_block: BlockLayout, *, text: str, invisible: bool) -> None:
    clone = target_block.add_attdef(
        source_attdef.dxf.tag,
        insert=source_attdef.dxf.insert,
        text=text,
        height=source_attdef.dxf.height,
        rotation=source_attdef.dxf.get("rotation", 0.0),
        dxfattribs={
            "layer": source_attdef.dxf.layer,
            "color": source_attdef.dxf.color,
            "style": source_attdef.dxf.style,
            "flags": source_attdef.dxf.flags,
            "lock_position": source_attdef.dxf.get("lock_position", 1),
        },
    )
    clone.dxf.prompt = source_attdef.dxf.prompt
    if invisible:
        clone.dxf.invisible = 1
    else:
        clone.dxf.discard("invisible")


def _set_property_attdef_reactors(block: BlockLayout, table_handle: str) -> None:
    for entity in block:
        if entity.dxftype() == "ATTDEF":
            entity.set_reactors([table_handle])


def _assoc_variable_tags(network_handle: str, variable_index: int, name: str, value: str) -> list[list[tuple[int, Any]]]:
    stored_value = value
    int_value = 0
    if isinstance(value, str) and value.startswith("VAL "):
        try:
            int_value = int(value.split()[-1])
            stored_value = str(int_value)
        except ValueError:
            int_value = 0
    else:
        try:
            int_value = int(value)
            stored_value = str(int_value)
        except (TypeError, ValueError):
            int_value = 0
    return [
        [
            (100, "AcDbAssocAction"),
            (90, 2),
            (90, 0),
            (330, network_handle),
            (360, "0"),
            (90, variable_index),
            (90, 0),
            (90, 0),
            (90, 0),
            (90, 0),
            (90, 0),
            (90, 0),
        ],
        [
            (100, "AcDbAssocVariable"),
            (90, 2),
            (1, name),
            (1, stored_value),
            (1, "AcDbCalc:1.0"),
            (1, ""),
            (90, int_value),
            (290, 0),
            (290, 0),
            (90, 0),
        ],
    ]


def _ensure_root_assoc_network(doc: Drawing) -> DXFTagStorage:
    rootdict = doc.rootdict
    outer = rootdict.get("ACAD_ASSOCNETWORK")
    if not isinstance(outer, Dictionary):
        outer = rootdict.add_new_dict("ACAD_ASSOCNETWORK")
        outer.set_reactors([rootdict.dxf.handle])
    network = _resolve_assoc_network(outer)
    if isinstance(network, DXFTagStorage):
        return network
    network = _new_tag_storage_object(
        doc,
        "ACDBASSOCNETWORK",
        outer.dxf.handle,
        [
            [
                (100, "AcDbAssocAction"),
                (90, 2),
                (90, 0),
                (330, "0"),
                (360, "0"),
                (90, 0),
                (90, 0),
                (90, 0),
                (90, 0),
                (90, 0),
                (90, 0),
                (90, 0),
            ],
            [(100, "AcDbAssocNetwork"), (90, 0), (90, 6), (90, 0), (90, 0)],
        ],
    )
    _set_owner_reactor(network, outer.dxf.handle)
    outer.add("ACAD_ASSOCNETWORK", network)
    return network


def _set_root_assoc_children(network: DXFTagStorage, child_handles: Sequence[str]) -> None:
    sub = network.xtags.get_subclass("AcDbAssocNetwork")
    tags = [(100, "AcDbAssocNetwork"), (90, 0), (90, len(child_handles) + 6), (90, len(child_handles))]
    tags.extend((330, handle) for handle in child_handles)
    tags.append((90, 0))
    sub.clear()
    from ezdxf.lldxf.types import dxftag

    sub.extend(dxftag(code, value) for code, value in tags)


def _new_assoc_network_bundle(
    block_record: BlockRecord,
    root_network_handle: str,
    variables: Sequence[tuple[str, str]],
    *,
    action_index: int,
) -> DynamicBlockAssocNetwork:
    doc = block_record.doc
    assert doc is not None
    outer = doc.objects.add_dictionary(owner=block_record.dxf.handle)
    inner = outer.add_new_dict("ACAD_ASSOCNETWORK")
    inner.set_reactors([outer.dxf.handle])
    network = _new_tag_storage_object(
        doc,
        "ACDBASSOCNETWORK",
        inner.dxf.handle,
        [
            [
                (100, "AcDbAssocAction"),
                (90, 2),
                (90, 0),
                (330, root_network_handle),
                (360, "0"),
                (90, action_index),
                (90, 0),
                (90, 0),
                (90, 0),
                (90, 0),
                (90, 0),
                (90, 0),
            ],
            [
                (100, "AcDbAssocNetwork"),
                (90, 0),
                (90, len(variables)),
                (90, len(variables)),
                *[(360, "0") for _ in variables],
                (90, 0),
            ],
        ],
    )
    _set_owner_reactor(network, inner.dxf.handle)
    inner.add("ACAD_ASSOCNETWORK", network)
    network_sub = network.xtags.get_subclass("AcDbAssocNetwork")
    created_variables: list[DynamicBlockAssocVariable] = []
    handles: list[str] = []
    for index, (name, value) in enumerate(variables, start=1):
        entity = _new_tag_storage_object(
            doc,
            "ACDBASSOCVARIABLE",
            network.dxf.handle,
            _assoc_variable_tags(network.dxf.handle, index, name, value),
        )
        handles.append(entity.dxf.handle)
        created_variables.append(
            DynamicBlockAssocVariable(
                handle=entity.dxf.handle or "",
                name=name,
                value=value,
                evaluator_id="AcDbCalc:1.0",
                expression="",
                raw_ints=(2, int(value.split()[-1]) if value.startswith("VAL ") else 0, 0),
            )
        )
    tags = [(100, "AcDbAssocNetwork"), (90, 0), (90, len(variables)), (90, len(variables))]
    tags.extend((360, handle) for handle in handles)
    tags.append((90, 0))
    network_sub.clear()
    from ezdxf.lldxf.types import dxftag

    network_sub.extend(dxftag(code, value) for code, value in tags)
    return DynamicBlockAssocNetwork(
        handle=network.dxf.handle or "",
        block_record_handle=block_record.dxf.handle or "",
        block_name=block_record.dxf.name,
        dictionary_handle=outer.dxf.handle or "",
        variables=tuple(created_variables),
    )


def _resolve_property_table_columns(
    block: BlockLayout,
    table: DynamicBlockPropertiesTable,
    visibility: DynamicBlockVisibilityParameter,
) -> tuple[DynamicBlockPropertyColumn, ...]:
    doc = block.doc
    assert doc is not None
    entitydb = doc.entitydb
    columns: list[DynamicBlockPropertyColumn] = []
    attdef_index = 1
    for column in table.columns:
        source_handle = column.source_handle
        source_dxftype = column.source_dxftype or "ATTDEF"
        name = column.name
        display_name = column.display_name
        if source_dxftype == "BLOCKVISIBILITYPARAMETER":
            source_handle = visibility.handle
            display_name = display_name or name or "VisibilityState"
            name = name or visibility.parameter_name
        elif source_dxftype == "ATTDEF":
            attdef = entitydb.get(source_handle) if source_handle else None
            if attdef is None:
                x = table.location[0] + 1.5 + (attdef_index % 2) * 0.25
                y = table.location[1] - 4.5 * attdef_index - (attdef_index % 2) * 0.3
                attdef = block.add_attdef(
                    name or f"PARAM_{attdef_index}",
                    insert=(x, y),
                    text=table.table_name or "Block Table1",
                    height=2.5,
                    dxfattribs={"flags": 1, "lock_position": 1},
                )
                source_handle = attdef.dxf.handle
            else:
                source_handle = attdef.dxf.handle
            name = name or attdef.dxf.get("tag", source_handle)
            display_name = display_name or attdef.dxf.get("text", "")
            attdef_index += 1
        columns.append(
            DynamicBlockPropertyColumn(
                source_handle=source_handle,
                source_dxftype=source_dxftype,
                name=name or source_handle,
                display_name=display_name,
            )
        )
    return tuple(columns)


def _build_block_properties_table_subclass(
    table: DynamicBlockPropertiesTable,
    columns: Sequence[DynamicBlockPropertyColumn],
) -> list[tuple[int, Any]]:
    tags: list[tuple[int, Any]] = [
        (100, "AcDbBlockPropertiesTable"),
        (90, 2),
        (300, table.table_name),
        (301, table.description),
        (91, len(columns)),
    ]
    for column in columns:
        value_type = 6 if column.source_dxftype == "BLOCKVISIBILITYPARAMETER" else 0
        editable = 0 if column.source_dxftype == "BLOCKVISIBILITYPARAMETER" else 1
        tags.extend(
            [
                (340, column.source_handle),
                (170, 0),
                (171, -1),
                (300, ""),
                (301, column.display_name if column.source_dxftype == "BLOCKVISIBILITYPARAMETER" else ""),
                (90, value_type),
                (170, -9999),
                (170, -9999),
                (290, 0),
                (291, 1),
                (292, 1),
                (293, 0),
                (294, editable),
                (302, ""),
                (340, "0"),
            ]
        )
    tags.append((92, len(table.rows)))
    for row in table.rows:
        tags.append((90, row.index))
        for value in row.values:
            if value is None:
                tags.append((170, -9999))
                continue
            tags.append((170, 1))
            tags.append((300, str(value)))
    tags.extend([(93, len(table.rows)), (290, 0), (291, 1), (292, 0)])
    return tags


def _build_property_visibility_parameter_subclass(
    visibility: DynamicBlockVisibilityParameter,
    properties_table_handle: str,
    properties_grip_handle: str,
    *,
    extra_state_refs: Sequence[Sequence[str]] = (),
    all_handles: Optional[Sequence[str]] = None,
    include_table_in_all_states: bool = False,
    table_before_grip: bool = False,
) -> list[tuple[int, Any]]:
    if all_handles is None:
        all_handles = visibility.all_entity_handles or tuple(
            handle
            for state in visibility.states
            for handle in state.entity_handles
            if handle
        )
    tags: list[tuple[int, Any]] = [
        (100, "AcDbBlockVisibilityParameter"),
        (281, 1),
        (301, visibility.parameter_name),
        (302, ""),
        (91, 0),
        (93, len(all_handles)),
        *[(331, handle) for handle in all_handles],
        (92, len(visibility.states)),
    ]
    for index, state in enumerate(visibility.states):
        tags.extend(
            [
                (303, state.name),
                (94, len(state.entity_handles)),
                *[(332, handle) for handle in state.entity_handles],
            ]
        )
        refs: list[str] = []
        if table_before_grip and properties_table_handle and (include_table_in_all_states or index == 0):
            refs.append(properties_table_handle)
        refs.append(properties_grip_handle)
        if not table_before_grip and properties_table_handle and (include_table_in_all_states or index == 0):
            refs.append(properties_table_handle)
        if index < len(extra_state_refs):
            refs.extend(extra_state_refs[index])
        refs = [handle for handle in refs if handle and handle != "0"]
        tags.extend([(95, len(refs)), *[(333, handle) for handle in refs]])
    return tags


def _unique_handles(handles: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for handle in handles:
        value = str(handle)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _augment_visibility_with_property_attdefs(
    visibility: DynamicBlockVisibilityParameter,
    attdefs: Sequence[Any],
) -> DynamicBlockVisibilityParameter:
    property_handles = tuple(attdef.dxf.handle for attdef in attdefs if attdef.dxf.handle)
    if not property_handles:
        return visibility
    all_handles = _unique_handles([*(visibility.all_entity_handles or ()), *property_handles])
    if not all_handles:
        all_handles = _unique_handles(
            [handle for state in visibility.states for handle in state.entity_handles]
        )
    return DynamicBlockVisibilityParameter(
        handle=visibility.handle,
        label=visibility.label,
        parameter_name=visibility.parameter_name,
        location=visibility.location,
        states=visibility.states,
        all_entity_handles=all_handles,
    )


def _replace_subclass_tags(subclass, tags: Sequence[tuple[int, Any]]) -> None:
    from ezdxf.lldxf.types import dxftag

    subclass.clear()
    subclass.extend(dxftag(code, value) for code, value in tags)


def _patch_eval_graph_handles(graph: DXFTagStorage, handles: Sequence[str]) -> None:
    eval_graph = graph.xtags.get_subclass("AcDbEvalGraph")
    from ezdxf.lldxf.types import dxftag

    handle_index = 0
    for index, tag in enumerate(eval_graph):
        if tag.code == 360 and handle_index < len(handles):
            eval_graph[index] = dxftag(360, handles[handle_index])
            handle_index += 1


def _set_graph_node_id(graph: DXFTagStorage, node_id: int) -> None:
    graph.set_xdata(AcadBPTGraphNodeId, [(1071, node_id)])


def _set_visibility_column_value_type(
    table_entity: DXFTagStorage,
    visibility_handle: str,
    value_type: int,
) -> None:
    sub = table_entity.xtags.get_subclass("AcDbBlockPropertiesTable")
    tags = list(sub)
    column_count = int(next((tag.value for tag in tags if tag.code == 91), 0))
    if column_count <= 0:
        return
    offset = 5
    chunk_size = 15
    for _ in range(column_count):
        if offset + chunk_size > len(tags):
            break
        chunk = list(tags[offset : offset + chunk_size])
        if chunk[0].code == 340 and str(chunk[0].value) == visibility_handle:
            chunk[5] = type(chunk[5])(90, value_type)
            tags[offset : offset + chunk_size] = chunk
            _replace_subclass_tags(sub, [(tag.code, tag.value) for tag in tags])
            return
        offset += chunk_size


def _register_blkref_handle(block: BlockLayout, insert: Insert) -> None:
    handles = block.block_record.blkref_handles
    handle = insert.dxf.handle
    if handle and handle not in handles:
        handles.append(handle)


def _build_linear_eval_graph_subclass() -> list[tuple[int, Any]]:
    return [
        (100, "AcDbEvalGraph"),
        (96, 52),
        (97, 52),
        (91, 0),
        (93, 32),
        (95, 6),
        (360, "0"),
        (92, 3),
        (92, 3),
        (92, 4),
        (92, 4),
        (91, 1),
        (93, 32),
        (95, 16),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (91, 2),
        (93, 32),
        (95, 32),
        (360, "0"),
        (92, 0),
        (92, 4),
        (92, 1),
        (92, 3),
        (91, 3),
        (93, 32),
        (95, 33),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 0),
        (92, 0),
        (91, 4),
        (93, 32),
        (95, 34),
        (360, "0"),
        (92, 1),
        (92, 1),
        (92, -1),
        (92, -1),
        (91, 5),
        (93, 32),
        (95, 35),
        (360, "0"),
        (92, 2),
        (92, 2),
        (92, -1),
        (92, -1),
        (91, 6),
        (93, 32),
        (95, 45),
        (360, "0"),
        (92, 7),
        (92, 10),
        (92, 5),
        (92, 11),
        (91, 7),
        (93, 32),
        (95, 46),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 7),
        (92, 7),
        (91, 8),
        (93, 32),
        (95, 47),
        (360, "0"),
        (92, 5),
        (92, 5),
        (92, -1),
        (92, -1),
        (91, 9),
        (93, 32),
        (95, 48),
        (360, "0"),
        (92, 6),
        (92, 6),
        (92, -1),
        (92, -1),
        (91, 10),
        (93, 32),
        (95, 49),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 10),
        (92, 10),
        (91, 11),
        (93, 32),
        (95, 50),
        (360, "0"),
        (92, 8),
        (92, 8),
        (92, -1),
        (92, -1),
        (91, 12),
        (93, 32),
        (95, 51),
        (360, "0"),
        (92, 9),
        (92, 9),
        (92, -1),
        (92, -1),
        (91, 13),
        (93, 32),
        (95, 52),
        (360, "0"),
        (92, 11),
        (92, 11),
        (92, -1),
        (92, -1),
        (92, 0),
        (93, 0),
        (94, 1),
        (91, 3),
        (91, 2),
        (92, -1),
        (92, 4),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 1),
        (93, 0),
        (94, 1),
        (91, 2),
        (91, 4),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 2),
        (92, -1),
        (92, 2),
        (93, 0),
        (94, 1),
        (91, 2),
        (91, 5),
        (92, -1),
        (92, -1),
        (92, 1),
        (92, 3),
        (92, -1),
        (92, 3),
        (93, 4),
        (94, 1),
        (91, 2),
        (91, 0),
        (92, -1),
        (92, -1),
        (92, 2),
        (92, -1),
        (92, 4),
        (92, 4),
        (93, 4),
        (94, 1),
        (91, 0),
        (91, 2),
        (92, 0),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 3),
        (92, 5),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 8),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 6),
        (92, -1),
        (92, 6),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 9),
        (92, -1),
        (92, -1),
        (92, 5),
        (92, 8),
        (92, -1),
        (92, 7),
        (93, 0),
        (94, 2),
        (91, 7),
        (91, 6),
        (92, -1),
        (92, 10),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 8),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 11),
        (92, -1),
        (92, -1),
        (92, 6),
        (92, 9),
        (92, -1),
        (92, 9),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 12),
        (92, -1),
        (92, -1),
        (92, 8),
        (92, 11),
        (92, -1),
        (92, 10),
        (93, 0),
        (94, 2),
        (91, 10),
        (91, 6),
        (92, 7),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 11),
        (93, 0),
        (94, 2),
        (91, 6),
        (91, 13),
        (92, -1),
        (92, -1),
        (92, 9),
        (92, -1),
        (92, -1),
    ]


def _build_visibility_basepoint_eval_graph_subclass() -> list[tuple[int, Any]]:
    return [
        (100, "AcDbEvalGraph"),
        (96, 5),
        (97, 5),
        (91, 0),
        (93, 32),
        (95, 1),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (91, 1),
        (93, 32),
        (95, 2),
        (360, "0"),
        (92, 0),
        (92, 0),
        (92, 1),
        (92, 2),
        (91, 2),
        (93, 32),
        (95, 3),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 0),
        (92, 0),
        (91, 3),
        (93, 32),
        (95, 4),
        (360, "0"),
        (92, 1),
        (92, 1),
        (92, -1),
        (92, -1),
        (91, 4),
        (93, 32),
        (95, 5),
        (360, "0"),
        (92, 2),
        (92, 2),
        (92, -1),
        (92, -1),
        (92, 0),
        (93, 0),
        (94, 1),
        (91, 2),
        (91, 1),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 1),
        (93, 0),
        (94, 1),
        (91, 1),
        (91, 3),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 2),
        (92, -1),
        (92, 2),
        (93, 0),
        (94, 1),
        (91, 1),
        (91, 4),
        (92, -1),
        (92, -1),
        (92, 1),
        (92, -1),
        (92, -1),
    ]


def _build_lookup_eval_graph_subclass() -> list[tuple[int, Any]]:
    return [
        (100, "AcDbEvalGraph"),
        (96, 75),
        (97, 75),
        (91, 0),
        (93, 32),
        (95, 6),
        (360, "0"),
        (92, 3),
        (92, 3),
        (92, 4),
        (92, 4),
        (91, 1),
        (93, 32),
        (95, 16),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (91, 2),
        (93, 32),
        (95, 32),
        (360, "0"),
        (92, 0),
        (92, 4),
        (92, 1),
        (92, 3),
        (91, 3),
        (93, 32),
        (95, 33),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 0),
        (92, 0),
        (91, 4),
        (93, 32),
        (95, 34),
        (360, "0"),
        (92, 1),
        (92, 1),
        (92, -1),
        (92, -1),
        (91, 5),
        (93, 32),
        (95, 35),
        (360, "0"),
        (92, 2),
        (92, 2),
        (92, -1),
        (92, -1),
        (91, 6),
        (93, 32),
        (95, 45),
        (360, "0"),
        (92, 7),
        (92, 17),
        (92, 5),
        (92, 16),
        (91, 7),
        (93, 32),
        (95, 46),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 7),
        (92, 7),
        (91, 8),
        (93, 32),
        (95, 47),
        (360, "0"),
        (92, 5),
        (92, 5),
        (92, -1),
        (92, -1),
        (91, 9),
        (93, 32),
        (95, 48),
        (360, "0"),
        (92, 6),
        (92, 6),
        (92, -1),
        (92, -1),
        (91, 10),
        (93, 32),
        (95, 49),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 10),
        (92, 10),
        (91, 11),
        (93, 32),
        (95, 50),
        (360, "0"),
        (92, 8),
        (92, 8),
        (92, -1),
        (92, -1),
        (91, 12),
        (93, 32),
        (95, 51),
        (360, "0"),
        (92, 9),
        (92, 9),
        (92, -1),
        (92, -1),
        (91, 13),
        (93, 32),
        (95, 52),
        (360, "0"),
        (92, 11),
        (92, 11),
        (92, -1),
        (92, -1),
        (91, 14),
        (93, 32),
        (95, 57),
        (360, "0"),
        (92, 12),
        (92, 12),
        (92, -1),
        (92, -1),
        (91, 15),
        (93, 32),
        (95, 71),
        (360, "0"),
        (92, 13),
        (92, 18),
        (92, 14),
        (92, 19),
        (91, 16),
        (93, 32),
        (95, 72),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 13),
        (92, 13),
        (91, 17),
        (93, 32),
        (95, 73),
        (360, "0"),
        (92, 14),
        (92, 14),
        (92, -1),
        (92, -1),
        (91, 18),
        (93, 32),
        (95, 74),
        (360, "0"),
        (92, 15),
        (92, 15),
        (92, -1),
        (92, -1),
        (91, 19),
        (93, 32),
        (95, 75),
        (360, "0"),
        (92, 16),
        (92, 19),
        (92, 17),
        (92, 18),
        (92, 0),
        (93, 0),
        (94, 1),
        (91, 3),
        (91, 2),
        (92, -1),
        (92, 4),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 1),
        (93, 0),
        (94, 1),
        (91, 2),
        (91, 4),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 2),
        (92, -1),
        (92, 2),
        (93, 0),
        (94, 1),
        (91, 2),
        (91, 5),
        (92, -1),
        (92, -1),
        (92, 1),
        (92, 3),
        (92, -1),
        (92, 3),
        (93, 4),
        (94, 1),
        (91, 2),
        (91, 0),
        (92, -1),
        (92, -1),
        (92, 2),
        (92, -1),
        (92, 4),
        (92, 4),
        (93, 4),
        (94, 1),
        (91, 0),
        (91, 2),
        (92, 0),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 3),
        (92, 5),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 8),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 6),
        (92, -1),
        (92, 6),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 9),
        (92, -1),
        (92, -1),
        (92, 5),
        (92, 8),
        (92, -1),
        (92, 7),
        (93, 0),
        (94, 2),
        (91, 7),
        (91, 6),
        (92, -1),
        (92, 10),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 8),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 11),
        (92, -1),
        (92, -1),
        (92, 6),
        (92, 9),
        (92, -1),
        (92, 9),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 12),
        (92, -1),
        (92, -1),
        (92, 8),
        (92, 11),
        (92, -1),
        (92, 10),
        (93, 0),
        (94, 2),
        (91, 10),
        (91, 6),
        (92, 7),
        (92, 17),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 11),
        (93, 0),
        (94, 2),
        (91, 6),
        (91, 13),
        (92, -1),
        (92, -1),
        (92, 9),
        (92, 12),
        (92, -1),
        (92, 12),
        (93, 0),
        (94, 1),
        (91, 6),
        (91, 14),
        (92, -1),
        (92, -1),
        (92, 11),
        (92, 16),
        (92, -1),
        (92, 13),
        (93, 0),
        (94, 1),
        (91, 16),
        (91, 15),
        (92, -1),
        (92, 18),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 14),
        (93, 0),
        (94, 1),
        (91, 15),
        (91, 17),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 15),
        (92, -1),
        (92, 15),
        (93, 0),
        (94, 1),
        (91, 15),
        (91, 18),
        (92, -1),
        (92, -1),
        (92, 14),
        (92, 19),
        (92, -1),
        (92, 16),
        (93, 4),
        (94, 1),
        (91, 6),
        (91, 19),
        (92, -1),
        (92, 19),
        (92, 12),
        (92, -1),
        (92, 17),
        (92, 17),
        (93, 4),
        (94, 1),
        (91, 19),
        (91, 6),
        (92, 10),
        (92, -1),
        (92, -1),
        (92, 18),
        (92, 16),
        (92, 18),
        (93, 4),
        (94, 1),
        (91, 19),
        (91, 15),
        (92, 13),
        (92, -1),
        (92, 17),
        (92, -1),
        (92, 19),
        (92, 19),
        (93, 4),
        (94, 1),
        (91, 15),
        (91, 19),
        (92, 16),
        (92, -1),
        (92, 15),
        (92, -1),
        (92, 18),
    ]


def _build_lookup_action_subclass(action: DynamicBlockLookupAction) -> list[tuple[int, Any]]:
    tags: list[tuple[int, Any]] = [
        (100, "AcDbBlockLookupAction"),
        (92, action.row_count),
        (93, action.column_count),
        (301, ""),
    ]
    for row in action.entries:
        for value in row:
            tags.append((302, value))
    for binding in action.bindings:
        tags.extend(
            [
                (303, binding.group_label),
                (94, binding.expr_id),
                (95, binding.value_code),
                (96, binding.value_type),
                (282, binding.flag282),
                (305, binding.display_name),
                (281, binding.flag281),
                (304, binding.property_name),
            ]
        )
    tags.append((280, action.enabled))
    return tags


def _build_basepoint_linear_eval_graph_subclass() -> list[tuple[int, Any]]:
    return [
        (100, "AcDbEvalGraph"),
        (96, 20),
        (97, 20),
        (91, 0),
        (93, 32),
        (95, 1),
        (360, "0"),
        (92, 3),
        (92, 3),
        (92, 4),
        (92, 4),
        (91, 1),
        (93, 32),
        (95, 5),
        (360, "0"),
        (92, 9),
        (92, 9),
        (92, -1),
        (92, -1),
        (91, 2),
        (93, 32),
        (95, 6),
        (360, "0"),
        (92, 0),
        (92, 4),
        (92, 1),
        (92, 3),
        (91, 3),
        (93, 32),
        (95, 7),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 0),
        (92, 0),
        (91, 4),
        (93, 32),
        (95, 8),
        (360, "0"),
        (92, 1),
        (92, 1),
        (92, -1),
        (92, -1),
        (91, 5),
        (93, 32),
        (95, 9),
        (360, "0"),
        (92, 2),
        (92, 2),
        (92, -1),
        (92, -1),
        (91, 6),
        (93, 32),
        (95, 10),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (91, 7),
        (93, 32),
        (95, 16),
        (360, "0"),
        (92, 7),
        (92, 7),
        (92, 5),
        (92, 8),
        (91, 8),
        (93, 32),
        (95, 17),
        (360, "0"),
        (92, -1),
        (92, -1),
        (92, 7),
        (92, 7),
        (91, 9),
        (93, 32),
        (95, 18),
        (360, "0"),
        (92, 5),
        (92, 5),
        (92, -1),
        (92, -1),
        (91, 10),
        (93, 32),
        (95, 19),
        (360, "0"),
        (92, 6),
        (92, 6),
        (92, -1),
        (92, -1),
        (91, 11),
        (93, 32),
        (95, 20),
        (360, "0"),
        (92, 8),
        (92, 8),
        (92, 9),
        (92, 9),
        (92, 0),
        (93, 0),
        (94, 1),
        (91, 3),
        (91, 2),
        (92, -1),
        (92, 4),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 1),
        (93, 0),
        (94, 1),
        (91, 2),
        (91, 4),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 2),
        (92, -1),
        (92, 2),
        (93, 0),
        (94, 1),
        (91, 2),
        (91, 5),
        (92, -1),
        (92, -1),
        (92, 1),
        (92, 3),
        (92, -1),
        (92, 3),
        (93, 4),
        (94, 1),
        (91, 2),
        (91, 0),
        (92, -1),
        (92, -1),
        (92, 2),
        (92, -1),
        (92, 4),
        (92, 4),
        (93, 4),
        (94, 1),
        (91, 0),
        (91, 2),
        (92, 0),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 3),
        (92, 5),
        (93, 0),
        (94, 1),
        (91, 7),
        (91, 9),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 6),
        (92, -1),
        (92, 6),
        (93, 0),
        (94, 1),
        (91, 7),
        (91, 10),
        (92, -1),
        (92, -1),
        (92, 5),
        (92, 8),
        (92, -1),
        (92, 7),
        (93, 0),
        (94, 2),
        (91, 8),
        (91, 7),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, 8),
        (93, 0),
        (94, 2),
        (91, 7),
        (91, 11),
        (92, -1),
        (92, -1),
        (92, 6),
        (92, -1),
        (92, -1),
        (92, 9),
        (93, 0),
        (94, 1),
        (91, 11),
        (91, 1),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
        (92, -1),
    ]


def set_dynamic_block_properties_table(
    block: BlockLayout,
    table: DynamicBlockPropertiesTable,
) -> DynamicBlockPropertiesTable:
    """Attach a dynamic block properties table to an existing dynamic block.

    This is a minimal authoring helper for the `BLOCKPROPERTIESTABLE` stack
    observed in AutoCAD-authored dynamic blocks. It currently supports string
    table values and expects an existing visibility parameter on `block`.
    """
    doc = block.doc
    if doc is None:
        raise const.DXFStructureError("valid DXF document required")
    _ensure_dynamic_block_properties_appids(doc)
    visibility = get_dynamic_block_visibility_parameter(block)
    if visibility is None:
        raise const.DXFValueError("dynamic block has no visibility parameter")
    linear_parameters = get_dynamic_block_linear_parameters(block)
    stretch_actions = get_dynamic_block_stretch_actions(block)
    if len(linear_parameters) > 1:
        raise const.DXFValueError("multiple dynamic block linear parameters are not supported")
    if len(stretch_actions) != len(linear_parameters):
        raise const.DXFValueError("linear parameter and stretch action counts do not match")

    preexisting_attdefs = {
        entity.dxf.tag: _property_attdef_state(entity)
        for entity in block
        if entity.dxftype() == "ATTDEF"
    }

    resolved_columns = _resolve_property_table_columns(block, table, visibility)
    _tag_block_representation_entities(block)
    for index, entity in enumerate(block):
        if entity.dxftype() == "ATTDEF":
            metadata = preexisting_attdefs.get(
                entity.dxf.tag,
                _PropertyAttdefState(True, 0, False, True, None),
            )
            was_annotative = metadata.annotative
            invisible = metadata.invisible
            has_context_record = metadata.has_context_record
            if not metadata.has_extension_dict:
                was_annotative = True
                invisible = 0
                has_context_record = True
            _set_property_attdef_rep_etag(entity, index)
            if was_annotative:
                _ensure_property_attdef_annotative_metadata(
                    entity, create_context_record=has_context_record
                )
            else:
                entity.discard_xdata("AcadAnnotative")
            if invisible:
                entity.dxf.invisible = invisible
            else:
                entity.dxf.discard("invisible")
    _delete_graph_stack(block.block_record)

    true_name = block.name
    if block.block_record.has_xdata(AcDbDynamicBlockTrueName):
        for tag in block.block_record.get_xdata(AcDbDynamicBlockTrueName):
            if tag.code == 1000 and tag.value:
                true_name = str(tag.value)
                break
        block.block_record.discard_xdata(AcDbDynamicBlockTrueName)
    block.block_record.set_xdata(AcDbDynamicBlockTrueName2, [(1000, true_name)])

    xdict = _ensure_dynamic_block_extension_dict(block.block_record)
    graph = _new_tag_storage_object(
        doc,
        "ACAD_EVALUATION_GRAPH",
        xdict.dxf.handle,
        [[
            (100, "AcDbEvalGraph"),
            (96, 35),
            (97, 35),
            (91, 0),
            (93, 32),
            (95, 6),
            (360, "0"),
            (92, 3),
            (92, 3),
            (92, 4),
            (92, 4),
            (91, 1),
            (93, 32),
            (95, 16),
            (360, "0"),
            (92, -1),
            (92, -1),
            (92, -1),
            (92, -1),
            (91, 2),
            (93, 32),
            (95, 32),
            (360, "0"),
            (92, 0),
            (92, 4),
            (92, 1),
            (92, 3),
            (91, 3),
            (93, 32),
            (95, 33),
            (360, "0"),
            (92, -1),
            (92, -1),
            (92, 0),
            (92, 0),
            (91, 4),
            (93, 32),
            (95, 34),
            (360, "0"),
            (92, 1),
            (92, 1),
            (92, -1),
            (92, -1),
            (91, 5),
            (93, 32),
            (95, 35),
            (360, "0"),
            (92, 2),
            (92, 2),
            (92, -1),
            (92, -1),
            (92, 0),
            (93, 0),
            (94, 1),
            (91, 3),
            (91, 2),
            (92, -1),
            (92, 4),
            (92, -1),
            (92, -1),
            (92, -1),
            (92, 1),
            (93, 0),
            (94, 1),
            (91, 2),
            (91, 4),
            (92, -1),
            (92, -1),
            (92, -1),
            (92, 2),
            (92, -1),
            (92, 2),
            (93, 0),
            (94, 1),
            (91, 2),
            (91, 5),
            (92, -1),
            (92, -1),
            (92, 1),
            (92, 3),
            (92, -1),
            (92, 3),
            (93, 4),
            (94, 1),
            (91, 2),
            (91, 0),
            (92, -1),
            (92, -1),
            (92, 2),
            (92, -1),
            (92, 4),
            (92, 4),
            (93, 4),
            (94, 1),
            (91, 0),
            (91, 2),
            (92, 0),
            (92, -1),
            (92, -1),
            (92, -1),
            (92, 3),
        ]],
    )
    _set_owner_reactor(graph, xdict.dxf.handle)
    _set_graph_node_id(graph, 32)
    xdict.add("ACAD_ENHANCEDBLOCK", graph)
    purge = _new_tag_storage_object(
        doc,
        "ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION",
        xdict.dxf.handle,
        [[(100, "AcDbDynamicBlockPurgePreventer"), (70, 1)]],
    )
    _set_owner_reactor(purge, xdict.dxf.handle)
    xdict.add("AcDbDynamicBlockRoundTripPurgePreventer", purge)

    proxy = _new_tag_storage_object(
        doc,
        "ACDB_DYNAMICBLOCKPROXYNODE",
        graph.dxf.handle,
        [[(100, "AcDbEvalExpr"), (90, 16), (98, 33), (99, 378)]],
    )
    grip = _new_tag_storage_object(
        doc,
        "BLOCKPROPERTIESTABLEGRIP",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 33), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Grip"), (98, 33), (99, 378), (1071, 0)],
            [
                (100, "AcDbBlockGrip"),
                (91, 34),
                (92, 35),
                (1010, table.grip_location or table.location),
                (280, 0),
                (93, -1),
            ],
        ],
    )
    x_comp = _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 34), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 32), (300, "UpdatedX")],
        ],
    )
    y_comp = _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 35), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 32), (300, "UpdatedY")],
        ],
    )
    visibility_entity = _new_tag_storage_object(
        doc,
        "BLOCKVISIBILITYPARAMETER",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 6), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, visibility.label), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [(100, "AcDbBlock1PtParameter"), (1010, visibility.location), (93, 0), (170, 0), (171, 0)],
            _build_property_visibility_parameter_subclass(visibility, "0", grip.dxf.handle),
        ],
    )
    table_entity = _new_tag_storage_object(
        doc,
        "BLOCKPROPERTIESTABLE",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 32), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, table.label), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [(100, "AcDbBlock1PtParameter"), (1010, table.location), (93, 33), (170, 0), (171, 0)],
            _build_block_properties_table_subclass(table, [
                *resolved_columns[:-1],
                DynamicBlockPropertyColumn(
                    source_handle=visibility_entity.dxf.handle,
                    source_dxftype="BLOCKVISIBILITYPARAMETER",
                    name=resolved_columns[-1].name,
                    display_name=resolved_columns[-1].display_name,
                ),
            ]),
        ],
    )
    _set_property_attdef_reactors(block, table_entity.dxf.handle)

    # Patch the visibility parameter with the actual table handle once it exists.
    vis_subclass = visibility_entity.xtags.get_subclass("AcDbBlockVisibilityParameter")
    patched_tags = _build_property_visibility_parameter_subclass(
        visibility,
        table_entity.dxf.handle,
        grip.dxf.handle,
    )
    _replace_subclass_tags(vis_subclass, patched_tags)
    visibility_entity.set_reactors([table_entity.dxf.handle])

    handles = [
        visibility_entity.dxf.handle,
        proxy.dxf.handle,
        table_entity.dxf.handle,
        grip.dxf.handle,
        x_comp.dxf.handle,
        y_comp.dxf.handle,
    ]
    _patch_eval_graph_handles(graph, handles)

    if linear_parameters:
        set_dynamic_block_linear_parameter(block, linear_parameters[0], stretch_actions[0])

    return DynamicBlockPropertiesTable(
        handle=table_entity.dxf.handle or "",
        label=table.label,
        table_name=table.table_name,
        description=table.description,
        location=table.location,
        grip_location=table.grip_location,
        columns=tuple([
            *resolved_columns[:-1],
            DynamicBlockPropertyColumn(
                source_handle=visibility_entity.dxf.handle or "",
                source_dxftype="BLOCKVISIBILITYPARAMETER",
                name=resolved_columns[-1].name,
                display_name=resolved_columns[-1].display_name,
            ),
        ]),
        rows=table.rows,
    )


def set_dynamic_block_base_point_parameter(
    block: BlockLayout,
    parameter: DynamicBlockBasePointParameter,
) -> DynamicBlockBasePointParameter:
    doc = block.doc
    if doc is None:
        raise const.DXFStructureError("valid DXF document required")
    graph = _get_enhanced_block_graph(block.block_record)
    if graph is None:
        raise const.DXFStructureError("dynamic block graph not found")
    if get_dynamic_block_base_point_parameter(block) is not None:
        raise const.DXFValueError("multiple dynamic block base point parameters are not supported")
    entity = _new_tag_storage_object(
        doc,
        "BLOCKBASEPOINTPARAMETER",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 5), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, parameter.label), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [(100, "AcDbBlock1PtParameter"), (1010, parameter.location), (93, 0), (170, 0), (171, 0)],
            [(100, "AcDbBlockBasepointParameter"), (1011, parameter.base_point), (1012, parameter.second_point)],
        ],
    )
    owned = tuple(_iter_graph_owned_objects(graph))
    visibility_entity = next((obj for obj in owned if obj.dxftype() == "BLOCKVISIBILITYPARAMETER"), None)
    visibility_grip = next((obj for obj in owned if obj.dxftype() == "BLOCKVISIBILITYGRIP"), None)
    grip_components = [obj for obj in owned if obj.dxftype() == "BLOCKGRIPLOCATIONCOMPONENT"]
    graph_types = {obj.dxftype() for obj in owned}
    if (
        isinstance(visibility_entity, DXFTagStorage)
        and isinstance(visibility_grip, DXFTagStorage)
        and len(grip_components) == 2
        and graph_types.isdisjoint(
            {
                "ACDB_DYNAMICBLOCKPROXYNODE",
                "BLOCKPROPERTIESTABLE",
                "BLOCKPROPERTIESTABLEGRIP",
                "BLOCKLINEARPARAMETER",
                "BLOCKLINEARGRIP",
                "BLOCKLOOKUPPARAMETER",
                "BLOCKLOOKUPGRIP",
                "BLOCKLOOKUPACTION",
                "BLOCKSTRETCHACTION",
            }
        )
    ):
        x_comp = next(
            (
                obj
                for obj in grip_components
                if obj.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedX"
            ),
            None,
        )
        y_comp = next(
            (
                obj
                for obj in grip_components
                if obj.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedY"
            ),
            None,
        )
        if isinstance(x_comp, DXFTagStorage) and isinstance(y_comp, DXFTagStorage):
            vis_location = visibility_entity.xtags.get_subclass("AcDbBlock1PtParameter").get_first_value(1010, parameter.location)
            grip_location = visibility_grip.xtags.get_subclass("AcDbBlockGrip").get_first_value(1010, vis_location)
            _replace_subclass_tags(
                visibility_entity.xtags.get_subclass("AcDbEvalExpr"),
                [(100, "AcDbEvalExpr"), (90, 2), (98, 33), (99, 378)],
            )
            _replace_subclass_tags(
                visibility_entity.xtags.get_subclass("AcDbBlock1PtParameter"),
                [(100, "AcDbBlock1PtParameter"), (1010, vis_location), (93, 3), (170, 0), (171, 0)],
            )
            _replace_subclass_tags(
                visibility_grip.xtags.get_subclass("AcDbEvalExpr"),
                [(100, "AcDbEvalExpr"), (90, 3), (98, 33), (99, 378)],
            )
            _replace_subclass_tags(
                visibility_grip.xtags.get_subclass("AcDbBlockGrip"),
                [(100, "AcDbBlockGrip"), (91, 4), (92, 5), (1010, grip_location), (280, 0), (93, -1)],
            )
            _replace_subclass_tags(
                x_comp.xtags.get_subclass("AcDbEvalExpr"),
                [(100, "AcDbEvalExpr"), (90, 4), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            )
            _replace_subclass_tags(
                x_comp.xtags.get_subclass("AcDbBlockGripExpr"),
                [(100, "AcDbBlockGripExpr"), (91, 2), (300, "UpdatedX")],
            )
            _replace_subclass_tags(
                y_comp.xtags.get_subclass("AcDbEvalExpr"),
                [(100, "AcDbEvalExpr"), (90, 5), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            )
            _replace_subclass_tags(
                y_comp.xtags.get_subclass("AcDbBlockGripExpr"),
                [(100, "AcDbBlockGripExpr"), (91, 2), (300, "UpdatedY")],
            )
            _replace_subclass_tags(
                graph.xtags.get_subclass("AcDbEvalGraph"),
                _build_visibility_basepoint_eval_graph_subclass(),
            )
            _patch_eval_graph_handles(
                graph,
                [
                    entity.dxf.handle,
                    visibility_entity.dxf.handle,
                    visibility_grip.dxf.handle,
                    x_comp.dxf.handle,
                    y_comp.dxf.handle,
                ],
            )
    return DynamicBlockBasePointParameter(
        handle=entity.dxf.handle or "",
        label=parameter.label,
        location=parameter.location,
        base_point=parameter.base_point,
        second_point=parameter.second_point,
        expr_id=5,
    )


def set_dynamic_block_linear_parameter(
    block: BlockLayout,
    parameter: DynamicBlockLinearParameter,
    stretch_action: DynamicBlockStretchAction,
) -> DynamicBlockLinearParameter:
    doc = block.doc
    if doc is None:
        raise const.DXFStructureError("valid DXF document required")
    if get_dynamic_block_linear_parameters(block):
        raise const.DXFValueError("multiple dynamic block linear parameters are not supported")
    visibility = get_dynamic_block_visibility_parameter(block)
    properties = get_dynamic_block_properties_table(block)
    basepoint = get_dynamic_block_base_point_parameter(block)
    if visibility is None or properties is None:
        raise const.DXFValueError("dynamic block requires visibility and properties table")
    graph = _get_enhanced_block_graph(block.block_record)
    if graph is None:
        raise const.DXFStructureError("dynamic block graph not found")

    owned = tuple(_iter_graph_owned_objects(graph))
    visibility_entity = next((entity for entity in owned if entity.dxftype() == "BLOCKVISIBILITYPARAMETER"), None)
    table_entity = next((entity for entity in owned if entity.dxftype() == "BLOCKPROPERTIESTABLE"), None)
    proxy = next((entity for entity in owned if entity.dxftype() == "ACDB_DYNAMICBLOCKPROXYNODE"), None)
    table_grip = next((entity for entity in owned if entity.dxftype() == "BLOCKPROPERTIESTABLEGRIP"), None)
    property_components = [entity for entity in owned if entity.dxftype() == "BLOCKGRIPLOCATIONCOMPONENT"]
    if not isinstance(visibility_entity, DXFTagStorage):
        raise const.DXFStructureError("visibility parameter object not found")
    if not isinstance(table_entity, DXFTagStorage):
        raise const.DXFStructureError("properties table object not found")
    if not isinstance(proxy, DXFTagStorage):
        raise const.DXFStructureError("dynamic block proxy node not found")
    if not isinstance(table_grip, DXFTagStorage):
        raise const.DXFStructureError("properties table grip not found")
    if len(property_components) != 2:
        raise const.DXFStructureError("properties table grip components not found")

    x_comp = next((entity for entity in property_components if entity.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedX"), None)
    y_comp = next((entity for entity in property_components if entity.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedY"), None)
    if not isinstance(x_comp, DXFTagStorage) or not isinstance(y_comp, DXFTagStorage):
        raise const.DXFStructureError("properties table grip components not found")

    source_attdefs = _get_property_attdefs(block)
    linear_visibility = _augment_visibility_with_property_attdefs(visibility, source_attdefs)
    primary_entity_handle = next(
        (entity.dxf.handle for entity in block if entity.dxftype() != "ATTDEF" and entity.dxf.handle),
        "",
    )
    dependency_handles = stretch_action.dependency_handles or tuple(
        handle
        for handle in (
            table_grip.dxf.handle,
            table_entity.dxf.handle,
            *[attdef.dxf.handle for attdef in reversed(source_attdefs)],
            primary_entity_handle,
        )
        if handle
    )
    targets = stretch_action.targets or tuple(
        [
            *(
                [DynamicBlockStretchActionTarget(primary_entity_handle, 2, (1, 2))]
                if primary_entity_handle
                else []
            ),
            *[
                DynamicBlockStretchActionTarget(attdef.dxf.handle, 1, (0,))
                for attdef in source_attdefs
                if attdef.dxf.handle
            ],
        ]
    )
    vector = (
        float(parameter.end_point[0] - parameter.base_point[0]),
        float(parameter.end_point[1] - parameter.base_point[1]),
        float(parameter.end_point[2] - parameter.base_point[2]),
    )
    base_grip_location = parameter.base_grip_location or parameter.base_point
    end_grip_location = parameter.end_grip_location or parameter.end_point
    base_grip_label = parameter.base_grip_label or "Base Grip"
    end_grip_label = parameter.end_grip_label or "End Grip"
    allowed_values = parameter.allowed_values
    value_count = parameter.value_count or len(allowed_values)
    value_set_type = parameter.value_set_type or 1

    if basepoint is not None:
        basepoint_entity = next((entity for entity in owned if entity.dxftype() == "BLOCKBASEPOINTPARAMETER"), None)
        if not isinstance(basepoint_entity, DXFTagStorage):
            raise const.DXFStructureError("base point parameter object not found")
        entity_type_by_handle = {
            entity.dxf.handle: entity.dxftype()
            for entity in block
            if entity.dxf.handle
        }
        normalized_targets = tuple(
            target
            for target in targets
            if entity_type_by_handle.get(target.entity_handle, "") != "ATTDEF"
        )
        if normalized_targets:
            targets = normalized_targets
        simple_line_targets = bool(targets) and all(
            entity_type_by_handle.get(target.entity_handle, "") == "LINE"
            and target.mode == 1
            and tuple(target.components) == (1,)
            for target in targets
        )
        _replace_subclass_tags(
            visibility_entity.xtags.get_subclass("AcDbEvalExpr"),
            [(100, "AcDbEvalExpr"), (90, 1), (98, 33), (99, 378)],
        )
        _replace_subclass_tags(
            proxy.xtags.get_subclass("AcDbEvalExpr"),
            [(100, "AcDbEvalExpr"), (90, 10), (98, 33), (99, 378)],
        )
        _replace_subclass_tags(
            table_entity.xtags.get_subclass("AcDbEvalExpr"),
            [(100, "AcDbEvalExpr"), (90, 6), (98, 33), (99, 378)],
        )
        table_1pt = list(table_entity.xtags.get_subclass("AcDbBlock1PtParameter"))
        table_1pt[1] = type(table_1pt[1])(1010, properties.location)
        table_1pt[2] = type(table_1pt[2])(93, 7)
        _replace_subclass_tags(table_entity.xtags.get_subclass("AcDbBlock1PtParameter"), table_1pt)
        _replace_subclass_tags(
            table_grip.xtags.get_subclass("AcDbEvalExpr"),
            [(100, "AcDbEvalExpr"), (90, 7), (98, 33), (99, 378)],
        )
        grip_sub = list(table_grip.xtags.get_subclass("AcDbBlockGrip"))
        grip_sub[1] = type(grip_sub[1])(91, 8)
        grip_sub[2] = type(grip_sub[2])(92, 9)
        _replace_subclass_tags(table_grip.xtags.get_subclass("AcDbBlockGrip"), grip_sub)
        _replace_subclass_tags(
            x_comp.xtags.get_subclass("AcDbEvalExpr"),
            [(100, "AcDbEvalExpr"), (90, 8), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
        )
        _replace_subclass_tags(
            x_comp.xtags.get_subclass("AcDbBlockGripExpr"),
            [(100, "AcDbBlockGripExpr"), (91, 6), (300, "UpdatedX")],
        )
        _replace_subclass_tags(
            y_comp.xtags.get_subclass("AcDbEvalExpr"),
            [(100, "AcDbEvalExpr"), (90, 9), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
        )
        _replace_subclass_tags(
            y_comp.xtags.get_subclass("AcDbBlockGripExpr"),
            [(100, "AcDbBlockGripExpr"), (91, 6), (300, "UpdatedY")],
        )

        linear_entity = _new_tag_storage_object(
            doc,
            "BLOCKLINEARPARAMETER",
            graph.dxf.handle,
            [
                [(100, "AcDbEvalExpr"), (90, 16), (98, 33), (99, 378)],
                [(100, "AcDbBlockElement"), (300, parameter.label), (98, 33), (99, 378), (1071, 0)],
                [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
                [
                    (100, "AcDbBlock2PtParameter"),
                    (1010, parameter.base_point),
                    (1011, parameter.end_point),
                    (170, 4),
                    (91, 0),
                    (91, 17),
                    (91, 0),
                    (91, 0),
                    (171, 0),
                    (172, 0),
                    (173, 1),
                    (94, 17),
                    (303, "DisplacementX"),
                    (174, 1),
                    (95, 17),
                    (304, "DisplacementY"),
                    (177, 0),
                ],
                [
                    (100, "AcDbBlockLinearParameter"),
                    (305, parameter.parameter_name),
                    (306, parameter.description),
                    (140, parameter.distance),
                    (307, ""),
                    (96, value_set_type),
                    (141, 0.0),
                    (142, 0.0),
                    (143, 0.0),
                    (175, value_count),
                    *[(144, value) for value in allowed_values],
                ],
            ],
        )
        end_grip = _new_tag_storage_object(
            doc,
            "BLOCKLINEARGRIP",
            graph.dxf.handle,
            [
                [(100, "AcDbEvalExpr"), (90, 17), (98, 33), (99, 378)],
                [(100, "AcDbBlockElement"), (300, end_grip_label), (98, 33), (99, 378), (1071, 0)],
                [(100, "AcDbBlockGrip"), (91, 18), (92, 19), (1010, end_grip_location), (280, 1), (93, -1)],
                [(100, "AcDbBlockLinearGrip"), (140, vector[0]), (141, vector[1]), (142, vector[2])],
            ],
        )
        end_x = _new_tag_storage_object(
            doc,
            "BLOCKGRIPLOCATIONCOMPONENT",
            graph.dxf.handle,
            [
                [(100, "AcDbEvalExpr"), (90, 18), (98, 33), (99, 378), (1, ""), (70, 40), (140, 1.797693134862314e+99)],
                [(100, "AcDbBlockGripExpr"), (91, 16), (300, "UpdatedEndX")],
            ],
        )
        end_y = _new_tag_storage_object(
            doc,
            "BLOCKGRIPLOCATIONCOMPONENT",
            graph.dxf.handle,
            [
                [(100, "AcDbEvalExpr"), (90, 19), (98, 33), (99, 378), (1, ""), (70, 40), (140, 1.797693134862314e+99)],
                [(100, "AcDbBlockGripExpr"), (91, 16), (300, "UpdatedEndY")],
            ],
        )
        entity_handle_set = {entity.dxf.handle for entity in block if entity.dxf.handle}
        explicit_entity_dependencies = tuple(
            handle for handle in stretch_action.dependency_handles if handle in entity_handle_set
        )
        dependency_handles = (
            (end_grip.dxf.handle, basepoint_entity.dxf.handle, *explicit_entity_dependencies)
            if explicit_entity_dependencies
            else tuple(
                handle
                for handle in (
                    end_grip.dxf.handle,
                    basepoint_entity.dxf.handle,
                    *[entity.dxf.handle for entity in reversed(list(block)) if entity.dxf.handle],
                )
                if handle
            )
        )
        stretch = _new_tag_storage_object(
            doc,
            "BLOCKSTRETCHACTION",
            graph.dxf.handle,
            [
                [(100, "AcDbEvalExpr"), (90, 20), (98, 33), (99, 378)],
                [(100, "AcDbBlockElement"), (300, stretch_action.label), (98, 33), (99, 378), (1071, 0)],
                [
                    (100, "AcDbBlockAction"),
                    (70, 1),
                    (91, 5),
                    (71, len(dependency_handles)),
                    *[(330, handle) for handle in dependency_handles],
                    (1010, stretch_action.action_location),
                ],
                [
                    (100, "AcDbBlockStretchAction"),
                    (92, 16),
                    (301, stretch_action.x_name or "EndXDelta"),
                    (93, 16),
                    (302, stretch_action.y_name or "EndYDelta"),
                    (72, len(stretch_action.selection_window)),
                    *[(1011, point) for point in stretch_action.selection_window],
                    (73, len(targets)),
                    *[
                        tag
                        for target in targets
                        for tag in (
                            (331, target.entity_handle),
                            (74, target.mode),
                            *[(94, component) for component in target.components],
                        )
                    ],
                    *(
                        [(75, 0)]
                        if simple_line_targets
                        else [(75, 1), (95, 5), (76, 1), (94, 0)]
                    ),
                    (140, 1.0),
                    (141, 0.0),
                    (280, 0),
                ],
            ],
        )
        _replace_subclass_tags(
            visibility_entity.xtags.get_subclass("AcDbBlockVisibilityParameter"),
            _build_property_visibility_parameter_subclass(
                linear_visibility,
                table_entity.dxf.handle,
                table_grip.dxf.handle,
                extra_state_refs=tuple((linear_entity.dxf.handle, end_grip.dxf.handle, stretch.dxf.handle) for _ in linear_visibility.states),
                all_handles=linear_visibility.all_entity_handles,
                include_table_in_all_states=True,
                table_before_grip=True,
            ),
        )
        _set_graph_node_id(graph, 6)
        _set_visibility_column_value_type(table_entity, visibility_entity.dxf.handle, 1)
        _replace_subclass_tags(graph.xtags.get_subclass("AcDbEvalGraph"), _build_basepoint_linear_eval_graph_subclass())
        _patch_eval_graph_handles(
            graph,
            [
                visibility_entity.dxf.handle,
                basepoint_entity.dxf.handle,
                table_entity.dxf.handle,
                table_grip.dxf.handle,
                x_comp.dxf.handle,
                y_comp.dxf.handle,
                proxy.dxf.handle,
                linear_entity.dxf.handle,
                end_grip.dxf.handle,
                end_x.dxf.handle,
                end_y.dxf.handle,
                stretch.dxf.handle,
            ],
        )
        return DynamicBlockLinearParameter(
            handle=linear_entity.dxf.handle or "",
            label=parameter.label,
            parameter_name=parameter.parameter_name,
            description=parameter.description,
            base_point=parameter.base_point,
            end_point=parameter.end_point,
            distance=parameter.distance,
            expr_id=16,
            end_grip_handle=end_grip.dxf.handle or "",
            end_grip_label=end_grip_label,
            end_grip_location=end_grip_location,
            value_set_type=value_set_type,
            value_count=value_count,
            allowed_values=allowed_values,
        )

    linear_entity = _new_tag_storage_object(
        doc,
        "BLOCKLINEARPARAMETER",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 45), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, parameter.label), (98, 33), (99, 378), (1071, 32)],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [
                (100, "AcDbBlock2PtParameter"),
                (1010, parameter.base_point),
                (1011, parameter.end_point),
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
                (305, parameter.parameter_name),
                (306, parameter.description),
                (140, parameter.distance),
                (307, ""),
                (96, value_set_type),
                (141, 0.0),
                (142, 0.0),
                (143, 0.0),
                (175, value_count),
                *[(144, value) for value in allowed_values],
            ],
        ],
    )
    end_grip = _new_tag_storage_object(
        doc,
        "BLOCKLINEARGRIP",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 46), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, end_grip_label), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockGrip"), (91, 47), (92, 48), (1010, end_grip_location), (280, 1), (93, -1)],
            [(100, "AcDbBlockLinearGrip"), (140, vector[0]), (141, vector[1]), (142, vector[2])],
        ],
    )
    end_x = _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 47), (98, 33), (99, 378), (1, ""), (70, 40), (140, 1.797693134862314e+99)],
            [(100, "AcDbBlockGripExpr"), (91, 45), (300, "UpdatedEndX")],
        ],
    )
    end_y = _new_tag_storage_object(
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
            [(100, "AcDbBlockElement"), (300, base_grip_label), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockGrip"), (91, 50), (92, 51), (1010, base_grip_location), (280, 1), (93, -1)],
            [(100, "AcDbBlockLinearGrip"), (140, -vector[0]), (141, -vector[1]), (142, -vector[2])],
        ],
    )
    base_x = _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 50), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 45), (300, "UpdatedBaseX")],
        ],
    )
    base_y = _new_tag_storage_object(
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
            [(100, "AcDbBlockElement"), (300, stretch_action.label), (98, 33), (99, 378), (1071, 0)],
            [
                (100, "AcDbBlockAction"),
                (70, 1),
                (91, 32),
                (71, len(dependency_handles)),
                *[(330, handle) for handle in dependency_handles],
                (1010, stretch_action.action_location),
            ],
            [
                (100, "AcDbBlockStretchAction"),
                (92, 45),
                (301, stretch_action.x_name or "EndXDelta"),
                (93, 45),
                (302, stretch_action.y_name or "EndYDelta"),
                (72, len(stretch_action.selection_window)),
                *[(1011, point) for point in stretch_action.selection_window],
                (73, len(targets)),
                *[
                    tag
                    for target in targets
                    for tag in (
                        (331, target.entity_handle),
                        (74, target.mode),
                        *[(94, component) for component in target.components],
                    )
                ],
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

    vis_subclass = visibility_entity.xtags.get_subclass("AcDbBlockVisibilityParameter")
    _replace_subclass_tags(
        vis_subclass,
        _build_property_visibility_parameter_subclass(
            linear_visibility,
            table_entity.dxf.handle,
            table_grip.dxf.handle,
            extra_state_refs=((base_grip.dxf.handle, linear_entity.dxf.handle, end_grip.dxf.handle, stretch.dxf.handle), (), ()),
            all_handles=linear_visibility.all_entity_handles,
        ),
    )
    _replace_subclass_tags(graph.xtags.get_subclass("AcDbEvalGraph"), _build_linear_eval_graph_subclass())
    _patch_eval_graph_handles(
        graph,
        [
            visibility_entity.dxf.handle,
            proxy.dxf.handle,
            table_entity.dxf.handle,
            table_grip.dxf.handle,
            x_comp.dxf.handle,
            y_comp.dxf.handle,
            linear_entity.dxf.handle,
            end_grip.dxf.handle,
            end_x.dxf.handle,
            end_y.dxf.handle,
            base_grip.dxf.handle,
            base_x.dxf.handle,
            base_y.dxf.handle,
            stretch.dxf.handle,
        ],
    )
    return DynamicBlockLinearParameter(
        handle=linear_entity.dxf.handle or "",
        label=parameter.label,
        parameter_name=parameter.parameter_name,
        description=parameter.description,
        base_point=parameter.base_point,
        end_point=parameter.end_point,
        distance=parameter.distance,
        expr_id=45,
        base_grip_handle=base_grip.dxf.handle or "",
        end_grip_handle=end_grip.dxf.handle or "",
        base_grip_label=base_grip_label,
        end_grip_label=end_grip_label,
        base_grip_location=base_grip_location,
        end_grip_location=end_grip_location,
        value_set_type=value_set_type,
        value_count=value_count,
        allowed_values=allowed_values,
    )


def set_dynamic_block_lookup_parameter(
    block: BlockLayout,
    parameter: DynamicBlockLookupParameter,
    actions: Sequence[DynamicBlockLookupAction],
) -> DynamicBlockLookupParameter:
    doc = block.doc
    if doc is None:
        raise const.DXFStructureError("valid DXF document required")
    if get_dynamic_block_lookup_parameters(block):
        raise const.DXFValueError("multiple dynamic block lookup parameters are not supported")
    visibility = get_dynamic_block_visibility_parameter(block)
    properties = get_dynamic_block_properties_table(block)
    linear_parameters = get_dynamic_block_linear_parameters(block)
    stretch_actions = get_dynamic_block_stretch_actions(block)
    if visibility is None or properties is None:
        raise const.DXFValueError("dynamic block requires visibility and properties table")
    if len(linear_parameters) != 1 or len(stretch_actions) != 1:
        raise const.DXFValueError("dynamic block requires exactly one linear parameter and stretch action")
    if len(actions) != 2:
        raise const.DXFValueError("dynamic block lookup parameter requires exactly two lookup actions")
    graph = _get_enhanced_block_graph(block.block_record)
    if graph is None:
        raise const.DXFStructureError("dynamic block graph not found")

    public_action = next((action for action in actions if action.expr_id == parameter.action_expr_id), None)
    if public_action is None:
        public_action = max(actions, key=lambda action: (action.column_count, action.expr_id))
    helper_actions = [action for action in actions if action is not public_action]
    if len(helper_actions) != 1:
        raise const.DXFValueError("dynamic block lookup parameter requires one helper action and one public action")
    helper_action = helper_actions[0]

    owned = tuple(_iter_graph_owned_objects(graph))
    visibility_entity = next((entity for entity in owned if entity.dxftype() == "BLOCKVISIBILITYPARAMETER"), None)
    table_entity = next((entity for entity in owned if entity.dxftype() == "BLOCKPROPERTIESTABLE"), None)
    proxy = next((entity for entity in owned if entity.dxftype() == "ACDB_DYNAMICBLOCKPROXYNODE"), None)
    table_grip = next((entity for entity in owned if entity.dxftype() == "BLOCKPROPERTIESTABLEGRIP"), None)
    linear_entity = next((entity for entity in owned if entity.dxftype() == "BLOCKLINEARPARAMETER"), None)
    end_grip = next((entity for entity in owned if entity.dxftype() == "BLOCKLINEARGRIP" and entity.xtags.get_subclass("AcDbBlockElement").get_first_value(300, "") == linear_parameters[0].end_grip_label), None)
    base_grip = next((entity for entity in owned if entity.dxftype() == "BLOCKLINEARGRIP" and entity.xtags.get_subclass("AcDbBlockElement").get_first_value(300, "") == linear_parameters[0].base_grip_label), None)
    stretch_entity = next((entity for entity in owned if entity.dxftype() == "BLOCKSTRETCHACTION"), None)
    property_components = [entity for entity in owned if entity.dxftype() == "BLOCKGRIPLOCATIONCOMPONENT"]
    if not all(isinstance(entity, DXFTagStorage) for entity in (visibility_entity, table_entity, proxy, table_grip, linear_entity, end_grip, base_grip, stretch_entity)):
        raise const.DXFStructureError("dynamic block graph is missing required linear/property objects")
    x_comp = next((entity for entity in property_components if entity.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedX"), None)
    y_comp = next((entity for entity in property_components if entity.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedY"), None)
    end_x = next((entity for entity in property_components if entity.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedEndX"), None)
    end_y = next((entity for entity in property_components if entity.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedEndY"), None)
    base_x = next((entity for entity in property_components if entity.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedBaseX"), None)
    base_y = next((entity for entity in property_components if entity.xtags.get_subclass("AcDbBlockGripExpr").get_first_value(300, "") == "UpdatedBaseY"), None)
    if not all(isinstance(entity, DXFTagStorage) for entity in (x_comp, y_comp, end_x, end_y, base_x, base_y)):
        raise const.DXFStructureError("dynamic block graph is missing required grip components")

    linear_parameter = linear_parameters[0]
    allowed_values = linear_parameter.allowed_values
    if not allowed_values and public_action.entries:
        values: list[float] = []
        for row in public_action.entries:
            if not row:
                continue
            try:
                values.append(float(row[0]))
            except ValueError:
                continue
        allowed_values = tuple(values)
    if not allowed_values:
        raise const.DXFValueError("dynamic block lookup parameter requires linear allowed values")
    linear_tags = [
        (100, "AcDbBlockLinearParameter"),
        (305, linear_parameter.parameter_name),
        (306, linear_parameter.description),
        (140, linear_parameter.distance),
        (307, ""),
        (96, 8),
        (141, 0.0),
        (142, 0.0),
        (143, 0.0),
        (175, len(allowed_values)),
        *[(144, value) for value in allowed_values],
    ]
    _replace_subclass_tags(linear_entity.xtags.get_subclass("AcDbBlockLinearParameter"), linear_tags)

    helper_action_entity = _new_tag_storage_object(
        doc,
        "BLOCKLOOKUPACTION",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 57), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, helper_action.label), (98, 33), (99, 378), (1071, 2)],
            [(100, "AcDbBlockAction"), (70, 0), (71, 0), (1010, helper_action.action_location)],
            _build_lookup_action_subclass(helper_action),
        ],
    )
    lookup_parameter_entity = _new_tag_storage_object(
        doc,
        "BLOCKLOOKUPPARAMETER",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 71), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, parameter.label), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [(100, "AcDbBlock1PtParameter"), (1010, parameter.location), (93, 72), (170, 0), (171, 0)],
            [(100, "AcDbBlockLookUpParameter"), (303, parameter.parameter_name), (304, parameter.description), (94, 75)],
        ],
    )
    lookup_grip = _new_tag_storage_object(
        doc,
        "BLOCKLOOKUPGRIP",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 72), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, parameter.grip_label or "Grip"), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockGrip"), (91, 73), (92, 74), (1010, parameter.location), (280, 0), (93, -1)],
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
    public_action_entity = _new_tag_storage_object(
        doc,
        "BLOCKLOOKUPACTION",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 75), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, public_action.label), (98, 33), (99, 378), (1071, 0)],
            [(100, "AcDbBlockAction"), (70, 0), (71, 0), (1010, public_action.action_location)],
            _build_lookup_action_subclass(public_action),
        ],
    )

    _replace_subclass_tags(
        visibility_entity.xtags.get_subclass("AcDbBlockVisibilityParameter"),
        _build_property_visibility_parameter_subclass(
            visibility,
            table_entity.dxf.handle,
            table_grip.dxf.handle,
            extra_state_refs=(
                (
                    base_grip.dxf.handle,
                    linear_entity.dxf.handle,
                    end_grip.dxf.handle,
                    stretch_entity.dxf.handle,
                    helper_action_entity.dxf.handle,
                    lookup_parameter_entity.dxf.handle,
                    lookup_grip.dxf.handle,
                    public_action_entity.dxf.handle,
                ),
                (lookup_grip.dxf.handle, lookup_parameter_entity.dxf.handle),
                (lookup_parameter_entity.dxf.handle,),
            ),
            all_handles=visibility.all_entity_handles,
        ),
    )
    _replace_subclass_tags(graph.xtags.get_subclass("AcDbEvalGraph"), _build_lookup_eval_graph_subclass())
    _patch_eval_graph_handles(
        graph,
        [
            visibility_entity.dxf.handle,
            proxy.dxf.handle,
            table_entity.dxf.handle,
            table_grip.dxf.handle,
            x_comp.dxf.handle,
            y_comp.dxf.handle,
            linear_entity.dxf.handle,
            end_grip.dxf.handle,
            end_x.dxf.handle,
            end_y.dxf.handle,
            base_grip.dxf.handle,
            base_x.dxf.handle,
            base_y.dxf.handle,
            stretch_entity.dxf.handle,
            helper_action_entity.dxf.handle,
            lookup_parameter_entity.dxf.handle,
            lookup_grip.dxf.handle,
            lookup_x.dxf.handle,
            lookup_y.dxf.handle,
            public_action_entity.dxf.handle,
        ],
    )
    return DynamicBlockLookupParameter(
        handle=lookup_parameter_entity.dxf.handle or "",
        label=parameter.label,
        parameter_name=parameter.parameter_name,
        description=parameter.description,
        location=parameter.location,
        expr_id=71,
        action_expr_id=75,
        grip_handle=lookup_grip.dxf.handle or "",
        grip_label=parameter.grip_label or "Grip",
    )


def set_dynamic_block_properties_editor_support(
    block: BlockLayout,
    table: DynamicBlockPropertiesTable,
) -> tuple[DynamicBlockPropertyRepresentation, ...]:
    """Create a first-pass editor-support layer for dynamic block properties.

    This helper authors hidden property representation blocks and assoc-network
    bundles derived from the authored table rows. The structure is intentionally
    simpler than the full AutoCAD-normalized graph, but preserves the important
    patterns we observed in the golden file.
    """
    doc = block.doc
    if doc is None:
        raise const.DXFStructureError("valid DXF document required")
    visibility = get_dynamic_block_visibility_parameter(block)
    properties = get_dynamic_block_properties_table(block)
    if visibility is None or properties is None:
        raise const.DXFValueError("dynamic block requires visibility and properties table")

    _delete_hidden_dynamic_support_blocks(block.block_record)
    root_network = _ensure_root_assoc_network(doc)
    created: list[DynamicBlockPropertyRepresentation] = []
    child_networks: list[str] = []
    source_attdefs = _get_property_attdefs(block)
    visible_state_name = visibility.states[0].name if visibility.states else ""
    state_names = [state.name for state in visibility.states]
    linear_parameters = get_dynamic_block_linear_parameters(block)
    lookup_parameters = get_dynamic_block_lookup_parameters(block)

    def add_hidden_representation(
        *,
        state_name: str | None,
        carrier_count: int,
        carrier_text: str,
        carriers_visible: bool,
        assoc_values: Sequence[tuple[str, str]] = (),
        carrier_metadata_indices: Optional[Sequence[int]] = None,
        carrier_reactor_indices: Optional[Sequence[int]] = None,
    ) -> None:
        hidden = doc.blocks.new_anonymous_block(type_char="U")
        if state_name is None:
            clone_geometry_visible(hidden)
        else:
            clone_geometry_and_masks(hidden, state_name)
        set_dynamic_block_reference(hidden, block, clone_property_attdefs=False)
        for attdef in source_attdefs[:carrier_count]:
            _clone_property_attdef(
                attdef,
                hidden,
                text=carrier_text,
                invisible=not carriers_visible,
            )
        _tag_block_representation_entities(hidden)
        carrier_items: list[tuple[int, Any, int]] = []
        for index, entity in enumerate(hidden):
            if entity.dxftype() == "ATTDEF":
                _set_property_attdef_rep_etag(entity, index)
                carrier_items.append((len(carrier_items), entity, index))
        metadata_indices = (
            {carrier_index for carrier_index, _, _ in carrier_items}
            if carrier_metadata_indices is None
            else set(carrier_metadata_indices)
        )
        reactor_indices = (
            {carrier_index for carrier_index, _, _ in carrier_items}
            if carrier_reactor_indices is None
            else set(carrier_reactor_indices)
        )
        for carrier_index, entity, hidden_index in carrier_items:
            if carrier_index in metadata_indices:
                _ensure_property_attdef_annotative_metadata(entity)
            if carrier_index in reactor_indices:
                entity.set_reactors([properties.handle])
        assoc_network = None
        if assoc_values:
            assoc_network = _new_assoc_network_bundle(
                hidden.block_record,
                root_network.dxf.handle,
                assoc_values,
                action_index=len(child_networks) + 1,
            )
            child_networks.append(assoc_network.handle)
        carriers = tuple(
            DynamicBlockPropertyCarrier(
                handle=entity.dxf.handle or "",
                tag=entity.dxf.tag,
                text=entity.dxf.text,
                invisible=int(entity.dxf.get("invisible", 0)),
            )
            for entity in hidden
            if entity.dxftype() == "ATTDEF"
        )
        created.append(
            DynamicBlockPropertyRepresentation(
                block_record_handle=hidden.block_record.dxf.handle or "",
                block_name=hidden.name,
                is_active=False,
                invisible_flags=tuple(int(entity.dxf.get("invisible", 0)) for entity in hidden),
                carriers=carriers,
                assoc_network=assoc_network,
            )
        )

    def clone_geometry_and_masks(target: BlockLayout, state_name: str) -> None:
        _clone_non_attdef_entities(block, target)
        _tag_block_representation_entities(target)
        _apply_visibility_state_to_block(target, visibility, state_name, dynamic_block=block)

    def clone_geometry_visible(target: BlockLayout) -> None:
        _clone_non_attdef_entities(block, target)
        _tag_block_representation_entities(target)
        for entity in target:
            entity.dxf.discard("invisible")

    def use_golden_style_templates() -> bool:
        return (
            len(source_attdefs) == 3
            and len(properties.columns) == 4
            and len(properties.rows) == 27
            and len(state_names) == 3
        )

    def use_linear_golden_style_templates() -> bool:
        return use_golden_style_templates() and len(linear_parameters) == 1

    def use_lookup_golden_style_templates() -> bool:
        return use_linear_golden_style_templates() and len(lookup_parameters) == 1

    if use_lookup_golden_style_templates():
        pair = (0, 1)
        triple_heads = (0, 1)
        triple_all = (0, 1, 2)

        for _ in range(2):
            add_hidden_representation(state_name=None, carrier_count=0, carrier_text="", carriers_visible=True)
        for state_name in state_names:
            add_hidden_representation(state_name=state_name, carrier_count=0, carrier_text="", carriers_visible=True)

        for _ in range(8):
            add_hidden_representation(
                state_name=visible_state_name,
                carrier_count=2,
                carrier_text="",
                carriers_visible=True,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        for _ in range(25):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        for _ in range(23):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )

        for _ in range(1):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(3):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )

        for _ in range(1):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text="Block Table 1",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(2):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text="Block Table 1",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )

        for _ in range(10):
            add_hidden_representation(
                state_name=visible_state_name,
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=True,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(6):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=True,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(6):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=True,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(8):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=False,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(6):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=False,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )

        _set_root_assoc_children(root_network, child_networks)
        return tuple(created)

    if use_linear_golden_style_templates():
        pair = (0, 1)
        triple_heads = (0, 1)
        triple_all = (0, 1, 2)

        for _ in range(2):
            add_hidden_representation(state_name=None, carrier_count=0, carrier_text="", carriers_visible=True)
        for state_name in state_names:
            add_hidden_representation(state_name=state_name, carrier_count=0, carrier_text="", carriers_visible=True)

        for _ in range(8):
            add_hidden_representation(
                state_name=visible_state_name,
                carrier_count=2,
                carrier_text="",
                carriers_visible=True,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        for _ in range(25):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        for _ in range(23):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )

        for _ in range(1):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(3):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )

        for _ in range(1):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text="Block Table 1",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(2):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text="Block Table 1",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )

        for _ in range(5):
            add_hidden_representation(
                state_name=visible_state_name,
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=True,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(1):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=True,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(1):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=True,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(8):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=False,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(6):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=False,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )

        _set_root_assoc_children(root_network, child_networks)
        return tuple(created)

    if use_golden_style_templates():
        pair = (0, 1)
        pair_first = (0,)
        pair_second = (1,)
        triple_heads = (0, 1)
        triple_all = (0, 1, 2)

        # Visibility-only support blocks: 2 fully visible + one masked rep per state.
        for _ in range(2):
            add_hidden_representation(state_name=None, carrier_count=0, carrier_text="", carriers_visible=True)
        for state_name in state_names:
            add_hidden_representation(state_name=state_name, carrier_count=0, carrier_text="", carriers_visible=True)

        # 2-carrier editor support families, matched to the golden file counts.
        for _ in range(5):
            add_hidden_representation(
                state_name=visible_state_name,
                carrier_count=2,
                carrier_text="",
                carriers_visible=True,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        add_hidden_representation(
            state_name=visible_state_name,
            carrier_count=2,
            carrier_text="",
            carriers_visible=True,
            carrier_metadata_indices=(),
            carrier_reactor_indices=pair_first,
        )
        for _ in range(9):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        add_hidden_representation(
            state_name=state_names[1],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            carrier_metadata_indices=(),
            carrier_reactor_indices=pair_first,
        )
        for _ in range(2):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair_second,
            )
        for _ in range(5):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=pair,
                carrier_reactor_indices=pair,
            )
        for _ in range(10):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        add_hidden_representation(
            state_name=state_names[2],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            carrier_metadata_indices=(),
            carrier_reactor_indices=pair_first,
        )
        add_hidden_representation(
            state_name=state_names[2],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            carrier_metadata_indices=(),
            carrier_reactor_indices=pair_second,
        )
        for _ in range(5):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=pair,
                carrier_reactor_indices=pair,
            )

        add_hidden_representation(
            state_name=visible_state_name,
            carrier_count=2,
            carrier_text="",
            carriers_visible=True,
            assoc_values=(("user1", "1"),),
            carrier_metadata_indices=(),
            carrier_reactor_indices=pair,
        )
        add_hidden_representation(
            state_name=state_names[1],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            assoc_values=(("user1", "1"),),
            carrier_metadata_indices=(),
            carrier_reactor_indices=pair,
        )
        add_hidden_representation(
            state_name=state_names[2],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            assoc_values=(("user1", "1"),),
            carrier_metadata_indices=(),
            carrier_reactor_indices=pair,
        )

        add_hidden_representation(
            state_name=visible_state_name,
            carrier_count=2,
            carrier_text="",
            carriers_visible=True,
            assoc_values=(("user1", "1"), ("user2", "1")),
            carrier_metadata_indices=(),
            carrier_reactor_indices=(),
        )
        add_hidden_representation(
            state_name=state_names[1],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            assoc_values=(("user1", "1"), ("user2", "1")),
            carrier_metadata_indices=(),
            carrier_reactor_indices=(),
        )
        for _ in range(4):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                assoc_values=(("user1", "1"), ("user2", "1")),
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        for _ in range(2):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                assoc_values=(("user1", "1"), ("user2", "1")),
                carrier_metadata_indices=pair,
                carrier_reactor_indices=pair,
            )
        add_hidden_representation(
            state_name=state_names[2],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            assoc_values=(("user1", "1"), ("user2", "1")),
            carrier_metadata_indices=(),
            carrier_reactor_indices=(),
        )
        for _ in range(2):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=2,
                carrier_text="",
                carriers_visible=False,
                assoc_values=(("user1", "1"), ("user2", "1")),
                carrier_metadata_indices=(),
                carrier_reactor_indices=pair,
            )
        add_hidden_representation(
            state_name=state_names[2],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            assoc_values=(("user1", "1"), ("user2", "1")),
            carrier_metadata_indices=pair,
            carrier_reactor_indices=pair,
        )
        add_hidden_representation(
            state_name=state_names[2],
            carrier_count=2,
            carrier_text="",
            carriers_visible=False,
            assoc_values=(("user1", "5667"), ("user2", "8")),
            carrier_metadata_indices=(),
            carrier_reactor_indices=(),
        )

        # 3-carrier support families.
        for _ in range(1):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(3):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text="",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )

        for _ in range(1):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text="Block Table 1",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(2):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text="Block Table 1",
                carriers_visible=False,
                carrier_metadata_indices=triple_heads,
                carrier_reactor_indices=triple_all,
            )

        for _ in range(3):
            add_hidden_representation(
                state_name=visible_state_name,
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=True,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(7):
            add_hidden_representation(
                state_name=state_names[1],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=False,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )
        for _ in range(5):
            add_hidden_representation(
                state_name=state_names[2],
                carrier_count=3,
                carrier_text=properties.table_name,
                carriers_visible=False,
                carrier_metadata_indices=triple_all,
                carrier_reactor_indices=triple_all,
            )

        _set_root_assoc_children(root_network, child_networks)
        return tuple(created)

    # Hidden visibility-only support blocks observed in AutoCAD-authored files:
    # two fully visible generic reps and one masked rep for each visibility state.
    for _ in range(2):
        generic = doc.blocks.new_anonymous_block(type_char="U")
        clone_geometry_visible(generic)
        set_dynamic_block_reference(generic, block, clone_property_attdefs=False)
    for visibility_state in visibility.states:
        hidden = doc.blocks.new_anonymous_block(type_char="U")
        clone_geometry_and_masks(hidden, visibility_state.name)
        set_dynamic_block_reference(hidden, block, clone_property_attdefs=False)

    # Hidden 2-column prefix representations keyed by the first 2 properties.
    for row in properties.rows:
        prefix_values = tuple(str(value) for value in row.values[:2])
        state_name = str(row.values[-1])
        hidden = doc.blocks.new_anonymous_block(type_char="U")
        clone_geometry_and_masks(hidden, state_name)
        set_dynamic_block_reference(hidden, block, clone_property_attdefs=False)
        for attdef in source_attdefs[:2]:
            _clone_property_attdef(attdef, hidden, text="", invisible=state_name != visible_state_name)
        _tag_block_representation_entities(hidden)
        for index, entity in enumerate(hidden):
            if entity.dxftype() == "ATTDEF":
                _ensure_property_attdef_metadata(entity, index)
        _set_property_attdef_reactors(hidden, properties.handle)
        network = _new_assoc_network_bundle(
            hidden.block_record,
            root_network.dxf.handle,
            (("user1", prefix_values[0]), ("user2", prefix_values[1])),
            action_index=row.index + 1,
        )
        child_networks.append(network.handle)
        carriers = tuple(
            DynamicBlockPropertyCarrier(
                handle=entity.dxf.handle or "",
                tag=entity.dxf.tag,
                text=entity.dxf.text,
                invisible=int(entity.dxf.get("invisible", 0)),
            )
            for entity in hidden
            if entity.dxftype() == "ATTDEF"
        )
        created.append(
            DynamicBlockPropertyRepresentation(
                block_record_handle=hidden.block_record.dxf.handle or "",
                block_name=hidden.name,
                is_active=False,
                invisible_flags=tuple(int(entity.dxf.get("invisible", 0)) for entity in hidden),
                carriers=carriers,
                assoc_network=network,
            )
        )

    # Hidden full 3-column row representations.
    for row in properties.rows:
        state_name = str(row.values[-1])
        hidden = doc.blocks.new_anonymous_block(type_char="U")
        clone_geometry_and_masks(hidden, state_name)
        set_dynamic_block_reference(hidden, block, clone_property_attdefs=False)
        for attdef, value in zip(source_attdefs, row.values[: len(source_attdefs)]):
            _clone_property_attdef(
                attdef,
                hidden,
                text=properties.table_name,
                invisible=state_name != visible_state_name,
            )
        _tag_block_representation_entities(hidden)
        for index, entity in enumerate(hidden):
            if entity.dxftype() == "ATTDEF":
                _ensure_property_attdef_metadata(entity, index)
        _set_property_attdef_reactors(hidden, properties.handle)
        carriers = tuple(
            DynamicBlockPropertyCarrier(
                handle=entity.dxf.handle or "",
                tag=entity.dxf.tag,
                text=entity.dxf.text,
                invisible=int(entity.dxf.get("invisible", 0)),
            )
            for entity in hidden
            if entity.dxftype() == "ATTDEF"
        )
        created.append(
            DynamicBlockPropertyRepresentation(
                block_record_handle=hidden.block_record.dxf.handle or "",
                block_name=hidden.name,
                is_active=False,
                invisible_flags=tuple(int(entity.dxf.get("invisible", 0)) for entity in hidden),
                carriers=carriers,
                assoc_network=None,
            )
        )

    _set_root_assoc_children(root_network, child_networks)
    return tuple(created)


def _new_tag_storage_object(doc: Drawing, dxftype: str, owner: str, subclasses) -> DXFTagStorage:
    from ezdxf.entities import factory
    from ezdxf.lldxf.extendedtags import ExtendedTags
    from ezdxf.lldxf.types import dxftag

    entity = factory.new(dxftype, dxfattribs={"owner": owner}, doc=doc)
    factory.bind(entity, doc)
    doc.objects.add_object(entity)
    tags = [
        dxftag(0, dxftype),
        dxftag(5, entity.dxf.handle),
        dxftag(330, owner),
    ]
    for subclass in subclasses:
        tags.extend(dxftag(code, value) for code, value in subclass)
    xtags = ExtendedTags(tags)
    entity.load_tags(xtags, dxfversion=doc.dxfversion)
    entity.store_tags(xtags)
    return entity


def _set_owner_reactor(entity: DXFTagStorage, owner: str) -> None:
    entity.set_reactors([owner])


def _ensure_dynamic_block_extension_dict(block_record: BlockRecord) -> Dictionary:
    xdict = block_record.get_extension_dict() if block_record.has_extension_dict else block_record.new_extension_dict()
    return xdict.dictionary


def set_dynamic_block_visibility_parameter(
    block: BlockLayout,
    parameter: DynamicBlockVisibilityParameter,
    *,
    guid: str = "",
    true_name: str = "",
) -> None:
    """Attach a minimal visibility-state dynamic-block graph to `block`.

    This helper models the visibility parameter stack observed in AutoCAD-authored
    dynamic blocks. It is intentionally minimal and currently limited to the
    visibility-parameter feature set.
    """
    doc = block.doc
    if doc is None:
        raise const.DXFStructureError("valid DXF document required")
    _ensure_dynamic_block_appids(doc)
    block_record = block.block_record
    if not guid:
        guid = "{" + str(uuid.uuid4()).upper() + "}"
    if not true_name:
        true_name = block.name
    block_record.set_xdata(AcDbDynamicBlockGUID, [(1000, guid)])
    block_record.set_xdata(AcDbDynamicBlockTrueName, [(1000, true_name)])
    block_record.set_xdata(AcDbBlockRepETag, [(1070, 1), (1071, len(block))])
    _tag_block_representation_entities(block)
    if len(parameter.states):
        _apply_visibility_state_to_block(block, parameter, parameter.states[0].name)

    xdict = _ensure_dynamic_block_extension_dict(block_record)
    graph = _new_tag_storage_object(
        doc,
        "ACAD_EVALUATION_GRAPH",
        xdict.dxf.handle,
        [[
            (100, "AcDbEvalGraph"),
            (96, 9),
            (97, 9),
            (91, 0),
            (93, 32),
            (95, 6),
            (360, "0"),
            (92, 0),
            (92, 0),
            (92, 1),
            (92, 2),
            (91, 1),
            (93, 32),
            (95, 7),
            (360, "0"),
            (92, -1),
            (92, -1),
            (92, 0),
            (92, 0),
            (91, 2),
            (93, 32),
            (95, 8),
            (360, "0"),
            (92, 1),
            (92, 1),
            (92, -1),
            (92, -1),
            (91, 3),
            (93, 32),
            (95, 9),
            (360, "0"),
            (92, 2),
            (92, 2),
            (92, -1),
            (92, -1),
            (92, 0),
            (93, 0),
            (94, 1),
            (91, 1),
            (91, 0),
            (92, -1),
            (92, -1),
            (92, -1),
            (92, -1),
            (92, -1),
            (92, 1),
            (93, 0),
            (94, 1),
            (91, 0),
            (91, 2),
            (92, -1),
            (92, -1),
            (92, -1),
            (92, 2),
            (92, -1),
            (92, 2),
            (93, 0),
            (94, 1),
            (91, 0),
            (91, 3),
            (92, -1),
            (92, -1),
            (92, 1),
            (92, -1),
            (92, -1),
        ]],
    )
    _set_owner_reactor(graph, xdict.dxf.handle)
    xdict.add("ACAD_ENHANCEDBLOCK", graph)
    purge = _new_tag_storage_object(
        doc,
        "ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION",
        xdict.dxf.handle,
        [[(100, "AcDbDynamicBlockPurgePreventer"), (70, 1)]],
    )
    _set_owner_reactor(purge, xdict.dxf.handle)
    xdict.add("AcDbDynamicBlockRoundTripPurgePreventer", purge)

    ordered_handles = list(parameter.all_entity_handles)
    if not ordered_handles:
        for state in parameter.states:
            for handle in state.entity_handles:
                if handle not in ordered_handles:
                    ordered_handles.append(handle)

    vis_subclass = [
        (100, "AcDbBlockVisibilityParameter"),
        (281, 1),
        (301, parameter.parameter_name),
        (302, ""),
        (91, 0),
        (93, len(ordered_handles)),
        *[(331, handle) for handle in ordered_handles],
        (92, len(parameter.states)),
    ]
    for state in parameter.states:
        vis_subclass.extend(
            [
                (303, state.name),
                (94, len(state.entity_handles)),
                *[(332, handle) for handle in state.entity_handles],
                (95, 0),
            ]
        )

    px, py, pz = parameter.location
    visibility = _new_tag_storage_object(
        doc,
        "BLOCKVISIBILITYPARAMETER",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 6), (98, 33), (99, 378)],
            [
                (100, "AcDbBlockElement"),
                (300, parameter.label),
                (98, 33),
                (99, 378),
                (1071, 0),
            ],
            [(100, "AcDbBlockParameter"), (280, 1), (281, 0)],
            [
                (100, "AcDbBlock1PtParameter"),
                (1010, (px, py, pz)),
                (93, 7),
                (170, 0),
                (171, 0),
            ],
            vis_subclass,
        ],
    )

    grip = _new_tag_storage_object(
        doc,
        "BLOCKVISIBILITYGRIP",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 7), (98, 33), (99, 378)],
            [(100, "AcDbBlockElement"), (300, "Grip"), (98, 33), (99, 378), (1071, 0)],
            [
                (100, "AcDbBlockGrip"),
                (91, 8),
                (92, 9),
                (1010, (px, py, pz)),
                (280, 0),
                (93, -1),
            ],
            [(100, "AcDbBlockVisibilityGrip")],
        ],
    )
    updated_x = _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 8), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 6), (300, "UpdatedX")],
        ],
    )
    updated_y = _new_tag_storage_object(
        doc,
        "BLOCKGRIPLOCATIONCOMPONENT",
        graph.dxf.handle,
        [
            [(100, "AcDbEvalExpr"), (90, 9), (98, 33), (99, 378), (1, ""), (70, 40), (140, 0.0)],
            [(100, "AcDbBlockGripExpr"), (91, 6), (300, "UpdatedY")],
        ],
    )

    eval_graph = graph.xtags.get_subclass("AcDbEvalGraph")
    handles = [
        visibility.dxf.handle,
        grip.dxf.handle,
        updated_x.dxf.handle,
        updated_y.dxf.handle,
    ]
    from ezdxf.lldxf.types import dxftag

    handle_index = 0
    for index, tag in enumerate(eval_graph):
        if tag.code == 360 and handle_index < len(handles):
            eval_graph[index] = dxftag(360, handles[handle_index])
            handle_index += 1


def set_dynamic_block_reference(
    block: BlockLayout,
    dynamic_block: BlockLayout,
    *,
    clone_property_attdefs: bool = True,
    normalize_entities: bool = True,
) -> None:
    """Mark `block` as an anonymous representation of `dynamic_block`."""
    if block.doc is None:
        raise const.DXFStructureError("valid DXF document required")
    _ensure_dynamic_block_appids(block.doc)
    if not block.block_record.has_extension_dict:
        block.block_record.new_extension_dict()
    if clone_property_attdefs:
        _clone_property_attdefs_to_reference(block, dynamic_block)
    if normalize_entities:
        source_attdefs = {
            attdef.dxf.tag: _property_attdef_state(attdef)
            for attdef in _get_property_attdefs(dynamic_block)
        }
        _tag_block_representation_entities(block)
        for index, entity in enumerate(block):
            if entity.dxftype() == "ATTDEF":
                metadata = source_attdefs.get(
                    entity.dxf.tag,
                    _property_attdef_state(entity),
                )
                _set_property_attdef_rep_etag(
                    entity,
                    metadata.rep_index if metadata.rep_index is not None else index,
                )
                if metadata.annotative:
                    _ensure_property_attdef_annotative_metadata(
                        entity,
                        create_context_record=metadata.has_context_record,
                    )
                else:
                    entity.discard_xdata("AcadAnnotative")
                if metadata.invisible:
                    entity.dxf.invisible = metadata.invisible
                else:
                    entity.dxf.discard("invisible")
        properties = get_dynamic_block_properties_table(dynamic_block)
        if properties is not None:
            _set_property_attdef_reactors(block, properties.handle)
    block.block_record.set_xdata(
        AcDbBlockRepBTag,
        [(1070, 1), (1005, dynamic_block.block_record_handle)],
    )


def set_dynamic_block_visibility_state(
    insert: Insert,
    dynamic_block: Optional[BlockLayout] = None,
    *,
    state: str,
    location: Optional[tuple[float, float, float]] = None,
    update_cache: bool = True,
) -> None:
    """Attach the current visibility-state cache to a dynamic block insert."""
    if dynamic_block is None:
        dynamic_block = get_dynamic_block_definition(insert)
    if dynamic_block is None:
        raise const.DXFStructureError("dynamic block definition not found")
    if insert.doc is None:
        raise const.DXFStructureError("valid DXF document required")
    parameter = get_dynamic_block_visibility_parameter(dynamic_block)
    if parameter is None:
        raise const.DXFValueError("dynamic block has no visibility parameter")
    if location is None:
        location = parameter.location
    reference = get_dynamic_block_reference(insert)
    if reference is not None:
        if not reference.block_record.has_extension_dict:
            reference.block_record.new_extension_dict()
        _register_blkref_handle(reference, insert)
        _apply_visibility_state_to_block(
            reference,
            parameter,
            state,
            dynamic_block=dynamic_block,
        )
    if len(parameter.states):
        _apply_property_attdef_visibility(
            reference,
            dynamic_block,
            state,
            parameter.states[0].name,
        )
    if not update_cache:
        return
    xdict = insert.get_extension_dict() if insert.has_extension_dict else insert.new_extension_dict()
    root = xdict.dictionary
    rep = root.get("AcDbBlockRepresentation")
    if not isinstance(rep, Dictionary):
        rep = root.add_new_dict("AcDbBlockRepresentation", hard_owned=True)
    repdata = rep.get("AcDbRepData")
    if not isinstance(repdata, DXFTagStorage) or repdata.dxftype() != "ACDB_BLOCKREPRESENTATION_DATA":
        repdata = _new_tag_storage_object(
            dynamic_block.doc,
            "ACDB_BLOCKREPRESENTATION_DATA",
            rep.dxf.handle,
            [[(100, "AcDbBlockRepresentationData"), (70, 1), (340, dynamic_block.block_record_handle)]],
        )
        rep.add("AcDbRepData", repdata)
    app_cache = rep.get("AppDataCache")
    if not isinstance(app_cache, Dictionary):
        app_cache = rep.add_new_dict("AppDataCache", hard_owned=True)
    enhanced = app_cache.get("ACAD_ENHANCEDBLOCKDATA")
    if not isinstance(enhanced, Dictionary):
        enhanced = app_cache.add_new_dict("ACAD_ENHANCEDBLOCKDATA", hard_owned=True)
    enhanced.set_reactors([app_cache.dxf.handle])
    xrecord = enhanced.get("6")
    if not isinstance(xrecord, XRecord):
        xrecord = enhanced.add_xrecord("6")
    xrecord.set_reactors([enhanced.dxf.handle])
    xrecord.reset(
        [
            (1071, 135625452),
            (1071, 184556386),
            (70, 25),
            (70, 104),
            (10, location),
            (1, state),
        ]
    )
    if _populate_linear_insert_cache_records(insert, dynamic_block, state=state):
        enhanced.discard("6")


def set_dynamic_block_insert_cache(
    insert: Insert,
    dynamic_block: Optional[BlockLayout] = None,
    *,
    location: Optional[tuple[float, float, float]] = None,
    update_cache: bool = True,
) -> None:
    if dynamic_block is None:
        dynamic_block = get_dynamic_block_definition(insert)
    if dynamic_block is None:
        raise const.DXFStructureError("dynamic block definition not found")
    if insert.doc is None:
        raise const.DXFStructureError("valid DXF document required")
    if location is None:
        location = tuple(insert.dxf.insert)
    reference = get_dynamic_block_reference(insert)
    if reference is not None:
        if not reference.block_record.has_extension_dict:
            reference.block_record.new_extension_dict()
        _register_blkref_handle(reference, insert)
    if not update_cache:
        return

    enhanced = _ensure_dynamic_insert_cache_dictionary(insert, dynamic_block)
    xrecord = enhanced.get("1")
    if not isinstance(xrecord, XRecord):
        xrecord = enhanced.add_xrecord("1")
    xrecord.set_reactors([enhanced.dxf.handle])
    xrecord.reset(
        [
            (1071, 82437801),
            (1071, 112294725),
            (70, 25),
            (70, 104),
            (10, location),
        ]
    )
    visibility = get_dynamic_block_visibility_parameter(dynamic_block)
    if visibility is not None and visibility.states:
        if _populate_linear_insert_cache_records(
            insert,
            dynamic_block,
            state=visibility.states[0].name,
        ):
            enhanced.discard("6")


def _ensure_dynamic_insert_cache_dictionary(
    insert: Insert,
    dynamic_block: BlockLayout,
) -> Dictionary:
    if insert.doc is None:
        raise const.DXFStructureError("valid DXF document required")

    app_cache = _ensure_dynamic_insert_app_cache_dictionary(insert, dynamic_block)
    enhanced = app_cache.get("ACAD_ENHANCEDBLOCKDATA")
    if not isinstance(enhanced, Dictionary):
        enhanced = app_cache.add_new_dict("ACAD_ENHANCEDBLOCKDATA", hard_owned=True)
    enhanced.set_reactors([app_cache.dxf.handle])
    return enhanced


def _ensure_dynamic_insert_app_cache_dictionary(
    insert: Insert,
    dynamic_block: BlockLayout,
) -> Dictionary:
    if insert.doc is None:
        raise const.DXFStructureError("valid DXF document required")

    xdict = insert.get_extension_dict() if insert.has_extension_dict else insert.new_extension_dict()
    root = xdict.dictionary
    rep = root.get("AcDbBlockRepresentation")
    if not isinstance(rep, Dictionary):
        rep = root.add_new_dict("AcDbBlockRepresentation", hard_owned=True)
    repdata = rep.get("AcDbRepData")
    if not isinstance(repdata, DXFTagStorage) or repdata.dxftype() != "ACDB_BLOCKREPRESENTATION_DATA":
        repdata = _new_tag_storage_object(
            dynamic_block.doc,
            "ACDB_BLOCKREPRESENTATION_DATA",
            rep.dxf.handle,
            [[(100, "AcDbBlockRepresentationData"), (70, 1), (340, dynamic_block.block_record_handle)]],
        )
        rep.add("AcDbRepData", repdata)
    app_cache = rep.get("AppDataCache")
    if not isinstance(app_cache, Dictionary):
        app_cache = rep.add_new_dict("AppDataCache", hard_owned=True)
    return app_cache


def set_dynamic_block_insert_cache_record(
    insert: Insert,
    key: str,
    tags: Sequence[tuple[int, Any]],
    dynamic_block: Optional[BlockLayout] = None,
) -> None:
    if dynamic_block is None:
        dynamic_block = get_dynamic_block_definition(insert)
    if dynamic_block is None:
        raise const.DXFStructureError("dynamic block definition not found")
    enhanced = _ensure_dynamic_insert_cache_dictionary(insert, dynamic_block)
    xrecord = enhanced.get(key)
    if not isinstance(xrecord, XRecord):
        xrecord = enhanced.add_xrecord(key)
    xrecord.set_reactors([enhanced.dxf.handle])
    xrecord.reset(tags)


def set_dynamic_block_insert_appdata_record(
    insert: Insert,
    key: str,
    tags: Sequence[tuple[int, Any]],
    dynamic_block: Optional[BlockLayout] = None,
) -> None:
    if dynamic_block is None:
        dynamic_block = get_dynamic_block_definition(insert)
    if dynamic_block is None:
        raise const.DXFStructureError("dynamic block definition not found")
    app_cache = _ensure_dynamic_insert_app_cache_dictionary(insert, dynamic_block)
    xrecord = app_cache.get(key)
    if not isinstance(xrecord, XRecord):
        xrecord = app_cache.add_xrecord(key)
    xrecord.set_reactors([app_cache.dxf.handle])
    xrecord.reset(tags)


def _populate_linear_insert_cache_records(
    insert: Insert,
    dynamic_block: BlockLayout,
    *,
    state: str,
) -> bool:
    basepoint = get_dynamic_block_base_point_parameter(dynamic_block)
    linear_parameters = get_dynamic_block_linear_parameters(dynamic_block)
    if basepoint is None or len(linear_parameters) != 1:
        return False
    graph = _get_enhanced_block_graph(dynamic_block.block_record)
    if graph is None:
        return False
    owned = tuple(_iter_graph_owned_objects(graph))
    visibility_entity = next(
        (entity for entity in owned if entity.dxftype() == "BLOCKVISIBILITYPARAMETER"),
        None,
    )
    table_entity = next(
        (entity for entity in owned if entity.dxftype() == "BLOCKPROPERTIESTABLE"),
        None,
    )
    linear_entity = next(
        (entity for entity in owned if entity.dxftype() == "BLOCKLINEARPARAMETER"),
        None,
    )
    stretch_entity = next(
        (entity for entity in owned if entity.dxftype() == "BLOCKSTRETCHACTION"),
        None,
    )
    if not all(
        isinstance(entity, DXFTagStorage)
        for entity in (visibility_entity, table_entity, linear_entity, stretch_entity)
    ):
        return False
    linear = linear_parameters[0]
    visibility = get_dynamic_block_visibility_parameter(dynamic_block)
    if visibility is None:
        return False

    visibility_expr_id = _eval_expr_id(visibility_entity)
    table_expr_id = _eval_expr_id(table_entity)
    linear_expr_id = _eval_expr_id(linear_entity)
    stretch_expr_id = _eval_expr_id(stretch_entity)
    basepoint_expr_id = basepoint.expr_id

    set_dynamic_block_insert_cache_record(
        insert,
        str(visibility_expr_id),
        [
            (1071, 135625452),
            (1071, 184556386),
            (70, 25),
            (70, 104),
            (10, visibility.location),
            (1, state),
        ],
        dynamic_block,
    )
    set_dynamic_block_insert_cache_record(
        insert,
        str(basepoint_expr_id),
        [
            (1071, 82437801),
            (1071, 112294725),
            (70, 25),
            (70, 104),
            (10, basepoint.base_point),
        ],
        dynamic_block,
    )
    set_dynamic_block_insert_cache_record(
        insert,
        str(linear_expr_id),
        [
            (1071, 18597260),
            (1071, 25303744),
            (70, 25),
            (70, 104),
            (10, linear.base_point),
            (10, linear.end_point),
            (10, (0.0, 0.0, -1.0)),
        ],
        dynamic_block,
    )
    set_dynamic_block_insert_cache_record(
        insert,
        str(stretch_expr_id),
        [
            (1071, 6895636),
            (1071, 9291323),
            (70, 25),
            (70, 104),
            (40, 0.0),
        ],
        dynamic_block,
    )
    set_dynamic_block_insert_appdata_record(
        insert,
        "ACAD_ENHANCEDBLOCKHISTORY",
        [
            (1070, 3),
            (1071, 17),
            (300, "GRIPLOC"),
            (11, (0.0, 0.0, 0.0)),
            (1071, table_expr_id),
            (300, get_dynamic_block_properties_table(dynamic_block).table_name),
            (70, 1),
            (1070, -1),
            (1071, visibility_expr_id),
            (300, visibility.parameter_name),
            (1, state),
            (1070, -2),
        ],
        dynamic_block,
    )
    return True
