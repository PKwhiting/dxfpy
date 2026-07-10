#  Copyright (c) 2021, Manfred Moitzi
#  License: MIT License

import time
import dxfpy
N = 10000
print(f"create {N} DXF drawings in a single process")
t0 = time.perf_counter()
for _ in range(N):
    dxfpy.new()
t = time.perf_counter()-t0
print(f"created {int(N / t)} DXF drawings per second")
