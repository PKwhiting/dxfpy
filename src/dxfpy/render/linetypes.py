# Copyright (c) 2020-2022, Manfred Moitzi
# License: MIT License
from typing import Iterable, Iterator
import dxfpy
from dxfpy.math import UVec
from ._linetypes import _LineTypeRenderer, LineSegment

if dxfpy.options.use_c_ext:
    try:
        from dxfpy.acc.linetypes import _LineTypeRenderer  # type: ignore
    except ImportError:
        pass


class LineTypeRenderer(_LineTypeRenderer):
    def line_segments(self, vertices: Iterable[UVec]) -> Iterator[LineSegment]:
        last = None
        for vertex in vertices:
            if last is not None:
                yield from self.line_segment(last, vertex)
            last = vertex
