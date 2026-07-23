# Copyright (c) 2019 Manfred Moitzi
# License: MIT License
from pathlib import Path

import dxfpy
from dxfpy.sections.classes import CLASS_DEFINITIONS, ClassesSection
from dxfpy.entities.dxfclass import DXFClass
from dxfpy.lldxf.tagwriter import TagCollector
from dxfpy.tools.test import load_entities


def test_init():
    classes = ClassesSection()
    assert len(classes.classes) == 0


def test_add_known_class():
    classes = ClassesSection()
    classes.add_class("SUN")
    assert len(classes.classes) == 1


def test_add_color_and_dynamic_block_entity_classes():
    classes = ClassesSection()

    classes.add_class("DBCOLOR")
    companion_classes = {
        "BASEPOINTPARAMETERENTITY": "AcDbBlockBasepointParameterEntity",
        "LINEARPARAMETERENTITY": "AcDbBlockLinearParameterEntity",
        "LINEARGRIPENTITY": "AcDbBlockLinearGripEntity",
        "STRETCHACTIONENTITY": "AcDbBlockStretchActionEntity",
    }
    for name in companion_classes:
        classes.add_class(name)

    color_class = classes.get("DBCOLOR")
    assert color_class.dxf.cpp_class_name == "AcDbColor"
    for name, cpp_class_name in companion_classes.items():
        dxf_class = classes.get(name)
        assert dxf_class.dxf.cpp_class_name == cpp_class_name
        assert dxf_class.dxf.flags == 1025
        assert dxf_class.dxf.was_a_proxy == 0
        assert dxf_class.dxf.is_an_entity == 1


def test_add_required_classes():
    classes = ClassesSection()
    classes.add_required_classes(dxfpy.DXF2004)
    assert len(classes.classes) > 10  # may change


def test_known_class_definitions_match_autocad_fixture():
    fixture = (
        Path(__file__).parent.parent
        / "test_08_addons"
        / "autocad_nested_working_minimal_v1_edited.dxf"
    )
    doc = dxfpy.readfile(fixture)

    for dxf_class in doc.classes:
        expected = CLASS_DEFINITIONS.get(dxf_class.dxf.name)
        if expected is None:
            continue
        actual = (
            dxf_class.dxf.cpp_class_name,
            dxf_class.dxf.app_name,
            dxf_class.dxf.flags,
            dxf_class.dxf.was_a_proxy,
            dxf_class.dxf.is_an_entity,
        )
        assert actual == tuple(expected), dxf_class.dxf.name


def test_double_keys():
    classes = ClassesSection()
    sun1 = DXFClass()
    sun1.update_dxf_attribs({"name": "SUN", "cpp_class_name": "AcDbSun1"})

    sun2 = DXFClass()
    sun2.update_dxf_attribs({"name": "SUN", "cpp_class_name": "AcDbSun2"})
    # same class 'name' but different 'cpp class name', example: 'CADKitSamples/AEC Plan Elev Sample.dxf'
    classes.register([sun1, sun2])
    assert len(classes.classes) == 2


def test_export_dxf():
    classes = ClassesSection()
    classes.add_class("SUN")
    collector = TagCollector(dxfversion=dxfpy.DXF2004)
    classes.export_dxf(collector)
    tags = collector.tags
    assert tags[0] == (0, "SECTION")
    assert tags[1] == (2, "CLASSES")
    assert tags[2] == (0, "CLASS")
    # writing classes is tested in 'test_113_dxfclass.py'
    assert tags[-1] == (0, "ENDSEC")


def test_load_section():
    doc = dxfpy.new()
    entities = load_entities(TEST_CLASSES, "CLASSES")
    classes = ClassesSection(doc, entities)
    assert len(classes.classes) == 3

    # this tests internals - use storage key is not exposed by API
    assert (
        "ACDBDICTIONARYWDFLT",
        "AcDbDictionaryWithDefault",
    ) in classes.classes
    assert ("DICTIONARYVAR", "AcDbDictionaryVar") in classes.classes
    assert ("TABLESTYLE", "AcDbTableStyle") in classes.classes


TEST_CLASSES = """  0
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
  0
EOF
"""
