from __future__ import annotations

import pytest

import dxfpy
from dxfpy.addons.dxf2code import (
    entities_to_code,
    entities_to_code_with_dependencies,
    namespace_resource_names,
)
from dxfpy.dynblkhelper import set_dynamic_block_definition_metadata
from dxfpy.lldxf.types import dxftag
from dxfpy.math import Vec2
from dxfpy.render.mleader import ConnectionSide
from dxfpy.sections.blocks import is_anonymous_block

from tests.test_08_addons.dxf2code_support import execute_code_in_namespace


def test_dependency_code_recreates_transitive_resources_without_collisions():
    source = _source_with_transitive_resources()
    namespace_resource_names(source, "SOURCE")
    target = _target_with_conflicting_resources()
    target_layout = target.blocks.new("DESTINATION")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target_layout},
    )

    line = target_layout.query("LINE").first
    text = target_layout.query("TEXT").first
    leader = target_layout.query("LEADER").first
    inserted_block = target_layout.query("INSERT").first.block()
    imported_layer = target.layers.get(line.dxf.layer)
    imported_dimstyle = target.dimstyles.get(leader.dxf.dimstyle)
    assert imported_layer.dxf.color == 1
    assert target.layers.get("SHARED").dxf.color == 2
    assert text.dxf.style != "TEXT_STYLE"
    assert imported_dimstyle.dxf.dimblk in target.blocks
    imported_nested = inserted_block.query("INSERT").first.block()
    assert imported_nested.query("LINE").first.dxf.end.x == 99
    assert target.blocks.get("NESTED").query("LINE").first.dxf.end.x == 1


def test_dependency_code_recreates_namespaced_mleader_style():
    source = dxfpy.new("R2018")
    source.mleader_styles.get("Standard").dxf.landing_gap_size = 7
    builder = source.modelspace().add_multileader_mtext()
    builder.set_content("NOTE")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    namespace_resource_names(source, "SOURCE")
    target = dxfpy.new("R2018")
    target.mleader_styles.get("Standard").dxf.landing_gap_size = 123
    target_layout = target.blocks.new("DESTINATION")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target_layout},
    )

    multileader = target_layout.query("MULTILEADER").first
    imported_style = target.entitydb.get(multileader.dxf.style_handle)
    assert imported_style.dxf.landing_gap_size == 7
    assert target.mleader_styles.get("Standard").dxf.landing_gap_size == 123


def test_namespacing_preserves_standard_and_protected_resources():
    source = dxfpy.new("R2018")
    source.layers.new("UNSEEN")
    source.layers.new("CUSTOM")
    unseen = source.modelspace().add_line(
        (0, 0), (1, 0), dxfattribs={"layer": "UNSEEN"}
    )
    custom = source.modelspace().add_line(
        (0, 1), (1, 1), dxfattribs={"layer": "CUSTOM"}
    )

    namespace_resource_names(source, "SOURCE", protected_names={"layers": {"UNSEEN"}})

    assert unseen.dxf.layer == "UNSEEN"
    assert source.layers.get("UNSEEN") is not None
    assert source.layers.get("0") is not None
    assert custom.dxf.layer.startswith("SOURCE_layers_")
    assert "CUSTOM" not in source.layers


def test_namespacing_preserves_distinct_unicode_resource_names():
    source = dxfpy.new("R2018")
    source.layers.new("Straße", dxfattribs={"color": 1})
    source.layers.new("Strasse", dxfattribs={"color": 2})
    first = source.modelspace().add_line((0, 0), (1, 0), dxfattribs={"layer": "Straße"})
    second = source.modelspace().add_line(
        (0, 1), (1, 1), dxfattribs={"layer": "Strasse"}
    )

    namespace_resource_names(source, "SOURCE")

    assert first.dxf.layer != second.dxf.layer
    assert {
        source.layers.get(first.dxf.layer).dxf.color,
        source.layers.get(second.dxf.layer).dxf.color,
    } == {1, 2}


def test_namespacing_avoids_names_already_present_in_source():
    source = dxfpy.new("R2018")
    first = source.layers.new("FIRST", dxfattribs={"color": 1})
    first_index = list(source.layers).index(first)
    colliding_name = f"SOURCE_layers_{first_index}"
    second = source.layers.new(colliding_name, dxfattribs={"color": 2})
    first_line = source.modelspace().add_line(
        (0, 0), (1, 0), dxfattribs={"layer": first.dxf.name}
    )
    second_line = source.modelspace().add_line(
        (0, 1), (1, 1), dxfattribs={"layer": second.dxf.name}
    )

    namespace_resource_names(source, "SOURCE")

    assert first_line.dxf.layer != second_line.dxf.layer
    assert {
        source.layers.get(first_line.dxf.layer).dxf.color,
        source.layers.get(second_line.dxf.layer).dxf.color,
    } == {1, 2}


def test_namespacing_updates_header_table_and_geometry_references():
    source = dxfpy.new("R2018")
    source.layers.new("CUSTOM_LAYER")
    source.linetypes.new("CUSTOM_LTYPE", dxfattribs={"pattern": [0.0]})
    source.styles.new("CUSTOM_STYLE", dxfattribs={"font": "Arial.ttf"})
    source.dimstyles.new("CUSTOM_DIMSTYLE")
    source.header["$CLAYER"] = "CUSTOM_LAYER"
    source.header["$CELTYPE"] = "CUSTOM_LTYPE"
    source.header["$TEXTSTYLE"] = "CUSTOM_STYLE"
    source.header["$DIMSTYLE"] = "CUSTOM_DIMSTYLE"
    leader_arrow = source.blocks.new("LEADER_ARROW")
    leader_arrow.add_line((0, 0), (1, 0))
    source.header["$DIMLDRBLK"] = "LEADER_ARROW"
    table = source.modelspace().add_table((0, 0), [["A"]])
    table.set_cell_text_style(0, 0, "CUSTOM_STYLE")
    viewport = source.layout().add_viewport(
        center=(5, 5),
        size=(10, 10),
        view_center_point=(0, 0),
        view_height=10,
    )
    viewport.freeze("CUSTOM_LAYER")

    namespace_resource_names(source, "SOURCE")

    assert source.header["$CLAYER"] in source.layers
    assert source.header["$CELTYPE"] in source.linetypes
    assert source.header["$TEXTSTYLE"] in source.styles
    assert source.header["$DIMSTYLE"] in source.dimstyles
    assert source.header["$DIMLDRBLK"] in source.blocks
    assert table.dxf.geometry in source.blocks
    assert table.get_cell(0, 0).text_style in source.styles
    assert viewport.frozen_layers == [source.header["$CLAYER"]]


def test_namespacing_handles_maximum_length_mleader_style_names():
    source = dxfpy.new("R2018")
    source.mleader_styles.duplicate_entry("Standard", "OTHER")
    builder = source.modelspace().add_multileader_mtext()
    builder.set_content("NOTE")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    namespace_resource_names(source, "N" * 255)

    names = [name for name, _ in source.mleader_styles]
    multileader = source.modelspace().query("MULTILEADER").first
    assert len(names) == len(set(name.lower() for name in names))
    assert max(map(len, names)) <= 255
    assert source.entitydb.get(multileader.dxf.style_handle).is_alive


def test_dependency_code_ignores_selected_entity_types():
    source = dxfpy.new("R2018")
    source.modelspace().add_line((0, 0), (1, 0))
    source.modelspace().add_text("IGNORE")
    target = dxfpy.new("R2018")
    target_layout = target.blocks.new("DESTINATION")

    code = entities_to_code_with_dependencies(
        source,
        source.modelspace(),
        layout="target_layout",
        ignore={"TEXT"},
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target_layout},
    )

    assert len(target_layout.query("LINE")) == 1
    assert len(target_layout.query("TEXT")) == 0


def test_dependency_code_supports_nondefault_drawing_variable():
    source = dxfpy.new("R2018")
    source.layers.new("CUSTOM")
    source.modelspace().add_line((0, 0), (1, 0), dxfattribs={"layer": "CUSTOM"})
    source.blocks.new("GRANDCHILD").add_line((0, 0), (3, 0))
    source.blocks.new("CHILD").add_blockref("GRANDCHILD", (0, 0))
    source.modelspace().add_blockref("CHILD", (0, 0))
    target = dxfpy.new("R2018")
    target_layout = target.blocks.new("DESTINATION")

    code = entities_to_code_with_dependencies(
        source,
        source.modelspace(),
        layout="target_layout",
        drawing="target_doc",
    )
    execute_code_in_namespace(
        code,
        {
            "dxfpy": dxfpy,
            "target_doc": target,
            "target_layout": target_layout,
        },
    )

    assert target.layers.get("CUSTOM") is not None
    assert len(target_layout.query("LINE")) == 1
    child = target_layout.query("INSERT").first.block()
    assert child.query("INSERT").first.block().query("LINE").first.dxf.end.x == 3


def test_dependency_code_supports_layout_and_drawing_expressions():
    source = dxfpy.new("R2018")
    source.modelspace().add_line((0, 0), (1, 0))
    target = dxfpy.new("R2018")
    target.blocks.new("DESTINATION")

    code = entities_to_code_with_dependencies(
        source,
        source.modelspace(),
        layout="target_doc.blocks.get('DESTINATION')",
        drawing="target_doc",
    )
    execute_code_in_namespace(code, {"dxfpy": dxfpy, "target_doc": target})

    assert len(target.blocks.get("DESTINATION").query("LINE")) == 1


def test_dependency_code_isolates_generated_temporary_variables():
    source = dxfpy.new("R2018")
    source.layers.new("CUSTOM")
    source.modelspace().add_line((0, 0), (1, 0), dxfattribs={"layer": "CUSTOM"})
    target = dxfpy.new("R2018")
    target_layout = target.blocks.new("DESTINATION")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="t", drawing="e"
    )
    execute_code_in_namespace(code, {"dxfpy": dxfpy, "e": target, "t": target_layout})

    assert len(target_layout.query("LINE")) == 1


def test_dependency_code_rebinds_complex_linetype_shape_style():
    source = dxfpy.new("R2018")
    source.styles.add_shx("ltypeshp.shx")
    source.linetypes.new(
        "SHAPE_LTYPE",
        dxfattribs={
            "description": "Shape",
            "length": 1.0,
            "pattern": "A,.25,-.1,[132,ltypeshp.shx,x=-.1,s=.1],-.1,1",
        },
    )
    source.modelspace().add_line((0, 0), (1, 0), dxfattribs={"linetype": "SHAPE_LTYPE"})
    target = dxfpy.new("R2018")
    target_layout = target.blocks.new("DESTINATION")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target_layout},
    )

    linetype = target.linetypes.get("SHAPE_LTYPE")
    shape_style = target.styles.find_shx("ltypeshp.shx")
    assert shape_style is not None
    assert linetype.pattern_tags.get_style_handle() == shape_style.dxf.handle


def test_dependency_code_recreates_rendered_dimension_geometry():
    source = dxfpy.new("R2018")
    dimension = (
        source.modelspace().add_linear_dim(base=(5, 2), p1=(0, 0), p2=(10, 0)).dimension
    )
    dimension.render()
    source_geometry = dimension.dxf.geometry
    namespace_resource_names(source, "SOURCE")
    assert dimension.dxf.geometry != source_geometry
    target = dxfpy.new("R2018")
    target_layout = target.blocks.new("DESTINATION")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target_layout},
    )

    generated = target_layout.query("DIMENSION").first
    assert generated.get_geometry_block() is not None


def test_dependency_code_lets_acad_table_replay_own_its_geometry_block():
    source = dxfpy.new("R2018")
    table = source.modelspace().add_table((0, 0), [["A"]])
    source_geometry = table.dxf.geometry
    target = dxfpy.new("R2018")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    generated = target.modelspace().query("ACAD_TABLE").first
    assert generated.dxf.geometry == source_geometry


def test_namespacing_isolates_table_styles_from_target_collisions():
    source = dxfpy.new("R2018")
    table = source.modelspace().add_table((0, 0), [["A"]])
    namespace_resource_names(source, "SOURCE")
    isolated_name = table.get_table_style().dxf.name
    target = dxfpy.new("R2018")
    target.table_styles.get("Standard").data.title_style.text_height = 99

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    generated = target.modelspace().query("ACAD_TABLE").first
    assert isolated_name != "Standard"
    assert generated.get_table_style().dxf.name == isolated_name
    assert target.table_styles.get("Standard").data.title_style.text_height == 99


def test_dependency_code_rejects_missing_table_resource():
    source = dxfpy.new("R2018")
    line = source.modelspace().add_line((0, 0), (1, 0))
    line.dxf.layer = "MISSING"

    with pytest.raises(dxfpy.DXFStructureError, match="missing layers dependency"):
        entities_to_code_with_dependencies(source, source.modelspace())


def test_dependency_code_rejects_cross_scope_field_reference():
    source = dxfpy.new("R2018")
    line = source.modelspace().add_line((0, 0), (10, 0))
    block = source.blocks.new("FIELD_BLOCK")
    mtext = block.add_mtext("10")
    mtext.new_acobjprop_field(line, "Length", text="10", register_field_list=True)
    source.modelspace().add_blockref(block.name, (0, 0))

    with pytest.raises(dxfpy.DXFStructureError, match="FIELD.*crosses"):
        entities_to_code_with_dependencies(source, source.modelspace())


def test_dependency_code_rejects_attached_attrib_cross_scope_field_reference():
    source = dxfpy.new("R2018")
    line = source.modelspace().add_line((0, 0), (10, 0))
    symbol = source.blocks.new("SYMBOL")
    symbol.add_attdef("TAG", (0, 0))
    outer = source.blocks.new("OUTER")
    insert = outer.add_blockref(symbol.name, (0, 0))
    attrib = insert.add_attrib("TAG", "10", (0, 0))
    attrib.new_acobjprop_field(line, "Length", text="10", register_field_list=True)
    source.modelspace().add_blockref(outer.name, (0, 0))

    with pytest.raises(dxfpy.DXFStructureError, match="FIELD.*crosses"):
        entities_to_code_with_dependencies(source, source.modelspace())


def test_dependency_code_rejects_field_target_that_is_not_translated():
    source = dxfpy.new("R2018")
    mline = source.modelspace().add_mline([(0, 0), (10, 0)])
    mtext = source.modelspace().add_mtext("10")
    mtext.new_acobjprop_field(mline, "Length", text="10", register_field_list=True)

    with pytest.raises(dxfpy.DXFStructureError, match="FIELD.*crosses"):
        entities_to_code_with_dependencies(source, source.modelspace())


def test_dependency_code_rejects_field_targeting_own_block_record():
    source = dxfpy.new("R2018")
    block = source.blocks.new("FIELD_BLOCK_RECORD")
    mtext = block.add_mtext("0")
    mtext.new_acobjprop_field(
        block.block_record, "Units", text="0", register_field_list=True
    )
    source.modelspace().add_blockref(block.name, (0, 0))

    with pytest.raises(dxfpy.DXFStructureError, match="FIELD.*crosses"):
        entities_to_code_with_dependencies(source, source.modelspace())


def test_dependency_code_collects_raw_dynamic_block_resources():
    source = dxfpy.new("R2018")
    source.dimstyles.new("CUSTOM_DIM")
    block = source.blocks.new("DYNAMIC_BLOCK")
    block.add_leader([(0, 0), (1, 1)], dimstyle="CUSTOM_DIM")
    set_dynamic_block_definition_metadata(block, guid="{G}", true_name=block.name)
    source.modelspace().add_blockref(block.name, (0, 0))
    target = dxfpy.new("R2018")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    assert target.dimstyles.get("CUSTOM_DIM") is not None
    assert (
        target.blocks.get(block.name).query("LEADER").first.dxf.dimstyle == "CUSTOM_DIM"
    )


def test_dependency_code_remaps_raw_dynamic_table_block_cell(tmp_path):
    source = dxfpy.new("R2018")
    cell_block = source.blocks.new("CELL_BLOCK")
    cell_block.add_attdef("NAME", (0, 0), text="unset")
    dynamic = source.blocks.new("DYNAMIC_TABLE")
    table = dynamic.add_table((0, 0), [[""]])
    table.set_cell_block(0, 0, cell_block.name)
    table.set_cell_block_attribs(0, 0, {"NAME": "Widget"})
    set_dynamic_block_definition_metadata(
        dynamic, guid="{TABLE}", true_name=dynamic.name
    )
    source.modelspace().add_blockref(dynamic.name, (0, 0))
    source_path = tmp_path / "raw_dynamic_table_block_cell_source.dxf"
    source.saveas(source_path)
    source = dxfpy.readfile(source_path)
    dynamic = source.blocks.get("DYNAMIC_TABLE")
    target = dxfpy.new("R2018")
    for index in range(12):
        target.layers.new(f"SHIFT_{index}")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    generated = target.blocks.get(dynamic.name).query("ACAD_TABLE").first
    cell = generated.get_cell(0, 0)
    shell = target.entitydb.get(cell.block_record_handle)
    assert shell is not None
    assert shell.dxftype() == "BLOCK_RECORD"
    assert target.blocks.get(shell.dxf.name) is not None

    output = tmp_path / "raw_dynamic_table_block_cell.dxf"
    target.saveas(output)
    loaded = dxfpy.readfile(output)
    loaded_table = loaded.blocks.get(dynamic.name).query("ACAD_TABLE").first
    linked_cell = loaded_table.get_linked_cell(0, 0)
    linked_content = next(
        content for content in linked_cell.contents if content.is_block_content
    )
    linked_block = loaded.entitydb.get(linked_content.block_record_handle)
    assert linked_block is not None
    assert linked_block.dxftype() == "BLOCK_RECORD"
    for attribute in linked_content.block_attributes:
        assert loaded.entitydb.get(attribute.handle).dxftype() == "ATTDEF"


def test_dependency_code_emits_dynamic_representation_base_first():
    source = dxfpy.new("R2018")
    base = source.blocks.new("DYNAMIC_BASE")
    base.add_line((0, 0), (2, 0))
    set_dynamic_block_definition_metadata(base, guid="{BASE}", true_name=base.name)
    representation = source.blocks.new("*U900")
    representation.add_line((0, 0), (3, 0))
    representation.block_record.set_xdata(
        "AcDbBlockRepBTag", [(1005, base.block_record_handle)]
    )
    source.modelspace().add_blockref(representation.name, (0, 0))
    target = dxfpy.new("R2018")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    assert target.blocks.get(base.name) is not None
    assert target.blocks.get(representation.name) is not None


def test_dependency_code_rejects_missing_dynamic_representation_base():
    source = dxfpy.new("R2018")
    representation = source.blocks.new("*U901")
    representation.add_line((0, 0), (3, 0))
    representation.block_record.set_xdata("AcDbBlockRepBTag", [(1005, "DEADBEEF")])
    source.modelspace().add_blockref(representation.name, (0, 0))

    with pytest.raises(
        dxfpy.DXFStructureError, match="missing dynamic base block dependency"
    ):
        entities_to_code_with_dependencies(source, source.modelspace())


def test_dependency_code_collects_block_marker_resources():
    source = dxfpy.new("R2018")
    source.layers.new("BLOCK_LAYER")
    block = source.blocks.new("CUSTOM_BLOCK")
    block.block.dxf.layer = "BLOCK_LAYER"
    block.add_line((0, 0), (1, 0))
    source.modelspace().add_blockref(block.name, (0, 0))
    target = dxfpy.new("R2018")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    assert target.layers.get("BLOCK_LAYER") is not None
    assert target.blocks.get(block.name).block.dxf.layer == "BLOCK_LAYER"


def test_namespacing_updates_embedded_mtext_and_mline_style_resources():
    source = dxfpy.new("R2018")
    source.styles.new("CUSTOM_STYLE")
    source.linetypes.new("CUSTOM_LTYPE", dxfattribs={"pattern": [0.0]})
    attdef = source.blocks.new("ATTRIBUTES").add_attdef("TAG", (0, 0))
    mtext = source.modelspace().add_mtext("X", dxfattribs={"style": "CUSTOM_STYLE"})
    attdef.embed_mtext(mtext)
    mline_style = source.mline_styles.get("Standard")
    mline_style.elements.append(0.0, linetype="CUSTOM_LTYPE")

    namespace_resource_names(source, "SOURCE")

    assert attdef.virtual_mtext_entity().dxf.style in source.styles
    assert mline_style.elements[-1].linetype in source.linetypes


def test_namespacing_preserves_anonymous_block_classification():
    source = dxfpy.new("R2018")
    dimension = (
        source.modelspace().add_linear_dim(base=(5, 2), p1=(0, 0), p2=(10, 0)).dimension
    )
    dimension.render()

    namespace_resource_names(source, "SOURCE")
    geometry = dimension.dxf.geometry
    source.blocks.delete_all_blocks()

    assert is_anonymous_block(geometry)
    assert geometry in source.blocks


def test_dependency_code_does_not_mutate_existing_shx_style():
    source = dxfpy.new("R2018")
    source.styles.add_shx("ltypeshp.shx", dxfattribs={"last_height": 2.5})
    source.linetypes.new(
        "SHAPE_LTYPE",
        dxfattribs={
            "description": "Shape",
            "length": 1.0,
            "pattern": "A,.25,-.1,[132,ltypeshp.shx,x=-.1,s=.1],-.1,1",
        },
    )
    source.modelspace().add_line((0, 0), (1, 0), dxfattribs={"linetype": "SHAPE_LTYPE"})
    target = dxfpy.new("R2018")
    existing = target.styles.add_shx("ltypeshp.shx")
    existing.dxf.last_height = 9.0

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    assert existing.dxf.last_height == 9.0


def test_dependency_code_escapes_apostrophes_in_resource_names():
    source = dxfpy.new("R2018")
    source.layers.new("O'Brien")
    source.modelspace().add_line((0, 0), (1, 0), dxfattribs={"layer": "O'Brien"})
    target = dxfpy.new("R2018")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    assert target.layers.get("O'Brien") is not None


def test_dependency_code_escapes_encoded_unicode_block_names():
    source = dxfpy.new("R2018")
    block_name = r"\U+00FC"
    source.blocks.new(block_name).add_line((0, 0), (1, 0))
    source.modelspace().add_blockref(block_name, (0, 0))
    target = dxfpy.new("R2018")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    assert target.blocks.get(block_name) is not None


def test_dependency_code_remaps_forward_xdata_handle_reference():
    source = dxfpy.new("R2018")
    source.appids.new("HANDLE_TEST")
    first = source.modelspace().add_line((0, 0), (1, 0))
    second = source.modelspace().add_line((0, 1), (1, 1))
    first.set_xdata("HANDLE_TEST", [(1005, second.dxf.handle)])
    target = dxfpy.new("R2018")
    target.layers.new("SHIFT_HANDLES")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    generated = list(target.modelspace().query("LINE"))
    mapped_handle = generated[0].get_xdata("HANDLE_TEST").get_first_value(1005)
    assert mapped_handle == generated[1].dxf.handle


def test_dependency_code_persists_remapped_insert_and_attrib_xdata(tmp_path):
    source = dxfpy.new("R2018")
    source.appids.new("HANDLE_TEST")
    block = source.blocks.new("XDATA_BLOCK")
    block.add_attdef("TAG", (0, 0))
    insert = source.modelspace().add_blockref(block.name, (0, 0))
    attrib = insert.add_attrib("TAG", "VALUE", (0, 0))
    insert_target = source.modelspace().add_line((0, 1), (1, 1))
    attrib_target = source.modelspace().add_line((0, 2), (1, 2))
    insert.set_xdata("HANDLE_TEST", [(1005, insert_target.dxf.handle)])
    attrib.set_xdata("HANDLE_TEST", [(1005, attrib_target.dxf.handle)])
    target = dxfpy.new("R2018")
    for index in range(8):
        target.layers.new(f"SHIFT_{index}")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )
    output = tmp_path / "insert_xdata.dxf"
    target.saveas(output)
    loaded = dxfpy.readfile(output)

    loaded_insert = loaded.modelspace().query("INSERT").first
    loaded_lines = list(loaded.modelspace().query("LINE"))
    insert_handle = loaded_insert.get_xdata("HANDLE_TEST").get_first_value(1005)
    attrib_handle = (
        loaded_insert.attribs[0].get_xdata("HANDLE_TEST").get_first_value(1005)
    )
    assert insert_handle == loaded_lines[0].dxf.handle
    assert attrib_handle == loaded_lines[1].dxf.handle


def test_entities_to_code_does_not_map_ignored_entity_handles():
    source = dxfpy.new("R2018")
    source.appids.new("HANDLE_TEST")
    line = source.modelspace().add_line((0, 0), (1, 0))
    ignored = source.modelspace().add_circle((0, 0), 1)
    line.set_xdata("HANDLE_TEST", [(1005, ignored.dxf.handle)])
    target = dxfpy.new("R2018")

    code = entities_to_code(
        source.modelspace(), layout="target_layout", ignore={"CIRCLE"}
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    generated = target.modelspace().query("LINE").first
    referenced_handle = generated.get_xdata("HANDLE_TEST").get_first_value(1005)
    assert referenced_handle == ignored.dxf.handle
    assert referenced_handle != generated.dxf.handle
    assert target.entitydb.get(referenced_handle) is None
    assert len(target.modelspace().query("CIRCLE")) == 0


def test_dependency_code_maps_existing_standard_resource_handle():
    source = dxfpy.new("R2018")
    source_style = source.styles.get("Standard")
    assert source.entitydb.reset_handle(source_style, "ABC")
    block = source.blocks.new("DYNAMIC_BLOCK")
    block.add_text("TEXT", dxfattribs={"style": "Standard"})
    set_dynamic_block_definition_metadata(
        block, guid="{G}", true_name=block.name
    )
    xrecord = block.block_record.new_extension_dict().dictionary.add_xrecord(
        "STYLE_REF"
    )
    xrecord.tags.extend([(330, source_style.dxf.handle)])
    source.modelspace().add_blockref(block.name, (0, 0))
    target = dxfpy.new("R2018")
    target_style = target.styles.get("Standard")

    code = entities_to_code_with_dependencies(
        source, source.modelspace(), layout="target_layout"
    )
    execute_code_in_namespace(
        code,
        {"dxfpy": dxfpy, "doc": target, "target_layout": target.modelspace()},
    )

    generated = target.blocks.get(block.name)
    restored = generated.block_record.get_extension_dict().dictionary.get(
        "STYLE_REF"
    )
    restored_handle = next(tag.value for tag in restored.tags if tag.code == 330)
    assert restored_handle == target_style.dxf.handle


@pytest.mark.parametrize("argument", ["layout", "drawing"])
def test_dependency_code_requires_valid_expressions(argument):
    source = dxfpy.new("R2018")
    arguments = {argument: "doc["}

    with pytest.raises(ValueError):
        entities_to_code_with_dependencies(source, source.modelspace(), **arguments)


@pytest.mark.parametrize("argument", ["layout", "drawing"])
def test_dependency_code_rejects_blank_expressions(argument):
    source = dxfpy.new("R2018")

    with pytest.raises(ValueError):
        entities_to_code_with_dependencies(source, (), **{argument: ""})


@pytest.mark.parametrize("expression", ["await get_doc()", "(yield 1)"])
def test_dependency_code_rejects_context_dependent_expressions(expression):
    source = dxfpy.new("R2018")

    with pytest.raises(ValueError):
        entities_to_code_with_dependencies(source, (), drawing=expression)


def test_dependency_code_rejects_missing_dimstyle_nested_resource():
    source = dxfpy.new("R2018")
    dimstyle = source.dimstyles.new("BROKEN_DIMSTYLE")
    dimstyle.dxf.dimtxsty = "MISSING_STYLE"
    source.modelspace().add_leader([(0, 0), (1, 1)], dimstyle=dimstyle.dxf.name)

    with pytest.raises(dxfpy.DXFStructureError, match="missing styles dependency"):
        entities_to_code_with_dependencies(source, source.modelspace())


def test_dependency_code_rejects_missing_complex_linetype_style():
    source = dxfpy.new("R2018")
    linetype = source.linetypes.new(
        "BROKEN_LINETYPE", dxfattribs={"pattern": [1.0, 0.5, -0.5]}
    )
    linetype.pattern_tags.tags.append(dxftag(340, "DEADBEEF"))
    source.modelspace().add_line(
        (0, 0), (1, 0), dxfattribs={"linetype": linetype.dxf.name}
    )

    with pytest.raises(dxfpy.DXFStructureError, match="missing styles dependency"):
        entities_to_code_with_dependencies(source, source.modelspace())


def test_namespacing_rejects_unsupported_protected_table():
    with pytest.raises(ValueError):
        namespace_resource_names(
            dxfpy.new("R2018"),
            "SOURCE",
            protected_names={"blocks": {"KEEP"}},
        )


def _source_with_transitive_resources():
    source = dxfpy.new("R2018")
    source.styles.new("PATTERN_STYLE", dxfattribs={"font": "Arial.ttf"})
    source.styles.new("TEXT_STYLE", dxfattribs={"font": "Arial.ttf"})
    source.linetypes.new(
        "CUSTOM_LT",
        dxfattribs={
            "description": "Custom",
            "length": 1.0,
            "pattern": (
                'A,.5,-.2,["TXT",PATTERN_STYLE,S=.1,' "U=0.0,X=-.1,Y=-.05],-.25"
            ),
        },
    )
    source.layers.new("SHARED", dxfattribs={"color": 1, "linetype": "CUSTOM_LT"})
    arrow = source.blocks.new("CUSTOM_ARROW")
    arrow.add_line((0, 0), (3, 0))
    nested = source.blocks.new("NESTED")
    nested.add_line((0, 0), (99, 0))
    outer = source.blocks.new("OUTER")
    outer.add_blockref("NESTED", (0, 0))
    source.dimstyles.new("CUSTOM_DIM", dxfattribs={"dimblk": "CUSTOM_ARROW"})
    source.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "SHARED"})
    source.modelspace().add_text("TEXT", dxfattribs={"style": "TEXT_STYLE"})
    source.modelspace().add_leader([(0, 0), (1, 1)], dimstyle="CUSTOM_DIM")
    source.modelspace().add_blockref("OUTER", (0, 0))
    return source


def _target_with_conflicting_resources():
    target = dxfpy.new("R2018")
    target.layers.new("SHARED", dxfattribs={"color": 2})
    target.styles.new("TEXT_STYLE", dxfattribs={"font": "txt.shx"})
    target.blocks.new("NESTED").add_line((0, 0), (1, 0))
    return target
