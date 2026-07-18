#!/usr/bin/env bash
set -euo pipefail

RUN_START_ID="${RUN_START_ID:-0}"
RUN_COUNT="${RUN_COUNT:-30}"
BASE_PORT="${BASE_PORT:-50051}"
JVM_CORES="${JVM_CORES:-0,1}"
PHASE4_JCM_DIR="${PHASE4_JCM_DIR:-build/phase4_jcm}"

cleanup() {
  if [[ -n "${LAUNCHER_PID:-}" ]]; then
    kill "${LAUNCHER_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo "[phase4] starting ${RUN_COUNT} Python daemons"
.venv/bin/python3 -m physical_engine.daemon_launcher --run-start-id "${RUN_START_ID}" --run-count "${RUN_COUNT}" --base-port "${BASE_PORT}" --jvm-reserved-cores 2 &
LAUNCHER_PID=$!

echo "[phase4] generating JCM files"
.venv/bin/python3 scripts/generate_factory_jcm.py --run-start-id "${RUN_START_ID}" --run-count "${RUN_COUNT}" --output-jcm "${PHASE4_JCM_DIR}/factory_phase4.jcm"

echo "[phase4] waiting for daemon readiness"
for run_id in $(seq ${RUN_START_ID} $((RUN_START_ID + RUN_COUNT - 1))); do
  port=$((BASE_PORT + (run_id - RUN_START_ID)))
  until .venv/bin/python3 - "$port" <<'PY'
import sys

import grpc

from physical_engine.protos import sim_bridge_pb2, sim_bridge_pb2_grpc

port = sys.argv[1]
channel = grpc.insecure_channel(f"127.0.0.1:{port}")
stub = sim_bridge_pb2_grpc.SimBridgeStub(channel)
try:
    response = stub.HealthCheck(sim_bridge_pb2.Empty(), timeout=1)
    raise SystemExit(0 if response.ready else 1)
except grpc.RpcError:
    raise SystemExit(1)
PY
  do
    sleep 0.5
  done
  echo "[phase4] daemon ${run_id} ready on port ${port}"
done

echo "[phase4] launching JVM pinned to cores ${JVM_CORES}"
taskset -c "${JVM_CORES}" ./gradlew run --args="--phase4 --run-start-id=${RUN_START_ID} --run-count=${RUN_COUNT} --base-port=${BASE_PORT} --phase4-jcm-dir=${PHASE4_JCM_DIR} --max-sim-time=3600"