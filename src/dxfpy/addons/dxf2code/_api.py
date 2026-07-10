from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional

from ._code import Code
from ._format import _fmt_mapping, _purge_handles
from ._generator import _SourceCodeGenerator

if TYPE_CHECKING:
    from dxfpy.entities import DXFEntity
    from dxfpy.layouts import BlockLayout


def entities_to_code(
    entities: Iterable[DXFEntity],
    layout: str = "layout",
    ignore: Optional[Iterable[str]] = None,
    runtime_var: str | None = None,
) -> Code:
    code = _SourceCodeGenerator(layout=layout, runtime_var=runtime_var)
    code.translate_entities(entities, ignore=ignore)
    return code.code


def block_to_code(
    block: BlockLayout,
    drawing: str = "doc",
    ignore: Optional[Iterable[str]] = None,
    full_document_mode: bool = False,
) -> Code:
    assert block.block is not None
    dxfattribs = _purge_handles(block.block.dxfattribs())
    block_name = dxfattribs.pop("name")
    base_point = dxfattribs.pop("base_point")
    code = _SourceCodeGenerator(layout="b", full_document_mode=full_document_mode)
    prolog = (
        f'b = {drawing}.blocks.new("{block_name}", base_point={base_point}, '
        "dxfattribs={"
    )
    code.add_source_code_line(prolog)
    code.add_source_code_lines(_fmt_mapping(dxfattribs, indent=4))
    code.add_source_code_line("    }")
    code.add_source_code_line(")")
    if block.block_record.dxf.hasattr("units"):
        code.add_source_code_line(
            f"b.block_record.dxf.units = {block.block_record.dxf.units}"
        )
    if block.block_record.dxf.hasattr("explode"):
        code.add_source_code_line(
            f"b.block_record.dxf.explode = {block.block_record.dxf.explode}"
        )
    if block.block_record.dxf.hasattr("scale"):
        code.add_source_code_line(
            f"b.block_record.dxf.scale = {block.block_record.dxf.scale}"
        )
    if block.block_record.preview_data:
        code.add_source_code_line(
            f"b.block_record.preview_data = {block.block_record.preview_data!r}"
        )
    if not code._needs_raw_dynamic_block_layout_fallback(block):
        code.translate_entities(block, ignore=ignore)
    code._register_block_handle(block)
    code._emit_dynamic_block_metadata(block)
    if code._post_block_deferred_code:
        code.add_source_code_line("# post block raw restores")
        code.add_source_code_lines(code._post_block_deferred_code)
    return code.code


def table_entries_to_code(entities: Iterable[DXFEntity], drawing="doc") -> Code:
    code = _SourceCodeGenerator(doc=drawing)
    code.translate_entities(entities)
    return code.code


def document_to_code_file(source: str, script_path: str, output_path: str) -> None:
    from ._document import write_document_code

    write_document_code(source, script_path, output_path)
