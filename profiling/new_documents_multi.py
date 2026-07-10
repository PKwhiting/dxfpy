#  Copyright (c) 2021, Manfred Moitzi
#  License: MIT License

import time
import dxfpy
from multiprocessing import Pool, cpu_count


def work():
    dxfpy.new()


if __name__ == '__main__':
    cpu = cpu_count()
    N = 10000

    print(f"create {N} DXF drawings in {cpu} subprocesses")
    t0 = time.perf_counter()
    with Pool(processes=cpu) as pool:
        for _ in range(N):
            pool.apply(work)

    t = time.perf_counter() - t0
    print(f"created {int(N / t)} DXF drawings per second")
