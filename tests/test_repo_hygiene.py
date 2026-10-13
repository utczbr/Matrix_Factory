"""Repo hygiene tests for Matrix Factory Twin.

Guards defined in need-to-fix/SPEC-baseline-freeze.md:
- SC-BF-1: Baseline tag and SHA-256 manifest integrity
- SC-BF-2: Elimination of literal secret fallback and resolution testing
- SC-BF-3: Retraction of uncorrected p < 0.001 claims
- SC-BF-4: Audit banners in README and docs/index.md
"""

import os
import re
import subprocess
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_sc_bf_1_audit_baseline_tag():
    """SC-BF-1: Tag audit-baseline-2026-10 exists and audited manifest passes at that tag."""
    import hashlib

    res = subprocess.run(
        ["git", "tag", "-l", "audit-baseline-2026-10"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "audit-baseline-2026-10" in res.stdout.strip(), (
        "Tag audit-baseline-2026-10 not found"
    )

    manifest_path = REPO_ROOT / "need-to-fix" / "AUDIT-MANIFEST.sha256"
    assert manifest_path.exists(), f"Manifest file missing: {manifest_path}"

    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        expected_hash, rel_file = line.split(None, 1)
        rel_file = rel_file.strip()

        show = subprocess.run(
            ["git", "show", f"audit-baseline-2026-10:{rel_file}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
        actual_hash = hashlib.sha256(show.stdout).hexdigest()
        assert actual_hash == expected_hash, (
            f"Hash mismatch at tag audit-baseline-2026-10 for {rel_file}: "
            f"expected {expected_hash}, got {actual_hash}"
        )


def test_sc_bf_2_secret_scan_empty():
    """SC-BF-2: No literal secret phase4_monte_carlo_secure_key remains in repo."""
    res = subprocess.run(
        ["git", "grep", "-n", "phase4_monte_carlo_secure_key"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0 and len(res.stdout.strip()) == 0, (
        f"Found literal secret occurrences:\n{res.stdout}"
    )


def test_sc_bf_2_resolve_telemetry_secret_unit():
    """SC-BF-2: Unit tests for resolve_telemetry_secret behavior."""
    from experiments.run_prosa_vs_adacor import resolve_telemetry_secret

    # 1. Unset returns 64 hex chars (32 bytes token_hex)
    val1 = resolve_telemetry_secret({})
    assert isinstance(val1, str)
    assert len(val1) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", val1)

    # 2. Differs between calls (ephemeral random)
    val2 = resolve_telemetry_secret({})
    assert val1 != val2

    # 3. Environment value takes precedence
    custom = "my_custom_production_secret_key"
    val3 = resolve_telemetry_secret({"TELEMETRY_HMAC_SECRET": custom})
    assert val3 == custom


def test_sc_bf_2_main_resolves_secret_once(monkeypatch):
    """SC-BF-2: main() resolves TELEMETRY_HMAC_SECRET once rather than per batch."""
    import experiments.run_prosa_vs_adacor as runner

    call_count = 0
    orig_resolve = runner.resolve_telemetry_secret

    def counting_resolve(environ):
        nonlocal call_count
        call_count += 1
        return orig_resolve(environ)

    monkeypatch.setattr(runner, "resolve_telemetry_secret", counting_resolve)

    # Inspect AST or verify main() only calls resolve_telemetry_secret once
    import ast
    source = Path(runner.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    main_func = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    # Count calls to resolve_telemetry_secret inside main()
    calls = [
        n for n in ast.walk(main_func)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == "resolve_telemetry_secret")
            or (isinstance(n.func, ast.Attribute) and n.func.attr == "resolve_telemetry_secret")
        )
    ]
    assert len(calls) == 1, f"Expected exactly 1 call to resolve_telemetry_secret in main(), found {len(calls)}"


def test_sc_bf_3_claim_scan_empty():
    r"""SC-BF-3: git grep -nE 'p ?< ?0\.001' -- docs README.md returns nothing."""
    res = subprocess.run(
        ["git", "grep", "-nE", r"p ?< ?0\.001", "--", "docs", "README.md"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0 and len(res.stdout.strip()) == 0, (
        f"Found unretracted p < 0.001 claims:\n{res.stdout}"
    )


def test_sc_bf_3_claim_matrix_section_5_1_row():
    """SC-BF-3: claim-matrix.md Section 5.1 row is updated with proper context."""
    claim_matrix = (REPO_ROOT / "docs" / "artifact-evaluation" / "claim-matrix.md").read_text(encoding="utf-8")
    sec_5_1_lines = [
        line for line in claim_matrix.splitlines()
        if "Section 5.1" in line
    ]
    assert len(sec_5_1_lines) == 1, "Section 5.1 row not found in claim-matrix.md"
    row = sec_5_1_lines[0]

    assert "p < 0.001" not in row, f"Row still contains 'p < 0.001': {row}"
    assert "under revision" in row.lower(), f"Row does not mention 'under revision': {row}"
    assert "results_stats.md" in row, f"Row does not link results_stats.md: {row}"
    assert "0.030" in row, f"Row does not quote smallest p-value 0.030: {row}"
    assert "15" in row, f"Row does not quote n=15: {row}"


def test_sc_bf_4_audit_banners():
    """SC-BF-4: README.md and docs/index.md start with RESULTS UNDER AUDIT banner."""
    for rel_path in ["README.md", "docs/index.md"]:
        path = REPO_ROOT / rel_path
        content = path.read_text(encoding="utf-8")
        first_15_lines = "\n".join(content.splitlines()[:15])

        assert "RESULTS UNDER AUDIT" in first_15_lines, (
            f"{rel_path} header does not contain 'RESULTS UNDER AUDIT'"
        )
        assert "VERIFICATION.md" in first_15_lines, (
            f"{rel_path} header does not link or mention VERIFICATION.md"
        )
