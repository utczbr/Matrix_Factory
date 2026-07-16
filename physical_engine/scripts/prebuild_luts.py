import sys
import logging
from physical_engine.optimization.lut_manager import LUTManager, MATRIX_FACTORY_LUT_CONFIG

logging.basicConfig(level=logging.INFO)

def main():
    print("Prebuilding LUTs using MATRIX_FACTORY_LUT_CONFIG...")
    manager = LUTManager(config=MATRIX_FACTORY_LUT_CONFIG)
    manager.initialize()
    print("LUT prebuild complete.")

if __name__ == "__main__":
    main()
