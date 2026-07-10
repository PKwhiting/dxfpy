#  Copyright (c) 2020-2022, Manfred Moitzi
#  License: MIT License
from typing import Union, Sequence
from typing_extensions import TypeAlias
# noinspection PyUnresolvedReferences
from dxfpy.acc import USE_C_EXT

__all__ = [
    "Vec3",
    "Vec2",
    "AnyVec",
    "UVec",
    "X_AXIS",
    "Y_AXIS",
    "Z_AXIS",
    "NULLVEC",
    "distance",
    "lerp",
    "Matrix44",
    "Bezier4P",
    "Bezier3P",
    "Basis",
    "Evaluator",
    "cubic_bezier_arc_parameters",
    "cubic_bezier_from_arc",
    "cubic_bezier_from_ellipse",
    "has_clockwise_orientation",
    "intersection_line_line_2d",
    "intersection_ray_ray_3d",
    "arc_angle_span_deg",
    "arc_angle_span_rad",
    "is_point_in_polygon_2d",
    "world_mercator_to_gps",
    "gps_to_world_mercator",
]
# Import of Python or Cython implementations:
if USE_C_EXT:
    from dxfpy.acc.vector import (
        Vec3,
        Vec2,
        X_AXIS,
        Y_AXIS,
        Z_AXIS,
        NULLVEC,
        distance,
        lerp,
    )
    from dxfpy.acc.matrix44 import Matrix44
    from dxfpy.acc.bezier4p import (
        Bezier4P,
        cubic_bezier_arc_parameters,
        cubic_bezier_from_arc,
        cubic_bezier_from_ellipse,
    )
    from dxfpy.acc.bezier3p import Bezier3P
    from dxfpy.acc.bspline import Basis, Evaluator
    from dxfpy.acc.construct import (
        has_clockwise_orientation,
        intersection_line_line_2d,
        intersection_ray_ray_3d,
        arc_angle_span_deg,
        arc_angle_span_rad,
        is_point_in_polygon_2d,
        world_mercator_to_gps,
        gps_to_world_mercator,

    )
else:
    from ._vector import (
        Vec3,
        Vec2,
        X_AXIS,
        Y_AXIS,
        Z_AXIS,
        NULLVEC,
        distance,
        lerp,
    )
    from ._matrix44 import Matrix44
    from ._bezier4p import (
        Bezier4P,
        cubic_bezier_arc_parameters,
        cubic_bezier_from_arc,
        cubic_bezier_from_ellipse,
    )
    from ._bezier3p import Bezier3P
    from ._bspline import Basis, Evaluator
    from ._construct import (
        has_clockwise_orientation,
        intersection_line_line_2d,
        intersection_ray_ray_3d,
        arc_angle_span_deg,
        arc_angle_span_rad,
        is_point_in_polygon_2d,
        world_mercator_to_gps,
        gps_to_world_mercator,
    )

# Early required type aliases
AnyVec: TypeAlias = Union[Vec2, Vec3]
UVec: TypeAlias = Union[Sequence[float], Vec2, Vec3]
