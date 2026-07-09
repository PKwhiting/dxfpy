# Copyright (c) 2019 Manfred Moitzi
# License: MIT License

import ezdxf
from ezdxf.addons.dxf2code import document_to_code_file
from ezdxf.dynblkhelper import restore_raw_entity_export, snapshot_raw_entity_export, snapshot_raw_extension_subtree
from ezdxf.lldxf.extendedtags import ExtendedTags
from ezdxf.math import Vec2

from tests.test_08_addons.dxf2code_support import (
    assert_clean_replay,
    execute_code_in_namespace,
    export_text,
    normalize_handle_refs_in_text,
    replay_doc_to_new_doc,
)


def test_insert_xdata_replay_preserves_nonhandle_payload():
    source_doc = ezdxf.new("R2018")
    block = source_doc.blocks.new("XDATA_BLOCK")
    block.add_line((0, 0), (1, 0))
    insert = source_doc.modelspace().add_blockref(block.name, (0, 0))
    insert.set_xdata(
        "AcadAnnotativeAttributeDecomposition",
        [(1000, "AnnotativeData"), (1002, "{"), (1070, 1), (1070, 1), (1002, "}")],
    )

    new_doc = replay_doc_to_new_doc(source_doc)
    new_insert = list(new_doc.modelspace().query("INSERT"))[0]

    assert list(new_insert.get_xdata("AcadAnnotativeAttributeDecomposition")) == [
        (1000, "AnnotativeData"),
        (1002, "{"),
        (1070, 1),
        (1070, 1),
        (1002, "}"),
    ]


def test_header_material_handle_replay_maps_by_material_name():
    source_doc = ezdxf.new("R2010")
    material = source_doc.materials.get("ByLayer")
    source_doc.header["$CMATERIAL"] = material.dxf.handle

    new_doc = replay_doc_to_new_doc(source_doc)

    assert new_doc.header["$CMATERIAL"] == new_doc.materials.get("ByLayer").dxf.handle


def test_layer_material_handle_replay_maps_by_material_name():
    source_doc = ezdxf.new("R2010")
    source_doc.layers.new("MATERIAL_LAYER")

    new_doc = replay_doc_to_new_doc(source_doc)

    layer = new_doc.layers.get("MATERIAL_LAYER")
    assert layer is not None
    assert layer.dxf.material_handle == new_doc.materials.get("Global").dxf.handle


def test_dxf2code_replay_comparison_reports_clean_basic_replay():
    source_doc = ezdxf.new("R2018")
    source_doc.modelspace().add_line((0, 0), (1, 0))

    new_doc = replay_doc_to_new_doc(source_doc)
    comparison = assert_clean_replay(source_doc, new_doc)

    assert comparison.layout_names_match is True


def test_document_to_code_file_maps_header_interfere_visualstyle_handles(tmp_path):
    source_doc = ezdxf.readfile(
        "tests/test_08_addons/autocad_nested_working_minimal_v1_edited.dxf"
    )
    visualstyle_dict = source_doc.rootdict.get("ACAD_VISUALSTYLE")
    assert visualstyle_dict is not None
    keys = list(visualstyle_dict.keys())[:2]
    assert len(keys) == 2
    source_doc.header["$INTERFEREOBJVS"] = visualstyle_dict.get(keys[0]).dxf.handle
    source_doc.header["$INTERFEREVPVS"] = visualstyle_dict.get(keys[1]).dxf.handle

    source_path = tmp_path / "source_interfere_visualstyles.dxf"
    script_path = tmp_path / "generated_interfere_visualstyles.py"
    output_path = tmp_path / "generated_interfere_visualstyles.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    new_doc = ezdxf.readfile(output_path)

    replayed_visualstyle_dict = new_doc.rootdict.get("ACAD_VISUALSTYLE")
    assert replayed_visualstyle_dict is not None
    assert new_doc.header["$INTERFEREOBJVS"] == replayed_visualstyle_dict.get(keys[0]).dxf.handle
    assert new_doc.header["$INTERFEREVPVS"] == replayed_visualstyle_dict.get(keys[1]).dxf.handle


def test_layer_extension_subtree_replay_remaps_external_handles():
    source_doc = ezdxf.new("R2018")
    ref_layer = source_doc.layers.new("U-MISC")
    annotated_layer = source_doc.layers.new("U-MISC @ 1")
    material = source_doc.materials.get("Global")
    assert source_doc.entitydb.reset_handle(ref_layer, "1A2C") is True
    assert source_doc.entitydb.reset_handle(material, "1A2D") is True
    xdict = annotated_layer.new_extension_dict().dictionary
    xrecord = xdict.add_xrecord("ASDK_XREC_ANNO_SCALE_INFO")
    xrecord.set_reactors([xdict.dxf.handle])
    xrecord.reset([(70, 1), (340, material.dxf.handle), (340, ref_layer.dxf.handle), (70, -1)])

    new_doc = replay_doc_to_new_doc(source_doc)

    replayed_layer = new_doc.layers.get("U-MISC @ 1")
    replayed_ref = new_doc.layers.get("U-MISC")
    replayed_material = new_doc.materials.get("Global")
    assert replayed_layer is not None
    assert replayed_ref is not None
    assert replayed_material is not None

    snapshot = snapshot_raw_extension_subtree(replayed_layer)
    pointer_values = [value for code, value in snapshot[1] if code == 340]

    assert pointer_values == [replayed_material.dxf.handle, replayed_ref.dxf.handle]


def test_document_to_code_file_remaps_layer_annotation_xrecord_handles(tmp_path):
    from ezdxf.dynblkhelper import _default_annotation_scale_handle

    source_doc = ezdxf.new("R2018")
    base_layer = source_doc.layers.new("BASE_ANNO")
    annotated_layer = source_doc.layers.new("BASE_ANNO @ 1")
    assert source_doc.entitydb.reset_handle(base_layer, "ABC") is True
    scale_handle = _default_annotation_scale_handle(source_doc)
    xdict = annotated_layer.new_extension_dict().dictionary
    xrecord = xdict.add_xrecord("ASDK_XREC_ANNO_SCALE_INFO")
    xrecord.set_reactors([xdict.dxf.handle])
    xrecord.reset([(70, 1), (340, scale_handle), (340, base_layer.dxf.handle), (70, -1)])
    source_doc.modelspace().add_line(
        (0, 0), (1, 0), dxfattribs={"layer": annotated_layer.dxf.name}
    )

    source_path = tmp_path / "source_layer_annotation_xrecord.dxf"
    script_path = tmp_path / "generated_layer_annotation_xrecord.py"
    output_path = tmp_path / "generated_layer_annotation_xrecord.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    script_text = script_path.read_text(encoding="utf-8")

    assert "sync_layer_annotation_scale_xrecords(doc)" in script_text

    exec(script_text, {})

    out_doc = ezdxf.readfile(output_path)
    out_layer = out_doc.layers.get(annotated_layer.dxf.name)
    out_xdict = out_layer.get_extension_dict().dictionary
    out_xrecord = out_xdict.get("ASDK_XREC_ANNO_SCALE_INFO")
    pointer_values = [value for code, value in out_xrecord.tags if code == 340]

    assert out_doc.entitydb.get(pointer_values[0]).dxftype() == "SCALE"
    assert out_doc.entitydb.get(pointer_values[1]) is out_doc.layers.get(base_layer.dxf.name)


def test_document_to_code_file_advances_handseed_after_raw_handle_restore(tmp_path):
    source_doc = ezdxf.new("R2018")
    layer = source_doc.layers.new("HIGH_HANDLE_LAYER")
    xdict = layer.new_extension_dict().dictionary
    xrecord = xdict.add_xrecord("HIGH_HANDLE_XRECORD")
    assert source_doc.entitydb.reset_handle(xdict, "F000") is True
    assert source_doc.entitydb.reset_handle(xrecord, "F001") is True
    xrecord.set_reactors([xdict.dxf.handle])
    source_doc.modelspace().add_line((0, 0), (1, 0), dxfattribs={"layer": layer.dxf.name})
    block = source_doc.blocks.new("HIGH_HANDLE_ATTRIB_BLOCK")
    block.add_attdef("TAG", insert=(0, 0))
    insert = source_doc.modelspace().add_blockref(block.name, (0, 0))
    insert.add_attrib("TAG", "value", insert=(0, 0))
    insert.take_ownership()
    assert insert.seqend is not None
    assert source_doc.entitydb.reset_handle(insert.seqend, "F100") is True

    source_path = tmp_path / "source_high_handseed.dxf"
    script_path = tmp_path / "generated_high_handseed.py"
    output_path = tmp_path / "generated_high_handseed.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    script_text = script_path.read_text(encoding="utf-8")

    assert "ensure_insert_seqends(doc)" in script_text
    assert "sync_handseed(doc)" in script_text

    exec(script_text, {})

    out_doc = ezdxf.readfile(output_path)
    max_handle = max(int(str(handle), 16) for handle in out_doc.entitydb.keys())
    handseed = int(out_doc.header["$HANDSEED"], 16)

    assert handseed > max_handle


def test_sync_handseed_scans_attached_insert_seqend_handles():
    from ezdxf.dynblkhelper import sync_handseed

    doc = ezdxf.new("R2018")
    block = doc.blocks.new("ATTRIB_BLOCK")
    block.add_attdef("TAG", insert=(0, 0))
    insert = doc.modelspace().add_blockref(block.name, (0, 0))
    insert.add_attrib("TAG", "value", insert=(0, 0))
    insert.take_ownership()
    assert insert.seqend is not None
    insert.seqend.dxf.handle = "F100"

    sync_handseed(doc)

    assert int(str(doc.entitydb.handles), 16) > int("F100", 16)


def test_ensure_insert_seqends_materializes_missing_seqend():
    from ezdxf.dynblkhelper import ensure_insert_seqends

    doc = ezdxf.new("R2018")
    block = doc.blocks.new("ATTRIB_BLOCK")
    block.add_attdef("TAG", insert=(0, 0))
    insert = doc.modelspace().add_blockref(block.name, (0, 0))
    insert.add_attrib("TAG", "value", insert=(0, 0))
    insert.take_ownership()
    assert insert.seqend is not None
    doc.entitydb.delete_entity(insert.seqend)
    insert.seqend = None

    ensure_insert_seqends(doc)

    assert insert.seqend is not None
    assert insert.seqend.dxf.handle in doc.entitydb
    assert insert.seqend.dxf.owner == insert.dxf.handle


def test_dimstyle_raw_replay_aligns_runtime_handle_with_raw_export_handle():
    source_doc = ezdxf.new("R2018")
    dimstyle = source_doc.dimstyles.new("RAW_HANDLE_STYLE")

    assert source_doc.entitydb.reset_handle(dimstyle, "1FE") is True

    new_doc = replay_doc_to_new_doc(source_doc)

    replayed = new_doc.dimstyles.get("RAW_HANDLE_STYLE")
    assert replayed is not None
    assert replayed.dxf.handle == "1FE"
    assert new_doc.entitydb.get("1FE") is replayed


def test_restore_raw_dimstyle_export_remaps_handle_105_on_collision():
    source_doc = ezdxf.new("R2018")
    source_dimstyle = source_doc.dimstyles.new("RAW_HANDLE_STYLE")
    assert source_doc.entitydb.reset_handle(source_dimstyle, "1FE") is True
    snapshot = snapshot_raw_entity_export(source_dimstyle)

    target_doc = ezdxf.new("R2018")
    blocker = target_doc.modelspace().add_circle((0, 0), 1)
    assert target_doc.entitydb.reset_handle(blocker, "1FE") is True
    target_dimstyle = target_doc.dimstyles.new("RAW_HANDLE_STYLE")

    restore_raw_entity_export(target_dimstyle, snapshot)
    exported = ExtendedTags.from_text(snapshot_raw_entity_export(target_dimstyle)[0])

    assert target_dimstyle.dxf.handle != "1FE"
    assert exported.get_handle() == target_dimstyle.dxf.handle


def test_restore_raw_attrib_export_updates_existing_extension_dict_owner_after_handle_reset():
    source_doc = ezdxf.new("R2010")
    source_block = source_doc.blocks.new("ATTRIB_HANDLE_BLOCK")
    source_insert = source_block.add_blockref("TARGET", (0, 0))
    source_attrib = source_insert.add_attrib("TAG", "TEXT", insert=(1, 2))
    source_attrib.new_extension_dict().dictionary.add_new_dict(
        "AcDbContextDataManager"
    ).add_new_dict("ACDB_ANNOTATIONSCALES")
    assert source_doc.entitydb.reset_handle(source_attrib, "1FE") is True
    source_insert.take_ownership()
    snapshot = snapshot_raw_entity_export(source_attrib)

    target_doc = ezdxf.new("R2010")
    target_block = target_doc.blocks.new("ATTRIB_HANDLE_BLOCK")
    target_insert = target_block.add_blockref("TARGET", (0, 0))
    target_attrib = target_insert.add_attrib("TAG", "TEXT", insert=(1, 2))
    target_attrib.new_extension_dict().dictionary.add_new_dict(
        "AcDbContextDataManager"
    ).add_new_dict("ACDB_ANNOTATIONSCALES")

    assert target_attrib.dxf.handle != "1FE"

    restore_raw_entity_export(target_attrib, snapshot)

    assert target_attrib.dxf.handle == "1FE"
    assert target_attrib.get_extension_dict().dictionary.dxf.owner == target_attrib.dxf.handle


def test_dimstyle_replay_preserves_normalized_raw_export():
    source_doc = ezdxf.new("R2010")
    source_doc.styles.new("DIM_TXT", dxfattribs={"font": "txt"})
    ltype = source_doc.linetypes.new("DIM_LT", dxfattribs={"description": "DIM_LT"})
    ltype.setup_pattern([0.2, 0.1, -0.1])
    arrow = source_doc.blocks.new("DIM_ARROW")
    arrow.add_line((0, 0), (1, 0))

    dimstyle = source_doc.dimstyles.new("TEST_DIMSTYLE")
    dimstyle.dxf.dimtxsty = "DIM_TXT"
    dimstyle.dxf.dimblk = "DIM_ARROW"
    dimstyle.dxf.dimldrblk = "DIM_ARROW"
    dimstyle.dxf.dimltype = "DIM_LT"
    dimstyle.dxf.dimltex1 = "DIM_LT"
    dimstyle.dxf.dimltex2 = "DIM_LT"
    dimstyle.set_xdata("ACAD_DSTYLE_DIMBREAK", [(1070, 391), (1040, 0.125)])

    new_doc = replay_doc_to_new_doc(source_doc)
    new_dimstyle = new_doc.dimstyles.get("TEST_DIMSTYLE")

    assert new_dimstyle is not None
    assert new_dimstyle.dxf.dimtxsty == "DIM_TXT"
    assert new_dimstyle.dxf.dimblk == "DIM_ARROW"
    assert new_dimstyle.dxf.dimldrblk == "DIM_ARROW"
    assert new_dimstyle.dxf.dimltype == "DIM_LT"
    assert new_dimstyle.dxf.dimltex1 == "DIM_LT"
    assert new_dimstyle.dxf.dimltex2 == "DIM_LT"
    assert normalize_handle_refs_in_text(export_text(new_dimstyle, new_doc.dxfversion)) == normalize_handle_refs_in_text(
        export_text(dimstyle, source_doc.dxfversion)
    )


def test_document_to_code_file_generates_executable_full_doc_script(tmp_path):
    source_doc = ezdxf.new("R2010")
    line = source_doc.modelspace().add_line((0, 0), (1, 0))
    source_doc.header["$LASTSAVEDBY"] = "tester"
    source_doc.header.custom_vars.append("CustomTag", "CustomValue")
    standard_table_style = source_doc.table_styles.get("Standard")
    assert standard_table_style is not None
    assert source_doc.entitydb.reset_handle(standard_table_style, "1FE") is True
    xrecord = source_doc.objects.add_xrecord(owner=source_doc.rootdict.dxf.handle)
    xrecord.set_reactors([source_doc.rootdict.dxf.handle])
    xrecord.tags.extend([(90, 1), (330, line.dxf.handle), (330, standard_table_style.dxf.handle)])
    source_doc.rootdict.add("ACDB_RECOMPOSE_DATA", xrecord)

    source_path = tmp_path / "source_doc.dxf"
    script_path = tmp_path / "generated_doc.py"
    output_path = tmp_path / "generated_doc.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    script_text = script_path.read_text(encoding="utf-8")

    assert "from ezdxf.addons.dxf2code import DocumentCodegenRuntime" in script_text
    assert "rt = DocumentCodegenRuntime(doc)" in script_text
    assert "def _add_raw_object(" not in script_text
    assert "def _swap_raw_graphic_entity(" not in script_text

    exec(script_text, {})

    out_doc = ezdxf.readfile(output_path)
    out_line = out_doc.modelspace()[0]
    restored = out_doc.rootdict.get("ACDB_RECOMPOSE_DATA")
    out_standard_table_style = out_doc.table_styles.get("Standard")

    assert script_path.exists()
    assert output_path.exists()
    assert out_doc.header["$LASTSAVEDBY"] == "tester"
    assert list(out_doc.header.custom_vars) == [("CustomTag", "CustomValue")]
    assert restored is not None
    assert out_standard_table_style is not None
    assert f"330\n{out_line.dxf.handle}\n" in export_text(restored, out_doc.dxfversion)
    assert f"330\n{out_standard_table_style.dxf.handle}\n" in export_text(
        restored, out_doc.dxfversion
    )


def test_document_to_code_file_renders_missing_dimension_geometry_block(tmp_path):
    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("DIM_BLOCK")
    dim = block.add_linear_dim(base=(5, 2), p1=(0, 0), p2=(10, 0)).dimension
    dim.dxf.geometry = "*D17"
    source_doc.modelspace().add_blockref(block.name, (0, 0))

    source_path = tmp_path / "source_missing_dim_geometry.dxf"
    script_path = tmp_path / "generated_missing_dim_geometry.py"
    output_path = tmp_path / "generated_missing_dim_geometry.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    script_text = script_path.read_text(encoding="utf-8")

    assert "e.render()" in script_text

    exec(script_text, {})

    out_doc = ezdxf.readfile(output_path)
    out_block = out_doc.blocks.get("DIM_BLOCK")
    assert out_block is not None
    out_dim = list(out_block.query("DIMENSION"))[0]
    assert out_dim.get_geometry_block() is not None


def test_document_to_code_file_replays_existing_dimension_geometry_block(tmp_path):
    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("DIM_BLOCK_WITH_GEOMETRY")
    dim = block.add_linear_dim(base=(5, 2), p1=(0, 0), p2=(10, 0)).dimension
    dim.render()
    assert dim.get_geometry_block() is not None
    source_doc.modelspace().add_blockref(block.name, (0, 0))

    source_path = tmp_path / "source_existing_dim_geometry.dxf"
    script_path = tmp_path / "generated_existing_dim_geometry.py"
    output_path = tmp_path / "generated_existing_dim_geometry.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_block = out_doc.blocks.get("DIM_BLOCK_WITH_GEOMETRY")
    assert out_block is not None
    out_dim = list(out_block.query("DIMENSION"))[0]
    assert out_dim.get_geometry_block() is not None


def test_document_to_code_file_removes_stale_hatch_source_boundary_handles(tmp_path):
    source_doc = ezdxf.new("R2018")
    block = source_doc.blocks.new("STALE_HATCH_BLOCK")
    hatch = block.add_hatch(color=2)
    path = hatch.paths.add_polyline_path(
        [(0, 0), (5, 0), (5, 5), (0, 5)], is_closed=True
    )
    hatch.dxf.associative = 1
    path.source_boundary_objects = ["DEAD"]
    source_doc.modelspace().add_blockref(block.name, (0, 0))

    source_path = tmp_path / "source_stale_hatch_assoc.dxf"
    script_path = tmp_path / "generated_stale_hatch_assoc.py"
    output_path = tmp_path / "generated_stale_hatch_assoc.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    script_text = script_path.read_text(encoding="utf-8")

    assert "remove_stale_hatch_associations(doc)" in script_text

    exec(script_text, {})

    out_doc = ezdxf.readfile(output_path)
    out_block = out_doc.blocks.get(block.name)
    assert out_block is not None
    out_hatch = list(out_block.query("HATCH"))[0]

    assert out_hatch.dxf.associative == 0
    assert not any(path.source_boundary_objects for path in out_hatch.paths)
    assert "DEAD" not in export_text(out_hatch, out_doc.dxfversion)


def test_remove_stale_hatch_associations_requires_boundary_reactor():
    from ezdxf.dynblkhelper import remove_stale_hatch_associations

    doc = ezdxf.new("R2018")
    block = doc.blocks.new("HATCH_BOUNDARY_REACTOR_BLOCK")
    bad_boundary = block.add_lwpolyline(
        [(0, 0), (5, 0), (5, 5), (0, 5)], close=True
    )
    bad_hatch = block.add_hatch(color=2)
    bad_path = bad_hatch.paths.add_polyline_path(
        [(0, 0), (5, 0), (5, 5), (0, 5)], is_closed=True
    )
    bad_hatch.dxf.associative = 1
    bad_path.source_boundary_objects = [bad_boundary.dxf.handle]

    good_boundary = block.add_lwpolyline(
        [(10, 0), (15, 0), (15, 5), (10, 5)], close=True
    )
    good_hatch = block.add_hatch(color=3)
    good_path = good_hatch.paths.add_polyline_path(
        [(10, 0), (15, 0), (15, 5), (10, 5)], is_closed=True
    )
    good_hatch.dxf.associative = 1
    good_path.source_boundary_objects = [good_boundary.dxf.handle]
    good_boundary.set_reactors([good_hatch.dxf.handle])

    remove_stale_hatch_associations(doc)

    assert bad_hatch.dxf.associative == 0
    assert not bad_path.source_boundary_objects
    assert good_hatch.dxf.associative == 1
    assert good_path.source_boundary_objects == [good_boundary.dxf.handle]


def test_document_to_code_file_recreates_paperspace_viewports(tmp_path):
    source_doc = ezdxf.new("R2010")
    psp = source_doc.layout("Layout1")
    psp.delete_all_entities()
    psp.add_viewport(
        center=(100, 100),
        size=(120, 90),
        view_center_point=(0, 0),
        view_height=10,
        status=2,
    )
    psp.add_viewport(
        center=(260, 100),
        size=(120, 90),
        view_center_point=(5, 5),
        view_height=20,
        status=3,
    )

    source_path = tmp_path / "source_layouts.dxf"
    script_path = tmp_path / "generated_layouts.py"
    output_path = tmp_path / "generated_layouts.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_layout = out_doc.layout("Layout1")

    assert len(list(out_layout.query("VIEWPORT"))) == 2


def test_document_to_code_file_preserves_paperspace_layout_metadata(tmp_path):
    source_doc = ezdxf.new("R2010")
    pv1 = source_doc.new_layout("PV-1")
    pv2 = source_doc.new_layout("PV-2")
    source_doc.layouts.set_active_layout("PV-2")
    source_doc.delete_layout("Layout1")
    pv1.dxf.update(
        {
            "page_setup_name": "24x36 Commercial",
            "plot_configuration_file": "DWG To PDF.pc3",
            "paper_size": "ANSI_full_bleed_B_(17.00_x_11.00_Inches)",
            "current_style_sheet": "RAE Plot Style.ctb",
            "paper_width": 431.7999877929687,
            "paper_height": 279.3999938964844,
            "left_margin": 0.0,
            "right_margin": 0.0,
            "top_margin": 0.0,
            "bottom_margin": 0.0,
            "plot_paper_units": 0,
            "plot_layout_flags": 688,
            "limmax": (16.99999951940822, 10.99999975970411, 0.0),
        }
    )
    pv1.add_line((0, 0), (1, 0))
    pv2.add_line((0, 0), (0, 1))

    source_path = tmp_path / "source_layout_metadata.dxf"
    script_path = tmp_path / "generated_layout_metadata.py"
    output_path = tmp_path / "generated_layout_metadata.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_layout_names = list(out_doc.layouts.names())
    out_pv1 = out_doc.layout("PV-1")

    assert "Layout1" not in out_layout_names
    assert "PV-1" in out_layout_names
    assert "PV-2" in out_layout_names
    assert out_doc.layouts.active_layout().name == "PV-2"
    assert out_pv1.dxf.page_setup_name == "24x36 Commercial"
    assert out_pv1.dxf.plot_configuration_file == "DWG To PDF.pc3"
    assert out_pv1.dxf.paper_size == "ANSI_full_bleed_B_(17.00_x_11.00_Inches)"
    assert out_pv1.dxf.current_style_sheet == "RAE Plot Style.ctb"
    assert out_pv1.dxf.paper_width == 431.7999877929687
    assert out_pv1.dxf.paper_height == 279.3999938964844
    assert out_pv1.dxf.left_margin == 0.0
    assert out_pv1.dxf.bottom_margin == 0.0
    assert out_pv1.dxf.plot_paper_units == 0
    assert out_pv1.dxf.plot_layout_flags == 688
    assert tuple(out_pv1.dxf.limmax) == (16.99999951940822, 10.99999975970411, 0.0)


def test_document_to_code_file_restores_extra_rootdict_resources(tmp_path):
    source_doc = ezdxf.new("R2010")
    source_doc.objects.set_raster_variables(frame=1, quality=0, units="m")
    source_doc.objects.set_wipeout_variables(frame=1)
    color_dict = source_doc.rootdict.get_required_dict("ACAD_COLOR")
    color_dict.add_new_dict("TEST_COLOR_FAMILY")

    source_path = tmp_path / "source_rootdict.dxf"
    script_path = tmp_path / "generated_rootdict.py"
    output_path = tmp_path / "generated_rootdict.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    root_handle = out_doc.rootdict.dxf.handle

    assert "ACAD_IMAGE_VARS" in out_doc.rootdict
    assert "ACAD_WIPEOUT_VARS" in out_doc.rootdict
    assert "ACAD_COLOR" in out_doc.rootdict
    assert "TEST_COLOR_FAMILY" in out_doc.rootdict["ACAD_COLOR"]
    assert out_doc.rootdict["ACAD_IMAGE_VARS"].dxf.owner == root_handle
    assert out_doc.rootdict["ACAD_WIPEOUT_VARS"].dxf.owner == root_handle
    assert out_doc.rootdict["ACAD_COLOR"].dxf.owner == root_handle


def test_document_codegen_runtime_remaps_dangling_fieldlist_handles_once():
    from ezdxf.addons.dxf2code import DocumentCodegenRuntime

    runtime_doc = ezdxf.new("R2010")
    line = runtime_doc.modelspace().add_line((0, 0), (1, 0))
    runtime = DocumentCodegenRuntime(runtime_doc)
    runtime.source_entity_map["LINE_SRC"] = line

    mapped = runtime.remap_fieldlist_handles(["LINE_SRC", "DANGLE", "DANGLE"], {"DANGLE"})

    assert mapped[0] == line.dxf.handle
    assert mapped[1] == mapped[2]
    assert mapped[1] != "DANGLE"


def test_document_codegen_runtime_swap_raw_graphic_entity_uses_source_xdata():
    from ezdxf.addons.dxf2code import DocumentCodegenRuntime

    runtime_doc = ezdxf.new("R2010")
    runtime_doc.appids.new("AcadAnnotativeAttributeDecomposition")
    runtime_doc.blocks.new("TARGET")
    host = runtime_doc.blocks.new("HOST")
    insert = host.add_blockref("TARGET", (0, 0))
    insert.set_xdata("AcDbBlockRepETag", [(1070, 1), (1071, 7), (1005, insert.dxf.handle)])

    runtime = DocumentCodegenRuntime(runtime_doc)
    runtime.source_entity_map["SRC_INSERT"] = insert
    runtime.swap_raw_graphic_entity(
        host,
        "SRC_INSERT",
        host.block_record.dxf.handle,
        "",
        [],
        [
            (100, "AcDbEntity"),
            (8, "0"),
            (100, "AcDbBlockReference"),
            (2, "TARGET"),
            (10, 0.0),
            (20, 0.0),
            (30, 0.0),
        ],
        [[
            (1001, "AcadAnnotativeAttributeDecomposition"),
            (1000, "AnnotativeData"),
            (1002, "{"),
            (1070, 1),
            (1005, "SRC_INSERT"),
            (1070, 1),
            (1002, "}"),
        ]],
    )

    swapped = runtime.source_entity_map["SRC_INSERT"]

    assert swapped.has_xdata("AcadAnnotativeAttributeDecomposition") is True
    assert swapped.has_xdata("AcDbBlockRepETag") is False
    assert [(tag.code, tag.value) for tag in swapped.get_xdata("AcadAnnotativeAttributeDecomposition")] == [
        (1000, "AnnotativeData"),
        (1002, "{"),
        (1070, 1),
        (1005, swapped.dxf.handle),
        (1070, 1),
        (1002, "}"),
    ]


def test_document_codegen_runtime_swap_raw_graphic_entity_nulls_dangling_xdata_handles():
    from ezdxf.addons.dxf2code import DocumentCodegenRuntime

    runtime_doc = ezdxf.new("R2010")
    runtime_doc.appids.new("TEST_APP")
    host = runtime_doc.blocks.new("HOST")
    line = host.add_line((0, 0), (1, 0))

    runtime = DocumentCodegenRuntime(runtime_doc)
    runtime.source_entity_map["LINE_SRC"] = line
    runtime.swap_raw_graphic_entity(
        host,
        "LINE_SRC",
        host.block_record.dxf.handle,
        "",
        [],
        [
            (100, "AcDbEntity"),
            (8, "0"),
            (100, "AcDbLine"),
            (10, 0.0),
            (20, 0.0),
            (11, 1.0),
            (21, 0.0),
        ],
        [[(1001, "TEST_APP"), (1005, "DEADBEEF")]],
    )

    swapped = runtime.source_entity_map["LINE_SRC"]

    assert [(tag.code, tag.value) for tag in swapped.get_xdata("TEST_APP")] == [
        (1005, "0")
    ]


def test_document_codegen_runtime_swap_raw_graphic_entity_remaps_source_330_refs():
    from ezdxf.addons.dxf2code import DocumentCodegenRuntime

    runtime_doc = ezdxf.new("R2010")
    runtime_doc.blocks.new("TARGET")
    host = runtime_doc.blocks.new("HOST")
    line = host.add_line((0, 0), (1, 0))
    resource = runtime_doc.modelspace().add_circle((0, 0), 1)
    source_resource_handle = "330_SOURCE_RESOURCE"
    line.dxf.material_handle = resource.dxf.handle

    runtime = DocumentCodegenRuntime(runtime_doc)
    runtime.source_entity_map["LINE_SRC"] = line

    runtime.swap_raw_graphic_entity(
        host,
        "LINE_SRC",
        host.block_record.dxf.handle,
        "",
        [(source_resource_handle, "material_handle")],
        [
            (100, "AcDbEntity"),
            (8, "0"),
            (100, "AcDbLine"),
            (10, 0.0),
            (20, 0.0),
            (11, 1.0),
            (21, 0.0),
            (330, source_resource_handle),
        ],
        [],
    )

    swapped = runtime.source_entity_map["LINE_SRC"]
    swapped_330_refs = [
        str(tag.value)
        for tag in ExtendedTags.from_text(export_text(swapped, runtime_doc.dxfversion))
        if tag.code == 330
    ]

    assert source_resource_handle not in swapped_330_refs
    assert resource.dxf.handle in swapped_330_refs


def test_capture_raw_graphic_entity_swap_rejects_unsupported_multileader():
    from ezdxf.addons.dxf2code._capture import _raw_graphic_entity_can_be_swapped
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2018")
    block = source_doc.blocks.new("UNSUPPORTED_MLEADER_BLOCK")
    builder = block.add_multileader_mtext("Standard")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    mleader = next(entity for entity in block if entity.dxftype() == "MULTILEADER")
    mleader.dxf.text_style_handle = "DEADBEEF"

    assert _raw_graphic_entity_can_be_swapped(mleader) is False
    assert _raw_graphic_entity_can_be_swapped(block.add_line((0, 0), (1, 0))) is True


def test_replay_cleanup_normalizes_unresolved_xdata_handles():
    from ezdxf.dynblkhelper import normalize_unresolved_xdata_handles
    from ezdxf.entities.dxfentity import RAW_TAGS_OVERRIDE_ATTRIBUTE

    doc = ezdxf.new("R2010")
    doc.appids.new("TEST_APP")
    line = doc.modelspace().add_line((0, 0), (1, 0))
    line.set_xdata("TEST_APP", [(1005, "DEADBEEF")])
    setattr(
        line,
        RAW_TAGS_OVERRIDE_ATTRIBUTE,
        "  0\nLINE\n  5\nABC\n330\n0\n100\nAcDbEntity\n  8\n0\n"
        "100\nAcDbLine\n 10\n0.0\n 20\n0.0\n 11\n1.0\n 21\n0.0\n"
        "1001\nTEST_APP\n1005\nDEADBEEF\n",
    )

    normalize_unresolved_xdata_handles(doc)

    assert [(tag.code, tag.value) for tag in line.get_xdata("TEST_APP")] == [
        (1005, "0")
    ]
    assert "1005\n0\n" in getattr(line, RAW_TAGS_OVERRIDE_ATTRIBUTE)


def test_replay_cleanup_syncs_extension_dict_owner_to_exported_handle():
    from ezdxf.dynblkhelper import sync_extension_dict_owners
    from ezdxf.entities.dxfentity import RAW_TAGS_OVERRIDE_ATTRIBUTE

    doc = ezdxf.new("R2010")
    line = doc.modelspace().add_line((0, 0), (1, 0))
    xdict = line.new_extension_dict().dictionary
    xdict.dxf.owner = "BAD"

    sync_extension_dict_owners(doc)

    assert xdict.dxf.owner == line.dxf.handle

    xdict.dxf.owner = "BAD"
    setattr(
        line,
        RAW_TAGS_OVERRIDE_ATTRIBUTE,
        "  0\nLINE\n  5\nABC\n330\n0\n100\nAcDbEntity\n  8\n0\n"
        "100\nAcDbLine\n 10\n0.0\n 20\n0.0\n 11\n1.0\n 21\n0.0\n",
    )

    sync_extension_dict_owners(doc)

    assert xdict.dxf.owner == "ABC"


def test_capture_document_codegen_inputs_returns_typed_specs(tmp_path):
    from ezdxf.addons.dxf2code._capture import capture_document_codegen_inputs
    from ezdxf.addons.dxf2code._specs import MLeaderStyleSpec, VisualStyleEntry

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "TEST_STYLE")
    style.set_xdata("ACAD_MLEADERVER", [(1070, 2)])
    source_doc.rootdict.get_required_dict("ACAD_VISUALSTYLE")

    source_path = tmp_path / "capture_source.dxf"
    source_doc.saveas(source_path)
    loaded = ezdxf.readfile(source_path)

    captured = capture_document_codegen_inputs(loaded, source_path)

    assert "mleader_style_specs" in captured
    assert all(isinstance(spec, MLeaderStyleSpec) for spec in captured["mleader_style_specs"])
    assert all(isinstance(entry, VisualStyleEntry) for entry in captured["visualstyle_entries"])


def test_replay_block_multileader_external_handles_remap_to_target_resources():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_doc.blocks.new("_ClosedBlank")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "RAE SLD Leader (Model Only)")
    style.dxf.name = "Standard"
    style.dxf.block_record_handle = source_doc.blocks.get("_ClosedBlank").block_record_handle
    block = source_doc.blocks.new("MLEADER_BLOCK_SOURCE")
    builder = block.add_multileader_mtext("RAE SLD Leader (Model Only)")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    source_doc.modelspace().add_blockref(block.name, (0, 0))

    new_doc = replay_doc_to_new_doc(source_doc)
    new_block = new_doc.blocks.get("MLEADER_BLOCK_SOURCE")
    assert new_block is not None
    new_entity = next(entity for entity in new_block if entity.dxftype() == "MULTILEADER")
    text = export_text(new_entity, new_doc.dxfversion)
    refs = []
    for tag in ExtendedTags.from_text(text):
        if tag.code not in (340, 342):
            continue
        target = new_doc.entitydb.get(str(tag.value))
        if target is None:
            continue
        name = target.dxf.name if target.dxf.hasattr("name") else ""
        refs.append((tag.code, target.dxftype(), name))

    assert (340, "MLEADERSTYLE", "Standard") in refs
    new_style = new_doc.mleader_styles.get("RAE SLD Leader (Model Only)")
    assert new_style is not None
    assert new_entity.dxf.style_handle == new_style.dxf.handle
    assert new_style.dxf.block_record_handle == new_doc.blocks.get("_ClosedBlank").block_record_handle


def test_document_to_code_file_rebinds_mleader_style_after_late_rootdict_restore(tmp_path):
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_doc.blocks.new("_ClosedBlank")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "RAE Leader [Paper]")
    style.dxf.name = "Standard"
    style.dxf.block_record_handle = source_doc.blocks.get("_ClosedBlank").block_record_handle
    psp = source_doc.layout("Layout1")
    builder = psp.add_multileader_mtext("RAE Leader [Paper]")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    source_path = tmp_path / "source_mleader_style_rebind.dxf"
    script_path = tmp_path / "generated_mleader_style_rebind.py"
    output_path = tmp_path / "generated_mleader_style_rebind.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_entity = next(entity for entity in out_doc.layout("Layout1") if entity.dxftype() == "MULTILEADER")
    out_style = out_doc.mleader_styles.get("RAE Leader [Paper]")

    assert out_style is not None
    assert out_entity.dxf.style_handle == out_style.dxf.handle


def test_document_codegen_runtime_rebinds_raw_mleader_style():
    from ezdxf.addons.dxf2code import DocumentCodegenRuntime
    from ezdxf.entities.dxfentity import DXFTagStorage

    doc = ezdxf.new("R2010")
    style = doc.mleader_styles.duplicate_entry("Standard", "RAE Leader [Paper]")
    raw = DXFTagStorage.load(
        ExtendedTags.from_text(
            "  0\nMULTILEADER\n  5\nABC\n330\n0\n100\nAcDbEntity\n  8\n0\n"
            "100\nAcDbMLeader\n270\n2\n300\nCONTEXT_DATA{\n304\nnote\n"
            "340\nTEXT_STYLE_HANDLE\n301\n}\n340\nOLD_MLEADER_STYLE\n"
        ),
        doc,
    )
    runtime = DocumentCodegenRuntime(doc)
    runtime.source_entity_map["SRC_MLEADER"] = raw

    runtime.restore_mleader_entity_styles([("SRC_MLEADER", "RAE Leader [Paper]")])

    style_handles = [
        tag.value
        for tag in raw.xtags.get_subclass("AcDbMLeader")
        if tag.code == 340
    ]
    assert style_handles == ["TEXT_STYLE_HANDLE", style.dxf.handle]


def test_replay_cleanup_replaces_dynamic_block_acad_tables_with_blockrefs():
    from ezdxf.dynblkhelper import replace_dynamic_block_acad_tables_with_blockrefs

    doc = ezdxf.new("R2018")
    dyn_block = doc.blocks.new("*U900")
    table = dyn_block.add_table((1, 2), [["A"]])
    table.dxf.horizontal_direction = (0, 1, 0)
    table_handle = table.dxf.handle
    table_geometry = table.dxf.geometry
    normal_block = doc.blocks.new("NORMAL_TABLE_BLOCK")
    normal_table = normal_block.add_table((0, 0), [["B"]])

    replace_dynamic_block_acad_tables_with_blockrefs(doc)

    replacement = doc.entitydb.get(table_handle)
    assert replacement is not None
    assert replacement.dxftype() == "INSERT"
    assert replacement.dxf.name == table_geometry
    assert replacement.dxf.owner == dyn_block.block_record_handle
    assert replacement.dxf.rotation == 90.0
    assert all(entity.dxftype() != "ACAD_TABLE" for entity in dyn_block)
    assert normal_table.is_alive
    assert next(entity for entity in normal_block if entity.dxftype() == "ACAD_TABLE") is normal_table


def test_document_codegen_restores_table_geometry_block_contents(tmp_path):
    from ezdxf.addons.dxf2code._capture import capture_document_codegen_inputs
    from ezdxf.addons.dxf2code._emit import render_document_codegen_script

    source_doc = ezdxf.new("R2018")
    dyn_block = source_doc.blocks.new("*U900")
    table = dyn_block.add_table((0, 0), [["A"]])
    geometry_name = table.dxf.geometry
    source_path = tmp_path / "source_dynamic_table_geometry.dxf"
    script_path = tmp_path / "generated_dynamic_table_geometry.py"
    output_path = tmp_path / "generated_dynamic_table_geometry.dxf"
    source_doc.saveas(source_path)

    geometry_block = source_doc.blocks.get(geometry_name)
    geometry_block.delete_all_entities()
    geometry_block.add_mtext("SOURCE GEOMETRY")

    captured = capture_document_codegen_inputs(source_doc, source_path)
    script_path.write_text(
        render_document_codegen_script(captured, output_path), encoding="utf-8"
    )
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_block = out_doc.blocks.get("*U900")
    replacement = next(
        entity
        for entity in out_block
        if entity.dxftype() == "INSERT" and entity.dxf.name == geometry_name
    )
    out_geometry = out_doc.blocks.get(geometry_name)

    assert replacement.dxf.name == geometry_name
    assert [(entity.dxftype(), entity.text) for entity in out_geometry] == [
        ("MTEXT", "SOURCE GEOMETRY")
    ]


def test_dynamic_block_table_raw_restore_remaps_geometry_btr():
    from ezdxf.addons.dxf2code import block_to_code
    from ezdxf.dynblkhelper import (
        DynamicBlockBasePointParameter,
        set_dynamic_block_base_point_parameter,
        set_dynamic_block_definition_metadata,
    )

    source_doc = ezdxf.new("R2018")
    source_block = source_doc.blocks.new("DYN_TABLE")
    source_table = source_block.add_table((0, 0), [["A", "B"]])
    set_dynamic_block_definition_metadata(
        source_block,
        guid="{GUID}",
        true_name="DYN_TABLE",
    )
    set_dynamic_block_base_point_parameter(
        source_block,
        DynamicBlockBasePointParameter(
            handle="",
            label="Base Point",
            location=(0, 0, 0),
            base_point=(0, 0, 0),
            second_point=(0, 0, 0),
            expr_id=0,
        ),
    )

    target_doc = ezdxf.new("R2018")
    target_doc.blocks.new(source_table.dxf.geometry)
    # Advance handles so a stale source BTR does not accidentally point at the
    # regenerated TABLE geometry block.
    target_doc.modelspace().add_line((0, 0), (1, 0))
    code = block_to_code(source_block, drawing="doc", full_document_mode=True)
    execute_code_in_namespace(code, {"ezdxf": ezdxf, "doc": target_doc})
    target_block = target_doc.blocks.get("DYN_TABLE")
    table = next(entity for entity in target_block if entity.dxftype() == "ACAD_TABLE")
    raw_geometry_name = ""
    raw_btr_handles = []
    in_block_reference = False
    for tag in ExtendedTags.from_text(export_text(table, target_doc.dxfversion)):
        if tag.code == 100:
            in_block_reference = tag.value == "AcDbBlockReference"
            continue
        if in_block_reference and tag.code == 2:
            raw_geometry_name = str(tag.value)
        if tag.code == 343:
            raw_btr_handles.append(str(tag.value))
    geometry_block = target_doc.blocks.get(raw_geometry_name)

    assert raw_btr_handles == [geometry_block.block_record_handle]
    assert target_doc.entitydb.get(raw_btr_handles[0]).dxftype() == "BLOCK_RECORD"


def test_document_to_code_file_preserves_acad_table_geometry_block_name(tmp_path):
    source_doc = ezdxf.new("R2018")
    table = source_doc.modelspace().add_table((0, 0), [["A"]])
    source_geometry = "*T42"
    source_doc.blocks.rename_block(table.dxf.geometry, source_geometry)
    table.dxf.geometry = source_geometry

    source_path = tmp_path / "source_table_geometry_name.dxf"
    script_path = tmp_path / "generated_table_geometry_name.py"
    output_path = tmp_path / "generated_table_geometry_name.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    script_text = script_path.read_text(encoding="utf-8")

    assert "replace_dynamic_block_acad_tables_with_blockrefs(doc)" in script_text

    exec(script_text, {})

    out_doc = ezdxf.readfile(output_path)
    out_table = next(entity for entity in out_doc.modelspace() if entity.dxftype() == "ACAD_TABLE")
    out_geometry = out_doc.blocks.get(source_geometry)

    assert out_geometry is not None
    assert out_table.dxf.geometry == source_geometry
    assert out_table.dxf.block_record_handle == out_geometry.block_record_handle


def test_document_to_code_file_remaps_paper_layout_viewport_handle(tmp_path):
    source_doc = ezdxf.new("R2018")
    layout = source_doc.layout("Layout1")
    layout.add_line((0, 0), (1, 0))
    viewport = layout.add_viewport(
        center=(5, 5), size=(10, 10), view_center_point=(0, 0), view_height=10
    )
    layout.dxf.viewport_handle = viewport.dxf.handle

    source_path = tmp_path / "source_layout_viewport.dxf"
    script_path = tmp_path / "generated_layout_viewport.py"
    output_path = tmp_path / "generated_layout_viewport.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_layout = out_doc.layout("Layout1")
    viewport = out_doc.entitydb.get(out_layout.dxf.viewport_handle)

    assert viewport is not None
    assert viewport.dxftype() == "VIEWPORT"
    assert viewport.dxf.owner == out_layout.block_record_handle


def test_document_to_code_file_preserves_paper_layout_block_record_name(tmp_path):
    source_doc = ezdxf.new("R2018")
    layout = source_doc.new_layout("Custom")
    source_block_name = "*Paper_Space42"
    source_doc.blocks.rename_block(layout.block_record.dxf.name, source_block_name)

    source_path = tmp_path / "source_layout_block_name.dxf"
    script_path = tmp_path / "generated_layout_block_name.py"
    output_path = tmp_path / "generated_layout_block_name.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_layout = out_doc.layout("Custom")
    out_block_record = out_doc.entitydb.get(out_layout.block_record_handle)

    assert out_block_record.dxf.name == source_block_name


def test_document_to_code_file_preserves_layout_dictionary_order(tmp_path):
    source_doc = ezdxf.new("R2018")
    source_doc.new_layout("Custom")
    source_order = ["Custom", "Model", "Layout1"]
    layout_dict = source_doc.rootdict["ACAD_LAYOUT"]
    layout_dict._data = {name: layout_dict._data[name] for name in source_order}
    source_doc.layouts._layouts = {
        name.upper(): source_doc.layouts.get(name) for name in source_order
    }

    source_path = tmp_path / "source_layout_order.dxf"
    script_path = tmp_path / "generated_layout_order.py"
    output_path = tmp_path / "generated_layout_order.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    script_text = script_path.read_text(encoding="utf-8")

    assert "rt.restore_layout_order" in script_text
    assert "doc.layouts._dxf_layouts" not in script_text
    assert "doc.layouts._layouts" not in script_text

    exec(script_text, {})

    out_doc = ezdxf.readfile(output_path)

    assert out_doc.layouts.names() == source_order


def test_document_to_code_file_restores_acad_groups(tmp_path):
    source_doc = ezdxf.new("R2018")
    msp = source_doc.modelspace()
    line = msp.add_line((0, 0), (1, 0))
    circle = msp.add_circle((0, 0), radius=1)
    group = source_doc.groups.new("TEST_GROUP")
    group.set_data([line, circle])

    source_path = tmp_path / "source_groups.dxf"
    script_path = tmp_path / "generated_groups.py"
    output_path = tmp_path / "generated_groups.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_group = out_doc.groups.get("TEST_GROUP")

    assert out_group is not None
    assert sorted(entity.dxftype() for entity in out_group) == ["CIRCLE", "LINE"]


def test_document_to_code_file_restores_layout_sortents(tmp_path):
    source_doc = ezdxf.new("R2018")
    layout = source_doc.layout("Layout1")
    first = layout.add_line((0, 0), (1, 0))
    second = layout.add_line((0, 1), (1, 1))
    block = source_doc.blocks.get(layout.block_record.dxf.name)
    xdict = block.block_record.new_extension_dict().dictionary
    sortents = source_doc.objects.new_entity(
        "SORTENTSTABLE",
        dxfattribs={
            "owner": xdict.dxf.handle,
            "block_record_handle": block.block_record.dxf.handle,
        },
    )
    sortents.set_handles([(second.dxf.handle, first.dxf.handle)])
    xdict.add("ACAD_SORTENTS", sortents)

    source_path = tmp_path / "source_layout_sortents.dxf"
    script_path = tmp_path / "generated_layout_sortents.py"
    output_path = tmp_path / "generated_layout_sortents.dxf"
    source_doc.saveas(source_path)

    document_to_code_file(str(source_path), str(script_path), str(output_path))
    exec(script_path.read_text(encoding="utf-8"), {})

    out_doc = ezdxf.readfile(output_path)
    out_layout = out_doc.layout("Layout1")
    out_block = out_doc.blocks.get(out_layout.block_record.dxf.name)
    out_xdict = out_block.block_record.get_extension_dict().dictionary
    out_sortents = out_xdict.get("ACAD_SORTENTS")

    assert out_sortents is not None
    assert len(out_sortents.table) == 1
