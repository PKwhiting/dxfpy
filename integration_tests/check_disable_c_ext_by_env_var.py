# This test is hard to do in pytest!

import os

os.environ["DXFPY_DISABLE_C_EXT"] = "1"

import dxfpy
from dxfpy.math import Vec3
from dxfpy.math._vector import Vec3 as PythonVec3

print(f"disable C-Extension (should be True): {dxfpy.options.disable_c_ext}")
assert dxfpy.options.disable_c_ext is True

print(f"using C-Extension (should be False): {dxfpy.options.use_c_ext}")
assert dxfpy.options.use_c_ext is False

print(f"Vec3 is Python implementation (should be True): {Vec3 is PythonVec3}")
assert Vec3 is PythonVec3
