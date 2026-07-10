# Copyright (c) 2019-2022 Manfred Moitzi
# License: MIT License
import pathlib

import dxfpy
from dxfpy.tools.standards import styles

CWD = pathlib.Path("~/Desktop/Outbox").expanduser()
if not CWD.exists():
    CWD = pathlib.Path(".")

# ------------------------------------------------------------------------------
# This example creates TEXT entities for all text styles predefined by dxfpy.
#
# tutorial for TEXT: https://dxfpy.mozman.at/docs/tutorials/text.html
# ------------------------------------------------------------------------------

# The predefined text styles only exists if setup is TRUE and the open source
# fonts are installed on your system, see the folder "/fonts" in the repository.

doc = dxfpy.new("R12", setup=True)
msp = doc.modelspace()

y = 0
height = 0.5
line_height = 1.5
for style, font in styles():
    msp.add_text(
        style, dxfattribs={"style": style, "height": height}
    ).set_placement((0, y))
    y += height * line_height

doc.saveas(CWD / "using_all_text_styles.dxf")
