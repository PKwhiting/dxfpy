#  Copyright (c) 2021-2022, Manfred Moitzi
#  License: MIT License

import pytest
import dxfpy
from dxfpy import colors
from dxfpy.math import Vec2
from dxfpy.render import mleader
from dxfpy.entities import MultiLeader


@pytest.fixture(scope="module")
def doc():
    return dxfpy.new()


def make_multi_leader(doc) -> MultiLeader:
    style = doc.mleader_styles.get("Standard")
    ml = MultiLeader.new(doc=doc)
    ml.dxf.style_handle = style.dxf.handle
    return ml


class TestMultiLeaderMTextBuilder:
    """The MultiLeaderMTextBuilder is a construction tool to build the
    MULTILEADER entity with MTEXT content and the necessary geometry
    information stored in the entity.
    """

    def test_set_content(self, doc):
        ml = make_multi_leader(doc)
        builder = mleader.MultiLeaderMTextBuilder(ml)
        builder.set_content("line1")
        builder.build(insert=Vec2(0, 0))
        assert ml.context.mtext is not None
        assert ml.context.mtext.default_content == "line1"
        assert ml.context.mtext.color == colors.BY_LAYER_RAW_VALUE
        assert ml.context.mtext.use_word_break == 0

    def test_set_acvar_field(self, doc):
        ml = make_multi_leader(doc)
        builder = mleader.MultiLeaderMTextBuilder(ml)
        child, wrapper = builder.set_acvar_field(
            "Author", text="----", register_field_list=True
        )
        builder.build(insert=Vec2(0, 0))
        assert ml.context.mtext is not None
        assert ml.context.mtext.default_content == "----"
        assert ml.get_field() is wrapper
        assert ml.get_primary_field() is child
        assert child.field_code == "\\AcVar Author"

    def test_set_dwgprops_field(self, doc):
        ml = make_multi_leader(doc)
        builder = mleader.MultiLeaderMTextBuilder(ml)
        child, wrapper = builder.set_dwgprops_field(
            "ProjectCode", text="VALUE-123", register_field_list=True
        )
        builder.build(insert=Vec2(0, 0))
        assert ml.context.mtext is not None
        assert ml.context.mtext.default_content == "VALUE-123"
        assert ml.get_field() is wrapper
        assert ml.get_primary_field() is child
        assert child.field_code == "\\AcVar CustomDP.ProjectCode"

    def test_set_acobjprop_field(self, doc):
        line = doc.modelspace().add_line((0, 0), (10, 0))
        ml = make_multi_leader(doc)
        builder = mleader.MultiLeaderMTextBuilder(ml)
        child, wrapper = builder.set_acobjprop_field(
            line, "Length", register_field_list=True
        )
        builder.build(insert=Vec2(0, 0))
        assert ml.context.mtext is not None
        assert ml.context.mtext.default_content == "10.0000"
        assert ml.get_field() is wrapper
        assert ml.get_primary_field() is child
        assert "Length" in child.field_code


class TestMultiLeaderBlockBuilder:
    """The MultiLeaderBlockBuilder is a construction tool to build the
    MULTILEADER entity with BLOCK content and the necessary geometry
    information stored in the entity.
    """

    def test_set_content(self, doc):
        ml = make_multi_leader(doc)
        builder = mleader.MultiLeaderBlockBuilder(ml)
        assert builder is not None


if __name__ == '__main__':
    pytest.main([__file__])
