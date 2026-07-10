#  Copyright (c) 2022, Manfred Moitzi
#  License: MIT License
import pathlib
import math
import dxfpy
from dxfpy.render import forms


CWD = pathlib.Path("~/Desktop/Outbox").expanduser()
if not CWD.exists():
    CWD = pathlib.Path(".")

# ------------------------------------------------------------------------------
# This example shows how to use the extended dxfpy.forms.extrude_twist_scale
# method to create a 3D figure from a base polygon (profile).
#
# docs: https://dxfpy.mozman.at/docs/render/forms.html#dxfpy.render.forms.extrude_twist_scale
# ------------------------------------------------------------------------------

DEBUG_COLOR = dxfpy.colors.CYAN

doc = dxfpy.new()
msp = doc.modelspace()


circle = list(forms.translate(forms.circle(8), (1, 0, 0)))
extrusion_path = [(0, 0, 0), (1, 0, 10)]
mesh = forms.extrude_twist_scale(
    circle, extrusion_path, close=True, caps=True, scale=2, twist=math.pi / 2
)
mesh.render_mesh(msp, dxfattribs={"color": dxfpy.colors.MAGENTA})
doc.saveas(CWD / "extrude_twist_scale_profile.dxf")
