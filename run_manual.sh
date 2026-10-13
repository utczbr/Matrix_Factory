#!/usr/bin/env bash
set -e

# 1. Generate Phase 4 Mega-JCM files if missing
python3 scripts/generate_factory_jcm.py --run-start-id=0 --run-count=2

# 2. Launch MainSimulator via Gradle with project classpath and JVM arguments
./gradlew run --args="--phase4 --run-count=2 --base-port=50051 --phase4-jcm-dir=build/phase4_jcm"
