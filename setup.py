"""
setup.py — Cython Extension Build Configuration.

Usage:
    python setup.py build_ext --inplace
"""

from setuptools import Extension, setup
from Cython.Build import cythonize
import numpy

extensions = [
    Extension(
        name="physical_engine.optimization._numba_ops_core",
        sources=["physical_engine/optimization/_numba_ops_core.pyx"],
        include_dirs=[numpy.get_include()],
    )
]

setup(
    name="matrix_factory_twin",
    ext_modules=cythonize(extensions, compiler_directives={"language_level": "3"}),
)
