from __future__ import annotations

import sys
from pathlib import Path

import ezdxf
from ezdxf.addons.dxf2code import block_to_code, entities_to_code, table_entries_to_code
from ezdxf.dynblkhelper import (
    get_dynamic_block_linear_parameters,
    get_dynamic_block_record_handle,
    snapshot_raw_extension_subtree,
    snapshot_raw_dynamic_block_layout,
)
from ezdxf.sections.classes import snapshot_raw_classes
from ezdxf.sections.header import snapshot_raw_header_vars
from ezdxf.lldxf.tagwriter import TagCollector


def _names(table) -> set[str]:
    return {entry.dxf.name for entry in table}


def _maybe_get(table, name: str):
    try:
        return table.get(name)
    except Exception:
        return None


def _xrecord_tags(xrecord) -> list[tuple[int, object]]:
    return [(tag.code, tag.value) for tag in xrecord.tags]


def _raw_object_tags(entity) -> list[tuple[int, object]]:
    if hasattr(entity, "xtags"):
        return [
            (tag.code, tag.value)
            for subclass in entity.xtags.subclasses[1:]
            for tag in subclass
        ]
    return []


def _raw_object_subclasses(entity) -> list[list[tuple[int, object]]]:
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


def _entity_export_tags(entity) -> list[tuple[int, object]]:
    def normalize(value):
        if type(value).__name__ == "float64":
            return float(value)
        if isinstance(value, tuple):
            return tuple(normalize(item) for item in value)
        return value

    collector = TagCollector(dxfversion=entity.doc.dxfversion if entity.doc else "AC1032")
    entity.export_entity(collector)
    return [(tag.code, normalize(tag.value)) for tag in collector.tags]


def _raw_xdata(entity) -> list[list[tuple[int, object]]]:
    if not getattr(entity, "xdata", None):
        return []
    return [[(tag.code, tag.value) for tag in tags] for tags in entity.xdata.data.values()]


def _owned_object_specs(doc, owner_handle: str) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for obj in doc.objects:
        if obj.dxf.owner != owner_handle:
            continue
        specs.append(
            {
                "handle": obj.dxf.handle,
                "owner": owner_handle,
                "dxftype": obj.dxftype(),
                "subclasses": _raw_object_subclasses(obj),
            }
        )
        specs.extend(_owned_object_specs(doc, obj.dxf.handle))
    return specs


def _block_dependencies(blocks) -> dict[str, set[str]]:
    block_by_name = {block.name: block for block in blocks}
    dependencies: dict[str, set[str]] = {block.name: set() for block in blocks}
    for block in blocks:
        deps = dependencies[block.name]
        for entity in block:
            if entity.dxftype() != "INSERT":
                continue
            name = entity.dxf.name
            if name in block_by_name and name != block.name:
                deps.add(name)
        base_handle = get_dynamic_block_record_handle(block.block_record)
        if base_handle:
            base_record = block.doc.entitydb.get(base_handle) if block.doc is not None else None
            if base_record is not None:
                base_name = base_record.dxf.get("name", "")
                if base_name in block_by_name and base_name != block.name:
                    deps.add(base_name)
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


def write_document_code(
    source: str | Path,
    script_path: str | Path,
    out_path: str | Path,
) -> None:
    source = Path(source)
    script_path = Path(script_path)
    out_path = Path(out_path)

    doc = ezdxf.readfile(source)
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
    header_custom_vars = [(_normalize(tag), _normalize(value)) for tag, value in doc.header.custom_vars]
    raw_header_overrides = snapshot_raw_header_vars(str(source), header_raw_override_keys)
    raw_classes = snapshot_raw_classes(doc.classes)

    block_codes = []
    imports = {"import ezdxf", "from pathlib import Path"}
    used_layers: set[str] = set()
    used_linetypes: set[str] = set()
    used_styles: set[str] = set()
    used_dimstyles: set[str] = set()

    blocks = _sort_blocks([block for block in doc.blocks if not block.is_any_layout])
    for block in blocks:
        code = block_to_code(block, drawing="doc")
        block_codes.append(code)
        imports.update(code.imports)
        used_layers.update(code.layers)
        used_linetypes.update(code.linetypes)
        used_styles.update(code.styles)
        used_dimstyles.update(code.dimstyles)

    msp_code = entities_to_code(doc.modelspace(), layout="msp")
    imports.update(msp_code.imports)
    used_layers.update(msp_code.layers)
    used_linetypes.update(msp_code.linetypes)
    used_styles.update(msp_code.styles)
    used_dimstyles.update(msp_code.dimstyles)

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

        resource_code = table_entries_to_code(resource_entities, drawing="doc") if resource_entities else None
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
    deferred_recompose_tags: list[tuple[int, object]] = []
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

    variable_dict_entries: list[tuple[str, str]] = []
    variable_dict = root.get("AcDbVariableDictionary")
    if hasattr(variable_dict, "items"):
        for key, value in variable_dict.items():
            variable_dict_entries.append((key, value.dxf.get("value", "")))

    visualstyle_entries: list[tuple[str, dict]] = []
    visualstyle_extensions: list[
        tuple[str, tuple[tuple[tuple[int, object], ...], ...]]
    ] = []
    visualstyle_dict = root.get("ACAD_VISUALSTYLE")
    if hasattr(visualstyle_dict, "items"):
        for key, value in visualstyle_dict.items():
            dxfattribs = dict(value.dxfattribs())
            dxfattribs.pop("handle", None)
            dxfattribs.pop("owner", None)
            visualstyle_entries.append((key, dxfattribs))
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

    interfere_handles: list[tuple[str, str]] = []
    for var_name in ("$INTERFEREOBJVS", "$INTERFEREVPVS"):
        handle = doc.header.get(var_name, None)
        if isinstance(handle, str) and handle:
            interfere_handles.append((var_name, handle))

    mleader_style_specs: list[dict[str, object]] = []
    for _, style in doc.mleader_styles:
        xdata_tags: list[tuple[int, object]] = []
        if style.xdata and "ACAD_MLEADERVER" in style.xdata.data:
            xdata_tags = [(tag.code, tag.value) for tag in style.xdata.data["ACAD_MLEADERVER"] if tag.code != 1001]
        reactors = [str(handle) for handle in style.get_reactors() if handle]
        if xdata_tags or len(reactors) > 1:
            mleader_style_specs.append(
                {
                    "name": style.dxf.name,
                    "xdata_tags": xdata_tags,
                    "reactors": reactors,
                }
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
    if getattr(layerstates_present, 'has_extension_dict', False):
        lx = layerstates_present.get_extension_dict().dictionary
        has_acad_layerstates = 'ACAD_LAYERSTATES' in lx

    assoc_network_tags: list[tuple[int, object]] = []
    assoc_root = root.get("ACAD_ASSOCNETWORK")
    if hasattr(assoc_root, "get"):
        inner = assoc_root.get("ACAD_ASSOCNETWORK")
        if inner is not None:
            assoc_network_tags = _raw_object_tags(inner)

    detail_view_styles: list[tuple[str, list[tuple[int, object]]]] = []
    detail_view_style_extensions: list[
        tuple[str, tuple[tuple[tuple[int, object], ...], ...]]
    ] = []
    detail_root = root.get("ACAD_DETAILVIEWSTYLE")
    if hasattr(detail_root, "items"):
        for key, value in detail_root.items():
            detail_view_styles.append((key, _raw_object_tags(value)))
            if getattr(value, "has_extension_dict", False):
                detail_view_style_extensions.append(
                    (str(key), snapshot_raw_extension_subtree(value))
                )

    section_view_styles: list[tuple[str, list[tuple[int, object]]]] = []
    section_view_style_extensions: list[
        tuple[str, tuple[tuple[tuple[int, object], ...], ...]]
    ] = []
    section_root = root.get("ACAD_SECTIONVIEWSTYLE")
    if hasattr(section_root, "items"):
        for key, value in section_root.items():
            section_view_styles.append((key, _raw_object_tags(value)))
            if getattr(value, "has_extension_dict", False):
                section_view_style_extensions.append(
                    (str(key), snapshot_raw_extension_subtree(value))
                )

    layer_extension_snapshots: list[
        tuple[str, tuple[tuple[tuple[int, object], ...], ...]]
    ] = []
    for layer in doc.layers:
        if layer.has_extension_dict:
            layer_extension_snapshots.append(
                (layer.dxf.name, snapshot_raw_extension_subtree(layer))
            )

    mleader_style_extension_snapshots: list[
        tuple[str, tuple[tuple[tuple[int, object], ...], ...]]
    ] = []
    for key, style in doc.mleader_styles.object_dict.items():
        if getattr(style, "has_extension_dict", False):
            mleader_style_extension_snapshots.append(
                (str(key), snapshot_raw_extension_subtree(style))
            )

    table_style_cellstylemap: list[tuple[str, list[tuple[int, object]]]] = []
    table_style_root = root.get("ACAD_TABLESTYLE")
    if hasattr(table_style_root, "items"):
        standard = table_style_root.get("Standard")
        if getattr(standard, "has_extension_dict", False):
            xdict = standard.get_extension_dict().dictionary
            for key, value in xdict.items():
                if value.dxftype() == "CELLSTYLEMAP":
                    table_style_cellstylemap.append((key, _raw_object_tags(value)))

    sortents_by_block: list[tuple[str, list[tuple[str, str]]]] = []
    block_xdict_orders: dict[str, list[str]] = {}
    for block in blocks:
        xdict = block.block_record.get_extension_dict().dictionary if block.block_record.has_extension_dict else None
        if xdict is not None:
            block_xdict_orders[block.name] = [str(key) for key in xdict.keys()]
        if xdict is None or "ACAD_SORTENTS" not in xdict:
            continue
        sortents = xdict.get("ACAD_SORTENTS")
        if sortents is not None:
            sortents_by_block.append((block.name, list(sortents.table.items())))

    entity_xrecord_fallbacks: dict[str, list[dict[str, object]]] = {}
    for block in blocks:
        specs: list[dict[str, object]] = []
        for entity in block:
            if not getattr(entity, "has_extension_dict", False):
                continue
            xdict = entity.get_extension_dict().dictionary
            for key, value in xdict.items():
                if value.dxftype() != "XRECORD":
                    continue
                specs.append(
                    {
                        "entity_handle": entity.dxf.handle,
                        "dict_key": str(key),
                        "dict_order": [str(name) for name in xdict.keys()],
                        "root_handle": value.dxf.handle,
                        "root_dxftype": value.dxftype(),
                        "root_subclasses": _raw_object_subclasses(value),
                        "owned_specs": _owned_object_specs(doc, value.dxf.handle),
                    }
                )
        if specs:
            entity_xrecord_fallbacks[block.name] = specs

    raw_graph_fallbacks: dict[str, dict[str, object]] = {}
    for block in blocks:
        xdict = block.block_record.get_extension_dict().dictionary if block.block_record.has_extension_dict else None
        graph = xdict.get("ACAD_ENHANCEDBLOCK") if xdict is not None else None
        if graph is None:
            continue
        purge = xdict.get("AcDbDynamicBlockRoundTripPurgePreventer") if xdict is not None else None
        owned_specs = []
        for obj in doc.objects:
            if obj.dxf.owner != graph.dxf.handle:
                continue
            owned_specs.append(
                {
                    "handle": obj.dxf.handle,
                    "dxftype": obj.dxftype(),
                    "subclasses": _raw_object_subclasses(obj),
                    "xdata": _raw_xdata(obj),
                    "reactors": list(obj.get_reactors()),
                }
            )
        raw_graph_fallbacks[block.name] = {
            "graph_handle": graph.dxf.handle,
            "graph_subclasses": _raw_object_subclasses(graph),
            "graph_xdata": [(tag.code, tag.value) for tag in graph.get_xdata("AcadBPTGraphNodeId")] if graph.has_xdata("AcadBPTGraphNodeId") else [],
            "purge_subclasses": _raw_object_subclasses(purge) if purge is not None else [],
            "owned_specs": owned_specs,
        }

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

    raw_entity_swap_fallbacks: dict[str, list[dict[str, object]]] = {}
    handle_codes = {320, 331, 332, 333, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 360, 390, 1005}
    for block in blocks:
        if block.name not in raw_entity_swap_blocks:
            continue
        specs: list[dict[str, object]] = []
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
                (str(value), key)
                for key, value in entity.dxfattribs().items()
                if key.endswith("_handle") and isinstance(value, str) and value not in {"0", handle, owner, xdict_handle}
            ]
            resource_values = {value for value, _ in source_resource_handles}
            raw_tags = _entity_export_tags(entity)
            external_handles = {
                str(value)
                for code, value in raw_tags
                if code in handle_codes and isinstance(value, str) and value not in allowed_handles and value != "0"
            }
            if external_handles - resource_values:
                continue
            specs.append(
                {
                    "source_handle": handle,
                    "source_owner": owner,
                    "source_xdict_handle": xdict_handle,
                    "source_resource_handles": source_resource_handles,
                    "raw_tags": raw_tags,
                }
            )
        if specs:
            raw_entity_swap_fallbacks[block.name] = specs

    lines: list[str] = []
    raw_entity_swap_calls: list[str] = []
    sortents_calls: list[str] = []
    lines.extend(sorted(imports))
    lines.append("from ezdxf.sections.classes import restore_raw_classes")
    lines.append("from ezdxf.sections.header import restore_raw_header_vars")
    lines.append("")
    lines.append("from ezdxf.entities import factory")
    lines.append("from ezdxf.entities.dxfentity import DXFTagStorage")
    lines.append("from ezdxf.lldxf.extendedtags import ExtendedTags")
    lines.append("from ezdxf.lldxf.tags import Tags")
    lines.append("from ezdxf.lldxf.types import DXFTag")
    lines.append("from ezdxf.lldxf.types import dxftag")
    lines.append("from ezdxf.dynblkhelper import _delete_graph_stack, _ensure_dynamic_block_extension_dict, _new_tag_storage_object")
    lines.append("")
    lines.append(f'OUT = Path(r"{out_path.as_posix()}")')
    lines.append(f'doc = ezdxf.new("{doc.dxfversion}")')
    lines.append("msp = doc.modelspace()")
    lines.append("_source_entity_map = {}")
    lines.append("_source_object_map = {}")
    lines.append("_dangling_handle_map = {}")
    lines.append("")
    lines.append("def _add_raw_object(_parent, _key, _dxftype, _tags):")
    lines.append("    _raw = Tags([dxftag(0, _dxftype), dxftag(330, _parent.dxf.handle)])")
    lines.append("    _raw.extend(dxftag(code, value) for code, value in _tags)")
    lines.append("    _obj = factory.load(ExtendedTags(_raw), doc)")
    lines.append("    factory.bind(_obj, doc)")
    lines.append("    doc.objects.add_object(_obj)")
    lines.append("    _parent.add(_key, _obj)")
    lines.append("    return _obj")
    lines.append("")
    lines.append("def _map_raw_graph_value(_value, _entity_map, _object_map):")
    lines.append("    if isinstance(_value, str):")
    lines.append("        if _value in _object_map:")
    lines.append("            return _object_map[_value].dxf.handle")
    lines.append("        if _value in _entity_map:")
    lines.append("            return _entity_map[_value].dxf.handle")
    lines.append("    return _value")
    lines.append("")
    lines.append("def _new_raw_graph_object(_dxftype, _owner):")
    lines.append("    if _dxftype in ('XRECORD', 'FIELD'):")
    lines.append("        _obj = factory.new(_dxftype, dxfattribs={'owner': _owner}, doc=doc)")
    lines.append("        factory.bind(_obj, doc)")
    lines.append("        doc.objects.add_object(_obj)")
    lines.append("        return _obj")
    lines.append("    return _new_tag_storage_object(doc, _dxftype, _owner, [])")
    lines.append("")
    lines.append("def _load_raw_graph_object(_obj, _owner, _subclasses, _xdata, _entity_map, _object_map):")
    lines.append("    _tags = [dxftag(0, _obj.dxftype()), dxftag(5, _obj.dxf.handle), dxftag(330, _owner)]")
    lines.append("    for _subclass in _subclasses:")
    lines.append("        _tags.extend(")
    lines.append("            dxftag(code, _map_raw_graph_value(value, _entity_map, _object_map) if code in (330, 331, 332, 333, 340, 360, 1005) else value)")
    lines.append("            for code, value in _subclass")
    lines.append("        )")
    lines.append("    for _xdata_tags in _xdata:")
    lines.append("        for code, value in _xdata_tags:")
    lines.append("            if isinstance(value, (tuple, list)):")
    lines.append("                _tags.append(dxftag(code, value))")
    lines.append("            else:")
    lines.append("                _tags.append(DXFTag(code, value))")
    lines.append("    _xtags = ExtendedTags(_tags)")
    lines.append("    _obj.load_tags(_xtags, dxfversion=doc.dxfversion)")
    lines.append("    if hasattr(_obj, 'store_tags'):")
    lines.append("        _obj.store_tags(_xtags)")
    lines.append("    return _obj")
    lines.append("")
    lines.append("def _set_raw_graph_reactors(_obj, _reactors, _entity_map, _object_map):")
    lines.append("    _mapped = [")
    lines.append("        _map_raw_graph_value(_handle, _entity_map, _object_map)")
    lines.append("        for _handle in _reactors")
    lines.append("    ]")
    lines.append("    _mapped = [str(_handle) for _handle in _mapped if _handle]")
    lines.append("    if _mapped:")
    lines.append("        _obj.set_reactors(_mapped)")
    lines.append("")
    lines.append("def _refresh_entity_map_from_block(_entity_map, _block, _entity_snapshots):")
    lines.append("    for (_entity_text, _ext_snapshot), _entity in zip(_entity_snapshots, _block):")
    lines.append("        _source_handle = ExtendedTags.from_text(_entity_text).get_handle()")
    lines.append("        if _source_handle:")
    lines.append("            _entity_map[_source_handle] = _entity")
    lines.append("")
    lines.append("def _mapped_handle(_source_handle):")
    lines.append("    if _source_handle in _source_entity_map:")
    lines.append("        return _source_entity_map[_source_handle].dxf.handle")
    lines.append("    if _source_handle in _source_object_map:")
    lines.append("        return _source_object_map[_source_handle].dxf.handle")
    lines.append("    return None")
    lines.append("")
    lines.append("def _reorder_dictionary_entries(_dictionary, _ordered_keys):")
    lines.append("    _data = _dictionary._data")
    lines.append("    if not _data:")
    lines.append("        return")
    lines.append("    _reordered = {}")
    lines.append("    for _key in _ordered_keys:")
    lines.append("        if _key in _data:")
    lines.append("            _reordered[_key] = _data[_key]")
    lines.append("    for _key, _value in _data.items():")
    lines.append("        if _key not in _reordered:")
    lines.append("            _reordered[_key] = _value")
    lines.append("    _dictionary._data = _reordered")
    lines.append("")
    lines.append("def _register_field_tree_handles(_objects):")
    lines.append("    _handles = []")
    lines.append("    for _obj in _objects:")
    lines.append("        if _obj.dxftype() == 'FIELD' and _obj.dxf.handle:")
    lines.append("            _handles.append(_obj.dxf.handle)")
    lines.append("    if not _handles:")
    lines.append("        return")
    lines.append("    _field_list = doc.objects.setup_field_list()")
    lines.append("    _existing = list(_field_list.handles)")
    lines.append("    for _handle in _handles:")
    lines.append("        if _handle not in _existing:")
    lines.append("            _existing.append(_handle)")
    lines.append("    _field_list.handles = _existing")
    lines.append("")
    lines.append("def _remap_root_xrecord_tags(_tags):")
    lines.append("    _mapped = []")
    lines.append("    for code, value in _tags:")
    lines.append("        if code == 330 and isinstance(value, str):")
    lines.append("            if value in _source_entity_map:")
    lines.append("                value = _source_entity_map[value].dxf.handle")
    lines.append("            elif value in _source_object_map:")
    lines.append("                value = _source_object_map[value].dxf.handle")
    lines.append("        _mapped.append((code, value))")
    lines.append("    return _mapped")
    lines.append("")
    lines.append("def _remap_fieldlist_handles(_handles, _dangling):")
    lines.append("    _mapped = []")
    lines.append("    for _handle in _handles:")
    lines.append("        if _handle in _source_object_map:")
    lines.append("            _mapped.append(_source_object_map[_handle].dxf.handle)")
    lines.append("        elif _handle in _source_entity_map:")
    lines.append("            _mapped.append(_source_entity_map[_handle].dxf.handle)")
    lines.append("        elif _handle in _dangling:")
    lines.append("            if _handle not in _dangling_handle_map:")
    lines.append("                _new_handle = doc.entitydb.next_handle()")
    lines.append("                while _new_handle in doc.entitydb or _new_handle in _dangling_handle_map.values():")
    lines.append("                    _new_handle = doc.entitydb.next_handle()")
    lines.append("                _dangling_handle_map[_handle] = _new_handle")
    lines.append("            _mapped.append(_dangling_handle_map[_handle])")
    lines.append("        else:")
    lines.append("            _mapped.append(_handle)")
    lines.append("    return _mapped")
    lines.append("")
    lines.append("def _remap_sortents_handles(_handles):")
    lines.append("    _mapped = []")
    lines.append("    for _handle, _sort_handle in _handles:")
    lines.append("        if _handle in _source_entity_map:")
    lines.append("            _handle = _source_entity_map[_handle].dxf.handle")
    lines.append("        if _sort_handle in _source_entity_map:")
    lines.append("            _sort_handle = _source_entity_map[_sort_handle].dxf.handle")
    lines.append("        _mapped.append((_handle, _sort_handle))")
    lines.append("    return _mapped")
    lines.append("")
    lines.append("def _restore_mleader_style(_name, _xdata_tags, _source_reactors):")
    lines.append("    _style = doc.mleader_styles.get(_name)")
    lines.append("    if _style is None:")
    lines.append("        return")
    lines.append("    if _xdata_tags:")
    lines.append("        _style.set_xdata('ACAD_MLEADERVER', _xdata_tags)")
    lines.append("    _reactors = []")
    lines.append("    for _handle in _source_reactors:")
    lines.append("        if _handle == _style.dxf.owner:")
    lines.append("            _reactors.append(_style.dxf.owner)")
    lines.append("        elif _handle in _source_entity_map:")
    lines.append("            _reactors.append(_source_entity_map[_handle].dxf.handle)")
    lines.append("    if _reactors:")
    lines.append("        _style.set_reactors(_reactors)")
    lines.append("")
    lines.append("def _rebuild_entity_xrecord_tree(_host, _dict_key, _dict_order, _root_handle, _root_dxftype, _root_subclasses, _owned_specs, _entity_map):")
    lines.append("    _xdict = _host.get_extension_dict() if _host.has_extension_dict else _host.new_extension_dict()")
    lines.append("    if _dict_key in _xdict.dictionary:")
    lines.append("        _reorder_dictionary_entries(_xdict.dictionary, _dict_order)")
    lines.append("        return")
    lines.append("    _object_map = {}")
    lines.append("    _root = _new_raw_graph_object(_root_dxftype, _xdict.dictionary.dxf.handle)")
    lines.append("    _object_map[_root_handle] = _root")
    lines.append("    _source_object_map[_root_handle] = _root")
    lines.append("    for _spec in _owned_specs:")
    lines.append("        _mapped_owner = _map_raw_graph_value(_spec['owner'], _entity_map, _object_map)")
    lines.append("        _object_map[_spec['handle']] = _new_raw_graph_object(_spec['dxftype'], _mapped_owner)")
    lines.append("        _source_object_map[_spec['handle']] = _object_map[_spec['handle']]")
    lines.append("    _load_raw_graph_object(_root, _xdict.dictionary.dxf.handle, _root_subclasses, [], _entity_map, _object_map)")
    lines.append("    _xdict.dictionary.add(_dict_key, _root)")
    lines.append("    for _spec in _owned_specs:")
    lines.append("        _mapped_owner = _map_raw_graph_value(_spec['owner'], _entity_map, _object_map)")
    lines.append("        _load_raw_graph_object(_object_map[_spec['handle']], _mapped_owner, _spec['subclasses'], [], _entity_map, _object_map)")
    lines.append("    _reorder_dictionary_entries(_xdict.dictionary, _dict_order)")
    lines.append("    _register_field_tree_handles(list(_object_map.values()))")
    lines.append("")
    lines.append("def _swap_raw_graphic_entity(_block, _source_handle, _source_owner, _source_xdict_handle, _source_resource_handles, _raw_tags):")
    lines.append("    _old = _source_entity_map[_source_handle]")
    lines.append("    _xdict_handle = ''")
    lines.append("    if _source_xdict_handle and _old.has_extension_dict:")
    lines.append("        _xdict_handle = _old.get_extension_dict().dictionary.dxf.handle")
    lines.append("    _resource_handle_map = {}")
    lines.append("    for _source_value, _attr_name in _source_resource_handles:")
    lines.append("        _target_value = _old.dxf.get(_attr_name)")
    lines.append("        if _target_value:")
    lines.append("            _resource_handle_map[_source_value] = _target_value")
    lines.append("    _mapped = [dxftag(0, _old.dxftype()), dxftag(5, _old.dxf.handle), dxftag(330, _old.dxf.owner)]")
    lines.append("    for code, value in _raw_tags:")
    lines.append("        if code in (320, 331, 332, 333, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 360, 390, 1005) and isinstance(value, str):")
    lines.append("            if value in _resource_handle_map:")
    lines.append("                value = _resource_handle_map[value]")
    lines.append("            elif value == _source_handle:")
    lines.append("                value = _old.dxf.handle")
    lines.append("            elif value == _source_owner:")
    lines.append("                value = _old.dxf.owner")
    lines.append("            elif _source_xdict_handle and value == _source_xdict_handle and _xdict_handle:")
    lines.append("                value = _xdict_handle")
    lines.append("        if code in (310, 311, 312, 313, 314, 315, 316, 317, 318, 319) and isinstance(value, str):")
    lines.append("            _mapped.append(dxftag(code, bytes.fromhex(value)))")
    lines.append("        elif code in (310, 311, 312, 313, 314, 315, 316, 317, 318, 319) or isinstance(value, (tuple, list)):")
    lines.append("            _mapped.append(dxftag(code, value))")
    lines.append("        else:")
    lines.append("            _mapped.append(DXFTag(code, value))")
    lines.append("    _new = DXFTagStorage.load(ExtendedTags(Tags(_mapped)), doc)")
    lines.append("    _new.doc = doc")
    lines.append("    _new.appdata = _old.appdata")
    lines.append("    _new.reactors = _old.reactors")
    lines.append("    _new.xdata = _old.xdata")
    lines.append("    if _old.has_extension_dict:")
    lines.append("        _new.extension_dict = _old.extension_dict")
    lines.append("    _idx = _block.block_record.entity_space.entities.index(_old)")
    lines.append("    _block.block_record.entity_space.entities[_idx] = _new")
    lines.append("    doc.entitydb._database[_old.dxf.handle] = _new")
    lines.append("    _source_entity_map[_source_handle] = _new")
    lines.append("")

    if resource_code is not None and resource_code.code:
        lines.append("# required table resources")
        lines.extend(resource_code.code)
        for name in sorted(layers_with_xdict):
            lines.append(f'_layer = doc.layers.get({name!r})')
            lines.append('if _layer is not None and not _layer.has_extension_dict: _layer.new_extension_dict()')
        for name, snapshot in layer_extension_snapshots:
            lines.append(f'_layer = doc.layers.get({name!r})')
            lines.append(f'if _layer is not None: restore_raw_extension_subtree(_layer, {snapshot!r})')
        if has_acad_layerstates:
            lines.append('_layers_head = doc.layers.head')
            lines.append('_lx = _layers_head.get_extension_dict() if _layers_head.has_extension_dict else _layers_head.new_extension_dict()')
            lines.append('if "ACAD_LAYERSTATES" not in _lx.dictionary:')
            lines.append('    _lx.dictionary.add_new_dict("ACAD_LAYERSTATES")')
        lines.append("")

    if required_root_dicts or root_xrecords or variable_dict_entries or visualstyle_entries:
        lines.append("# root-owned object resources")
        for key in required_root_dicts:
            lines.append(f'doc.rootdict.get_required_dict({key!r})')
        for key, tags in root_xrecords.items():
            lines.append(f'if {key!r} not in doc.rootdict:')
            lines.append('    _xr = doc.objects.add_xrecord(owner=doc.rootdict.dxf.handle)')
            lines.append(f'    _xr.reset({tags!r})')
            lines.append(f'    doc.rootdict.add({key!r}, _xr)')
        if variable_dict_entries:
            lines.append('_var_dict = doc.rootdict.get_required_dict("AcDbVariableDictionary")')
            for key, value in variable_dict_entries:
                lines.append(f'if {key!r} not in _var_dict:')
                lines.append(f'    _var_dict.add_dict_var({key!r}, {value!r})')
        if visualstyle_entries:
            lines.append('_vs_dict = doc.rootdict.get_required_dict("ACAD_VISUALSTYLE")')
            for key, dxfattribs in visualstyle_entries:
                lines.append(f'if {key!r} not in _vs_dict:')
                lines.append('    _vs_attribs = dict(owner=_vs_dict.dxf.handle)')
                lines.append(f'    _vs_attribs.update({dxfattribs!r})')
                lines.append('    _vs = doc.objects.new_entity("VISUALSTYLE", dxfattribs=_vs_attribs)')
                lines.append(f'    _vs_dict.add({key!r}, _vs)')
            for key, snapshot in visualstyle_extensions:
                lines.append(f'_vs = _vs_dict.get({key!r})')
                lines.append(f'if _vs is not None: restore_raw_extension_subtree(_vs, {snapshot!r})')
        if assoc_network_tags:
            lines.append('_assoc_dict = doc.rootdict.get_required_dict("ACAD_ASSOCNETWORK")')
            lines.append('if "ACAD_ASSOCNETWORK" not in _assoc_dict:')
            lines.append(f'    _add_raw_object(_assoc_dict, "ACAD_ASSOCNETWORK", "ACDBASSOCNETWORK", {assoc_network_tags!r})')
        if detail_view_styles:
            lines.append('_detail_dict = doc.rootdict.get_required_dict("ACAD_DETAILVIEWSTYLE")')
            for key, tags in detail_view_styles:
                lines.append(f'if {key!r} not in _detail_dict:')
                lines.append(f'    _add_raw_object(_detail_dict, {key!r}, "ACDBDETAILVIEWSTYLE", {tags!r})')
            for key, snapshot in detail_view_style_extensions:
                lines.append(f'_detail = _detail_dict.get({key!r})')
                lines.append(f'if _detail is not None: restore_raw_extension_subtree(_detail, {snapshot!r})')
        if section_view_styles:
            lines.append('_section_dict = doc.rootdict.get_required_dict("ACAD_SECTIONVIEWSTYLE")')
            for key, tags in section_view_styles:
                lines.append(f'if {key!r} not in _section_dict:')
                lines.append(f'    _add_raw_object(_section_dict, {key!r}, "ACDBSECTIONVIEWSTYLE", {tags!r})')
            for key, snapshot in section_view_style_extensions:
                lines.append(f'_section = _section_dict.get({key!r})')
                lines.append(f'if _section is not None: restore_raw_extension_subtree(_section, {snapshot!r})')
        if table_style_cellstylemap:
            lines.append('_table_style_dict = doc.rootdict.get("ACAD_TABLESTYLE")')
            lines.append('if _table_style_dict is not None and "Standard" in _table_style_dict:')
            lines.append('    _std = _table_style_dict.get("Standard")')
            lines.append('    _xd = _std.get_extension_dict() if _std.has_extension_dict else _std.new_extension_dict()')
            for key, tags in table_style_cellstylemap:
                lines.append(f'    if {key!r} not in _xd.dictionary:')
                lines.append(f'        _add_raw_object(_xd.dictionary, {key!r}, "CELLSTYLEMAP", {tags!r})')
        lines.append("")

    for block, code in zip(blocks, block_codes):
        lines.append(f"# block: {block.name}")
        lines.extend(code.code)
        if "restore_raw_dynamic_block_layout" in str(code):
            lines.append(
                f"_refresh_entity_map_from_block(_entity_map, b, {snapshot_raw_dynamic_block_layout(block)[1]!r})"
            )
        fallback = raw_graph_fallbacks.get(block.name)
        if fallback is not None:
            lines.append(f"# raw graph fallback for {block.name}")
            lines.append("_xd = _ensure_dynamic_block_extension_dict(b.block_record)")
            lines.append("_delete_graph_stack(b.block_record)")
            lines.append("_graph_map = {}")
            lines.append(f'_graph = _new_raw_graph_object("ACAD_EVALUATION_GRAPH", _xd.dxf.handle)')
            lines.append(f'_graph_map[{fallback["graph_handle"]!r}] = _graph')
            for spec in fallback["owned_specs"]:
                lines.append(f'_graph_map[{spec["handle"]!r}] = _new_raw_graph_object({spec["dxftype"]!r}, _graph.dxf.handle)')
            lines.append(f'_load_raw_graph_object(_graph, _xd.dxf.handle, {fallback["graph_subclasses"]!r}, [], _entity_map, _graph_map)')
            lines.append("_graph.set_reactors([_xd.dxf.handle])")
            lines.append('_xd.add("ACAD_ENHANCEDBLOCK", _graph)')
            if fallback["graph_xdata"]:
                lines.append(f'_graph.set_xdata("AcadBPTGraphNodeId", {fallback["graph_xdata"]!r})')
            if fallback["purge_subclasses"]:
                lines.append('_purge = _new_raw_graph_object("ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION", _xd.dxf.handle)')
                lines.append(f'_load_raw_graph_object(_purge, _xd.dxf.handle, {fallback["purge_subclasses"]!r}, [], _entity_map, _graph_map)')
                lines.append("_purge.set_reactors([_xd.dxf.handle])")
                lines.append('_xd.add("AcDbDynamicBlockRoundTripPurgePreventer", _purge)')
            for spec in fallback["owned_specs"]:
                lines.append(f'_load_raw_graph_object(_graph_map[{spec["handle"]!r}], _graph.dxf.handle, {spec["subclasses"]!r}, {spec["xdata"]!r}, _entity_map, _graph_map)')
            for spec in fallback["owned_specs"]:
                if spec["reactors"]:
                    lines.append(f'_set_raw_graph_reactors(_graph_map[{spec["handle"]!r}], {spec["reactors"]!r}, _entity_map, _graph_map)')
        xrecord_specs = entity_xrecord_fallbacks.get(block.name, [])
        for spec in xrecord_specs:
            lines.append(
                f'_rebuild_entity_xrecord_tree(_entity_map[{spec["entity_handle"]!r}], {spec["dict_key"]!r}, {spec["dict_order"]!r}, {spec["root_handle"]!r}, {spec["root_dxftype"]!r}, {spec["root_subclasses"]!r}, {spec["owned_specs"]!r}, _entity_map)'
            )
        lines.append("_source_entity_map.update(_entity_map)")
        raw_specs = raw_entity_swap_fallbacks.get(block.name, [])
        for spec in raw_specs:
            raw_entity_swap_calls.append(
                f'_swap_raw_graphic_entity(doc.blocks.get({block.name!r}), {spec["source_handle"]!r}, {spec["source_owner"]!r}, {spec["source_xdict_handle"]!r}, {spec["source_resource_handles"]!r}, {spec["raw_tags"]!r})'
            )
        lines.append("")

    if sortents_by_block:
        for block_name, tags in sortents_by_block:
            sortents_calls.append(f'_sort_block = doc.blocks.get({block_name!r})')
            sortents_calls.append('if _sort_block is not None:')
            sortents_calls.append('    _xd = _sort_block.block_record.get_extension_dict() if _sort_block.block_record.has_extension_dict else _sort_block.block_record.new_extension_dict()')
            sortents_calls.append('    if "ACAD_SORTENTS" not in _xd.dictionary:')
            sortents_calls.append('        _sort = doc.objects.new_entity("SORTENTSTABLE", dxfattribs={"owner": _xd.dictionary.dxf.handle, "block_record_handle": _sort_block.block_record.dxf.handle})')
            sortents_calls.append(f'        _sort.set_handles(_remap_sortents_handles({tags!r}))')
            sortents_calls.append('        _xd.dictionary.add("ACAD_SORTENTS", _sort)')

    if block_xdict_orders:
        lines.append("# block extension dictionary order")
        for block_name, ordered_keys in block_xdict_orders.items():
            lines.append(f'_block = doc.blocks.get({block_name!r})')
            lines.append('if _block is not None and _block.block_record.has_extension_dict:')
            lines.append(f'    _reorder_dictionary_entries(_block.block_record.get_extension_dict().dictionary, {ordered_keys!r})')
        lines.append("")

    lines.append("# modelspace entities")
    lines.extend(msp_code.code)
    lines.append("_source_entity_map.update(_entity_map)")
    lines.append("")
    if source_fieldlist_handles:
        lines.append("# restore FIELDLIST")
        lines.append("_field_list = doc.objects.setup_field_list()")
        lines.append(f"_field_list.handles = _remap_fieldlist_handles({source_fieldlist_handles!r}, {set(source_fieldlist_dangling)!r})")
        lines.append("_field_list.set_reactors([doc.rootdict.dxf.handle])")
        lines.append("")
    if sortents_calls:
        lines.append("# block sort order")
        lines.extend(sortents_calls)
        lines.append("")
    if mleader_style_specs:
        lines.append("# restore MLEADERSTYLE metadata")
        for spec in mleader_style_specs:
            lines.append(
                f"_restore_mleader_style({spec['name']!r}, {spec['xdata_tags']!r}, {spec['reactors']!r})"
            )
        for key, snapshot in mleader_style_extension_snapshots:
            lines.append(f'_mlstyle = doc.mleader_styles.get({key!r})')
            lines.append(f'if _mlstyle is not None: restore_raw_extension_subtree(_mlstyle, {snapshot!r})')
        lines.append("")
    if deferred_recompose_tags:
        lines.append("# deferred ACDB_RECOMPOSE_DATA")
        lines.append("if 'ACDB_RECOMPOSE_DATA' not in doc.rootdict:")
        lines.append("    _xr = doc.objects.add_xrecord(owner=doc.rootdict.dxf.handle)")
        lines.append("    _xr.set_reactors([doc.rootdict.dxf.handle])")
        lines.append(f"    _xr.reset(_remap_root_xrecord_tags({deferred_recompose_tags!r}))")
        lines.append("    doc.rootdict.add('ACDB_RECOMPOSE_DATA', _xr)")
        lines.append("")
    if raw_entity_swap_calls:
        lines.append("# raw entity swaps")
        lines.extend(raw_entity_swap_calls)
        lines.append("")
    lines.append("# restore header state and classes")
    lines.append(f"doc.encoding = {doc.encoding!r}")
    lines.append(f"_header_state = {header_state!r}")
    lines.append("for _name, _value in _header_state.items():")
    lines.append("    doc.header[_name] = _value")
    lines.append("doc.header.custom_vars.clear()")
    for tag, value in header_custom_vars:
        lines.append(f"doc.header.custom_vars.append({tag!r}, {value!r})")
    if material_name is not None:
        lines.append(f'_mat = doc.materials.get({material_name!r})')
        lines.append('if _mat is not None:')
        lines.append('    doc.header["$CMATERIAL"] = _mat.dxf.handle')
    for var_name, source_handle in interfere_handles:
        lines.append(f'_mapped = _mapped_handle({source_handle!r})')
        lines.append(f'if _mapped is not None: doc.header[{var_name!r}] = _mapped')
    if raw_header_overrides:
        lines.append(f"restore_raw_header_vars(doc.header, {raw_header_overrides!r})")
    lines.append(f"restore_raw_classes(doc.classes, {raw_classes!r})")
    lines.append("")
    lines.append("doc.saveas(OUT)")
    lines.append("print(OUT)")

    script_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: generate_dxf2code_replay.py <source.dxf> <script.py> <output.dxf>"
        )

    write_document_code(sys.argv[1], sys.argv[2], sys.argv[3])
    print(Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
