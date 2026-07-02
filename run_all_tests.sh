#!/bin/bash
echo "Running V1..."
./gradlew run --args="--max-ticks=10 --log-epochs" > test_v1.log 2>&1
echo "Running V2..."
./gradlew run --args="--max-orders=5 --max-ticks=100" > test_v2.log 2>&1
echo "Running V3 (Part 1)..."
./gradlew run --args="--max-orders=5 --cnp-slow-accept --ttl=2000 --max-ticks=100" > test_v3_1.log 2>&1
echo "Running V3 (Part 2)..."
./gradlew run --args="--force-abort-on=station_1 --order=order_2 --max-ticks=100" > test_v3_2.log 2>&1
echo "Running V4..."
./gradlew run --args="--price-series=price_series_spike_test.csv --max-ticks=100" > test_v4.log 2>&1
echo "Running V5..."
./gradlew run --args="--max-ticks=30 --log-brf=supervisor" > test_v5.log 2>&1
echo "Running V6..."
./gradlew run --args="--force-spike-at=5.0 --max-ticks=30" > test_v6.log 2>&1
echo "Running V7..."
./gradlew run --args="--max-orders=5 --grid-stress --lock-hold-orders=order_1,order_2,order_3 --max-ticks=100" > test_v7.log 2>&1
echo "Running V8..."
./gradlew run --args="--force-spike-at=5.0 --max-ticks=100 --max-orders=5" > test_v8.log 2>&1
echo "Running V9..."
./gradlew run --args="--inject-epoch-mismatch-on=station_5 --max-ticks=40" > test_v9.log 2>&1
echo "All tests finished!"
