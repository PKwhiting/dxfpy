# Copyright (c) 2020-2021, Matthew Broadway
# License: MIT License
from __future__ import annotations

from dxfpy.addons.drawing.backend import BackendInterface
from dxfpy.addons.drawing.type_hints import Color
from dxfpy.math import Vec3


def draw_rect(points: list[Vec3], color: Color, out: BackendInterface):
    from dxfpy.addons.drawing.properties import BackendProperties

    props = BackendProperties(color=color)
    for a, b in zip(points, points[1:]):
        out.draw_line(a, b, props)
