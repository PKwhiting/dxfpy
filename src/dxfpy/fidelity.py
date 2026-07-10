"""Source-specific low-level document restoration helpers.

This module restores authored DXF document state for replay and code-generation
workflows. It is not generic document setup and is intentionally kept separate
from ``Drawing.new()`` and generic save/export paths.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dxfpy.dynblkhelper import (
    ensure_insert_seqends,
    register_source_entity_handle_mapping,
    remap_header_resource_handles,
    remove_stale_hatch_associations,
    replace_dynamic_block_acad_tables_with_blockrefs,
    reorder_objects_by_source_order,
    sync_handseed,
    sync_layer_annotation_scale_xrecords,
    restore_raw_block_entity_exports,
    restore_dictionary_key_order,
    restore_raw_entity_export,
    restore_raw_extension_subtree,
    restore_raw_rootdict_entries,
    snapshot_dictionary_key_order,
    snapshot_raw_dynamic_block_definition,
    snapshot_object_handle_order,
    snapshot_raw_entity_export,
    snapshot_raw_extension_subtree,
    snapshot_raw_rootdict_entries,
    sync_raw_acad_table_geometry_btrs,
)
from dxfpy.lldxf.extendedtags import ExtendedTags
from dxfpy.lldxf.types import is_pointer_code
from dxfpy.sections.classes import restore_raw_classes, snapshot_raw_classes
from dxfpy.sections.header import restore_raw_header_vars, snapshot_raw_header_vars

if TYPE_CHECKING:
    from dxfpy.document import Drawing


_HEADER_STATE_SKIP = frozenset(
    {
        "$HANDSEED",
        "$VERSIONGUID",
        "$FINGERPRINTGUID",
        "$TDCREATE",
        "$TDUPDATE",
    }
)
_HEADER_RAW_OVERRIDE_KEYS = (
    "$TDCREATE",
    "$TDUPDATE",
    "$PEXTMIN",
    "$PEXTMAX",
    "$FINGERPRINTGUID",
    "$VERSIONGUID",
)


def prepare_document_fidelity(source_doc: Drawing, target_doc: Drawing) -> None:
    restore_raw_rootdict_entries(
        target_doc,
        snapshot_raw_rootdict_entries(source_doc, tuple(source_doc.rootdict.keys())),
    )
    target_doc.layouts.setup_from_rootdict()
    restore_dictionary_key_order(
        target_doc.rootdict, snapshot_dictionary_key_order(source_doc.rootdict)
    )
    _register_named_table_entry_handle_mappings(source_doc.layers, target_doc.layers)
    _restore_named_table_entry_extension_subtrees(source_doc.layers, target_doc.layers)
    _register_named_object_collection_handle_mappings(
        source_doc.mleader_styles, target_doc.mleader_styles
    )
    _restore_named_object_collection_extension_subtrees(
        source_doc.mleader_styles, target_doc.mleader_styles
    )
    _register_named_object_collection_handle_mappings(
        source_doc.table_styles, target_doc.table_styles
    )
    _restore_named_object_collection_extension_subtrees(
        source_doc.table_styles, target_doc.table_styles
    )
    if source_doc.layers.head.has_extension_dict:
        restore_raw_extension_subtree(
            target_doc.layers.head, snapshot_raw_extension_subtree(source_doc.layers.head)
        )


def finalize_document_fidelity(source_doc: Drawing, target_doc: Drawing) -> None:
    _register_block_handle_mappings(source_doc, target_doc)
    _register_layout_handle_mappings(source_doc, target_doc)
    _restore_late_block_entity_exports(source_doc, target_doc)
    _restore_late_rootdict_entity_exports(source_doc, target_doc)
    _restore_named_object_collection_raw_exports(
        source_doc.mleader_styles, target_doc.mleader_styles, source_doc, target_doc
    )
    for source_dimstyle, target_dimstyle in _iter_named_table_entry_pairs(
        source_doc.dimstyles, target_doc.dimstyles
    ):
        _restore_raw_export_with_resource_mapping(
            source_dimstyle,
            target_dimstyle,
            source_doc,
            target_doc,
        )
    _copy_header_state(source_doc, target_doc)
    remap_header_resource_handles(source_doc, target_doc)
    if source_doc.filename:
        restore_raw_header_vars(
            target_doc.header,
            snapshot_raw_header_vars(source_doc.filename, _HEADER_RAW_OVERRIDE_KEYS),
        )
    restore_raw_classes(target_doc.classes, snapshot_raw_classes(source_doc.classes))
    sync_raw_acad_table_geometry_btrs(target_doc)
    sync_layer_annotation_scale_xrecords(target_doc)
    remove_stale_hatch_associations(target_doc)
    replace_dynamic_block_acad_tables_with_blockrefs(target_doc)
    reorder_objects_by_source_order(target_doc, snapshot_object_handle_order(source_doc))
    ensure_insert_seqends(target_doc)
    sync_handseed(target_doc)


def _copy_header_state(source_doc: Drawing, target_doc: Drawing) -> None:
    target_doc.encoding = source_doc.encoding
    for name in source_doc.header.varnames():
        if name in _HEADER_STATE_SKIP:
            continue
        target_doc.header[name] = source_doc.header.get(name)
    target_doc.header.custom_vars.clear()
    for tag, value in source_doc.header.custom_vars:
        target_doc.header.custom_vars.append(tag, value)


def _names(table) -> set[str]:
    return {entry.dxf.name for entry in table}


def _maybe_get(table, name: str):
    try:
        return table.get(name)
    except Exception:
        return None


def _object_dict_names(collection) -> tuple[str, ...]:
    return tuple(str(name) for name in collection.object_dict.keys())


def _iter_named_table_entry_pairs(source_table, target_table):
    for name in _names(source_table):
        source_entity = _maybe_get(source_table, name)
        target_entity = _maybe_get(target_table, name)
        if source_entity is not None and target_entity is not None:
            yield source_entity, target_entity


def _iter_named_object_collection_pairs(source_collection, target_collection):
    for name in _object_dict_names(source_collection):
        source_entity = source_collection.get(name)
        target_entity = target_collection.get(name)
        if source_entity is not None and target_entity is not None:
            yield source_entity, target_entity


def _restore_extension_subtree_if_present(source_entity, target_entity) -> None:
    if source_entity.has_extension_dict:
        restore_raw_extension_subtree(
            target_entity, snapshot_raw_extension_subtree(source_entity)
        )


def _restore_raw_export_with_resource_mapping(
    source_entity,
    target_entity,
    source_doc: Drawing,
    target_doc: Drawing,
) -> None:
    snapshot = snapshot_raw_entity_export(source_entity)
    restore_raw_entity_export(
        target_entity,
        snapshot,
        _resource_handle_mapping_for_raw_text(
            source_doc, target_doc, snapshot.text
        ),
    )


def _register_named_table_entry_handle_mappings(source_table, target_table) -> None:
    for source_entity, target_entity in _iter_named_table_entry_pairs(
        source_table, target_table
    ):
        register_source_entity_handle_mapping(source_entity, target_entity)


def _restore_named_table_entry_extension_subtrees(source_table, target_table) -> None:
    for source_entity, target_entity in _iter_named_table_entry_pairs(
        source_table, target_table
    ):
        _restore_extension_subtree_if_present(source_entity, target_entity)


def _register_named_object_collection_handle_mappings(
    source_collection, target_collection
) -> None:
    for source_entity, target_entity in _iter_named_object_collection_pairs(
        source_collection, target_collection
    ):
        register_source_entity_handle_mapping(source_entity, target_entity)


def _restore_named_object_collection_extension_subtrees(
    source_collection, target_collection
) -> None:
    for source_entity, target_entity in _iter_named_object_collection_pairs(
        source_collection, target_collection
    ):
        _restore_extension_subtree_if_present(source_entity, target_entity)


def _resource_handle_mapping_for_raw_text(
    source_doc: Drawing,
    target_doc: Drawing,
    text: str,
) -> list[tuple[str, str]]:
    mapping: list[tuple[str, str]] = []
    seen: set[str] = set()
    global_mapping = getattr(target_doc, "_raw_object_handle_mapping", {})
    for tag in ExtendedTags.from_text(text):
        if tag.code == 5 or tag.code == 1005 or is_pointer_code(tag.code):
            handle = str(tag.value)
            if handle in seen:
                continue
            seen.add(handle)
            target_handle = global_mapping.get(handle)
            if target_handle is not None and target_doc.entitydb.get(target_handle) is not None:
                mapping.append((handle, target_handle))
                continue
            source_entity = source_doc.entitydb.get(handle)
            if source_entity is None:
                continue
            target_handle = None
            dxftype = source_entity.dxftype()
            if dxftype == "STYLE":
                target = target_doc.styles.get(source_entity.dxf.name)
                target_handle = target.dxf.handle if target is not None else None
            elif dxftype == "LTYPE":
                target = target_doc.linetypes.get(source_entity.dxf.name)
                target_handle = target.dxf.handle if target is not None else None
            elif dxftype == "LAYER":
                target = target_doc.layers.get(source_entity.dxf.name)
                target_handle = target.dxf.handle if target is not None else None
            elif dxftype == "APPID":
                target = target_doc.appids.get(source_entity.dxf.name)
                target_handle = target.dxf.handle if target is not None else None
            elif dxftype == "BLOCK_RECORD":
                block = target_doc.blocks.get(source_entity.dxf.name)
                target_handle = block.block_record_handle if block is not None else None
            if target_handle is not None:
                mapping.append((handle, target_handle))
    return mapping


def _register_block_handle_mappings(source_doc: Drawing, target_doc: Drawing) -> None:
    for source_block in source_doc.blocks:
        if source_block.is_any_layout:
            continue
        target_block = target_doc.blocks.get(source_block.name)
        if target_block is None:
            continue
        register_source_entity_handle_mapping(source_block.block_record, target_block.block_record)
        if source_block.block is not None and target_block.block is not None:
            register_source_entity_handle_mapping(source_block.block, target_block.block)
        if source_block.endblk is not None and target_block.endblk is not None:
            register_source_entity_handle_mapping(source_block.endblk, target_block.endblk)
        for source_entity, target_entity in zip(source_block, target_block):
            _register_entity_with_subentities(source_entity, target_entity)


def _register_layout_handle_mappings(source_doc: Drawing, target_doc: Drawing) -> None:
    for layout_name in source_doc.layouts.names():
        source_layout = source_doc.layouts.get(layout_name)
        target_layout = target_doc.layouts.get(layout_name)
        for source_entity, target_entity in zip(source_layout, target_layout):
            _register_entity_with_subentities(source_entity, target_entity)


def _register_entity_with_subentities(source_entity, target_entity) -> None:
    register_source_entity_handle_mapping(source_entity, target_entity)
    source_attribs = tuple(getattr(source_entity, "attribs", ()))
    target_attribs = tuple(getattr(target_entity, "attribs", ()))
    for source_attrib, target_attrib in zip(source_attribs, target_attribs):
        register_source_entity_handle_mapping(source_attrib, target_attrib)


def _restore_late_block_entity_exports(source_doc: Drawing, target_doc: Drawing) -> None:
    for source_block in source_doc.blocks:
        if source_block.is_any_layout:
            continue
        target_block = target_doc.blocks.get(source_block.name)
        if target_block is None or len(source_block) != len(target_block):
            continue
        snapshot = snapshot_raw_dynamic_block_definition(source_block)
        entity_handle_map = {
            str(source_entity.dxf.handle): str(target_entity.dxf.handle)
            for source_entity, target_entity in zip(source_block, target_block)
            if source_entity.dxf.handle and target_entity.dxf.handle
        }
        restore_raw_block_entity_exports(
            target_block, snapshot.entity_snapshots, entity_handle_map
        )


def _restore_named_object_collection_raw_exports(
    source_collection, target_collection, source_doc: Drawing, target_doc: Drawing
) -> None:
    for source_entity, target_entity in _iter_named_object_collection_pairs(
        source_collection, target_collection
    ):
        _restore_raw_export_with_resource_mapping(
            source_entity,
            target_entity,
            source_doc,
            target_doc,
        )


def _restore_late_rootdict_entity_exports(
    source_doc: Drawing, target_doc: Drawing
) -> None:
    for key in tuple(source_doc.rootdict.keys()):
        source_entity = source_doc.rootdict.get(key)
        target_entity = target_doc.rootdict.get(key)
        if (
            source_entity is None
            or target_entity is None
            or source_entity.dxftype() == "DICTIONARY"
        ):
            continue
        _restore_raw_export_with_resource_mapping(
            source_entity,
            target_entity,
            source_doc,
            target_doc,
        )
