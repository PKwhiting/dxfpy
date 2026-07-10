# Copyright (c) 2018-2022, Manfred Moitzi
# License: MIT License
""" dxfpy typing hints

Only usable in type checking mode:

if TYPE_CHECKING:
    from dxfpy.document import Drawing
    from dxfpy.eztypes import GenericLayoutType

Tips for Type Imports
---------------------

Import Drawing class:

    from dxfpy.document import Drawing

Import DXF entities from dxfpy.entities:

    from dxfpy.entities import Line, Point, ...

Import layouts from dxfpy.layouts:

   from dxfpy.layouts import BaseLayout, Layout, Modelspace, Paperspace, BlockLayout

Import math tools from dxfpy.math:

    from dxfpy.math import Vec2, Vec3, Matrix44, ...

Import path tools from dxfpy.path:

    from dxfpy.path import Path, make_path, ...

"""
from __future__ import annotations
from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    Iterable,
    List,
    Sequence,
    TYPE_CHECKING,
    Tuple,
    Union,
)
from typing_extensions import TypeAlias

if TYPE_CHECKING:
    from dxfpy.entities import DXFEntity
    from dxfpy.layouts.base import VirtualLayout
    from dxfpy.layouts.blocklayout import BlockLayout
    from dxfpy.layouts.layout import Layout
    from dxfpy.lldxf.extendedtags import ExtendedTags
    from dxfpy.lldxf.tags import Tags
    from dxfpy.math import UVec

    IterableTags: TypeAlias = Iterable[Tuple[int, Any]]
    SectionDict: TypeAlias = Dict[str, List[Union[Tags, ExtendedTags]]]
    KeyFunc: TypeAlias = Callable[[DXFEntity], Hashable]
    FaceType: TypeAlias = Sequence[UVec]
    GenericLayoutType: TypeAlias = Union[Layout, BlockLayout, VirtualLayout]
