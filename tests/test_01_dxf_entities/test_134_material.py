# Copyright (c) 2018-2021 Manfred Moitzi
# License: MIT License
import pytest
import dxfpy


@pytest.fixture(scope="module")
def doc():
    return dxfpy.new("R2010")


def test_material_manager(doc):
    materials = doc.materials
    assert "ByLayer" in materials
    assert "ByBlock" in materials
    assert "Global" in materials
    assert "Test" not in materials

    global_material = materials.get("Global")
    assert global_material.dxf.name == "Global"
    assert global_material.dxf.channel_flags == 63


def test_export_matrix():
    from dxfpy.math import Matrix44
    from dxfpy.lldxf.tagwriter import TagCollector
    from dxfpy.entities.material import export_matrix

    m = Matrix44()
    tc = TagCollector()
    export_matrix(tc, 43, m)
    assert len(tc.tags) == 16
    assert tc.tags[0] == (43, 1.0)
