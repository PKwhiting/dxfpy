from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.dynblkhelper import (
    get_dynamic_block_record_handle,
    snapshot_raw_extension_subtree,
    snapshot_raw_dynamic_block_layout,
)
from ezdxf.lldxf.tagwriter import TagCollector
from ezdxf.sections.classes import snapshot_raw_classes
from ezdxf.sections.header import snapshot_raw_header_vars

from ._api import block_to_code, entities_to_code, table_entries_to_code
from ._common import _maybe_get, _names, _sort_blocks
from ._specs import (
    DocumentCodegenCapture,
    EntityXRecordFallbackSpec,
    ExtensionSnapshot,
    HeaderHandleRef,
    MLeaderStyleSpec,
    OwnedObjectSpec,
    RawEntitySwapFallbackSpec,
    RawGraphFallbackSpec,
    RawGraphOwnedObjectSpec,
    RawObjectDictEntry,
    RawSubclassList,
    RawTag,
    RawXDataTags,
    ResourceHandleRef,
    SortentsBlockSpec,
    VariableDictEntry,
    VisualStyleEntry,
)


def _xrecord_tags(xrecord) -> list[RawTag]:
    return [(tag.code, tag.value) for tag in xrecord.tags]


def _raw_object_tags(entity) -> list[RawTag]:
    if hasattr(entity, "xtags"):
        return [
            (tag.code, tag.value)
            for subclass in entity.xtags.subclasses[1:]
            for tag in subclass
        ]
    return []


def _raw_object_subclasses(entity) -> RawSubclassList:
    if entity.dxftype() == "XRECORD" and hasattr(entity, "tags"):
        return [[(100, "AcDbXrecord"), *[(tag.code, tag.value) for tag in entity.tags]]]
    if entity.dxftype() == "FIELD" and hasattr(entity, "tags"):
        return [[(100, "AcDbField"), *[(tag.code, tag.value) for tag in entity.tags]]]
    if hasattr(entity, "xtags"):
        return [
            [(tag.code, tag.value) for tag in subclass]
            for subclass in entity.xtags.subclasses[1:]
        ]
    return []


def _normalize(value):
    if type(value).__name__ == "float64":
        return float(value)
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _entity_export_tags(entity) -> list[RawTag]:
    def normalize(value):
        if type(value).__name__ == "float64":
            return float(value)
        if isinstance(value, tuple):
            return tuple(normalize(item) for item in value)
        return value

    collector = TagCollector(
        dxfversion=entity.doc.dxfversion if entity.doc else "AC1032"
    )
    entity.export_entity(collector)
    return [(tag.code, normalize(tag.value)) for tag in collector.tags]


def _raw_xdata(entity) -> RawXDataTags:
    if not getattr(entity, "xdata", None):
        return []
    return [[(tag.code, tag.value) for tag in tags] for tags in entity.xdata.data.values()]


def _owned_object_specs(doc, owner_handle: str) -> list[OwnedObjectSpec]:
    specs: list[OwnedObjectSpec] = []
    for obj in doc.objects:
        if obj.dxf.owner != owner_handle:
            continue
        specs.append(
            OwnedObjectSpec(
                handle=obj.dxf.handle,
                owner=owner_handle,
                dxftype=obj.dxftype(),
                subclasses=_raw_object_subclasses(obj),
            )
        )
        specs.extend(_owned_object_specs(doc, obj.dxf.handle))
    return specs


def capture_document_codegen_inputs(doc, source: Path) -> DocumentCodegenCapture:
    default_doc = ezdxf.new("R2018")
    header_state_skip = {
        "$HANDSEED",
        "$VERSIONGUID",
        "$FINGERPRINTGUID",
        "$TDCREATE",
        "$TDUPDATE",
        "$CMATERIAL",
        "$INTERFEREOBJVS",
        "$INTERFEREVPVS",
    }
    header_raw_override_keys = (
        "$TDCREATE",
        "$TDUPDATE",
        "$EXTMIN",
        "$EXTMAX",
        "$PEXTMIN",
        "$PEXTMAX",
        "$FINGERPRINTGUID",
        "$VERSIONGUID",
    )
    header_state = {
        name: _normalize(doc.header.get(name))
        for name in doc.header.varnames()
        if name not in header_state_skip
    }
    header_custom_vars = [
        (_normalize(tag), _normalize(value)) for tag, value in doc.header.custom_vars
    ]
    raw_header_overrides = snapshot_raw_header_vars(str(source), header_raw_override_keys)
    raw_classes = snapshot_raw_classes(doc.classes)

    block_codes = []
    block_layout_entity_snapshots: dict[str, Any] = {}
    imports = {"import ezdxf", "from pathlib import Path"}

    blocks = _sort_blocks([block for block in doc.blocks if not block.is_any_layout])
    for block in blocks:
        code = block_to_code(block, drawing="doc")
        block_codes.append(code)
        imports.update(code.imports)
        if "restore_raw_dynamic_block_layout" in str(code):
            block_layout_entity_snapshots[block.name] = snapshot_raw_dynamic_block_layout(
                block
            )[1]

    msp_code = entities_to_code(doc.modelspace(), layout="msp")
    imports.update(msp_code.imports)

    resource_entities = []
    layers_with_xdict: set[str] = set()
    selected_layers = _names(doc.layers) - _names(default_doc.layers)
    selected_linetypes = _names(doc.linetypes) - _names(default_doc.linetypes)
    selected_styles = _names(doc.styles) - _names(default_doc.styles)
    selected_dimstyles = _names(doc.dimstyles) - _names(default_doc.dimstyles)
    selected_appids = _names(doc.appids) - _names(default_doc.appids)
    added_layers: set[str] = set()
    added_linetypes: set[str] = set()
    added_styles: set[str] = set()
    added_dimstyles: set[str] = set()
    added_appids: set[str] = set()
    resource_code = None

    while True:
        for name in sorted(selected_layers - added_layers):
            entity = _maybe_get(doc.layers, name)
            if entity is not None:
                resource_entities.append(entity)
                if entity.has_extension_dict:
                    layers_with_xdict.add(name)
            added_layers.add(name)
        for name in sorted(selected_linetypes - added_linetypes):
            entity = _maybe_get(doc.linetypes, name)
            if entity is not None:
                resource_entities.append(entity)
            added_linetypes.add(name)
        for name in sorted(selected_styles - added_styles):
            entity = _maybe_get(doc.styles, name)
            if entity is not None:
                resource_entities.append(entity)
            added_styles.add(name)
        for name in sorted(selected_dimstyles - added_dimstyles):
            entity = _maybe_get(doc.dimstyles, name)
            if entity is not None:
                resource_entities.append(entity)
            added_dimstyles.add(name)
        for name in sorted(selected_appids - added_appids):
            entity = _maybe_get(doc.appids, name)
            if entity is not None:
                resource_entities.append(entity)
            added_appids.add(name)

        resource_code = (
            table_entries_to_code(resource_entities, drawing="doc")
            if resource_entities
            else None
        )
        if resource_code is None:
            break

        next_layers = resource_code.layers - _names(default_doc.layers)
        next_linetypes = resource_code.linetypes - _names(default_doc.linetypes)
        next_styles = resource_code.styles - _names(default_doc.styles)
        next_dimstyles = resource_code.dimstyles - _names(default_doc.dimstyles)
        if (
            next_layers <= selected_layers
            and next_linetypes <= selected_linetypes
            and next_styles <= selected_styles
            and next_dimstyles <= selected_dimstyles
        ):
            break
        selected_layers.update(next_layers)
        selected_linetypes.update(next_linetypes)
        selected_styles.update(next_styles)
        selected_dimstyles.update(next_dimstyles)

    if resource_code is not None:
        imports.update(resource_code.imports)

    root = doc.rootdict
    root_xrecords = {}
    deferred_recompose_tags: list[RawTag] = []
    source_fieldlist_handles: list[str] = []
    source_fieldlist_dangling: list[str] = []
    for key in (
        "ACAD_CIP_PREVIOUS_PRODUCT_INFO",
        "ACAD_LAST_SAVED_VERSION_INFO",
        "ACDB_RECOMPOSE_DATA",
    ):
        obj = root.get(key)
        if obj is not None and obj.dxftype() == "XRECORD":
            tags = _xrecord_tags(obj)
            if key == "ACDB_RECOMPOSE_DATA":
                deferred_recompose_tags = tags
            else:
                root_xrecords[key] = tags

    source_field_list = doc.objects.get_field_list()
    if source_field_list is not None:
        source_fieldlist_handles = [str(handle) for handle in source_field_list.handles]
        source_fieldlist_dangling = [
            str(handle)
            for handle in source_field_list.handles
            if doc.entitydb.get(str(handle)) is None
        ]

    variable_dict_entries: list[VariableDictEntry] = []
    variable_dict = root.get("AcDbVariableDictionary")
    if hasattr(variable_dict, "items"):
        for key, value in variable_dict.items():
            variable_dict_entries.append(
                VariableDictEntry(key=key, value=value.dxf.get("value", ""))
            )

    visualstyle_entries: list[VisualStyleEntry] = []
    visualstyle_extensions: list[tuple[str, ExtensionSnapshot]] = []
    visualstyle_dict = root.get("ACAD_VISUALSTYLE")
    if hasattr(visualstyle_dict, "items"):
        for key, value in visualstyle_dict.items():
            dxfattribs = dict(value.dxfattribs())
            dxfattribs.pop("handle", None)
            dxfattribs.pop("owner", None)
            visualstyle_entries.append(VisualStyleEntry(key=key, dxfattribs=dxfattribs))
            if getattr(value, "has_extension_dict", False):
                visualstyle_extensions.append(
                    (str(key), snapshot_raw_extension_subtree(value))
                )

    material_name = None
    material_handle = doc.header.get("$CMATERIAL", None)
    if material_handle:
        material = doc.entitydb.get(material_handle)
        if material is not None and material.dxftype() == "MATERIAL":
            material_name = material.dxf.name

    interfere_handles: list[HeaderHandleRef] = []
    for var_name in ("$INTERFEREOBJVS", "$INTERFEREVPVS"):
        handle = doc.header.get(var_name, None)
        if isinstance(handle, str) and handle:
            interfere_handles.append(HeaderHandleRef(name=var_name, handle=handle))

    mleader_style_specs: list[MLeaderStyleSpec] = []
    for _, style in doc.mleader_styles:
        xdata_tags: list[RawTag] = []
        if style.xdata and "ACAD_MLEADERVER" in style.xdata.data:
            xdata_tags = [
                (tag.code, tag.value)
                for tag in style.xdata.data["ACAD_MLEADERVER"]
                if tag.code != 1001
            ]
        reactors = [str(handle) for handle in style.get_reactors() if handle]
        if xdata_tags or len(reactors) > 1:
            mleader_style_specs.append(
                MLeaderStyleSpec(
                    name=style.dxf.name,
                    xdata_tags=xdata_tags,
                    reactors=reactors,
                )
            )

    required_root_dicts = [
        key
        for key in (
            "ACAD_ASSOCNETWORK",
            "ACAD_DETAILVIEWSTYLE",
            "ACAD_SECTIONVIEWSTYLE",
            "AEC_PROPERTY_SET_DEFS",
            "AcDbVariableDictionary",
        )
        if root.get(key) is not None
    ]

    layerstates_present = doc.entitydb.get(doc.layers.head.dxf.handle)
    has_acad_layerstates = False
    if getattr(layerstates_present, "has_extension_dict", False):
        lx = layerstates_present.get_extension_dict().dictionary
        has_acad_layerstates = "ACAD_LAYERSTATES" in lx

    assoc_network_tags: list[RawTag] = []
    assoc_root = root.get("ACAD_ASSOCNETWORK")
    if hasattr(assoc_root, "get"):
        inner = assoc_root.get("ACAD_ASSOCNETWORK")
        if inner is not None:
            assoc_network_tags = _raw_object_tags(inner)

    detail_view_styles: list[RawObjectDictEntry] = []
    detail_view_style_extensions: list[tuple[str, ExtensionSnapshot]] = []
    detail_root = root.get("ACAD_DETAILVIEWSTYLE")
    if hasattr(detail_root, "items"):
        for key, value in detail_root.items():
            detail_view_styles.append(RawObjectDictEntry(key=key, tags=_raw_object_tags(value)))
            if getattr(value, "has_extension_dict", False):
                detail_view_style_extensions.append(
                    (str(key), snapshot_raw_extension_subtree(value))
                )

    section_view_styles: list[RawObjectDictEntry] = []
    section_view_style_extensions: list[tuple[str, ExtensionSnapshot]] = []
    section_root = root.get("ACAD_SECTIONVIEWSTYLE")
    if hasattr(section_root, "items"):
        for key, value in section_root.items():
            section_view_styles.append(RawObjectDictEntry(key=key, tags=_raw_object_tags(value)))
            if getattr(value, "has_extension_dict", False):
                section_view_style_extensions.append(
                    (str(key), snapshot_raw_extension_subtree(value))
                )

    layer_extension_snapshots: list[tuple[str, ExtensionSnapshot]] = []
    for layer in doc.layers:
        if layer.has_extension_dict:
            layer_extension_snapshots.append(
                (layer.dxf.name, snapshot_raw_extension_subtree(layer))
            )

    mleader_style_extension_snapshots: list[tuple[str, ExtensionSnapshot]] = []
    for key, style in doc.mleader_styles.object_dict.items():
        if getattr(style, "has_extension_dict", False):
            mleader_style_extension_snapshots.append(
                (str(key), snapshot_raw_extension_subtree(style))
            )

    table_style_cellstylemap: list[RawObjectDictEntry] = []
    table_style_root = root.get("ACAD_TABLESTYLE")
    if hasattr(table_style_root, "items"):
        standard = table_style_root.get("Standard")
        if getattr(standard, "has_extension_dict", False):
            xdict = standard.get_extension_dict().dictionary
            for key, value in xdict.items():
                if value.dxftype() == "CELLSTYLEMAP":
                    table_style_cellstylemap.append(
                        RawObjectDictEntry(key=key, tags=_raw_object_tags(value))
                    )

    sortents_by_block: list[SortentsBlockSpec] = []
    block_xdict_orders: dict[str, list[str]] = {}
    for block in blocks:
        xdict = (
            block.block_record.get_extension_dict().dictionary
            if block.block_record.has_extension_dict
            else None
        )
        if xdict is not None:
            block_xdict_orders[block.name] = [str(key) for key in xdict.keys()]
        if xdict is None or "ACAD_SORTENTS" not in xdict:
            continue
        sortents = xdict.get("ACAD_SORTENTS")
        if sortents is not None:
            sortents_by_block.append(
                SortentsBlockSpec(block_name=block.name, tags=list(sortents.table.items()))
            )

    entity_xrecord_fallbacks: dict[str, list[EntityXRecordFallbackSpec]] = {}
    for block in blocks:
        specs: list[EntityXRecordFallbackSpec] = []
        for entity in block:
            if not getattr(entity, "has_extension_dict", False):
                continue
            xdict = entity.get_extension_dict().dictionary
            for key, value in xdict.items():
                if value.dxftype() != "XRECORD":
                    continue
                specs.append(
                    EntityXRecordFallbackSpec(
                        entity_handle=entity.dxf.handle,
                        dict_key=str(key),
                        dict_order=[str(name) for name in xdict.keys()],
                        root_handle=value.dxf.handle,
                        root_dxftype=value.dxftype(),
                        root_subclasses=_raw_object_subclasses(value),
                        owned_specs=_owned_object_specs(doc, value.dxf.handle),
                    )
                )
        if specs:
            entity_xrecord_fallbacks[block.name] = specs

    raw_graph_fallbacks: dict[str, RawGraphFallbackSpec] = {}
    for block in blocks:
        xdict = (
            block.block_record.get_extension_dict().dictionary
            if block.block_record.has_extension_dict
            else None
        )
        graph = xdict.get("ACAD_ENHANCEDBLOCK") if xdict is not None else None
        if graph is None:
            continue
        purge = xdict.get("AcDbDynamicBlockRoundTripPurgePreventer") if xdict is not None else None
        owned_specs: list[RawGraphOwnedObjectSpec] = []
        for obj in doc.objects:
            if obj.dxf.owner != graph.dxf.handle:
                continue
            owned_specs.append(
                RawGraphOwnedObjectSpec(
                    handle=obj.dxf.handle,
                    dxftype=obj.dxftype(),
                    subclasses=_raw_object_subclasses(obj),
                    xdata=_raw_xdata(obj),
                    reactors=list(obj.get_reactors()),
                )
            )
        raw_graph_fallbacks[block.name] = RawGraphFallbackSpec(
            graph_handle=graph.dxf.handle,
            graph_subclasses=_raw_object_subclasses(graph),
            graph_xdata=[(tag.code, tag.value) for tag in graph.get_xdata("AcadBPTGraphNodeId")]
            if graph.has_xdata("AcadBPTGraphNodeId")
            else [],
            purge_subclasses=_raw_object_subclasses(purge) if purge is not None else [],
            owned_specs=owned_specs,
        )

    raw_entity_swap_blocks = set(raw_graph_fallbacks.keys())
    raw_graph_block_record_handles = {
        doc.blocks.get(name).block_record.dxf.handle
        for name in raw_graph_fallbacks.keys()
        if doc.blocks.get(name) is not None
    }
    for block in blocks:
        base_handle = get_dynamic_block_record_handle(block.block_record)
        if base_handle and base_handle in raw_graph_block_record_handles:
            raw_entity_swap_blocks.add(block.name)

    raw_entity_swap_fallbacks: dict[str, list[RawEntitySwapFallbackSpec]] = {}
    handle_codes = {
        320,
        331,
        332,
        333,
        340,
        341,
        342,
        343,
        344,
        345,
        346,
        347,
        348,
        349,
        350,
        360,
        390,
        1005,
    }
    for block in blocks:
        if block.name not in raw_entity_swap_blocks:
            continue
        specs: list[RawEntitySwapFallbackSpec] = []
        for entity in block:
            handle = entity.dxf.handle
            owner = entity.dxf.owner
            if not handle or not owner:
                continue
            xdict_handle = ""
            allowed_handles = {handle, owner}
            if getattr(entity, "has_extension_dict", False):
                xdict_handle = entity.get_extension_dict().dictionary.dxf.handle
                allowed_handles.add(xdict_handle)
            source_resource_handles = [
                ResourceHandleRef(str(value), key)
                for key, value in entity.dxfattribs().items()
                if key.endswith("_handle")
                and isinstance(value, str)
                and value not in {"0", handle, owner, xdict_handle}
            ]
            resource_values = {ref.source_handle for ref in source_resource_handles}
            raw_tags = _entity_export_tags(entity)
            external_handles = {
                str(value)
                for code, value in raw_tags
                if code in handle_codes
                and isinstance(value, str)
                and value not in allowed_handles
                and value != "0"
            }
            if external_handles - resource_values:
                continue
            specs.append(
                RawEntitySwapFallbackSpec(
                    source_handle=handle,
                    source_owner=owner,
                    source_xdict_handle=xdict_handle,
                    source_resource_handles=source_resource_handles,
                    raw_tags=raw_tags,
                )
            )
        if specs:
            raw_entity_swap_fallbacks[block.name] = specs

    return {
        "doc": doc,
        "source": source,
        "header_state": header_state,
        "header_custom_vars": header_custom_vars,
        "raw_header_overrides": raw_header_overrides,
        "raw_classes": raw_classes,
        "blocks": blocks,
        "block_codes": block_codes,
        "block_layout_entity_snapshots": block_layout_entity_snapshots,
        "msp_code": msp_code,
        "imports": imports,
        "resource_code": resource_code,
        "layers_with_xdict": layers_with_xdict,
        "root_xrecords": root_xrecords,
        "deferred_recompose_tags": deferred_recompose_tags,
        "source_fieldlist_handles": source_fieldlist_handles,
        "source_fieldlist_dangling": source_fieldlist_dangling,
        "variable_dict_entries": variable_dict_entries,
        "visualstyle_entries": visualstyle_entries,
        "visualstyle_extensions": visualstyle_extensions,
        "material_name": material_name,
        "interfere_handles": interfere_handles,
        "mleader_style_specs": mleader_style_specs,
        "required_root_dicts": required_root_dicts,
        "has_acad_layerstates": has_acad_layerstates,
        "assoc_network_tags": assoc_network_tags,
        "detail_view_styles": detail_view_styles,
        "detail_view_style_extensions": detail_view_style_extensions,
        "section_view_styles": section_view_styles,
        "section_view_style_extensions": section_view_style_extensions,
        "layer_extension_snapshots": layer_extension_snapshots,
        "mleader_style_extension_snapshots": mleader_style_extension_snapshots,
        "table_style_cellstylemap": table_style_cellstylemap,
        "sortents_by_block": sortents_by_block,
        "block_xdict_orders": block_xdict_orders,
        "entity_xrecord_fallbacks": entity_xrecord_fallbacks,
        "raw_graph_fallbacks": raw_graph_fallbacks,
        "raw_entity_swap_fallbacks": raw_entity_swap_fallbacks,
    }
