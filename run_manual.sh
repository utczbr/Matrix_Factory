#!/bin/bash
CLASSPATH="build/classes/java/main:build/resources/main"
for jar in ~/.gradle/caches/modules-2/files-2.1/**/*.jar; do
    CLASSPATH="$CLASSPATH:$jar"
done
java -cp "$CLASSPATH" factory.MainSimulator --phase4 --run-count=2 --base-port=50051 --phase4-jcm-dir=build/phase4_jcm
echo "EXIT CODE: $?"
