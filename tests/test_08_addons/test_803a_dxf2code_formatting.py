# Copyright (c) 2019 Manfred Moitzi
# License: MIT License

from dxfpy.addons.dxf2code._format import (
    _fmt_api_call,
    _fmt_dxf_tags,
    _fmt_list,
    _fmt_mapping,
)
from dxfpy.lldxf.types import dxftag
from dxfpy.math import Vec3


def test_fmt_mapping():
    data = {"a": 1, "b": "str", "c": Vec3(), "d": 'xxx "yyy" \'zzz\''}
    result = list(_fmt_mapping(data))
    assert result[0] == "'a': 1,"
    assert result[1] == "'b': \"str\","
    assert result[2] == "'c': (0.0, 0.0, 0.0),"
    assert result[3] == "'d': \"xxx \\\"yyy\\\" 'zzz'\","


def test_fmt_int_list():
    values = [1, 2, 3]
    result = list(_fmt_list(values))
    assert result[0] == "1,"
    assert result[1] == "2,"
    assert result[2] == "3,"


def test_fmt_float_list():
    values = [1.0, 2.0, 3.0]
    result = list(_fmt_list(values))
    assert result[0] == "1.0,"
    assert result[1] == "2.0,"
    assert result[2] == "3.0,"


def test_fmt_vector_list():
    values = [Vec3(), (1.0, 2.0, 3.0)]
    result = list(_fmt_list(values))
    assert result[0] == "(0.0, 0.0, 0.0),"
    assert result[1] == "(1.0, 2.0, 3.0),"


def test_fmt_api_call():
    result = _fmt_api_call(
        "msp.add_line(",
        ["start", "end"],
        dxfattribs={"start": (0, 0), "end": (1, 0), "color": 7},
    )
    assert result[0] == "msp.add_line("
    assert result[1] == "    start=(0, 0),"
    assert result[2] == "    end=(1, 0),"
    assert result[3] == "    dxfattribs={"
    assert result[4] == "        'color': 7,"
    assert result[5] == "    },"
    assert result[6] == ")"


def test_fmt_dxf_tags():
    tags = [dxftag(1, "TEXT"), dxftag(10, (1, 2, 3))]
    code = "[{}]".format("".join(_fmt_dxf_tags(tags)))
    result = eval(code, globals())
    assert result == tags
