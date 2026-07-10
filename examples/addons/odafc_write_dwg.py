# Copyright (c) 2020-2022, Manfred Moitzi
# License: MIT License
import pathlib
import dxfpy
from dxfpy.addons import odafc

CWD = pathlib.Path("~/Desktop/Outbox").expanduser()
if not CWD.exists():
    CWD = pathlib.Path(".")

# ------------------------------------------------------------------------------
# This example shows how to export DWG files by the "Open Design Alliance File Converter" (odafc).
#
# docs: https://dxfpy.mozman.at/docs/addons/odafc.html
# ------------------------------------------------------------------------------


def main():
    doc = dxfpy.new(setup=True)
    msp = doc.modelspace()
    msp.add_text("DXF File created by dxfpy.")
    odafc.export_dwg(doc, str(CWD / "xyz.dwg"))


if __name__ == "__main__":
    main()
