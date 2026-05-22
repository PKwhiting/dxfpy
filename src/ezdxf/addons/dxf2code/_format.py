from __future__ import annotations

import json
from typing import TYPE_CHECKING, Iterable, Mapping

import numpy as np

if TYPE_CHECKING:
    from ezdxf.lldxf.types import DXFTag


_PURGE_DXF_ATTRIBUTES = {
    "handle",
    "owner",
    "paperspace",
    "material_handle",
    "visualstyle_handle",
    "plotstyle_handle",
}


def _purge_handles(attribs: dict) -> dict:
    return {k: v for k, v in attribs.items() if k not in _PURGE_DXF_ATTRIBUTES}


def _fmt_mapping(mapping: Mapping, indent: int = 0) -> Iterable[str]:
    fmt = " " * indent + "'{}': {},"
    for key, value in mapping.items():
        assert isinstance(key, str)
        if isinstance(value, str):
            value = json.dumps(value)
        else:
            value = str(value)
        yield fmt.format(key, value)


def _fmt_list(values: Iterable, indent: int = 0) -> Iterable[str]:
    def cleanup(items: Iterable) -> Iterable:
        for value in items:
            if isinstance(value, np.float64):
                yield float(value)
            else:
                yield value

    fmt = " " * indent + "{},"
    for value in values:
        if not isinstance(value, (float, int, str)):
            value = tuple(cleanup(value))
        yield fmt.format(str(value))


def _fmt_api_call(func_call: str, args: Iterable[str], dxfattribs: dict) -> list[str]:
    attributes = dict(dxfattribs)
    args = list(args) if args else []

    def fmt_keywords() -> Iterable[str]:
        for arg in args:
            if arg not in attributes:
                continue
            value = attributes.pop(arg)
            if isinstance(value, str):
                valuestr = json.dumps(value)
            else:
                valuestr = str(value)
            yield f"    {arg}={valuestr},"

    lines = [func_call]
    lines.extend(fmt_keywords())
    lines.append("    dxfattribs={")
    lines.extend(_fmt_mapping(attributes, indent=8))
    lines.extend(["    },", ")"])
    return lines


def _fmt_dxf_tags(tags: Iterable[DXFTag], indent: int = 0):
    fmt = " " * indent + "dxftag({}, {}),"
    for code, value in tags:
        assert isinstance(code, int)
        if isinstance(value, str):
            value = json.dumps(value)
        else:
            value = str(value)
        yield fmt.format(code, value)
