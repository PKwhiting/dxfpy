from __future__ import annotations

from pathlib import Path

from ._dxf2code_specs import OwnedObjectSpec
from ._dxf2code_specs import DocumentCodegenCapture


def _owned_object_specs_literal(specs: list[OwnedObjectSpec]) -> list[dict[str, object]]:
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
    msp_code = data["msp_code"]
    imports = data["imports"]
    resource_code = data["resource_code"]
    layers_with_xdict = data["layers_with_xdict"]
    root_xrecords = data["root_xrecords"]
    deferred_recompose_tags = data["deferred_recompose_tags"]
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
    lines.append("from ezdxf.sections.classes import restore_raw_classes")
    lines.append("from ezdxf.sections.header import restore_raw_header_vars")
    lines.append("")
    lines.append("from ezdxf.entities import factory")
    lines.append("from ezdxf.entities.dxfentity import DXFTagStorage")
    lines.append("from ezdxf.lldxf.extendedtags import ExtendedTags")
    lines.append("from ezdxf.lldxf.tags import Tags")
    lines.append("from ezdxf.lldxf.types import DXFTag")
    lines.append("from ezdxf.lldxf.types import dxftag")
    lines.append(
        "from ezdxf.dynblkhelper import _delete_graph_stack, _ensure_dynamic_block_extension_dict, _new_tag_storage_object"
    )
    lines.append("")
    lines.append(f'OUT = Path(r"{out_path.as_posix()}")')
    lines.append(f'doc = ezdxf.new("{doc.dxfversion}")')
    lines.append("msp = doc.modelspace()")
    lines.append("_source_entity_map = {}")
    lines.append("_source_object_map = {}")
    lines.append("_dangling_handle_map = {}")
    lines.append("")
    lines.append("def _add_raw_object(_parent, _key, _dxftype, _tags):")
    lines.append(
        "    _raw = Tags([dxftag(0, _dxftype), dxftag(330, _parent.dxf.handle)])"
    )
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
    lines.append(
        "def _load_raw_graph_object(_obj, _owner, _subclasses, _xdata, _entity_map, _object_map):"
    )
    lines.append(
        "    _tags = [dxftag(0, _obj.dxftype()), dxftag(5, _obj.dxf.handle), dxftag(330, _owner)]"
    )
    lines.append("    for _subclass in _subclasses:")
    lines.append("        _tags.extend(")
    lines.append(
        "            dxftag(code, _map_raw_graph_value(value, _entity_map, _object_map) if code in (330, 331, 332, 333, 340, 360, 1005) else value)"
    )
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
    lines.append(
        "    for (_entity_text, _ext_snapshot), _entity in zip(_entity_snapshots, _block):"
    )
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
    lines.append(
        "                while _new_handle in doc.entitydb or _new_handle in _dangling_handle_map.values():"
    )
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
    lines.append(
        "def _rebuild_entity_xrecord_tree(_host, _dict_key, _dict_order, _root_handle, _root_dxftype, _root_subclasses, _owned_specs, _entity_map):"
    )
    lines.append(
        "    _xdict = _host.get_extension_dict() if _host.has_extension_dict else _host.new_extension_dict()"
    )
    lines.append("    if _dict_key in _xdict.dictionary:")
    lines.append("        _reorder_dictionary_entries(_xdict.dictionary, _dict_order)")
    lines.append("        return")
    lines.append("    _object_map = {}")
    lines.append(
        "    _root = _new_raw_graph_object(_root_dxftype, _xdict.dictionary.dxf.handle)"
    )
    lines.append("    _object_map[_root_handle] = _root")
    lines.append("    _source_object_map[_root_handle] = _root")
    lines.append("    for _spec in _owned_specs:")
    lines.append(
        "        _mapped_owner = _map_raw_graph_value(_spec['owner'], _entity_map, _object_map)"
    )
    lines.append(
        "        _object_map[_spec['handle']] = _new_raw_graph_object(_spec['dxftype'], _mapped_owner)"
    )
    lines.append(
        "        _source_object_map[_spec['handle']] = _object_map[_spec['handle']]"
    )
    lines.append(
        "    _load_raw_graph_object(_root, _xdict.dictionary.dxf.handle, _root_subclasses, [], _entity_map, _object_map)"
    )
    lines.append("    _xdict.dictionary.add(_dict_key, _root)")
    lines.append("    for _spec in _owned_specs:")
    lines.append(
        "        _mapped_owner = _map_raw_graph_value(_spec['owner'], _entity_map, _object_map)"
    )
    lines.append(
        "        _load_raw_graph_object(_object_map[_spec['handle']], _mapped_owner, _spec['subclasses'], [], _entity_map, _object_map)"
    )
    lines.append("    _reorder_dictionary_entries(_xdict.dictionary, _dict_order)")
    lines.append("    _register_field_tree_handles(list(_object_map.values()))")
    lines.append("")
    lines.append(
        "def _swap_raw_graphic_entity(_block, _source_handle, _source_owner, _source_xdict_handle, _source_resource_handles, _raw_tags):"
    )
    lines.append("    _old = _source_entity_map[_source_handle]")
    lines.append("    _xdict_handle = ''")
    lines.append("    if _source_xdict_handle and _old.has_extension_dict:")
    lines.append(
        "        _xdict_handle = _old.get_extension_dict().dictionary.dxf.handle"
    )
    lines.append("    _resource_handle_map = {}")
    lines.append("    for _source_value, _attr_name in _source_resource_handles:")
    lines.append("        _target_value = _old.dxf.get(_attr_name)")
    lines.append("        if _target_value:")
    lines.append("            _resource_handle_map[_source_value] = _target_value")
    lines.append(
        "    _mapped = [dxftag(0, _old.dxftype()), dxftag(5, _old.dxf.handle), dxftag(330, _old.dxf.owner)]"
    )
    lines.append("    for code, value in _raw_tags:")
    lines.append(
        "        if code in (320, 331, 332, 333, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 360, 390, 1005) and isinstance(value, str):"
    )
    lines.append("            if value in _resource_handle_map:")
    lines.append("                value = _resource_handle_map[value]")
    lines.append("            elif value == _source_handle:")
    lines.append("                value = _old.dxf.handle")
    lines.append("            elif value == _source_owner:")
    lines.append("                value = _old.dxf.owner")
    lines.append(
        "            elif _source_xdict_handle and value == _source_xdict_handle and _xdict_handle:"
    )
    lines.append("                value = _xdict_handle")
    lines.append(
        "        if code in (310, 311, 312, 313, 314, 315, 316, 317, 318, 319) and isinstance(value, str):"
    )
    lines.append("            _mapped.append(dxftag(code, bytes.fromhex(value)))")
    lines.append(
        "        elif code in (310, 311, 312, 313, 314, 315, 316, 317, 318, 319) or isinstance(value, (tuple, list)):"
    )
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
            for key, snapshot in visualstyle_extensions:
                lines.append(f'_vs = _vs_dict.get({key!r})')
                lines.append(
                    f'if _vs is not None: restore_raw_extension_subtree(_vs, {snapshot!r})'
                )
        if assoc_network_tags:
            lines.append('_assoc_dict = doc.rootdict.get_required_dict("ACAD_ASSOCNETWORK")')
            lines.append('if "ACAD_ASSOCNETWORK" not in _assoc_dict:')
            lines.append(
                f'    _add_raw_object(_assoc_dict, "ACAD_ASSOCNETWORK", "ACDBASSOCNETWORK", {assoc_network_tags!r})'
            )
        if detail_view_styles:
            lines.append('_detail_dict = doc.rootdict.get_required_dict("ACAD_DETAILVIEWSTYLE")')
            for entry in detail_view_styles:
                lines.append(f'if {entry.key!r} not in _detail_dict:')
                lines.append(
                    f'    _add_raw_object(_detail_dict, {entry.key!r}, "ACDBDETAILVIEWSTYLE", {entry.tags!r})'
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
                    f'    _add_raw_object(_section_dict, {entry.key!r}, "ACDBSECTIONVIEWSTYLE", {entry.tags!r})'
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
                    f'        _add_raw_object(_xd.dictionary, {entry.key!r}, "CELLSTYLEMAP", {entry.tags!r})'
                )
        lines.append("")

    for block, code in zip(blocks, block_codes):
        lines.append(f"# block: {block.name}")
        lines.extend(code.code)
        if block.name in block_layout_entity_snapshots:
            lines.append(
                f"_refresh_entity_map_from_block(_entity_map, b, {block_layout_entity_snapshots[block.name]!r})"
            )
        fallback = raw_graph_fallbacks.get(block.name)
        if fallback is not None:
            lines.append(f"# raw graph fallback for {block.name}")
            lines.append("_xd = _ensure_dynamic_block_extension_dict(b.block_record)")
            lines.append("_delete_graph_stack(b.block_record)")
            lines.append("_graph_map = {}")
            lines.append(
                f'_graph = _new_raw_graph_object("ACAD_EVALUATION_GRAPH", _xd.dxf.handle)'
            )
            lines.append(f'_graph_map[{fallback.graph_handle!r}] = _graph')
            for spec in fallback.owned_specs:
                lines.append(
                    f'_graph_map[{spec.handle!r}] = _new_raw_graph_object({spec.dxftype!r}, _graph.dxf.handle)'
                )
            lines.append(
                f'_load_raw_graph_object(_graph, _xd.dxf.handle, {fallback.graph_subclasses!r}, [], _entity_map, _graph_map)'
            )
            lines.append("_graph.set_reactors([_xd.dxf.handle])")
            lines.append('_xd.add("ACAD_ENHANCEDBLOCK", _graph)')
            if fallback.graph_xdata:
                lines.append(
                    f'_graph.set_xdata("AcadBPTGraphNodeId", {fallback.graph_xdata!r})'
                )
            if fallback.purge_subclasses:
                lines.append(
                    '_purge = _new_raw_graph_object("ACDB_DYNAMICBLOCKPURGEPREVENTER_VERSION", _xd.dxf.handle)'
                )
                lines.append(
                    f'_load_raw_graph_object(_purge, _xd.dxf.handle, {fallback.purge_subclasses!r}, [], _entity_map, _graph_map)'
                )
                lines.append("_purge.set_reactors([_xd.dxf.handle])")
                lines.append('_xd.add("AcDbDynamicBlockRoundTripPurgePreventer", _purge)')
            for spec in fallback.owned_specs:
                lines.append(
                    f'_load_raw_graph_object(_graph_map[{spec.handle!r}], _graph.dxf.handle, {spec.subclasses!r}, {spec.xdata!r}, _entity_map, _graph_map)'
                )
            for spec in fallback.owned_specs:
                if spec.reactors:
                    lines.append(
                        f'_set_raw_graph_reactors(_graph_map[{spec.handle!r}], {spec.reactors!r}, _entity_map, _graph_map)'
                    )
        xrecord_specs = entity_xrecord_fallbacks.get(block.name, [])
        for spec in xrecord_specs:
            lines.append(
                f'_rebuild_entity_xrecord_tree(_entity_map[{spec.entity_handle!r}], {spec.dict_key!r}, {spec.dict_order!r}, {spec.root_handle!r}, {spec.root_dxftype!r}, {spec.root_subclasses!r}, {_owned_object_specs_literal(spec.owned_specs)!r}, _entity_map)'
            )
        lines.append("_source_entity_map.update(_entity_map)")
        raw_specs = raw_entity_swap_fallbacks.get(block.name, [])
        for spec in raw_specs:
            raw_entity_swap_calls.append(
                f'_swap_raw_graphic_entity(doc.blocks.get({block.name!r}), {spec.source_handle!r}, {spec.source_owner!r}, {spec.source_xdict_handle!r}, {[(ref.source_handle, ref.attrib_name) for ref in spec.source_resource_handles]!r}, {spec.raw_tags!r})'
            )
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
                f'        _sort.set_handles(_remap_sortents_handles({spec.tags!r}))'
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
                f'    _reorder_dictionary_entries(_block.block_record.get_extension_dict().dictionary, {ordered_keys!r})'
            )
        lines.append("")

    lines.append("# modelspace entities")
    lines.extend(msp_code.code)
    lines.append("_source_entity_map.update(_entity_map)")
    lines.append("")
    if source_fieldlist_handles:
        lines.append("# restore FIELDLIST")
        lines.append("_field_list = doc.objects.setup_field_list()")
        lines.append(
            f"_field_list.handles = _remap_fieldlist_handles({source_fieldlist_handles!r}, {set(source_fieldlist_dangling)!r})"
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
                f"_restore_mleader_style({spec.name!r}, {spec.xdata_tags!r}, {spec.reactors!r})"
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
        lines.append(
            f"    _xr.reset(_remap_root_xrecord_tags({deferred_recompose_tags!r}))"
        )
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
    for ref in interfere_handles:
        lines.append(f'_mapped = _mapped_handle({ref.handle!r})')
        lines.append(f'if _mapped is not None: doc.header[{ref.name!r}] = _mapped')
    if raw_header_overrides:
        lines.append(f"restore_raw_header_vars(doc.header, {raw_header_overrides!r})")
    lines.append(f"restore_raw_classes(doc.classes, {raw_classes!r})")
    lines.append("")
    lines.append("doc.saveas(OUT)")
    lines.append("print(OUT)")

    return "\n".join(lines) + "\n"
