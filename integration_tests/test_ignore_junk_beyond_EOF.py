#  Copyright (c) 2022, Manfred Moitzi
#  License: MIT License
import os
import dxfpy.recover

BASEDIR = os.path.dirname(__file__)
DATADIR = "data"
FILENAME = os.path.join(BASEDIR, DATADIR , "R12_with_trash_beyond_EOF.dxf")


def test_recover_ignores_junk_beyond_EOF():
    doc, auditor = dxfpy.recover.readfile(FILENAME)
    assert len(auditor.errors) == 0
    assert len(auditor.fixes) == 0
    msp = doc.modelspace()
    assert msp[0].dxftype() == "CIRCLE"


def test_readfile_ignores_junk_beyond_EOF():
    doc = dxfpy.readfile(FILENAME)
    msp = doc.modelspace()
    assert msp[0].dxftype() == "CIRCLE"
