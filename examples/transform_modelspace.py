# Copyright (c) 2021-2022 Manfred Moitzi
# License: MIT License
import pathlib

import dxfpy
from dxfpy.math import Matrix44, TransformError
from dxfpy.layouts import BaseLayout


CWD = pathlib.Path("~/Desktop/Outbox").expanduser()
if not CWD.exists():
    CWD = pathlib.Path(".")

# ------------------------------------------------------------------------------
# This example shows how to transform all entities of a layout by the
# general transformation interface.
# docs: https://dxfpy.mozman.at/docs/dxfentities/dxfgfx.html#dxfpy.entities.DXFGraphic.transform
# ------------------------------------------------------------------------------

EXAMPLE = (
    dxfpy.options.test_files_path / "CADKitSamples" / "AEC Plan Elev Sample.dxf"
)
INCH_TO_MM = 25.4


def transform_layout(layout: BaseLayout, m: Matrix44) -> None:
    for entity in layout:
        try:
            entity.transform(m)
        except (NotImplementedError, TransformError):
            pass


doc = dxfpy.readfile(EXAMPLE)
transform_layout(doc.modelspace(), Matrix44.scale(INCH_TO_MM))
doc.saveas(CWD / "scaled.dxf")
