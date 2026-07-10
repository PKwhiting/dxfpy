# Copyright (c) 2024, Manfred Moitzi
# License: MIT License
from pathlib import Path
import dxfpy
from dxfpy import xref

CWD = Path(__file__).parent
OUTBOX = Path("~/Desktop/Outbox").expanduser()
if not OUTBOX.exists():
    OUTBOX = CWD
SRC_BLK_NAME = "JustAnyBlockName"


def create_source_doc():
    doc = dxfpy.new()
    blk = doc.blocks.new(SRC_BLK_NAME)
    blk.add_circle((0, 0), radius=5)
    return doc


def main():
    sdoc = create_source_doc()
    tdoc = dxfpy.new()

    # import data from sdoc into tdoc
    loader = xref.Loader(sdoc, tdoc)
    blk = sdoc.blocks.get(SRC_BLK_NAME)
    # import block layout SRC_BLK_NAME
    loader.load_block_layout(blk)
    # run import process
    loader.execute()

    # test if SRC_BLK_NAME was imported
    assert SRC_BLK_NAME in tdoc.blocks
    msp = tdoc.modelspace()
    # create a new block reference to the imported  block
    msp.add_blockref(SRC_BLK_NAME, insert=(5, 5))

    tdoc.saveas(OUTBOX / "imported_block.dxf")


if __name__ == "__main__":
    main()
