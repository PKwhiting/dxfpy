from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from ezdxf.document import Drawing
    from ezdxf.entities import DXFEntity
    from ezdxf.layouts import BlockLayout

    from ._code import Code
    from ezdxf.dynblkhelper import RawEntityExportSnapshot


RawTag = tuple[int, object]
RawSubclass = list[RawTag]
RawSubclassList = list[RawSubclass]
RawXDataTags = list[list[RawTag]]
ExtensionSnapshot = tuple[tuple[tuple[int, object], ...], ...]
SortentsHandles = list[tuple[str, str]]
RootDictEntryRestoreSnapshot = tuple[
    str,
    tuple[tuple[int, object], ...],
    tuple[tuple[tuple[int, object], ...], ...],
]


@dataclass(slots=True)
class OwnedObjectSpec:
    handle: str
    owner: str
    dxftype: str
    subclasses: RawSubclassList


class OwnedObjectSpecData(TypedDict):
    handle: str
    owner: str
    dxftype: str
    subclasses: RawSubclassList


@dataclass(slots=True)
class MLeaderStyleSpec:
    name: str
    xdata_tags: list[RawTag]
    reactors: list[str]


@dataclass(slots=True)
class EntityXRecordFallbackSpec:
    entity_handle: str
    dict_key: str
    dict_order: list[str]
    root_handle: str
    root_dxftype: str
    root_subclasses: RawSubclassList
    owned_specs: list[OwnedObjectSpec]


@dataclass(slots=True)
class RawGraphOwnedObjectSpec:
    handle: str
    dxftype: str
    subclasses: RawSubclassList
    xdata: RawXDataTags
    reactors: list[str]


@dataclass(slots=True)
class RawGraphFallbackSpec:
    graph_handle: str
    graph_subclasses: RawSubclassList
    graph_xdata: list[RawTag]
    purge_subclasses: RawSubclassList
    owned_specs: list[RawGraphOwnedObjectSpec]


@dataclass(slots=True)
class ResourceHandleRef:
    source_handle: str
    attrib_name: str


@dataclass(slots=True)
class RawEntitySwapFallbackSpec:
    source_handle: str
    source_owner: str
    source_xdict_handle: str
    source_resource_handles: list[ResourceHandleRef]
    raw_tags: list[RawTag]
    xdata: RawXDataTags


@dataclass(slots=True)
class VariableDictEntry:
    key: str
    value: str


@dataclass(slots=True)
class VisualStyleEntry:
    handle: str
    key: str
    dxfattribs: dict[str, object]


@dataclass(slots=True)
class RawObjectDictEntry:
    key: str
    tags: list[RawTag]


@dataclass(slots=True)
class HeaderHandleRef:
    name: str
    handle: str


@dataclass(slots=True)
class SortentsBlockSpec:
    block_name: str
    tags: SortentsHandles


@dataclass(slots=True)
class GroupSpec:
    name: str
    handles: list[str]
    description: str
    selectable: bool
    unnamed: int


class DocumentCodegenCapture(TypedDict):
    doc: Drawing
    source: Path
    header_state: dict[str, object]
    header_custom_vars: list[tuple[object, object]]
    raw_header_overrides: tuple[tuple[str, str], ...]
    raw_classes: tuple[str, ...]
    blocks: list[BlockLayout]
    block_codes: list[Code]
    block_layout_entity_snapshots: dict[str, tuple[RawEntityExportSnapshot, ...]]
    layout_dictionary_order: list[str]
    paper_layout_names: list[str]
    active_paper_layout_name: str
    paper_layout_dxfattribs: dict[str, dict[str, object]]
    paper_layout_block_record_names: dict[str, str]
    paper_layout_codes: list[tuple[str, Code]]
    acad_table_geometry_block_codes: list[tuple[str, Code]]
    msp_code: Code
    imports: set[str]
    resource_code: Code | None
    layers_with_xdict: set[str]
    root_xrecords: dict[str, list[RawTag]]
    deferred_recompose_tags: list[RawTag]
    deferred_recompose_source_handle: str
    deferred_recompose_table_styles: list[tuple[str, str]]
    source_fieldlist_handles: list[str]
    source_fieldlist_dangling: list[str]
    variable_dict_entries: list[VariableDictEntry]
    visualstyle_entries: list[VisualStyleEntry]
    visualstyle_extensions: list[tuple[str, ExtensionSnapshot]]
    material_name: str | None
    interfere_handles: list[HeaderHandleRef]
    mleader_style_specs: list[MLeaderStyleSpec]
    mleader_entity_style_refs: list[tuple[str, str]]
    required_root_dicts: list[str]
    has_acad_layerstates: bool
    assoc_network_tags: list[RawTag]
    detail_view_styles: list[RawObjectDictEntry]
    detail_view_style_extensions: list[tuple[str, ExtensionSnapshot]]
    section_view_styles: list[RawObjectDictEntry]
    section_view_style_extensions: list[tuple[str, ExtensionSnapshot]]
    layer_extension_snapshots: list[tuple[str, ExtensionSnapshot]]
    mleader_style_extension_snapshots: list[tuple[str, ExtensionSnapshot]]
    table_style_cellstylemap: list[RawObjectDictEntry]
    late_rootdict_entries: tuple[RootDictEntryRestoreSnapshot, ...]
    sortents_by_block: list[SortentsBlockSpec]
    block_xdict_orders: dict[str, list[str]]
    group_specs: list[GroupSpec]
    entity_xrecord_fallbacks: dict[str, list[EntityXRecordFallbackSpec]]
    raw_graph_fallbacks: dict[str, RawGraphFallbackSpec]
    raw_entity_swap_fallbacks: dict[str, list[RawEntitySwapFallbackSpec]]
