# Copyright (c) 2019 Manfred Moitzi
# License: MIT License

import ezdxf
from ezdxf.addons.dxf2code import document_to_code_file
from ezdxf.dynblkhelper import restore_raw_entity_export, snapshot_raw_entity_export, snapshot_raw_extension_subtree
from ezdxf.lldxf.extendedtags import ExtendedTags
from ezdxf.math import Vec2

from tests.test_08_addons.dxf2code_support import (
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
    assert new_style.dxf.block_record_handle == new_doc.blocks.get("_ClosedBlank").block_record_handle
