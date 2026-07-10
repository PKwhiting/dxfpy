from io import StringIO

from dxfpy.entities import Block, EndBlk
from dxfpy.lldxf.tagwriter import TagWriter


BLOCK_WITH_TRANSPARENCY = """0
BLOCK
5
102E
330
102C
100
AcDbEntity
8
0
440
16777216
100
AcDbBlockBegin
2
*U40
70
1
10
0.0
20
0.0
30
0.0
3
*U40
1

"""

BLOCK_WITH_COLOR = """0
BLOCK
5
102E
330
102C
100
AcDbEntity
8
0
62
5
100
AcDbBlockBegin
2
*U40
70
1
10
0.0
20
0.0
30
0.0
3
*U40
1

"""

ENDBLK_WITH_TRANSPARENCY = """0
ENDBLK
5
1071
330
102C
100
AcDbEntity
8
0
440
16777216
100
AcDbBlockEnd
"""

ENDBLK_WITH_COLOR = """0
ENDBLK
5
1071
330
102C
100
AcDbEntity
8
0
62
3
100
AcDbBlockEnd
"""


def test_block_loads_transparency():
    entity = Block.from_text(BLOCK_WITH_TRANSPARENCY)

    assert entity.dxf.transparency == 16777216


def test_block_loads_color():
    entity = Block.from_text(BLOCK_WITH_COLOR)

    assert entity.dxf.color == 5


def test_block_exports_transparency():
    entity = Block.from_text(BLOCK_WITH_TRANSPARENCY)

    stream = StringIO()
    entity.export_dxf(TagWriter(stream, dxfversion="AC1024"))
    text = stream.getvalue().replace("\r\n", "\n")

    assert "\n440\n16777216\n" in text


def test_block_exports_color():
    entity = Block.from_text(BLOCK_WITH_COLOR)

    stream = StringIO()
    entity.export_dxf(TagWriter(stream, dxfversion="AC1024"))
    text = stream.getvalue().replace("\r\n", "\n")

    assert "\n 62\n5\n" in text


def test_endblk_loads_transparency():
    entity = EndBlk.from_text(ENDBLK_WITH_TRANSPARENCY)

    assert entity.dxf.transparency == 16777216


def test_endblk_loads_color():
    entity = EndBlk.from_text(ENDBLK_WITH_COLOR)

    assert entity.dxf.color == 3


def test_endblk_exports_transparency():
    entity = EndBlk.from_text(ENDBLK_WITH_TRANSPARENCY)

    stream = StringIO()
    entity.export_dxf(TagWriter(stream, dxfversion="AC1024"))
    text = stream.getvalue().replace("\r\n", "\n")

    assert "\n440\n16777216\n" in text


def test_endblk_exports_color():
    entity = EndBlk.from_text(ENDBLK_WITH_COLOR)

    stream = StringIO()
    entity.export_dxf(TagWriter(stream, dxfversion="AC1024"))
    text = stream.getvalue().replace("\r\n", "\n")

    assert "\n 62\n3\n" in text
