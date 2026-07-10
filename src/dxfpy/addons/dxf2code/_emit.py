from __future__ import annotations

from pathlib import Path

from ._code import Code
from ._specs import (
    AcadTableFieldHandleSpec,
    AcadTableRawFallbackSpec,
    DocumentCodegenCapture,
    EntityXRecordFallbackSpec,
    GroupSpec,
    OwnedObjectSpec,
    OwnedObjectSpecData,
    RawEntitySwapFallbackSpec,
)


def _owned_object_specs_literal(specs: list[OwnedObjectSpec]) -> list[OwnedObjectSpecData]:
    return [
        {
            "handle": spec.handle,
            "owner": spec.owner,
            "dxftype": spec.dxftype,
            "subclasses": spec.subclasses,
        }
        for spec in specs
    ]


def _resource_handle_refs_literal(spec: RawEntitySwapFallbackSpec) -> list[tuple[str, str]]:
    """Return generated-code literals for raw entity resource handle refs."""
    return [
        (ref.source_handle, ref.attrib_name)
        for ref in spec.source_resource_handles
    ]


def _raw_entity_swap_call(layout_expr: str, spec: RawEntitySwapFallbackSpec) -> str:
    """Return a generated raw-entity swap call."""
    return (
        f"rt.swap_raw_graphic_entity({layout_expr}, {spec.source_handle!r}, "
        f"{spec.source_owner!r}, {spec.source_xdict_handle!r}, "
        f"{_resource_handle_refs_literal(spec)!r}, {spec.raw_tags!r}, "
        f"{spec.xdata!r})"
    )


def _acad_table_fallback_layout_expr(spec: AcadTableRawFallbackSpec) -> str:
    """Return a generated layout expression for an ACAD_TABLE fallback."""
    if spec.layout_kind == "modelspace":
        return "msp"
    if spec.layout_kind == "paperspace":
        return f"doc.layout({spec.layout_name!r})"
    return f"doc.blocks.get({spec.layout_name!r})"


def _replace_xrecord_tree_call(spec: EntityXRecordFallbackSpec) -> str:
    """Return a generated XRECORD tree replacement call."""
    owned_specs = _owned_object_specs_literal(spec.owned_specs)
    return (
        f"rt.replace_entity_xrecord_tree(_table, {spec.dict_key!r}, "
        f"{spec.dict_order!r}, {spec.root_handle!r}, {spec.root_dxftype!r}, "
        f"{spec.root_subclasses!r}, {owned_specs!r}, rt.source_entity_map)"
    )


def _emit_paper_layouts(
    lines: list[str],
    *,
    layout_dictionary_order: list[str],
    paper_layout_names: list[str],
    active_paper_layout_name: str,
    paper_layout_dxfattribs: dict[str, dict[str, object]],
    paper_layout_block_record_names: dict[str, str],
    paper_layout_codes: list[tuple[str, Code]],
) -> None:
    if not paper_layout_names:
        return

    lines.append("# paperspace layouts")
    lines.append(f"_paper_layout_names = {paper_layout_names!r}")
    lines.append(f"_paper_layout_dxfattribs = {paper_layout_dxfattribs!r}")
    lines.append(
        f"_paper_layout_block_record_names = {paper_layout_block_record_names!r}"
    )
    lines.append("# viewport_handle is remapped after each layout VIEWPORT is recreated")
    lines.append("for _layout_name in _paper_layout_names:")
    lines.append(
        "    _layout_create_attribs = dict("
        "_paper_layout_dxfattribs.get(_layout_name, {}))"
    )
    lines.append('    _layout_create_attribs.pop("viewport_handle", None)')
    lines.append("    if _layout_name not in doc.layouts:")
    lines.append("        doc.new_layout(_layout_name, dxfattribs=_layout_create_attribs)")
    lines.append("for _layout_name in list(doc.layouts.names()):")
    lines.append(
        "    if _layout_name not in ('Model', 'Model_Space') "
        "and _layout_name not in _paper_layout_names: "
        "doc.delete_layout(_layout_name)"
    )
    lines.append("_layout_block_renames = []")
    lines.append(
        "for _layout_name, _target_block_name in "
        "_paper_layout_block_record_names.items():"
    )
    lines.append("    if _layout_name not in doc.layouts or not _target_block_name:")
    lines.append("        continue")
    lines.append("    _layout = doc.layout(_layout_name)")
    lines.append("    _current_block_name = _layout.block_record.dxf.name")
    lines.append("    if _current_block_name == _target_block_name:")
    lines.append("        continue")
    lines.append(
        "    _tmp_block_name = "
        "f'*DXF2CODE_LAYOUT_TMP_{len(_layout_block_renames)}'"
    )
    lines.append("    while _tmp_block_name in doc.blocks:")
    lines.append("        _tmp_block_name += '_'")
    lines.append("    doc.blocks.rename_block(_current_block_name, _tmp_block_name)")
    lines.append(
        "    _layout_block_renames.append("
        "(_tmp_block_name, _target_block_name))"
    )
    lines.append("for _tmp_block_name, _target_block_name in _layout_block_renames:")
    lines.append("    if _target_block_name not in doc.blocks:")
    lines.append("        doc.blocks.rename_block(_tmp_block_name, _target_block_name)")
    if active_paper_layout_name:
        lines.append(
            f"if {active_paper_layout_name!r} in doc.layouts: "
            f"doc.layouts.set_active_layout({active_paper_layout_name!r})"
        )
    for layout_name in paper_layout_names:
        lines.append(
            f"_layout_dxfattribs = _paper_layout_dxfattribs.get({layout_name!r}, {{}})"
        )
        lines.append(
            '_layout_viewport_handle = _layout_dxfattribs.get("viewport_handle", "")'
        )
        lines.append(
            "_layout_update_attribs = {k: v for k, v in "
            "_layout_dxfattribs.items() if k != 'viewport_handle'}"
        )
        lines.append(f"psp = doc.layout({layout_name!r})")
        lines.append("psp.dxf.update(_layout_update_attribs, ignore_errors=True)")
        lines.append("psp.delete_all_entities()")
        for name, code in paper_layout_codes:
            if name != layout_name:
                continue
            lines.extend(code.code)
            lines.append("rt.register_entity_map(_entity_map)")
        lines.append("_layout_viewport = _entity_map.get(_layout_viewport_handle)")
        lines.append("if _layout_viewport is None:")
        lines.append("    # Minimal or repaired layouts may only expose the recreated VIEWPORT")
        lines.append(
            '    _layout_viewport = next((e for e in psp if e.dxftype() == "VIEWPORT"), None)'
        )
        lines.append(
            'if _layout_viewport is not None and _layout_viewport.dxftype() == "VIEWPORT":'
        )
        lines.append("    psp.dxf.viewport_handle = _layout_viewport.dxf.handle")
        lines.append("")
    lines.append("# restore source ACAD_LAYOUT dictionary order")
    lines.append(f"rt.restore_layout_order({layout_dictionary_order!r})")
    lines.append("")


def _emit_acad_table_geometry_blocks(
    lines: list[str],
    acad_table_geometry_block_codes: list[tuple[str, Code]],
    acad_table_field_handle_specs: list[AcadTableFieldHandleSpec],
) -> None:
    if not acad_table_geometry_block_codes:
        return

    lines.append("# restore ACAD_TABLE geometry block contents")
    for block_name, code in acad_table_geometry_block_codes:
        lines.append(f"_table_block = doc.blocks.get({block_name!r})")
        lines.append("if _table_block is not None:")
        lines.append(f"    rt.prepare_acad_table_geometry_restore({block_name!r})")
        lines.append("    _table_block.delete_all_entities()")
        lines.extend(f"    {line}" for line in code.code)
        lines.append("    rt.register_entity_map(_entity_map)")
    lines.append("")
    if acad_table_field_handle_specs:
        lines.append("# restore ACAD_TABLE shell FIELD handles")
        for spec in acad_table_field_handle_specs:
            lines.append(
                f"rt.restore_acad_table_field_handles({spec.table_handle!r}, "
                f"{spec.cell_fields!r})"
            )
        lines.append("")


def _emit_acad_table_raw_fallbacks(
    lines: list[str], specs: list[AcadTableRawFallbackSpec]
) -> None:
    """Emit raw fallback restore calls for complex ACAD_TABLE entities."""
    if not specs:
        return
    lines.append("# restore complex ACAD_TABLE raw fallback")
    for spec in specs:
        if spec.xrecord is not None:
            lines.append(f"_table = rt.source_entity_map.get({spec.table_handle!r})")
            lines.append("if _table is not None:")
            lines.append(f"    {_replace_xrecord_tree_call(spec.xrecord)}")
        layout_expr = _acad_table_fallback_layout_expr(spec)
        lines.append(_raw_entity_swap_call(layout_expr, spec.raw_swap))
    lines.append("")


def _emit_groups(lines: list[str], group_specs: list[GroupSpec]) -> None:
    if not group_specs:
        return

    group_data = [
        (
            spec.name,
            spec.handles,
            spec.description,
            spec.selectable,
            spec.unnamed,
        )
        for spec in group_specs
    ]
    lines.append("# restore GROUPS")
    lines.append(f"_group_specs = {group_data!r}")
    lines.append(
        "for _group_name, _group_handles, _group_description, _group_selectable, _group_unnamed in _group_specs:"
    )
    lines.append(
        "    _group_entities = [rt.source_entity_map[_handle] "
        "for _handle in _group_handles if _handle in rt.source_entity_map]"
    )
    lines.append("    if not _group_entities: continue")
    lines.append("    if _group_name in doc.groups: doc.groups.delete(_group_name)")
    lines.append(
        "    _group = doc.groups.new(_group_name, description=_group_description, selectable=_group_selectable)"
    )
    lines.append("    _group.dxf.unnamed = _group_unnamed")
    lines.append("    _group.set_data(_group_entities)")
    lines.append("")


def _emit_final_cleanup(
    lines: list[str],
    *,
    doc,
    header_state,
    header_custom_vars,
    material_name,
    interfere_handles,
    raw_header_overrides,
    raw_classes,
) -> None:
    lines.append("# restore header state and classes")
    lines.append(f"doc.encoding = {doc.encoding!r}")
    lines.append(f"_header_state = {header_state!r}")
    lines.append("for _name, _value in _header_state.items():")
    lines.append("    doc.header[_name] = _value")
    lines.append("doc.header.custom_vars.clear()")
    for tag, value in header_custom_vars:
        lines.append(f"doc.header.custom_vars.append({tag!r}, {value!r})")
    if material_name is not None:
        lines.append(f"_mat = doc.materials.get({material_name!r})")
        lines.append("if _mat is not None:")
        lines.append('    doc.header["$CMATERIAL"] = _mat.dxf.handle')
    for ref in interfere_handles:
        lines.append(f"_mapped = rt.mapped_handle({ref.handle!r})")
        lines.append(f"if _mapped is not None: doc.header[{ref.name!r}] = _mapped")
    if raw_header_overrides:
        lines.append(f"restore_raw_header_vars(doc.header, {raw_header_overrides!r})")
    lines.append(f"restore_raw_classes(doc.classes, {raw_classes!r})")
    lines.append("sync_raw_acad_table_geometry_btrs(doc)")
    lines.append("sync_layer_annotation_scale_xrecords(doc)")
    lines.append("sync_extension_dict_owners(doc)")
    lines.append("normalize_unresolved_xdata_handles(doc)")
    lines.append("remove_stale_hatch_associations(doc)")
    lines.append("replace_dynamic_block_acad_tables_with_blockrefs(doc)")
    lines.append("ensure_insert_seqends(doc)")
    lines.append("sync_handseed(doc)")


def render_document_codegen_script(data: DocumentCodegenCapture, out_path: Path) -> str:
    doc = data["doc"]
    blocks = data["blocks"]
    block_codes = data["block_codes"]
    block_layout_entity_snapshots = data["block_layout_entity_snapshots"]
    layout_dictionary_order = data["layout_dictionary_order"]
    paper_layout_names = data["paper_layout_names"]
    active_paper_layout_name = data["active_paper_layout_name"]
    paper_layout_dxfattribs = data["paper_layout_dxfattribs"]
    paper_layout_block_record_names = data["paper_layout_block_record_names"]
    paper_layout_codes = data["paper_layout_codes"]
    acad_table_geometry_block_codes = data["acad_table_geometry_block_codes"]
    acad_table_field_handle_specs = data["acad_table_field_handle_specs"]
    msp_code = data["msp_code"]
    imports = data["imports"]
    resource_code = data["resource_code"]
    layers_with_xdict = data["layers_with_xdict"]
    root_xrecords = data["root_xrecords"]
    deferred_recompose_tags = data["deferred_recompose_tags"]
    deferred_recompose_source_handle = data["deferred_recompose_source_handle"]
    deferred_recompose_table_styles = data["deferred_recompose_table_styles"]
    source_fieldlist_handles = data["source_fieldlist_handles"]
    source_fieldlist_dangling = data["source_fieldlist_dangling"]
    variable_dict_entries = data["variable_dict_entries"]
    visualstyle_entries = data["visualstyle_entries"]
    visualstyle_extensions = data["visualstyle_extensions"]
    material_name = data["material_name"]
    interfere_handles = data["interfere_handles"]
    mleader_style_specs = data["mleader_style_specs"]
    mleader_entity_style_refs = data["mleader_entity_style_refs"]
    required_root_dicts = data["required_root_dicts"]
    has_acad_layerstates = data["has_acad_layerstates"]
    assoc_network_tags = data["assoc_network_tags"]
    detail_view_styles = data["detail_view_styles"]
    detail_view_style_extensions = data["detail_view_style_extensions"]
    section_view_styles = data["section_view_styles"]
    section_view_style_extensions = data["section_view_style_extensions"]
    layer_extension_snapshots = data["layer_extension_snapshots"]
    mleader_style_extension_snapshots = data["mleader_style_extension_snapshots"]
    table_style_cellstylemap = data["table_style_cellstylemap"]
    late_rootdict_entries = data["late_rootdict_entries"]
    sortents_by_block = data["sortents_by_block"]
    block_xdict_orders = data["block_xdict_orders"]
    group_specs = data["group_specs"]
    entity_xrecord_fallbacks = data["entity_xrecord_fallbacks"]
    acad_table_raw_fallbacks = data["acad_table_raw_fallbacks"]
    raw_graph_fallbacks = data["raw_graph_fallbacks"]
    raw_entity_swap_fallbacks = data["raw_entity_swap_fallbacks"]
    header_state = data["header_state"]
    header_custom_vars = data["header_custom_vars"]
    raw_header_overrides = data["raw_header_overrides"]
    raw_classes = data["raw_classes"]

    lines: list[str] = []
    raw_entity_swap_calls: list[str] = []
    sortents_calls: list[str] = []
    lines.extend(sorted(imports))
    lines.append("from dxfpy.addons.dxf2code import DocumentCodegenRuntime")
    lines.append("from dxfpy.sections.classes import restore_raw_classes")
    lines.append("from dxfpy.sections.header import restore_raw_header_vars")
    lines.append("from dxfpy.dynblkhelper import restore_raw_rootdict_entries")
    lines.append("from dxfpy.dynblkhelper import restore_raw_extension_subtree")
    lines.append("from dxfpy.dynblkhelper import sync_raw_acad_table_geometry_btrs")
    lines.append("from dxfpy.dynblkhelper import replace_dynamic_block_acad_tables_with_blockrefs")
    lines.append("from dxfpy.dynblkhelper import sync_layer_annotation_scale_xrecords")
    lines.append("from dxfpy.dynblkhelper import sync_extension_dict_owners")
    lines.append("from dxfpy.dynblkhelper import normalize_unresolved_xdata_handles")
    lines.append("from dxfpy.dynblkhelper import remove_stale_hatch_associations")
    lines.append("from dxfpy.dynblkhelper import ensure_insert_seqends")
    lines.append("from dxfpy.dynblkhelper import sync_handseed")
    lines.append("")
    lines.append(f'OUT = Path(r"{out_path.as_posix()}")')
    lines.append(f'doc = dxfpy.new("{doc.dxfversion}")')
    lines.append("msp = doc.modelspace()")
    lines.append("rt = DocumentCodegenRuntime(doc)")
    lines.append("")

    if resource_code is not None and resource_code.code:
        lines.append("# required table resources")
        lines.extend(resource_code.code)
        for name in sorted(layers_with_xdict):
            lines.append(f'_layer = doc.layers.get({name!r})')
            lines.append(
                'if _layer is not None and not _layer.has_extension_dict: _layer.new_extension_dict()'
            )
        for name, snapshot in layer_extension_snapshots:
            lines.append(f'_layer = doc.layers.get({name!r})')
            lines.append(
                f'if _layer is not None: restore_raw_extension_subtree(_layer, {snapshot!r})'
            )
        if has_acad_layerstates:
            lines.append("_layers_head = doc.layers.head")
            lines.append(
                "_lx = _layers_head.get_extension_dict() if _layers_head.has_extension_dict else _layers_head.new_extension_dict()"
            )
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
            for entry in variable_dict_entries:
                lines.append(f'if {entry.key!r} not in _var_dict:')
                lines.append(f'    _var_dict.add_dict_var({entry.key!r}, {entry.value!r})')
        if visualstyle_entries:
            lines.append('_vs_dict = doc.rootdict.get_required_dict("ACAD_VISUALSTYLE")')
            for entry in visualstyle_entries:
                lines.append(f'if {entry.key!r} not in _vs_dict:')
                lines.append('    _vs_attribs = dict(owner=_vs_dict.dxf.handle)')
                lines.append(f'    _vs_attribs.update({entry.dxfattribs!r})')
                lines.append('    _vs = doc.objects.new_entity("VISUALSTYLE", dxfattribs=_vs_attribs)')
                lines.append(f'    _vs_dict.add({entry.key!r}, _vs)')
            lines.append(
                f"rt.register_visualstyle_handles({[(entry.handle, entry.key) for entry in visualstyle_entries]!r})"
            )
            for key, snapshot in visualstyle_extensions:
                lines.append(f'_vs = _vs_dict.get({key!r})')
                lines.append(
                    f'if _vs is not None: restore_raw_extension_subtree(_vs, {snapshot!r})'
                )
        if assoc_network_tags:
            lines.append('_assoc_dict = doc.rootdict.get_required_dict("ACAD_ASSOCNETWORK")')
            lines.append('if "ACAD_ASSOCNETWORK" not in _assoc_dict:')
            lines.append(
                f'    rt.add_raw_object(_assoc_dict, "ACAD_ASSOCNETWORK", "ACDBASSOCNETWORK", {assoc_network_tags!r})'
            )
        if detail_view_styles:
            lines.append('_detail_dict = doc.rootdict.get_required_dict("ACAD_DETAILVIEWSTYLE")')
            for entry in detail_view_styles:
                lines.append(f'if {entry.key!r} not in _detail_dict:')
                lines.append(
                    f'    rt.add_raw_object(_detail_dict, {entry.key!r}, "ACDBDETAILVIEWSTYLE", {entry.tags!r})'
                )
            for key, snapshot in detail_view_style_extensions:
                lines.append(f'_detail = _detail_dict.get({key!r})')
                lines.append(
                    f'if _detail is not None: restore_raw_extension_subtree(_detail, {snapshot!r})'
                )
        if section_view_styles:
            lines.append('_section_dict = doc.rootdict.get_required_dict("ACAD_SECTIONVIEWSTYLE")')
            for entry in section_view_styles:
                lines.append(f'if {entry.key!r} not in _section_dict:')
                lines.append(
                    f'    rt.add_raw_object(_section_dict, {entry.key!r}, "ACDBSECTIONVIEWSTYLE", {entry.tags!r})'
                )
            for key, snapshot in section_view_style_extensions:
                lines.append(f'_section = _section_dict.get({key!r})')
                lines.append(
                    f'if _section is not None: restore_raw_extension_subtree(_section, {snapshot!r})'
                )
        if table_style_cellstylemap:
            lines.append('_table_style_dict = doc.rootdict.get("ACAD_TABLESTYLE")')
            lines.append('if _table_style_dict is not None and "Standard" in _table_style_dict:')
            lines.append('    _std = _table_style_dict.get("Standard")')
            lines.append(
                '    _xd = _std.get_extension_dict() if _std.has_extension_dict else _std.new_extension_dict()'
            )
            for entry in table_style_cellstylemap:
                lines.append(f'    if {entry.key!r} not in _xd.dictionary:')
                lines.append(
                    f'        rt.add_raw_object(_xd.dictionary, {entry.key!r}, "CELLSTYLEMAP", {entry.tags!r})'
                )
        lines.append("")

    for block, code in zip(blocks, block_codes):
        lines.append(f"# block: {block.name}")
        lines.extend(code.code)
        if block.name in block_layout_entity_snapshots:
            lines.append(
                f"rt.refresh_entity_map_from_block(_entity_map, b, {block_layout_entity_snapshots[block.name]!r})"
            )
        fallback = raw_graph_fallbacks.get(block.name)
        if fallback is not None:
            lines.append(f"# raw graph fallback for {block.name}")
            lines.append("_xd = rt.ensure_dynamic_block_extension_dict(b.block_record)")
            lines.append("rt.delete_graph_stack(b.block_record)")
            lines.append("_graph_map = {}")
            lines.append(
                f'_graph = rt.new_raw_graph_object("ACAD_EVALUATION_GRAPH", _xd.dxf.handle)'
            )
            lines.append(f'_graph_map[{fallback.graph_handle!r}] = _graph')
            for spec in fallback.owned_specs:
                lines.append(
                    f'_graph_map[{spec.handle!r}] = rt.new_raw_graph_object({spec.dxftype!r}, _graph.dxf.handle)'
                )
            lines.append(
                f'rt.load_raw_graph_object(_graph, _xd.dxf.handle, {fallback.graph_subclasses!r}, [], _entity_map, _graph_map)'
            )
            lines.append("_graph.set_reactors([_xd.dxf.handle])")
            lines.append('_xd.add("ACAD_ENHANCEDBLOCK", _graph)')
            if fallback.graph_xdata:
                lines.append(
                    f'_graph.set_xdata("AcadBPTGraphNodeId", {fallback.graph_xdata!r})'
                )
            if fallback.purge_subclasses:
                lines.append(
                    '_purge = rt.new_raw_graph_object("ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION", _xd.dxf.handle)'
                )
                lines.append(
                    f'rt.load_raw_graph_object(_purge, _xd.dxf.handle, {fallback.purge_subclasses!r}, [], _entity_map, _graph_map)'
                )
                lines.append("_purge.set_reactors([_xd.dxf.handle])")
                lines.append('_xd.add("AcDbDynamicBlockRoundTripPurgePreventer", _purge)')
            for spec in fallback.owned_specs:
                lines.append(
                    f'rt.load_raw_graph_object(_graph_map[{spec.handle!r}], _graph.dxf.handle, {spec.subclasses!r}, {spec.xdata!r}, _entity_map, _graph_map)'
                )
            for spec in fallback.owned_specs:
                if spec.reactors:
                    lines.append(
                        f'rt.set_raw_graph_reactors(_graph_map[{spec.handle!r}], {spec.reactors!r}, _entity_map, _graph_map)'
                    )
        xrecord_specs = entity_xrecord_fallbacks.get(block.name, [])
        for spec in xrecord_specs:
            lines.append(
                f'rt.rebuild_entity_xrecord_tree(_entity_map[{spec.entity_handle!r}], {spec.dict_key!r}, {spec.dict_order!r}, {spec.root_handle!r}, {spec.root_dxftype!r}, {spec.root_subclasses!r}, {_owned_object_specs_literal(spec.owned_specs)!r}, _entity_map)'
            )
        lines.append("rt.register_entity_map(_entity_map)")
        raw_specs = raw_entity_swap_fallbacks.get(block.name, [])
        for spec in raw_specs:
            raw_entity_swap_calls.append(
                _raw_entity_swap_call(f"doc.blocks.get({block.name!r})", spec)
            )
    lines.append("")

    _emit_paper_layouts(
        lines,
        layout_dictionary_order=layout_dictionary_order,
        paper_layout_names=paper_layout_names,
        active_paper_layout_name=active_paper_layout_name,
        paper_layout_dxfattribs=paper_layout_dxfattribs,
        paper_layout_block_record_names=paper_layout_block_record_names,
        paper_layout_codes=paper_layout_codes,
    )

    if sortents_by_block:
        for spec in sortents_by_block:
            sortents_calls.append(f'_sort_block = doc.blocks.get({spec.block_name!r})')
            sortents_calls.append('if _sort_block is not None:')
            sortents_calls.append(
                '    _xd = _sort_block.block_record.get_extension_dict() if _sort_block.block_record.has_extension_dict else _sort_block.block_record.new_extension_dict()'
            )
            sortents_calls.append('    if "ACAD_SORTENTS" not in _xd.dictionary:')
            sortents_calls.append(
                '        _sort = doc.objects.new_entity("SORTENTSTABLE", dxfattribs={"owner": _xd.dictionary.dxf.handle, "block_record_handle": _sort_block.block_record.dxf.handle})'
            )
            sortents_calls.append(
                f'        _sort.set_handles(rt.remap_sortents_handles({spec.tags!r}))'
            )
            sortents_calls.append('        _xd.dictionary.add("ACAD_SORTENTS", _sort)')

    if block_xdict_orders:
        lines.append("# block extension dictionary order")
        for block_name, ordered_keys in block_xdict_orders.items():
            lines.append(f'_block = doc.blocks.get({block_name!r})')
            lines.append(
                'if _block is not None and _block.block_record.has_extension_dict:'
            )
            lines.append(
                f'    rt.reorder_dictionary_entries(_block.block_record.get_extension_dict().dictionary, {ordered_keys!r})'
            )
        lines.append("")

    lines.append("# modelspace entities")
    lines.extend(msp_code.code)
    lines.append("rt.register_entity_map(_entity_map)")
    lines.append("")
    _emit_acad_table_geometry_blocks(
        lines, acad_table_geometry_block_codes, acad_table_field_handle_specs
    )
    _emit_acad_table_raw_fallbacks(lines, acad_table_raw_fallbacks)
    _emit_groups(lines, group_specs)
    if source_fieldlist_handles:
        lines.append("# restore FIELDLIST")
        lines.append("_field_list = doc.objects.setup_field_list()")
        lines.append(
            f"_field_list.handles = rt.remap_fieldlist_handles({source_fieldlist_handles!r}, {set(source_fieldlist_dangling)!r})"
        )
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
                f"rt.restore_mleader_style({spec.name!r}, {spec.xdata_tags!r}, {spec.reactors!r})"
            )
        for key, snapshot in mleader_style_extension_snapshots:
            lines.append(f'_mlstyle = doc.mleader_styles.get({key!r})')
            lines.append(
                f'if _mlstyle is not None: restore_raw_extension_subtree(_mlstyle, {snapshot!r})'
            )
        lines.append("")
    if deferred_recompose_tags:
        lines.append("# deferred ACDB_RECOMPOSE_DATA")
        lines.append("if 'ACDB_RECOMPOSE_DATA' not in doc.rootdict:")
        lines.append("    _xr = doc.objects.add_xrecord(owner=doc.rootdict.dxf.handle)")
        lines.append("    _xr.set_reactors([doc.rootdict.dxf.handle])")
        if deferred_recompose_source_handle:
            lines.append(f"    _source_handle = {deferred_recompose_source_handle!r}")
            lines.append("    _existing = doc.entitydb.get(_source_handle)")
            lines.append("    if _existing is None or _existing is _xr or not _existing.is_alive:")
            lines.append("        doc.entitydb.reset_handle(_xr, _source_handle)")
        if deferred_recompose_table_styles:
            lines.append(
                f"    rt.register_recompose_table_styles({deferred_recompose_table_styles!r})"
            )
        lines.append(
            f"    _xr.reset(rt.remap_root_xrecord_tags({deferred_recompose_tags!r}))"
        )
        lines.append("    doc.rootdict.add('ACDB_RECOMPOSE_DATA', _xr)")
        lines.append("")
    if late_rootdict_entries:
        lines.append("# late rootdict resources")
        lines.append(f"restore_raw_rootdict_entries(doc, {late_rootdict_entries!r})")
        lines.append("")
    if raw_entity_swap_calls:
        lines.append("# raw entity swaps")
        lines.extend(raw_entity_swap_calls)
        lines.append("")
    if mleader_entity_style_refs:
        lines.append("# restore MLEADER entity style handles")
        lines.append(f"rt.restore_mleader_entity_styles({mleader_entity_style_refs!r})")
        lines.append("")
    _emit_final_cleanup(
        lines,
        doc=doc,
        header_state=header_state,
        header_custom_vars=header_custom_vars,
        material_name=material_name,
        interfere_handles=interfere_handles,
        raw_header_overrides=raw_header_overrides,
        raw_classes=raw_classes,
    )
    lines.append("")
    lines.append("doc.saveas(OUT)")
    lines.append("print(OUT)")

    return "\n".join(lines) + "\n"
