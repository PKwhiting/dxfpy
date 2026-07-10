#!/usr/bin/env python3
# Copyright (c) 2011-2024 Manfred Moitzi
# License: MIT License
import sys
from setuptools import setup
from setuptools import Extension

# setuptools docs: https://setuptools.pypa.io/en/latest/index.html
# build source distribution
#
#   python setup.py sdist --formats=zip,gztar
#
# build wheels:
#
#   python setup.py bdist_wheel
#
# All Cython modules are optional:
ext_modules = [
    Extension("dxfpy.acc.vector", ["src/dxfpy/acc/vector.pyx"], optional=True),
    Extension("dxfpy.acc.matrix44", ["src/dxfpy/acc/matrix44.pyx"], optional=True),
    Extension("dxfpy.acc.bezier4p", ["src/dxfpy/acc/bezier4p.pyx"], optional=True),
    Extension("dxfpy.acc.bezier3p", ["src/dxfpy/acc/bezier3p.pyx"], optional=True),
    Extension("dxfpy.acc.bspline", ["src/dxfpy/acc/bspline.pyx"], optional=True),
    Extension("dxfpy.acc.construct", ["src/dxfpy/acc/construct.pyx"], optional=True),
    Extension(
        "dxfpy.acc.mapbox_earcut", ["src/dxfpy/acc/mapbox_earcut.pyx"], optional=True
    ),
    Extension("dxfpy.acc.linetypes", ["src/dxfpy/acc/linetypes.pyx"], optional=True),
    Extension("dxfpy.acc.np_support", ["src/dxfpy/acc/np_support.pyx"], optional=True),
]
commands = {}
try:
    from Cython.Distutils import build_ext

    commands = {"build_ext": build_ext}
except ImportError:
    ext_modules = []


PYPY = hasattr(sys, "pypy_version_info")
if PYPY:
    print(
        "C-extensions are disabled for pypy, because JIT compiled Python code "
        "is much faster!"
    )
    ext_modules = []
    commands = {}


def get_version() -> str:
    v = {}
    for line in open("./src/dxfpy/version.py").readlines():
        if line.strip().startswith("__version__"):
            exec(line, v)
            return v["__version__"]
    raise IOError("__version__ string not found")


# static attributes are stored in pyproject.toml
# https://packaging.python.org/en/latest/guides/writing-pyproject-toml/
# https://setuptools.pypa.io/en/latest/index.html
setup(
    version=get_version(),
    cmdclass=commands,
    ext_modules=ext_modules,
)
