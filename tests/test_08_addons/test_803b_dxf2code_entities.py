# Copyright (c) 2019 Manfred Moitzi
# License: MIT License
from io import StringIO

import ezdxf
from ezdxf.addons.dxf2code import block_to_code, entities_to_code, table_entries_to_code
from ezdxf.addons.dxf2code._generator import _SourceCodeGenerator
from ezdxf.entities.ltype import LinetypePattern  # required by exec() or eval()
from ezdxf.lldxf.extendedtags import ExtendedTags
from ezdxf.lldxf.tags import Tags  # required by exec() or eval()
from ezdxf.lldxf.tagwriter import TagWriter
from ezdxf.lldxf.types import dxftag  # required by exec() or eval()
from ezdxf.math import Vec3

from tests.test_08_addons.dxf2code_support import (
    cmp_vertices,
    execute_code_in_namespace,
    translate_entities_to_new_layout,
)

doc = ezdxf.new("R2010")
msp = doc.modelspace()


def translate_to_code_and_execute(entity):
    code = entities_to_code([entity], layout="msp")
    exec(code.import_str() + "\n" + str(code), globals())
    return msp[-1]


def test_line_to_code():
    from ezdxf.entities.line import Line

    entity = Line.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"color": "7", "start": (1, 2, 3), "end": (4, 5, 6)},
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "start", "end"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_point_to_code():
    from ezdxf.entities.point import Point

    entity = Point.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"color": "7", "location": (1, 2, 3)},
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "location"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_circle_to_code():
    from ezdxf.entities.circle import Circle

    entity = Circle.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"color": "7", "center": (1, 2, 3), "radius": 2},
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "center", "radius"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_arc_to_code():
    from ezdxf.entities.arc import Arc

    entity = Arc.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "center": (1, 2, 3),
            "radius": 2,
            "start_angle": 30,
            "end_angle": 60,
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "center", "radius", "start_angle", "end_angle"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_text_to_code():
    from ezdxf.entities.text import Text

    entity = Text.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"color": "7", "text": "xyz", "insert": (2, 3, 4)},
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "text", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_solid_to_code():
    from ezdxf.entities.solid import Solid

    entity = Solid.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "vtx0": (1, 2, 3),
            "vtx1": (4, 5, 6),
            "vtx2": (7, 8, 9),
            "vtx3": (3, 2, 1),
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("vtx0", "vtx1", "vtx2", "vtx3"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_shape_to_code():
    from ezdxf.entities.shape import Shape

    entity = Shape.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"color": "7", "name": "shape_name", "insert": (2, 3, 4)},
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "name", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_ellipse_to_code():
    from ezdxf.entities.ellipse import Ellipse

    entity = Ellipse.new(
        handle="ABBA",
        owner="0",
        dxfattribs={
            "color": "7",
            "center": (1, 2, 3),
            "major_axis": (2, 0, 0),
            "ratio": 0.5,
            "start_param": 1,
            "end_param": 3,
        },
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in (
        "color",
        "center",
        "major_axis",
        "ratio",
        "start_param",
        "end_param",
    ):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_insert_to_code():
    from ezdxf.entities.insert import Insert

    entity = Insert.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"name": "block1", "insert": (2, 3, 4)},
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("name", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_insert_with_attrib_to_code():
    source_doc = ezdxf.new("R2010")
    source_doc.blocks.new("ATTRIB_BLOCK")
    source_msp = source_doc.modelspace()
    insert = source_msp.add_blockref("ATTRIB_BLOCK", (2, 3, 4))
    insert.add_attrib("TAG1", "Text1", (5, 6, 7))

    _, new_msp = translate_entities_to_new_layout([insert])
    new_insert = next(entity for entity in new_msp if entity.dxftype() == "INSERT")

    assert len(new_insert.attribs) == 1
    assert len([entity for entity in new_msp if entity.dxftype() == "ATTRIB"]) == 0
    assert new_insert.attribs[0].dxf.tag == "TAG1"
    assert new_insert.attribs[0].dxf.text == "Text1"


def test_attdef_to_code():
    from ezdxf.entities.attrib import AttDef

    entity = AttDef.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"tag": "TAG1", "text": "Text1", "insert": (2, 3, 4)},
    )
    new_entity = translate_to_code_and_execute(entity)
    for name in ("tag", "text", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)


def test_mtext_to_code():
    from ezdxf.entities.mtext import MText

    entity = MText.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"color": "7", "insert": (2, 3, 4)},
    )
    entity.text = 'xxx "yyy" \'zzz\''
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "insert"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)
    assert new_entity.text == 'xxx "yyy" \'zzz\''


def test_mtext_to_code_preserves_explicit_optional_line_spacing_style():
    from ezdxf.entities.mtext import MText

    entity = MText.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"insert": (2, 3, 4), "line_spacing_style": 1},
    )

    new_entity = translate_to_code_and_execute(entity)
    stream = StringIO()
    new_entity.export_dxf(TagWriter(stream, dxfversion=new_entity.doc.dxfversion))
    tags = ExtendedTags.from_text(stream.getvalue())

    assert any(tag.code == 73 and tag.value == 1 for tag in tags)


def test_mtext_to_code_preserves_explicit_optional_line_spacing_factor():
    from ezdxf.entities.mtext import MText

    entity = MText.new(
        handle="ABBA",
        owner="0",
        dxfattribs={"insert": (2, 3, 4), "line_spacing_factor": 1.0},
    )

    new_entity = translate_to_code_and_execute(entity)
    stream = StringIO()
    new_entity.export_dxf(TagWriter(stream, dxfversion=new_entity.doc.dxfversion))
    tags = ExtendedTags.from_text(stream.getvalue())

    assert any(tag.code == 44 and tag.value == 1.0 for tag in tags)


def test_wipeout_to_code_preserves_proxy_graphic_payload():
    source_doc = ezdxf.new("R2010")
    wipeout = source_doc.modelspace().add_wipeout([(0, 0), (2, 0), (2, 1), (0, 1)])
    wipeout.proxy_graphic = b"\x01\x02\x03\x04"

    _, new_msp = translate_entities_to_new_layout([wipeout])
    new_entity = new_msp[0]
    stream = StringIO()
    new_entity.export_dxf(TagWriter(stream, dxfversion=new_entity.doc.dxfversion))
    text = stream.getvalue().replace("\r\n", "\n")

    assert new_entity.proxy_graphic == wipeout.proxy_graphic
    assert "\n 92\n4\n310\n01020304\n" in text


def test_insert_attrib_to_code_preserves_explicit_attrib_layer():
    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("ATTRIB_LAYER_BLOCK")
    insert = block.add_blockref("TEST_REF", (0, 0), dxfattribs={"layer": "INSERT_LAYER"})
    insert.add_attrib("TAG", "TEXT", insert=(1, 2), dxfattribs={"layer": "ATTRIB_LAYER"})

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)

    new_insert = next(
        entity
        for entity in namespace["doc"].blocks.get("ATTRIB_LAYER_BLOCK")
        if entity.dxftype() == "INSERT"
    )

    assert new_insert.attribs[0].dxf.layer == "ATTRIB_LAYER"


def test_insert_attrib_to_code_preserves_context_data_subtree():
    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("ATTRIB_CONTEXT_BLOCK")
    insert = block.add_blockref("TEST_REF", (0, 0))
    attrib = insert.add_attrib("TAG", "TEXT", insert=(1, 2))
    xdict = attrib.new_extension_dict()
    mgr = xdict.dictionary.add_new_dict("AcDbContextDataManager")
    mgr.add_new_dict("ACDB_ANNOTATIONSCALES")

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)

    new_insert = next(
        entity
        for entity in namespace["doc"].blocks.get("ATTRIB_CONTEXT_BLOCK")
        if entity.dxftype() == "INSERT"
    )
    new_attrib = new_insert.attribs[0]

    assert new_attrib.has_extension_dict is True
    assert new_attrib.get_extension_dict().dictionary.dxf.owner == new_attrib.dxf.handle
    new_mgr = new_attrib.get_extension_dict().dictionary.get("AcDbContextDataManager")
    assert new_mgr is not None
    assert new_mgr.dxf.owner == new_attrib.get_extension_dict().dictionary.dxf.handle
    assert new_mgr.get("ACDB_ANNOTATIONSCALES") is not None


def test_block_to_code_preserves_block_record_preview_data():
    source_doc = ezdxf.new("R2010")
    block = source_doc.blocks.new("BLOCK_PREVIEW_DATA")
    block.add_line((0, 0), (1, 0))
    block.block_record.preview_data = bytes.fromhex("01020304")

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc, "msp": target_doc.modelspace()}
    execute_code_in_namespace(block_to_code(block, drawing="doc"), namespace)

    new_block = namespace["doc"].blocks.get("BLOCK_PREVIEW_DATA")
    assert new_block.block_record.preview_data == block.block_record.preview_data


def test_lwpolyline_to_code():
    from ezdxf.entities.lwpolyline import LWPolyline

    entity = LWPolyline.new(handle="ABBA", owner="0", dxfattribs={"color": "7"})
    entity.set_points([(1, 2, 0, 0, 0), (4, 3, 0, 0, 0), (7, 8, 0, 0, 0)])
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "count"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)
    for new_point, entity_point in zip(new_entity.get_points(), entity.get_points()):
        assert new_point == entity_point


def test_polyline_to_code():
    polyline = msp.add_polyline3d([(1, 2, 3), (2, 3, 7), (9, 3, 1), (4, 4, 4), (0, 5, 8)])

    new_entity = translate_to_code_and_execute(polyline)
    assert msp[-2].dxftype() == msp[-1].dxftype()
    assert len(new_entity) == len(polyline)
    assert new_entity.dxf.flags == polyline.dxf.flags
    for new_point, entity_point in zip(new_entity.points(), polyline.points()):
        assert new_point == entity_point


def test_spline_to_code():
    from ezdxf.entities.spline import Spline

    entity = Spline.new(handle="ABBA", owner="0", dxfattribs={"color": "7", "degree": 3})
    entity.fit_points = [(1, 2, 0), (4, 3, 0), (7, 8, 0)]
    entity.control_points = [(1, 2, 0), (4, 3, 0), (7, 8, 0)]
    entity.knots = [1, 2, 3, 4, 5, 6, 7]
    entity.weights = [1.0, 2.0, 3.0]
    new_entity = translate_to_code_and_execute(entity)
    for name in ("color", "n_knots", "n_control_points", "n_fit_points", "degree"):
        assert new_entity.get_dxf_attrib(name) == entity.get_dxf_attrib(name)
    assert new_entity.knots == entity.knots
    assert cmp_vertices(new_entity.control_points, entity.control_points) is True
    assert cmp_vertices(new_entity.fit_points, entity.fit_points) is True
    assert new_entity.weights == entity.weights


def test_leader_to_code():
    from ezdxf.entities.leader import Leader

    entity = Leader.new(handle="ABBA", owner="0", dxfattribs={"color": "7"})
    entity.set_vertices([(1, 2, 0), (4, 3, 0), (7, 8, 0)])
    new_entity = translate_to_code_and_execute(entity)
    assert new_entity.dxf.color == entity.dxf.color
    for new_point, entity_point in zip(new_entity.vertices, entity.vertices):
        assert new_point == entity_point


def test_mesh_to_code():
    from ezdxf.entities.mesh import Mesh
    from ezdxf.render.forms import cube

    entity = Mesh.new(handle="ABBA", owner="0", dxfattribs={"color": "7"})
    cube_mesh = cube()
    entity.vertices = cube_mesh.vertices
    entity.faces = cube_mesh.faces

    assert len(entity.vertices) == 8
    new_entity = translate_to_code_and_execute(entity)
    assert cmp_vertices(entity.vertices, new_entity.vertices) is True
    assert list(entity.faces) == list(new_entity.faces)


def test_layer_entry():
    from ezdxf.entities.layer import Layer

    layer = Layer.new("LAYER", dxfattribs={"name": "TestTest", "color": 3})
    code = table_entries_to_code([layer], drawing="doc")
    exec(str(code), globals())
    new_layer = doc.layers.get("TestTest")
    assert new_layer.dxf.color == 3


def test_ltype_entry():
    from ezdxf.entities.ltype import Linetype

    ltype = Linetype.new(
        "FFFF",
        dxfattribs={"name": "TEST", "description": "TESTDESC"},
    )
    ltype.setup_pattern([0.2, 0.1, -0.1])
    code = table_entries_to_code([ltype], drawing="doc")
    exec(str(code), globals())
    new_ltype = doc.linetypes.get("TEST")
    assert new_ltype.dxf.description == ltype.dxf.description
    assert new_ltype.pattern_tags.tags == ltype.pattern_tags.tags
    assert any(line.endswith("Tags") for line in code.imports)
    assert any(line.endswith("dxftag") for line in code.imports)
    assert any(line.endswith("LinetypePattern") for line in code.imports)


def test_mleaderstyle_entry():
    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "TEST_STYLE")
    style.dxf.default_text_content = "STYLE_TEXT"
    style.dxf.char_height = 3.5
    style.set_arrow_head("DOT")

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc}
    code = table_entries_to_code([style], drawing="doc")
    execute_code_in_namespace(code, namespace)
    new_style = target_doc.mleader_styles.get("TEST_STYLE")

    assert new_style is not None
    assert new_style.dxf.default_text_content == "STYLE_TEXT"
    assert new_style.dxf.char_height == 3.5
    assert target_doc.entitydb.get(new_style.dxf.arrow_head_handle).dxf.name == "_DOT"


def test_mleaderstyle_entry_missing_block_handle_is_safe():
    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "TEST_STYLE")
    source_doc.blocks.new("STYLE_BLOCK")
    style.dxf.block_record_handle = source_doc.blocks.get("STYLE_BLOCK").block_record_handle

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc}
    code = table_entries_to_code([style], drawing="doc")
    execute_code_in_namespace(code, namespace)
    new_style = target_doc.mleader_styles.get("TEST_STYLE")

    assert new_style is not None
    assert new_style.dxf.hasattr("block_record_handle") is False


def test_mleaderstyle_entry_uses_object_dict_key_when_entity_name_diverges():
    source_doc = ezdxf.new("R2010")
    style = source_doc.mleader_styles.duplicate_entry("Standard", "TEST_STYLE")
    style.dxf.name = "Standard"
    style.dxf.default_text_content = "STYLE_TEXT"

    target_doc = ezdxf.new("R2010")
    namespace = {"ezdxf": ezdxf, "doc": target_doc}
    code = table_entries_to_code([style], drawing="doc")
    execute_code_in_namespace(code, namespace)
    new_style = target_doc.mleader_styles.get("TEST_STYLE")

    assert new_style is not None
    assert new_style.dxf.default_text_content == "STYLE_TEXT"


def test_block_to_code():
    testdoc = ezdxf.new()
    block = testdoc.blocks.new("TestBlock", dxfattribs={"description": "test"})
    block.add_line((1, 1), (2, 2))
    code = block_to_code(block, drawing="doc")
    exec(str(code), globals())
    new_block = doc.blocks.get("TestBlock")
    assert new_block.block.dxf.description == block.block.dxf.description
    assert new_block[0].dxftype() == block[0].dxftype()


def test_hatch_to_code():
    from ezdxf.entities import Hatch

    hatch = Hatch()
    hatch.set_pattern_fill(name="ANGLE")
    hatch.paths.add_polyline_path([(0, 0), (100, 0), (100, 100), (0, 100)], is_closed=True)

    new_hatch = translate_to_code_and_execute(hatch)
    assert isinstance(new_hatch, Hatch)
    assert new_hatch.has_pattern_fill
    assert len(new_hatch.pattern.lines) == len(hatch.pattern.lines)


def test_unsupported_translator_does_not_register_entity_handle(monkeypatch):
    class DummyDXF:
        def __init__(self, handle: str):
            self.handle = handle

        def get(self, key: str, default=None):
            if key == "handle":
                return self.handle
            return default

    class DummyEntity:
        def __init__(self, handle: str):
            self.dxf = DummyDXF(handle)

        def dxftype(self):
            return "FAKE"

    generator = _SourceCodeGenerator(layout="msp", doc="doc")
    monkeypatch.setattr(
        _SourceCodeGenerator,
        "_fake",
        lambda self, entity: False,
        raising=False,
    )

    generator.translate_entities([DummyEntity("ABBA")])

    assert '_entity_map["ABBA"]' not in str(generator.code)
