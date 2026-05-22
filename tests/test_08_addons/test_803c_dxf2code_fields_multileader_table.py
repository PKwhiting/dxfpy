# Copyright (c) 2019 Manfred Moitzi
# License: MIT License
from io import StringIO

import ezdxf
from ezdxf.addons.dxf2code import block_to_code, entities_to_code
from ezdxf.entities.dxfobj import Field
from ezdxf.lldxf.extendedtags import ExtendedTags
from ezdxf.lldxf.tagwriter import TagWriter
from ezdxf.math import Vec2

from tests.test_08_addons.dxf2code_support import (
    cmp_vertices,
    execute_code_in_namespace,
    execute_entities_code_in_doc,
    translate_entities_to_new_layout,
)


def test_text_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    text = source_msp.add_text("----")
    child, _ = text.new_acvar_field("Author", text="----", register_field_list=True)

    new_doc, new_msp = translate_entities_to_new_layout([text])
    new_text = new_msp[-1]
    new_child = new_text.get_primary_field("TEXT")

    assert new_text.dxf.text == text.dxf.text
    assert new_child.field_code == child.field_code
    assert new_doc.objects.get_field_list() is not None


def test_mtext_object_property_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (2, 0))
    mtext = source_msp.add_mtext("0")
    child, _ = mtext.new_acobjprop_field(line, "Length", register_field_list=True)

    _, new_msp = translate_entities_to_new_layout([line, mtext])
    new_line = new_msp[0]
    new_mtext = new_msp[1]
    new_child = new_mtext.get_primary_field("TEXT")

    assert new_child.field_code == child.field_code
    assert new_child.object_handles == [new_line.dxf.handle]


def test_text_acexpr_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (10, 0))
    circle = source_msp.add_circle((5, 0), radius=2.5)
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    text = source_msp.add_text_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    _, new_msp = translate_entities_to_new_layout([line, circle, text])
    new_line = new_msp[0]
    new_circle = new_msp[1]
    new_text = new_msp[2]
    new_expr = new_text.get_primary_field("TEXT")

    assert new_expr is not None
    assert new_expr.evaluator_id == "AcExpr"
    assert new_expr.field_code == '\\AcExpr (%<\\_FldIdx 0>%*%<\\_FldIdx 1>%) \\f "%lu2"'
    children = new_expr.get_child_fields()
    assert len(children) == 2
    assert children[0].object_handles == [new_line.dxf.handle]
    assert children[1].object_handles == [new_circle.dxf.handle]


def test_mtext_acexpr_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (10, 0))
    circle = source_msp.add_circle((5, 0), radius=2.5)
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    mtext = source_msp.add_mtext_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    _, new_msp = translate_entities_to_new_layout([line, circle, mtext])
    new_line = new_msp[0]
    new_circle = new_msp[1]
    new_mtext = new_msp[2]
    new_expr = new_mtext.get_primary_field("TEXT")

    assert new_expr is not None
    assert new_expr.evaluator_id == "AcExpr"
    children = new_expr.get_child_fields()
    assert len(children) == 2
    assert children[0].object_handles == [new_line.dxf.handle]
    assert children[1].object_handles == [new_circle.dxf.handle]


def test_insert_attrib_field_to_code():
    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    insert = source_msp.add_blockref("TEST", (0, 0))
    attrib = insert.add_attrib("TAG", "VALUE", (0, 0))
    child, _ = attrib.new_dwgprops_field(
        "ProjectCode",
        value="VALUE-123",
        text="VALUE-123",
        register_field_list=True,
    )

    new_doc, new_msp = translate_entities_to_new_layout([insert])
    new_insert = next(entity for entity in new_msp if entity.dxftype() == "INSERT")
    new_attrib = new_insert.attribs[0]
    new_child = new_attrib.get_primary_field("TEXT")

    assert new_child.field_code == child.field_code
    assert new_doc.header.custom_vars.get("ProjectCode") == "VALUE-123"


def test_multileader_mtext_to_code():
    from ezdxf.render.mleader import ConnectionSide, TextAlignment

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note", color=3, char_height=2.5, alignment=TextAlignment.right)
    builder.set_connection_properties(landing_gap=2.0, dogleg_length=4.0)
    builder.set_overall_scaling(1.25)
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    _, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]

    assert new_ml.dxftype() == "MULTILEADER"
    assert new_ml.context.mtext is not None
    assert new_ml.context.mtext.default_content == "note"
    assert new_ml.context.mtext.alignment == 3
    assert new_ml.context.char_height == builder.multileader.context.char_height
    assert len(new_ml.context.leaders) == 1
    assert len(new_ml.context.leaders[0].lines) == 1
    assert cmp_vertices(
        new_ml.context.leaders[0].lines[0].vertices,
        builder.multileader.context.leaders[0].lines[0].vertices,
    ) is True
    assert len(list(new_ml.virtual_entities())) == len(list(builder.multileader.virtual_entities()))


def test_multileader_field_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    child, _ = builder.set_acvar_field("Author", text="----", register_field_list=True)
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_child = new_ml.get_primary_field("TEXT")

    assert new_ml.context.mtext is not None
    assert new_ml.context.mtext.default_content == "----"
    assert new_child is not None
    assert new_child.field_code == child.field_code
    assert new_doc.objects.get_field_list() is not None


def test_multileader_to_code_preserves_proxy_graphic_payload():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    builder.multileader.proxy_graphic = b"\x01\x02\x03\x04"

    _, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    stream = StringIO()
    new_ml.export_dxf(TagWriter(stream, dxfversion=new_ml.doc.dxfversion))
    text = stream.getvalue().replace("\r\n", "\n")

    assert new_ml.proxy_graphic == builder.multileader.proxy_graphic
    assert "\n 92\n4\n310\n01020304\n" in text


def test_multileader_to_code_does_not_inject_version_tag_when_source_omits_it():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    _, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    stream = StringIO()
    new_ml.export_dxf(TagWriter(stream, dxfversion=new_ml.doc.dxfversion))
    text = stream.getvalue().replace("\r\n", "\n")

    assert new_ml.dxf.hasattr("version") is False
    assert "\n270\n2\n" not in text


def test_multileader_to_code_tolerates_unresolved_leader_linetype_handle():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "BROKEN_LT_STYLE")
    style.dxf.leader_linetype_handle = "25"
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("BROKEN_LT_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    builder.multileader.dxf.leader_linetype_handle = "25"

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_style = new_doc.mleader_styles.get("BROKEN_LT_STYLE")

    assert new_ml.dxftype() == "MULTILEADER"
    assert new_style is not None
    assert new_ml.dxf.style_handle == new_style.dxf.handle


def test_multileader_acexpr_field_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (10, 0))
    circle = source_msp.add_circle((5, 0), radius=2.5)
    builder = source_msp.add_multileader_mtext()
    builder.set_content("TEXT")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    multileader = builder.multileader
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    multileader.new_acexpr_field(
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    _, new_msp = translate_entities_to_new_layout([line, circle, multileader])
    new_line = new_msp[0]
    new_circle = new_msp[1]
    new_ml = new_msp[2]
    new_expr = new_ml.get_primary_field("TEXT")

    assert new_ml.get_mtext_content() == "25.0000"
    assert new_expr is not None
    assert new_expr.evaluator_id == "AcExpr"
    children = new_expr.get_child_fields()
    assert len(children) == 2
    assert children[0].object_handles == [new_line.dxf.handle]
    assert children[1].object_handles == [new_circle.dxf.handle]


def test_multileader_custom_style_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "MY_STYLE")
    style.dxf.default_text_content = "STYLE_TEXT"
    style.dxf.char_height = 3.5
    style.dxf.text_alignment_type = 1
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("MY_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_style = new_doc.mleader_styles.get("MY_STYLE")

    assert new_style is not None
    assert new_style.dxf.default_text_content == "STYLE_TEXT"
    assert new_style.dxf.char_height == 3.5
    assert new_style.dxf.text_alignment_type == 1
    assert new_ml.dxf.style_handle == new_style.dxf.handle


def test_multileader_custom_style_to_code_does_not_inherit_standard_extension_dict():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    standard = source_doc.mleader_styles.get("Standard")
    assert standard is not None
    if not standard.has_extension_dict:
        xdict = standard.new_extension_dict()
        xdict.dictionary.add_xrecord("ACAD_XREC_ROUNDTRIP")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "CUSTOM_NO_XDICT")
    if style.has_extension_dict:
        style.discard_extension_dict()
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("CUSTOM_NO_XDICT")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_style = new_doc.mleader_styles.get("CUSTOM_NO_XDICT")

    assert new_ml.dxftype() == "MULTILEADER"
    assert new_style is not None
    assert new_style.has_extension_dict is False


def test_multileader_custom_style_arrow_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "ARROW_STYLE")
    style.set_arrow_head("DOT")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("ARROW_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    new_style = new_doc.mleader_styles.get("ARROW_STYLE")

    assert new_style is not None
    assert new_style.dxf.arrow_head_handle is not None
    assert new_doc.entitydb.get(new_style.dxf.arrow_head_handle).dxf.name == "_DOT"
    assert new_ml.dxf.style_handle == new_style.dxf.handle


def test_multileader_arrow_override_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note")
    builder.set_arrow_properties(name="DOT", size=2.0)
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]

    assert new_ml.dxf.arrow_head_handle is not None
    assert new_doc.entitydb.get(new_ml.dxf.arrow_head_handle).dxf.name == "_DOT"


def test_multileader_arrow_heads_to_code():
    from ezdxf.entities.mleader import ArrowHeadData
    from ezdxf.render.arrows import ARROWS
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))
    multileader = builder.multileader
    multileader.arrow_heads = [
        ArrowHeadData(0, ARROWS.arrow_handle(source_doc.blocks, "DOT")),
        ArrowHeadData(1, ARROWS.arrow_handle(source_doc.blocks, "OPEN")),
    ]

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_ml = new_msp[-1]
    arrow0, arrow1 = new_ml.arrow_heads

    assert len(new_ml.arrow_heads) == 2
    assert arrow0.index == 0
    assert arrow1.index == 1
    assert new_doc.entitydb.get(arrow0.handle).dxf.name == "_DOT"
    assert new_doc.entitydb.get(arrow1.handle).dxf.name == "_OPEN"


def test_multileader_custom_style_block_reference_missing_is_safe():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "STYLE_BLOCK_STYLE")
    source_doc.blocks.new("STYLE_BLOCK")
    style.dxf.block_record_handle = source_doc.blocks.get("STYLE_BLOCK").block_record_handle
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("STYLE_BLOCK_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_style = new_doc.mleader_styles.get("STYLE_BLOCK_STYLE")

    assert new_style is not None
    assert new_style.dxf.hasattr("block_record_handle") is False
    assert new_msp[-1].dxftype() == "MULTILEADER"


def test_multileader_custom_style_block_reference_preserved_if_available():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "STYLE_BLOCK_STYLE")
    source_doc.blocks.new("STYLE_BLOCK")
    style.dxf.block_record_handle = source_doc.blocks.get("STYLE_BLOCK").block_record_handle
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_mtext("STYLE_BLOCK_STYLE")
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(-5, 0), Vec2(-2, 0)])
    builder.build(insert=Vec2(0, 0))

    target_doc = ezdxf.new("R2010")
    target_doc.blocks.new("STYLE_BLOCK")
    new_doc, _ = execute_entities_code_in_doc(source_msp, target_doc)
    new_style = new_doc.mleader_styles.get("STYLE_BLOCK_STYLE")

    assert new_style is not None
    assert new_style.dxf.block_record_handle == new_doc.blocks.get("STYLE_BLOCK").block_record_handle


def test_multileader_block_content_to_code():
    from ezdxf.render.mleader import ConnectionSide

    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("TEST_BLOCK")
    block.add_lwpolyline([(0, 0), (1, 0), (1, 1), (0, 1)], close=True)
    block.add_attdef("ONE", insert=(0, 0), text="ONE")
    block.add_attdef("TWO", insert=(1, 1), text="TWO")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "BLOCK_STYLE")
    style.dxf.block_record_handle = block.block_record_handle
    source_msp = source_doc.modelspace()
    builder = source_msp.add_multileader_block("BLOCK_STYLE")
    builder.set_content(name="TEST_BLOCK")
    builder.set_attribute("ONE", "Data1")
    builder.set_attribute("TWO", "Data2")
    builder.add_leader_line(ConnectionSide.right, [Vec2(5, 0)])
    builder.build(insert=Vec2(0, 0))

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)
    execute_code_in_namespace(entities_to_code(source_msp, layout="msp"), namespace)

    new_doc = namespace["doc"]
    new_msp = namespace["msp"]
    new_ml = new_msp[-1]
    new_block = new_doc.blocks.get("TEST_BLOCK")
    new_style = new_doc.mleader_styles.get("BLOCK_STYLE")
    attdef0, attdef1 = list(new_block.attdefs())
    block_attrib0, block_attrib1 = new_ml.block_attribs

    assert new_ml.dxftype() == "MULTILEADER"
    assert new_style is not None
    assert new_style.dxf.block_record_handle == new_block.block_record_handle
    assert new_ml.dxf.block_record_handle == new_block.block_record_handle
    assert new_ml.context.block is not None
    assert new_ml.context.block.block_record_handle == new_block.block_record_handle
    assert block_attrib0.handle == attdef0.dxf.handle
    assert block_attrib1.handle == attdef1.dxf.handle
    assert block_attrib0.text == "Data1"
    assert block_attrib1.text == "Data2"


def test_acad_table_text_surface_to_code():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    table = source_msp.add_table(
        (1, 2),
        [["TITLE", "STATUS"], ["HEADER", "VALUE"], ["DATA", "OK"]],
        row_heights=[11.0, 9.0, 9.0],
        col_widths=[38.0, 28.0],
    )
    table.set_row_height(0, 20.0)
    table.set_col_width(1, 30.0)
    table.set_title_suppressed(True)
    table.set_cell_text(1, 1, "VALUE-LONG")
    table.set_cell_text_height(0, 0, 20.0)
    table.set_cell_alignment(0, 1, 4)
    table.set_cell_content_color(1, 0, 215, 10507177)
    table.set_cell_fill_color(0, 1, 177, 3811732)
    table.clear_cell_fill(0, 1)

    new_doc, new_msp = translate_entities_to_new_layout(source_msp)
    new_table = next(entity for entity in new_msp if entity.dxftype() == "ACAD_TABLE")

    assert new_table.data is not None
    assert new_table.dxf.insert == table.dxf.insert
    assert new_table.data.row_heights == table.data.row_heights
    assert new_table.data.col_widths == table.data.col_widths
    assert new_table.data.suppress_title == table.data.suppress_title
    assert new_table.data.suppress_column_header == table.data.suppress_column_header
    assert [cell.text for cell in new_table.data.cells] == [cell.text for cell in table.data.cells]

    src_cells = table.data.cells
    dst_cells = new_table.data.cells
    assert dst_cells[0].text_height == src_cells[0].text_height
    assert dst_cells[1].alignment == src_cells[1].alignment
    assert dst_cells[1].fill_enabled == 1
    assert dst_cells[1].fill_color == 0
    assert dst_cells[2].text == src_cells[2].text

    assert len(list(new_table.virtual_entities())) == len(list(table.virtual_entities()))
    assert new_doc.table_styles.get("Standard") is not None


def test_acad_table_minimal_block_cell_to_code():
    source_doc = ezdxf.new("R2018")
    block = source_doc.blocks.new("TABLE_BLOCK_CELL_MIN", base_point=(0, 0))
    block.add_lwpolyline([(0, 0), (2, 0), (2, 2), (0, 2)], close=True)
    source_msp = source_doc.modelspace()
    table = source_msp.add_table((0, 0), [["T"], ["H"], [""]])
    table.set_cell_block(2, 0, "TABLE_BLOCK_CELL_MIN", block_scale=1.0, alignment=1)

    target_doc = ezdxf.new("R2018")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)
    execute_code_in_namespace(entities_to_code(source_msp, layout="msp"), namespace)

    new_table = next(entity for entity in namespace["msp"] if entity.dxftype() == "ACAD_TABLE")
    new_cell = new_table.get_cell(2, 0)

    assert new_cell.is_block_cell is True
    assert new_cell.block_scale == 1.0
    assert new_cell.alignment == 1
    assert new_table.get_cell_block_name(2, 0) == "TABLE_BLOCK_CELL_MIN"
    inserts = [entity for entity in new_table.virtual_entities() if entity.dxftype() == "INSERT"]
    assert len(inserts) == 1
    assert inserts[0].dxf.name == "TABLE_BLOCK_CELL_MIN"


def test_acad_table_acexpr_field_to_code():
    source_doc = ezdxf.new("R2018")
    source_msp = source_doc.modelspace()
    line = source_msp.add_line((0, 0), (10, 0))
    circle = source_msp.add_circle((5, 0), radius=2.5)
    table = source_msp.add_table(
        (0, 0),
        [["FIELD EXPR", "AUTHORED"], ["LABEL", "VALUE"], ["Length", "10.0000"], ["Radius", "2.5000"], ["Result", "25.0000"]],
        col_widths=[30.0, 38.0],
    )
    table.new_cell_acobjprop_field(2, 1, line, "Length", text="10.0000", register_field_list=True)
    table.new_cell_acobjprop_field(3, 1, circle, "Radius", text="2.5000", register_field_list=True)
    child1 = Field()
    child1.set_acobjprop(line, "Length", value=10.0, display="10.0000")
    child2 = Field()
    child2.set_acobjprop(circle, "Radius", value=2.5, display="2.5000")
    table.new_cell_acexpr_field(
        4,
        1,
        "(%<\\_FldIdx 0>%*%<\\_FldIdx 1>%)",
        [child1, child2],
        value=25.0,
        text="25.0000",
        register_field_list=True,
    )

    new_doc, new_msp = translate_entities_to_new_layout([line, circle, table])
    new_line = new_msp[0]
    new_circle = new_msp[1]
    new_table = new_msp[2]
    new_expr = new_table.get_cell_primary_field(4, 1)

    assert new_expr is not None
    assert new_expr.evaluator_id == "AcExpr"
    children = new_expr.get_child_fields()
    assert len(children) == 2
    assert children[0].object_handles == [new_line.dxf.handle]
    assert children[1].object_handles == [new_circle.dxf.handle]
    assert new_table.get_cell_field(4, 1) is not None
