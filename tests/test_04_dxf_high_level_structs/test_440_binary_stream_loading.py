import base64
from io import BytesIO, StringIO

import dxfpy
import pytest


@pytest.mark.parametrize(
    ("version", "value"), (("R2000", "Größe"), ("R2018", "東京"))
)
def test_readbytes_loads_ascii_dxf_with_detected_encoding(version, value):
    source = dxfpy.new(version)
    source.modelspace().add_text(value)

    loaded = dxfpy.readbytes(_ascii_data(source))

    assert loaded.acad_release == version
    assert loaded.modelspace().query("TEXT").first.dxf.text == value


@pytest.mark.parametrize(
    ("version", "value"), (("R2000", "Größe"), ("R2018", "東京"))
)
def test_readbytes_loads_binary_dxf(version, value):
    source = dxfpy.new(version)
    source.modelspace().add_line((1, 2), (3, 4))
    source.modelspace().add_text(value)
    stream = BytesIO()
    source.write(stream, fmt="bin")

    loaded = dxfpy.readbytes(stream.getvalue())
    decoded = dxfpy.decode_base64(base64.b64encode(stream.getvalue()))

    line = loaded.modelspace().query("LINE").first
    assert line.dxf.start == (1, 2, 0)
    assert line.dxf.end == (3, 4, 0)
    assert loaded.modelspace().query("TEXT").first.dxf.text == value
    assert decoded.modelspace().query("TEXT").first.dxf.text == value


def test_readstream_consumes_from_current_position():
    data = _ascii_data(dxfpy.new("R2018"))
    stream = BytesIO(b"prefix" + data)
    stream.seek(len(b"prefix"))

    loaded = dxfpy.readstream(stream)

    assert loaded.acad_release == "R2018"
    assert stream.tell() == len(b"prefix") + len(data)


def test_readstream_rejects_text_stream():
    with pytest.raises(TypeError, match="binary DXF stream required"):
        dxfpy.readstream(StringIO("not binary"))  # type: ignore[arg-type]


def _ascii_data(document: dxfpy.document.Drawing) -> bytes:
    stream = StringIO()
    document.write(stream)
    return document.encode(stream.getvalue()).replace(b"\n", b"\r\n")
