#  Copyright (c) 2026, Manfred Moitzi
#  License: MIT License
import pathlib

import dxfpy

from dxfpy.addons.dxf2code import document_to_code_file

CWD = pathlib.Path("~/Desktop/Outbox").expanduser()
if not CWD.exists():
    CWD = pathlib.Path(".")

# ------------------------------------------------------------------------------
# This example shows how to generate a full-document replay script from a DXF.
#
# docs: https://dxfpy.mozman.at/docs/addons/dxf2code.html
# ------------------------------------------------------------------------------

FILENAME = "A_000217"
CADKIT = dxfpy.options.test_files_path / "CADKitSamples"
DXF_FILE = CADKIT / f"{FILENAME}.dxf"
SCRIPT_FILE = CWD / f"{FILENAME}_replay.py"
OUTPUT_FILE = CWD / f"{FILENAME}_replay.dxf"


def main():
    print("writing " + str(SCRIPT_FILE))
    document_to_code_file(str(DXF_FILE), str(SCRIPT_FILE), str(OUTPUT_FILE))
    print("generated replay script: " + str(SCRIPT_FILE))
    print("script output target: " + str(OUTPUT_FILE))
    print("execute the generated script to create the DXF output")


if __name__ == "__main__":
    main()
