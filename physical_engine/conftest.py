import os

# Set NUMBA_NUM_THREADS before any test module or Numba JIT import
os.environ["NUMBA_NUM_THREADS"] = "1"
