# Copyright (C) 2018-2023, Manfred Moitzi
# License: MIT License
from __future__ import annotations
from typing import BinaryIO, TextIO, TYPE_CHECKING, Union, Sequence, Optional
import base64
import io
import pathlib
import os

from dxfpy.tools.standards import setup_drawing
from dxfpy.lldxf.const import DXF2013
from dxfpy.document import Drawing

_BINARY_DXF_SIGNATURE = b"AutoCAD Binary DXF\r\n\x1a\x00"

if TYPE_CHECKING:
    from dxfpy.lldxf.validator import DXFInfo


def new(
    dxfversion: str = DXF2013,
    setup: Union[str, bool, Sequence[str]] = False,
    units: int = 6,
) -> Drawing:
    """Create a new :class:`~dxfpy.drawing.Drawing` from scratch, `dxfversion`
    can be either "AC1009" the official DXF version name or "R12" the
    AutoCAD release name.

    :func:`new` can create drawings for following DXF versions:

    ======= ========================
    Version AutoCAD Release
    ======= ========================
    AC1009  AutoCAD R12
    AC1015  AutoCAD R2000
    AC1018  AutoCAD R2004
    AC1021  AutoCAD R2007
    AC1024  AutoCAD R2010
    AC1027  AutoCAD R2013
    AC1032  AutoCAD R2018
    ======= ========================

    The `units` argument defines th document and modelspace units. The header
    variable $MEASUREMENT will be set according to the given `units`, 0 for
    inch, feet, miles, ... and 1 for metric units. For more information go to
    module :mod:`dxfpy.units`

    Args:
        dxfversion: DXF version specifier as string, default is "AC1027"
            respectively "R2013"
        setup: setup default styles, ``False`` for no setup,
            ``True`` to setup everything or a list of topics as strings,
            e.g. ["linetypes", "styles"] to setup only some topics:

            ================== ========================================
            Topic              Description
            ================== ========================================
            linetypes          setup line types
            styles             setup text styles
            dimstyles          setup default `dxfpy` dimension styles
            visualstyles       setup 25 standard visual styles
            ================== ========================================
        units: document and modelspace units, default is 6 for meters

    """
    doc = Drawing.new(dxfversion)
    doc.units = units
    doc.header["$MEASUREMENT"] = 0 if units in (1, 2, 3, 8, 9, 10) else 1
    if setup:
        setup_drawing(doc, topics=setup)
    return doc


def read(stream: TextIO) -> Drawing:
    """Read a DXF document from a text-stream. Open stream in text mode
    (``mode='rt'``) and set correct text encoding, the stream requires at least
    a :meth:`readline` method.

    Since DXF version R2007 (AC1021) file encoding is always "utf-8",
    use the helper function :func:`dxf_stream_info` to detect the required
    text encoding for prior DXF versions. To preserve possible binary data in
    use :code:`errors='surrogateescape'` as error handler for the import stream.

    If this function struggles to load the DXF document and raises a
    :class:`DXFStructureError` exception, try the :func:`dxfpy.recover.read`
    function to load this corrupt DXF document.

    Args:
        stream: input text stream opened with correct encoding

    Raises:
        DXFStructureError: for invalid or corrupted DXF structures

    """
    from dxfpy.document import Drawing

    return Drawing.read(stream)


def readbytes(
    data: bytes,
    encoding: Optional[str] = None,
    errors: str = "surrogateescape",
) -> Drawing:
    """Read an ASCII or Binary DXF document from bytes.

    :param data: Complete DXF document data.
    :param encoding: Optional ASCII DXF encoding override. Ignored for Binary
        DXF data.
    :param errors: Decoding error handler for text values.
    :return: Loaded DXF document.
    :raises TypeError: If `data` is not bytes.
    """
    if not isinstance(data, bytes):
        raise TypeError("DXF data must be bytes")
    if data.startswith(_BINARY_DXF_SIGNATURE):
        return _read_binary_dxf_data(data, errors)
    return _read_ascii_dxf_data(data, encoding, errors)


def readstream(
    stream: BinaryIO,
    encoding: Optional[str] = None,
    errors: str = "surrogateescape",
) -> Drawing:
    """Read an ASCII or Binary DXF document from a binary stream.

    Reading starts at the current position and consumes the stream through EOF.

    :param stream: Binary input stream.
    :param encoding: Optional ASCII DXF encoding override. Ignored for Binary
        DXF data.
    :param errors: Decoding error handler for text values.
    :return: Loaded DXF document.
    :raises TypeError: If the stream does not return bytes.
    """
    data = stream.read()
    if not isinstance(data, bytes):
        raise TypeError("binary DXF stream required")
    return readbytes(data, encoding=encoding, errors=errors)


def _read_binary_dxf_data(data: bytes, errors: str) -> Drawing:
    """Load native Binary DXF data."""
    from dxfpy.lldxf.tagger import binary_tags_loader

    return Drawing.load(binary_tags_loader(data, errors=errors))


def _read_ascii_dxf_data(
    data: bytes, encoding: Optional[str], errors: str
) -> Drawing:
    """Detect and decode ASCII DXF data."""
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    detected = _detect_ascii_dxf_encoding(normalized)
    document = read(io.StringIO(normalized.decode(encoding or detected, errors)))
    _apply_encoding_override(document, encoding)
    return document


def _detect_ascii_dxf_encoding(data: bytes) -> str:
    """Return the encoding declared by ASCII DXF data."""
    stream = io.StringIO(data.decode("utf-8", errors="ignore"))
    return dxf_stream_info(stream).encoding


def _apply_encoding_override(
    document: Drawing, encoding: Optional[str]
) -> None:
    """Store a supported explicit ASCII DXF encoding."""
    from dxfpy.tools.codepage import is_supported_encoding

    if encoding is not None and is_supported_encoding(encoding):
        document.encoding = encoding


def readfile(
    filename: str | os.PathLike,
    encoding: Optional[str] = None,
    errors: str = "surrogateescape",
) -> Drawing:
    """Read the DXF document `filename` from the file-system.

    This is the preferred method to load existing ASCII or Binary DXF files,
    the required text encoding will be detected automatically and decoding
    errors will be ignored.

    Override encoding detection by setting argument `encoding` to the
    estimated encoding. (use Python encoding names like in the :func:`open`
    function).

    If this function struggles to load the DXF document and raises a
    :class:`DXFStructureError` exception, try the :func:`dxfpy.recover.readfile`
    function to load this corrupt DXF document.

    Args:
        filename: filename of the ASCII- or Binary DXF document
        encoding: use ``None`` for auto detect (default), or set a specific
            encoding like "utf-8", argument is ignored for Binary DXF files
        errors: specify decoding error handler

            - "surrogateescape" to preserve possible binary data (default)
            - "ignore" to use the replacement char U+FFFD "\ufffd" for invalid data
            - "strict" to raise an :class:`UnicodeDecodeError` exception for invalid data

    Raises:
        IOError: not a DXF file or file does not exist
        DXFStructureError: for invalid or corrupted DXF structures
        UnicodeDecodeError: if `errors` is "strict" and a decoding error occurs

    """
    from dxfpy.lldxf.validator import is_dxf_file, is_binary_dxf_file
    from dxfpy.tools.codepage import is_supported_encoding
    from dxfpy.lldxf.tagger import binary_tags_loader

    filename = str(filename)
    if is_binary_dxf_file(filename):
        with open(filename, "rb") as fp:
            data = fp.read()
            loader = binary_tags_loader(data, errors=errors)
            doc = Drawing.load(loader)
            doc.filename = filename
            return doc

    if not is_dxf_file(filename):
        raise IOError(f"File '{filename}' is not a DXF file.")

    info = dxf_file_info(filename)
    if encoding is not None:
        # override default encodings if absolute necessary
        info.encoding = encoding
    with open(filename, mode="rt", encoding=info.encoding, errors=errors) as fp:
        doc = read(fp)

    doc.filename = filename
    if encoding is not None and is_supported_encoding(encoding):
        # store overridden encoding if supported by AutoCAD, else default
        # encoding stored in $DWGENCODING is used as document encoding or
        # 'cp1252' if $DWGENCODING is unset.
        doc.encoding = encoding
    return doc


def dxf_file_info(filename: str | os.PathLike) -> DXFInfo:
    """Reads basic file information from a DXF document: DXF version, encoding
    and handle seed.

    """
    filename = str(filename)
    with open(filename, mode="rt", encoding="utf-8", errors="ignore") as fp:
        return dxf_stream_info(fp)


def dxf_stream_info(stream: TextIO) -> DXFInfo:
    """Reads basic DXF information from a text stream: DXF version, encoding
    and handle seed.

    """
    from dxfpy.lldxf.validator import dxf_info

    info = dxf_info(stream)
    # R2007 files and later are always encoded as UTF-8
    if info.version >= "AC1021":
        info.encoding = "utf-8"
    return info


def readzip(
    zipfile: str | os.PathLike,
    filename: Optional[str] = None,
    errors: str = "surrogateescape",
) -> Drawing:
    """Load a DXF document specified by `filename` from a zip archive, or if
    `filename` is ``None`` the first DXF document in the zip archive.

    Args:
        zipfile: name of the zip archive
        filename: filename of DXF file, or ``None`` to load the first DXF
            document from the zip archive.
        errors: specify decoding error handler

            - "surrogateescape" to preserve possible binary data (default)
            - "ignore" to use the replacement char U+FFFD "\ufffd" for invalid data
            - "strict" to raise an :class:`UnicodeDecodeError` exception for invalid data

    Raises:
        IOError: not a DXF file or file does not exist or
            if `filename` is ``None`` - no DXF file found
        DXFStructureError: for invalid or corrupted DXF structures
        UnicodeDecodeError: if `errors` is "strict" and a decoding error occurs

    """
    from dxfpy.tools.zipmanager import ctxZipReader

    with ctxZipReader(str(zipfile), filename, errors=errors) as zipstream:
        doc = read(zipstream)  # type: ignore
        doc.filename = zipstream.dxf_file_name
    return doc


def decode_base64(data: bytes, errors: str = "surrogateescape") -> Drawing:
    """Load a DXF document from base64 encoded binary data, like uploaded data
    to web applications.

    Args:
        data: DXF document base64 encoded binary data
        errors: specify decoding error handler

            - "surrogateescape" to preserve possible binary data (default)
            - "ignore" to use the replacement char U+FFFD "\ufffd" for invalid data
            - "strict" to raise an :class:`UnicodeDecodeError` exception for invalid data

    Raises:
        DXFStructureError: for invalid or corrupted DXF structures
        UnicodeDecodeError: if `errors` is "strict" and a decoding error occurs

    """
    return readbytes(base64.b64decode(data), errors=errors)


def find_support_file(
    filename: str, support_dirs: Optional[Sequence[str]] = None
) -> str:
    """Find file `filename` in the support directories`."""
    if pathlib.Path(filename).exists():
        return filename
    if support_dirs is None:
        support_dirs = []
    for directory in support_dirs:
        directory = directory.strip("\"'")
        filepath = pathlib.Path(directory).expanduser() / filename
        if filepath.exists():
            return str(filepath)
    return filename
