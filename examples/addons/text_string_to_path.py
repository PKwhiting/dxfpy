# Copyright (c) 2021-2023, Manfred Moitzi
# License: MIT License
import pathlib
import dxfpy
from dxfpy import path, zoom
from dxfpy.fonts import fonts
from dxfpy.addons import text2path
from dxfpy.enums import TextEntityAlignment

CWD = pathlib.Path("~/Desktop/Outbox").expanduser()
if not CWD.exists():
    CWD = pathlib.Path(".")

# ------------------------------------------------------------------------------
# This example shows how to convert a text-string to outline paths.
#
# docs: https://dxfpy.mozman.at/docs/addons/text2path.html
# ------------------------------------------------------------------------------


def main():
    doc = dxfpy.new()
    doc.layers.new("OUTLINE")
    doc.layers.new("FILLING")
    msp = doc.modelspace()

    attr = {"layer": "OUTLINE", "color": 1}
    ff = fonts.FontFace(family="Noto Sans SC")
    s = "Noto Sans SC 0123456789 %@ 中国文字"
    align = TextEntityAlignment.LEFT
    path.render_splines_and_polylines(
        msp, text2path.make_paths_from_str(s, ff, align=align), dxfattribs=attr
    )

    attr["layer"] = "FILLING"
    attr["color"] = 2
    for hatch in text2path.make_hatches_from_str(s, ff, align=align, dxfattribs=attr):
        msp.add_entity(hatch)

    zoom.extents(msp)
    doc.saveas(CWD / "text2path.dxf")


if __name__ == "__main__":
    main()
