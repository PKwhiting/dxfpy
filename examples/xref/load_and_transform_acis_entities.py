# Copyright (c) 2024, Manfred Moitzi
# License: MIT License

from pathlib import Path
import dxfpy
from dxfpy import xref, transform

# ------------------------------------------------------------------------------
# 1. This example shows how to load ACIS based entities by the xref module from
#    one DXF document into another DXF document.
#
# 2. How to transform ACIS based entities.
#    The current implementation of the transformation is a trick.
#    The ACIS data format is not documented, therefore dxfpy puts ACIS based entities
#    into an anonymous block and transforms that block.  This transformation is applied
#    when exporting the DXF document.
# ------------------------------------------------------------------------------

CWD = Path(__file__).parent
OUTPUT = Path("~/Desktop/Outbox").expanduser()
if not OUTPUT.exists():
    OUTPUT = CWD


def main():
    sdoc = dxfpy.readfile(CWD / "sphere.dxf")
    tdoc = dxfpy.new(dxfversion=sdoc.dxfversion)
    xref.load_modelspace(sdoc, tdoc)
    transform.translate(tdoc.modelspace(), (10, 11, 12))
    tdoc.saveas(OUTPUT / "imported_and_translated_sphere.dxf")


if __name__ == "__main__":
    main()
