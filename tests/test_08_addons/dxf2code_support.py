from __future__ import annotations

from io import StringIO

import ezdxf
from ezdxf.addons.dxf2code import block_to_code, entities_to_code, table_entries_to_code
from ezdxf._fidelity_compare import (
    ReplayComparison,
    compare_replay_documents,
    format_replay_comparison,
)
from ezdxf.dynblkhelper import (
    get_dynamic_block_record_handle,
    register_source_entity_handle_mapping,
)
from ezdxf.fidelity import finalize_document_fidelity, prepare_document_fidelity
from ezdxf.lldxf.tagwriter import TagWriter
from ezdxf.lldxf.types import is_pointer_code
from ezdxf.math import Vec3


def execute_code_in_namespace(code, namespace):
    exec(code.import_str() + "\n" + str(code), namespace)


def execute_entities_code_in_doc(entities, target_doc):
    target_msp = target_doc.modelspace()
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_msp}
    code = entities_to_code(entities, layout="msp")
    execute_code_in_namespace(code, namespace)
    return target_doc, target_msp


def translate_entities_to_new_layout(entities):
    target_doc = ezdxf.new("R2010")
    return execute_entities_code_in_doc(entities, target_doc)


def normalize_handle_refs_in_text(text: str) -> str:
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


def export_text(entity, dxfversion: str) -> str:
    stream = StringIO()
    entity.export_dxf(TagWriter(stream, dxfversion=dxfversion))
    return stream.getvalue()


def cmp_vertices(a, b):
    return all(Vec3(v0).isclose(v1) for v0, v1 in zip(a, b))


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


def block_dependencies(blocks) -> dict[str, set[str]]:
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
            if entity.dxftype() == "INSERT":
                name = entity.dxf.name
            elif entity.dxftype() == "ACAD_TABLE":
                # Match production ordering: table geometry blocks feed raw BTR refs.
                name = entity.dxf.get("geometry", "")
            else:
                continue
            if name in block_by_name and name != block.name:
                deps.add(name)
    return dependencies


def sort_blocks(blocks):
    dependencies = block_dependencies(blocks)
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
    blocks = sort_blocks([block for block in source_doc.blocks if not block.is_any_layout])
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


def assert_clean_replay(
    source_doc: ezdxf.document.Drawing,
    replay_doc: ezdxf.document.Drawing,
    *,
    include_layout_order: bool = False,
) -> ReplayComparison:
    comparison = compare_replay_documents(source_doc, replay_doc)
    assert not comparison.has_issues(
        include_layout_order=include_layout_order
    ), format_replay_comparison(comparison)
    return comparison
