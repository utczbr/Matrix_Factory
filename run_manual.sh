#!/bin/bash
set -e

# 1. Compile Java classes and process resources if missing
./gradlew compileJava processResources --quiet

# 2. Generate Phase 4 Mega-JCM files if missing
python3 scripts/generate_factory_jcm.py --run-start-id=0 --run-count=2

# 3. Assemble runtime classpath
CLASSPATH="build/classes/java/main:build/resources/main"
shopt -s globstar nullglob
for jar in ~/.gradle/caches/modules-2/files-2.1/**/*.jar; do
    CLASSPATH="$CLASSPATH:$jar"
done

# 4. Launch MainSimulator
java -cp "$CLASSPATH" factory.MainSimulator --phase4 --run-count=2 --base-port=50051 --phase4-jcm-dir=build/phase4_jcm
echo "EXIT CODE: $?"
