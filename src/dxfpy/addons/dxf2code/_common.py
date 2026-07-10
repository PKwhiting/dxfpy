from __future__ import annotations

from dxfpy.dynblkhelper import get_dynamic_block_record_handle


def _names(table) -> set[str]:
    return {entry.dxf.name for entry in table}


def _maybe_get(table, name: str):
    try:
        return table.get(name)
    except Exception:
        return None


def _block_dependencies(blocks) -> dict[str, set[str]]:
    block_by_name = {block.name: block for block in blocks}
    dependencies: dict[str, set[str]] = {block.name: set() for block in blocks}
    for block in blocks:
        deps = dependencies[block.name]
        for entity in block:
            if entity.dxftype() == "INSERT":
                name = entity.dxf.name
            elif entity.dxftype() == "ACAD_TABLE":
                # Table geometry blocks must exist before raw table refs are restored.
                name = entity.dxf.get("geometry", "")
            else:
                continue
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
