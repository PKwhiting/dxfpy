#  Copyright (c) 2022, Manfred Moitzi
#  License: MIT License
import pathlib
import dxfpy
from dxfpy.addons.dxf2code import entities_to_code

CWD = pathlib.Path("~/Desktop/Outbox").expanduser()
if not CWD.exists():
    CWD = pathlib.Path(".")

# ------------------------------------------------------------------------------
# This example shows how to export DXF entities from modelspace as Python code.
#
# docs: https://dxfpy.mozman.at/docs/addons/dxf2code.html
# ------------------------------------------------------------------------------

FILENAME = "A_000217"
CADKIT = dxfpy.options.test_files_path / "CADKitSamples"
DXF_FILE = CADKIT / f"{FILENAME}.dxf"
SOURCE_CODE_FILE = CWD / f"{FILENAME}.py"


def main():
    doc = dxfpy.readfile(DXF_FILE)
    msp = doc.modelspace()

    source = entities_to_code(msp, layout="msp")

    print("writing " + str(SOURCE_CODE_FILE))
    with open(SOURCE_CODE_FILE, mode="wt") as f:
        f.write("import dxfpy\n")
        f.write(source.import_str())
        f.write("\n\n")

        f.write("doc = dxfpy.new()\n")
        f.write("msp = doc.modelspace()\n\n")
        f.write(source.code_str())
        f.write("\n")

    print("done.")


if __name__ == "__main__":
    main()
