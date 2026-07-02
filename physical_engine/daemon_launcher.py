"""Monte Carlo fan-out launcher for Phase 4.

Spawns one Python daemon per Monte Carlo run using the spawn start method so
each child can read its own NUMBA_NUM_THREADS value before importing any Numba
touching code.
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import signal
import time
from collections.abc import Sequence

logger = logging.getLogger(__name__)

DEFAULT_BASE_PORT = 50051
DEFAULT_RUN_COUNT = 30
DEFAULT_JVM_RESERVED_CORES = 2


def compute_daemon_core_sets(run_count: int, jvm_reserved_cores: int) -> list[list[int]]:
    total_cores = os.cpu_count() or run_count
    required_cores = jvm_reserved_cores + run_count
    if total_cores < required_cores:
        raise RuntimeError(
            f"Phase 4 requires at least {required_cores} CPU cores for strict disjoint pinning; "
            f"found {total_cores}."
        )

    available_cores = list(range(jvm_reserved_cores, total_cores))
    return [
        available_cores[i * len(available_cores) // run_count : (i + 1) * len(available_cores) // run_count]
        for i in range(run_count)
    ]


def _daemon_entry(port: int, run_id: int, num_threads: int, core_set: Sequence[int]) -> None:
    os.environ["NUMBA_NUM_THREADS"] = str(num_threads)

    try:
        os.sched_setaffinity(0, set(core_set))
    except (AttributeError, OSError) as exc:
        logger.warning("[run=%s] CPU affinity pin skipped: %s", run_id, exc)

    from physical_engine.sim_bridge_server import serve

    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [run={run_id}] [%(levelname)s] %(message)s",
    )
    serve(port=port, run_id=run_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Phase 4 Python daemons.")
    parser.add_argument("--run-count", type=int, default=DEFAULT_RUN_COUNT)
    parser.add_argument("--base-port", type=int, default=DEFAULT_BASE_PORT)
    parser.add_argument("--jvm-reserved-cores", type=int, default=DEFAULT_JVM_RESERVED_CORES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    total_cores = os.cpu_count() or args.run_count
    num_threads = max(1, total_cores // args.run_count)
    core_sets = compute_daemon_core_sets(args.run_count, args.jvm_reserved_cores)

    logger.info(
        "Launching %s daemons with %s threads each on %s total cores.",
        args.run_count,
        num_threads,
        total_cores,
    )

    ctx = multiprocessing.get_context("spawn")
    processes: dict[int, multiprocessing.process.BaseProcess] = {}
    shutdown_requested = False

    def _handle_signal(signum, frame) -> None:  # noqa: ANN001
        nonlocal shutdown_requested
        shutdown_requested = True
        logger.info("Received signal %s, beginning shutdown.", signum)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    for run_id in range(args.run_count):
        port = args.base_port + run_id
        process = ctx.Process(
            target=_daemon_entry,
            args=(port, run_id, num_threads, core_sets[run_id]),
            name=f"simbridge-daemon-{run_id}",
            daemon=False,
        )
        process.start()
        processes[run_id] = process
        logger.info("[run=%s] started pid=%s port=%s", run_id, process.pid, port)

    try:
        while not shutdown_requested:
            time.sleep(2.0)
            for run_id, process in list(processes.items()):
                if process.is_alive():
                    continue
                logger.error("[run=%s] daemon exited unexpectedly (exitcode=%s); restarting", run_id, process.exitcode)
                port = args.base_port + run_id
                replacement = ctx.Process(
                    target=_daemon_entry,
                    args=(port, run_id, num_threads, core_sets[run_id]),
                    name=f"simbridge-daemon-{run_id}",
                    daemon=False,
                )
                replacement.start()
                processes[run_id] = replacement
                logger.info("[run=%s] restarted pid=%s port=%s", run_id, replacement.pid, port)
    finally:
        logger.info("Stopping all daemons.")
        for process in processes.values():
            process.terminate()
        for run_id, process in processes.items():
            process.join(timeout=10)
            if process.is_alive():
                logger.warning("[run=%s] did not exit cleanly; killing", run_id)
                process.kill()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    main()