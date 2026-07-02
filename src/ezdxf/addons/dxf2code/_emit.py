from __future__ import annotations

from pathlib import Path

from ._specs import DocumentCodegenCapture, OwnedObjectSpec, OwnedObjectSpecData


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


def render_document_codegen_script(data: DocumentCodegenCapture, out_path: Path) -> str:
    doc = data["doc"]
    blocks = data["blocks"]
    block_codes = data["block_codes"]
    block_layout_entity_snapshots = data["block_layout_entity_snapshots"]
    paper_layout_names = data["paper_layout_names"]
    paper_layout_codes = data["paper_layout_codes"]
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
    entity_xrecord_fallbacks = data["entity_xrecord_fallbacks"]
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
    lines.append("from ezdxf.addons.dxf2code import DocumentCodegenRuntime")
    lines.append("from ezdxf.sections.classes import restore_raw_classes")
    lines.append("from ezdxf.sections.header import restore_raw_header_vars")
    lines.append("from ezdxf.dynblkhelper import restore_raw_rootdict_entries")
    lines.append("from ezdxf.dynblkhelper import restore_raw_extension_subtree")
    lines.append("")
    lines.append(f'OUT = Path(r"{out_path.as_posix()}")')
    lines.append(f'doc = ezdxf.new("{doc.dxfversion}")')
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
                f'rt.swap_raw_graphic_entity(doc.blocks.get({block.name!r}), {spec.source_handle!r}, {spec.source_owner!r}, {spec.source_xdict_handle!r}, {[(ref.source_handle, ref.attrib_name) for ref in spec.source_resource_handles]!r}, {spec.raw_tags!r}, {spec.xdata!r})'
            )
    lines.append("")

    if paper_layout_names:
        lines.append("# paperspace layouts")
        for layout_name in paper_layout_names:
            lines.append(
                f'if {layout_name!r} not in doc.layouts: doc.new_layout({layout_name!r})'
            )
            lines.append(f'psp = doc.layout({layout_name!r})')
            lines.append("psp.delete_all_entities()")
            for name, code in paper_layout_codes:
                if name != layout_name:
                    continue
                lines.extend(code.code)
                lines.append("rt.register_entity_map(_entity_map)")
            lines.append("")

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
    for ref in interfere_handles:
        lines.append(f'_mapped = rt.mapped_handle({ref.handle!r})')
        lines.append(f'if _mapped is not None: doc.header[{ref.name!r}] = _mapped')
    if raw_header_overrides:
        lines.append(f"restore_raw_header_vars(doc.header, {raw_header_overrides!r})")
    lines.append(f"restore_raw_classes(doc.classes, {raw_classes!r})")
    lines.append("")
    lines.append("doc.saveas(OUT)")
    lines.append("print(OUT)")

    return "\n".join(lines) + "\n"
