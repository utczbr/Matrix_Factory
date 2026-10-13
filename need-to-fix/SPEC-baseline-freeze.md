# Spec: `baseline-freeze`

Module id: `baseline-freeze` · Depends on: none · Findings: E-07, M-08 · Depth: **short** (no behaviour change)

## Objective

Make every later change attributable and stop the repo from asserting things the audit disproved.
Three things only: (1) pin what was audited, (2) retract the unsupported "p < 0.001" claim and flag results as under audit, (3) remove a hard-coded secret fallback.

**Done looks like:** a checkout of the tag verifies against the audit manifest; no document claims p < 0.001; no literal secret in source; the Python test suite is exactly as green as before.

## Tech Stack

Python 3.10 (CI), pytest, Markdown/MkDocs docs, git. No new dependencies.

## Commands

```
Verify audited snapshot : sha256sum -c AUDIT-MANIFEST.sha256          # run at the tag
Tag the snapshot        : git tag -a audit-baseline-2026-10 <commit> -m "Audited snapshot"
Python tests            : pytest physical_engine/ -q -p no:cacheprovider
New hygiene tests       : pytest tests/test_repo_hygiene.py -q
Secret scan             : git grep -n "phase4_monte_carlo_secure_key"      # must print nothing
Claim scan              : git grep -nE "p ?< ?0\.001" -- docs README.md    # must print nothing
Diff scope check        : git diff --stat audit-baseline-2026-10..HEAD
```

## Project Structure

```
AUDIT-MANIFEST.sha256        → SHA-256 of the 13 files I audited (already generated)
VERIFICATION.md              → evidence ledger (this initiative)
CAPABILITY-MAP.md, SPEC-*.md → initiative index and specs (project root)
tests/test_repo_hygiene.py   → NEW: secret + claim + banner guards
experiments/run_prosa_vs_adacor.py → secret resolution only
docs/artifact-evaluation/claim-matrix.md → Section 5.1 row
README.md, docs/index.md     → "results under audit" banner
```

## Code Style

```python
def resolve_telemetry_secret(environ: Mapping[str, str]) -> str:
    """Return the HMAC secret: the environment value, else an ephemeral random one.

    Never returns a literal embedded in source.
    """
    value = environ.get("TELEMETRY_HMAC_SECRET")
    if value:
        return value
    print("[warn] TELEMETRY_HMAC_SECRET unset; using an ephemeral per-invocation secret")
    return secrets.token_hex(32)
```
Type hints, docstring with one-line summary, no behaviour hidden in module scope.

## Testing Strategy

`pytest` unit tests in `tests/test_repo_hygiene.py` (file-scanning tests are acceptable here: the criteria are about repo content). CI runs `pytest physical_engine/` today; the new `tests/` directory needs a CI step (**ask first**, §Boundaries).

**Test integrity:** each guard is shown failing on the current tree before the fix (secret literal present → fail; claim row present → fail; banner absent → fail). Sabotage check: re-insert the literal / the claim and confirm the matching test fails, then revert. No oracle problem: expected values are the audit's own manifest and the literal strings.

## Boundaries

- **Always:** change only the files listed in *Project Structure*; run the full Python suite before and after and compare counts.
- **Ask first:** adding the `tests/` step to `.github/workflows/ci.yml`; moving `VERIFICATION.md`/specs into a `docs/audit/` folder instead of the root.
- **Never:** edit analysis results/CSVs, change any metric, touch physics or Java/ASL, delete the old claim text from git history, weaken any existing test.

## Success Criteria

| ID | Criterion | How verified |
|---|---|---|
| SC-BF-1 | A tag `audit-baseline-2026-10` exists and `sha256sum -c AUDIT-MANIFEST.sha256` passes at that tag. If it cannot (files changed since the audit), the failing file list is recorded in `VERIFICATION.md` and the tag is placed on the closest ancestor where it passes. | Command above, run at the tag |
| SC-BF-2 | No literal fallback secret remains; `resolve_telemetry_secret({})` returns 64 hex chars, differs between calls, and `resolve_telemetry_secret({"TELEMETRY_HMAC_SECRET": "x"}) == "x"`. All batches inside one `main()` use one resolved value. | `git grep` empty; 3 unit tests; test that `main()` resolves once (monkeypatch counter) |
| SC-BF-3 | `claim-matrix.md` Section 5.1 row contains no "p < 0.001"; it states *under revision* and links `analysis/results_stats.md`, quoting the repo's own smallest p (0.030, uncorrected, n = 15 v 15). | Claim scan empty; test parses the row |
| SC-BF-4 | `README.md` and `docs/index.md` start with a banner containing the text `RESULTS UNDER AUDIT` and a link to `VERIFICATION.md`. | Test asserts both files |
| SC-BF-5 | No behaviour change: `pytest physical_engine/` gives the same pass/skip counts as before (**70 passed, 14 skipped**, excluding `test_grpc_security.py`, as measured in the audit); diff touches only the listed files. | Before/after counts; `git diff --stat` |

## Open Questions

1. **Which commit was audited?** I audited a GitHub tarball of `main` (no `.git`, no SHA), so the manifest is the identity. *Default: tag HEAD if the manifest passes, else the nearest passing ancestor.*
2. **Secret fallback:** ephemeral random secret (default) vs. fail-fast when unset. Fail-fast is safer but breaks `python3 experiments/run_prosa_vs_adacor.py` for anyone who hasn't exported it (README documents that command).
3. Banner removal is owned by `claims-and-docs`, not this module. *Default: yes.*
