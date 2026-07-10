# Copyright (c) 2018-2019, Manfred Moitzi
# License: MIT License
import pytest
import os
import dxfpy
from dxfpy.lldxf.const import versions_supported_by_new


@pytest.fixture(params=versions_supported_by_new)
def drawing(request):
    return dxfpy.new(request.param)


def test_create_anonymous_block(drawing, tmpdir):
    modelspace = drawing.modelspace()
    anonymous_block = drawing.blocks.new_anonymous_block()
    points2d = [
        (0, 0),
        (1, 0),
        (1, 1),
        (0, 1),
        (0, 0),
        (1, 1),
        (0.5, 1.5),
        (0, 1),
        (1, 0),
    ]
    anonymous_block.add_polyline2d(points2d)
    modelspace.add_blockref(anonymous_block.name, (0, 0))
    filename = str(tmpdir.join("anonymous_blocks_%s.dxf" % drawing.dxfversion))
    try:
        drawing.saveas(filename)
    except dxfpy.DXFError as e:
        pytest.fail(
            "DXFError: {0} for DXF version {1}".format(
                str(e), drawing.dxfversion
            )
        )
    assert os.path.exists(filename)
