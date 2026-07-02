"""Phase 4 seeding and launch-budget checks."""

from __future__ import annotations

from unittest.mock import patch

from physical_engine.daemon_launcher import compute_daemon_core_sets
from physical_engine.sim_bridge_server import derive_seed


def test_derive_seed_is_reproducible() -> None:
    assert derive_seed("S5", 7) == derive_seed("S5", 7)


def test_derive_seed_differs_across_run_ids() -> None:
    assert derive_seed("S5", 7) != derive_seed("S5", 8)


def test_core_sets_are_disjoint() -> None:
    with patch("physical_engine.daemon_launcher.os.cpu_count", return_value=32):
        core_sets = compute_daemon_core_sets(run_count=30, jvm_reserved_cores=2)

    flattened = [core for core_set in core_sets for core in core_set]
    assert len(flattened) == len(set(flattened))
    assert all(core >= 2 for core in flattened)


def main() -> None:
    test_derive_seed_is_reproducible()
    test_derive_seed_differs_across_run_ids()
    test_core_sets_are_disjoint()
    print("seeding and launch-budget checks passed")


if __name__ == "__main__":
    main()