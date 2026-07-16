import pytest
import os
from physical_engine.daemon_launcher import compute_daemon_core_sets

def test_compute_daemon_core_sets_round_robin(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    # 8 cores, 2 reserved for JVM. 6 available. 10 runs needed.
    # 10 > 6, so round robin should trigger.
    core_sets = compute_daemon_core_sets(10, 2)
    assert len(core_sets) == 10
    
    # available_cores = [2, 3, 4, 5, 6, 7]
    assert core_sets[0] == [2]
    assert core_sets[1] == [3]
    assert core_sets[5] == [7]
    assert core_sets[6] == [2]  # wrapped around
    assert core_sets[9] == [5]

def test_compute_daemon_core_sets_strict(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 8)
    # 8 cores, 2 reserved. 6 available. 3 runs needed.
    # 3 <= 6, so strict disjoint pinning.
    # 6 // 3 = 2 cores per run.
    core_sets = compute_daemon_core_sets(3, 2)
    assert len(core_sets) == 3
    assert core_sets[0] == [2, 3]
    assert core_sets[1] == [4, 5]
    assert core_sets[2] == [6, 7]
