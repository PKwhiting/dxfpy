# Copyright (c) 2011-2019, Manfred Moitzi
# License: MIT License
import pytest
from io import StringIO
import dxfpy
from dxfpy.lldxf import const
from dxfpy.lldxf.tags import internal_tag_compiler
from dxfpy.lldxf.extendedtags import ExtendedTags
from dxfpy.sections.classes import ClassesSection, snapshot_raw_classes, restore_raw_classes
from dxfpy.lldxf.tagwriter import TagWriter
from dxfpy.tools.test import load_section
from dxfpy.entities import factory


@pytest.fixture(scope="module")
def section():
    sec = load_section(TESTCLASSES, "CLASSES")
    cls_entities = [factory.load(ExtendedTags(e)) for e in sec]
    return ClassesSection(None, iter(cls_entities))


def test_write(section):
    stream = StringIO()
    section.export_dxf(TagWriter(stream))
    result = stream.getvalue()
    stream.close()
    t1 = list(internal_tag_compiler(TESTCLASSES))
    t2 = list(internal_tag_compiler(result))
    assert t1 == t2


def test_empty_section():
    sec = load_section(EMPTYSEC, "CLASSES")
    cls_entities = [factory.load(ExtendedTags(e)) for e in sec]

    section = ClassesSection(None, iter(cls_entities))
    stream = StringIO()
    section.export_dxf(TagWriter(stream))
    result = stream.getvalue()
    stream.close()
    assert EMPTYSEC == result


def test_count_class_instances():
    def instance_count(name):
        return doc.classes.get(name).dxf.instance_count

    doc = dxfpy.new("R2004")

    doc.classes.add_class("IMAGE")
    doc.classes.add_class("IMAGEDEF")
    doc.classes.add_class("IMAGEDEF_REACTOR")
    doc.classes.add_class("RASTERVARIABLES")

    doc.classes.update_instance_counters()
    assert instance_count("IMAGE") == 0
    assert instance_count("IMAGEDEF") == 0
    assert instance_count("IMAGEDEF_REACTOR") == 0
    assert instance_count("RASTERVARIABLES") == 0

    image_def = doc.add_image_def("test", size_in_pixel=(400, 400))
    msp = doc.modelspace()
    msp.add_image(image_def, insert=(0, 0), size_in_units=(10, 10))

    doc.classes.update_instance_counters()
    assert instance_count("IMAGE") == 1
    assert instance_count("IMAGEDEF") == 1
    assert instance_count("IMAGEDEF_REACTOR") == 1
    assert instance_count("RASTERVARIABLES") == 1


def test_add_required_classes_registers_multileader_class_if_used():
    from dxfpy.render.mleader import ConnectionSide
    from dxfpy.math import Vec2

    doc = dxfpy.new("R2010")
    builder = doc.modelspace().add_multileader_mtext()
    builder.set_content("note")
    builder.add_leader_line(ConnectionSide.left, [Vec2(0, 0), Vec2(1, 0)])
    builder.build(insert=Vec2(0, 0))

    doc.classes.add_required_classes(doc.dxfversion)

    multileader_class = doc.classes.get("MULTILEADER")
    assert multileader_class.dxf.cpp_class_name == "AcDbMLeader"
    assert multileader_class.dxf.flags == 1025


def test_add_required_classes_does_not_force_layout_or_placeholder_classes():
    doc = dxfpy.new("R2000")

    doc.classes.add_required_classes(doc.dxfversion)

    with pytest.raises(const.DXFKeyError):
        doc.classes.get("LAYOUT")
    with pytest.raises(const.DXFKeyError):
        doc.classes.get("ACDBPLACEHOLDER")


def test_add_required_classes_does_not_force_sun_or_render_settings_classes():
    doc = dxfpy.new("R2007")

    doc.classes.add_required_classes(doc.dxfversion)

    with pytest.raises(const.DXFKeyError):
        doc.classes.get("SUN")
    with pytest.raises(const.DXFKeyError):
        doc.classes.get("MENTALRAYRENDERSETTINGS")


def test_add_class_wipeout_uses_full_oracle_metadata():
    doc = dxfpy.new("R2000")

    doc.classes.add_class("WIPEOUT")

    wipeout_class = doc.classes.get("WIPEOUT")
    assert wipeout_class.dxf.cpp_class_name == "AcDbWipeout"
    assert wipeout_class.dxf.app_name == (
        "WipeOut|Product Desc: Object Enabler for WipeOut entity | "
        "Company: Autodesk, Inc. | WEB Address: www.autodesk.com"
    )
    assert wipeout_class.dxf.flags == 2175


def test_snapshot_and_restore_raw_classes_preserves_oracle_text():
    source_doc = dxfpy.new("R2010")
    source_doc.classes.add_class("WIPEOUT")
    source_doc.classes.add_class("MULTILEADER")
    snapshot = snapshot_raw_classes(source_doc.classes)

    target_doc = dxfpy.new("R2010")
    restore_raw_classes(target_doc.classes, snapshot)

    stream = StringIO()
    target_doc.classes.export_dxf(TagWriter(stream))

    assert stream.getvalue() == (
        "  0\nSECTION\n  2\nCLASSES\n" + "".join(snapshot) + "  0\nENDSEC\n"
    )


EMPTYSEC = """  0
SECTION
  2
CLASSES
  0
ENDSEC
"""

TESTCLASSES = """  0
SECTION
  2
CLASSES
  0
CLASS
  1
ACDBDICTIONARYWDFLT
  2
AcDbDictionaryWithDefault
  3
ObjectDBX Classes
 90
        0
 91
        1
280
     0
281
     0
  0
CLASS
  1
DICTIONARYVAR
  2
AcDbDictionaryVar
  3
ObjectDBX Classes
 90
        0
 91
       13
280
     0
281
     0
  0
CLASS
  1
TABLESTYLE
  2
AcDbTableStyle
  3
ObjectDBX Classes
 90
     4095
 91
        1
280
     0
281
     0
0
ENDSEC
"""
