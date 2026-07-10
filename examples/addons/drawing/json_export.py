# Copyright (c) 2023-2024, Manfred Moitzi
# License: MIT License
import pathlib

import dxfpy
from dxfpy.addons.drawing import Frontend, RenderContext
from dxfpy.addons.drawing import json

CWD = pathlib.Path("~/Desktop/Outbox").expanduser()
if not CWD.exists():
    CWD = pathlib.Path(".")

# ------------------------------------------------------------------------------
# This example shows how to export the modelspace by the drawing add-on and the
# GeoJSONBackend.
#
# docs: https://dxfpy.mozman.at/docs/addons/drawing.html
# ------------------------------------------------------------------------------


def usa_geojson():
    filename = pathlib.Path(__file__).parent / "data" / "usa.dxf"
    doc = dxfpy.readfile(filename)
    msp = doc.modelspace()
    backend = json.GeoJSONBackend()
    Frontend(RenderContext(doc), backend).draw_layout(msp)
    json_string = backend.get_string()
    (CWD / "usa.geo.json").write_text(json_string)


def usa_custom_json():
    filename = pathlib.Path(__file__).parent / "data" / "usa.dxf"
    doc = dxfpy.readfile(filename)
    msp = doc.modelspace()
    backend = json.CustomJSONBackend()
    Frontend(RenderContext(doc), backend).draw_layout(msp)
    json_string = backend.get_string()
    (CWD / "usa.custom.json").write_text(json_string)


if __name__ == "__main__":
    usa_geojson()
    usa_custom_json()
