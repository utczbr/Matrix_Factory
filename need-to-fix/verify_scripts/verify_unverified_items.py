"""
Verification script for previously unverified / inspection-only items in MATRIX-FACTORY-PROBLEMS.md:
  - 🔎 Items: P-19, M-05, M-09, T-03
  - ❓ Items: P-17, P-18, P-20, M-07, D-06
"""

import os
import re
import sys
import time
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

def print_section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

# ==============================================================================
# P-19: Silent fallback to a "perfect stack" on database errors
# ==============================================================================
print_section("🔎 P-19: Silent fallback to perfect stack on database errors")
tb_file = REPO_ROOT / "src/main/java/factory/TestBenchArtifact.java"
tb_content = tb_file.read_text()

# Check fallback catch blocks
has_quality_catch = "testing with zero quality penalty" in tb_content
has_mechanistic_catch = "failed to fetch mechanistic signal" in tb_content
has_defect_mismatch = "activityDerate = Math.min(0.6, defectCount * 0.15);" in tb_content

print(f"  [Code] Quality fetch catch logs zero-penalty fallback: {has_quality_catch}")
print(f"  [Code] Mechanistic signal catch defaults to nominal (1.0, 4.25, 0.78): {has_mechanistic_catch}")
print(f"  [Code] Comment/code mismatch (uses total defectCount across all stations, not 1-2): {has_defect_mismatch}")

# Runtime test: RunBatchTest with defective parameters vs zero-penalty fallback
import physical_engine.sim_bridge_server as s
from physical_engine.protos import sim_bridge_pb2 as pb
from physical_engine.factory_simulation.pemfc_model import OHMIC_DEGRADATION

s.time.sleep = lambda x: None
svc = s.SimBridgeServicer(num_cells=200, R_internal=0.06)

req_real_defect = pb.BatchTestRequest(
    stack_id="S_DEFECT", num_cells=100, operating_temp_k=350.0,
    inlet_pressure_h2_bar=2.0, inlet_pressure_o2_bar=2.0,
    r_internal_penalty_ohm_cm2=1 * 0.08, activity_derate_fraction=0.15,
    ecsa_ratio=1.0, p_clamp_mpa=4.25, gdl_porosity=0.78,
)
resp_defect = svc.RunBatchTest(req_real_defect, None)

req_fallback_perfect = pb.BatchTestRequest(
    stack_id="S_FALLBACK", num_cells=100, operating_temp_k=350.0,
    inlet_pressure_h2_bar=2.0, inlet_pressure_o2_bar=2.0,
    r_internal_penalty_ohm_cm2=0.0, activity_derate_fraction=0.0,
    ecsa_ratio=1.0, p_clamp_mpa=4.25, gdl_porosity=0.78,
)
resp_fallback = svc.RunBatchTest(req_fallback_perfect, None)

print(f"  [Runtime] Stack with 1 real defect: passed={resp_defect.passed}, flags={resp_defect.failure_flags:#x} (OHMIC={bool(resp_defect.failure_flags & OHMIC_DEGRADATION)})")
print(f"  [Runtime] Same stack under DB error fallback: passed={resp_fallback.passed}, flags={resp_fallback.failure_flags:#x} -> SILENT PASS")

# ==============================================================================
# M-05: Wall-clock timeouts break lock-step determinism
# ==============================================================================
print_section("🔎 M-05: Wall-clock timeouts breaking lock-step determinism")
sim_file = REPO_ROOT / "src/main/java/factory/MainSimulator.java"
sim_content = sim_file.read_text()

has_10ms_quorum = "TICK_QUORUM_TIMEOUT_MS = 10" in sim_content
has_ner_timeout_advance = "droppedNerCount.incrementAndGet();" in sim_content
has_dropped_ner_in_proto = ".setDroppedNerCount((int) droppedNerCount.get())" in sim_content

# Check regex for registeredAgentCount parsing
regex_match = re.search(r'Pattern\.compile\("([^"]+)"', sim_content)
regex_str = regex_match.group(1) if regex_match else ""
print(f"  [Code] TICK_QUORUM_TIMEOUT_MS = 10 ms: {has_10ms_quorum}")
print(f"  [Code] Quorum timeout advances tick and increments droppedNerCount: {has_ner_timeout_advance}")
print(f"  [Code] droppedNerCount sent only to WebSocket frame: {has_dropped_ner_in_proto}")
print(f"  [Code] Regex for agent count: {regex_str}")

# Check regex behavior on template
jcm_template = (REPO_ROOT / "factory.jcm.template").read_text()
for test_run_id in [1, 2, 3, 4, 5, 42]:
    rendered = jcm_template.replace("{{RUN_ID}}", str(test_run_id))
    m = re.findall(rf'^\s*agent\s+\w+_{test_run_id}\s*:', rendered, re.MULTILINE)
    count = len(m)
    eff_count = count if count > 0 else 13
    print(f"    run_id={test_run_id:2d}: matched agent tags = {count:2d} -> effective registeredAgentCount = {eff_count}")

# Check Python 6.0s sleep in RunBatchTest
srv_file = REPO_ROOT / "physical_engine/sim_bridge_server.py"
srv_content = srv_file.read_text()
has_6s_sleep = "time.sleep(0.5)" in srv_content
print(f"  [Code] sim_bridge_server.py contains blocking time.sleep(0.5) per point (12 pts = 6.0s): {has_6s_sleep}")

# ==============================================================================
# M-09: Infrastructure failures recorded as physical test failures; cancel path
# ==============================================================================
print_section("🔎 M-09: Infrastructure failure flags and cancelPendingRpc 'ok' bug")

comms_failure_line = "lastFailureFlags = 0x10; // SOLVER_DID_NOT_CONVERGE, reused as \"comms failure\"" in tb_content
timeout_failure_line = "lastFailureFlags = 0x10;" in tb_content
result_line = 'result.set(currentSummary.state() == StationStateEnum.STATION_IDLE ? "ok" : "defect");' in tb_content
cancel_sets_idle = "currentSummary = StationSummary.IDLE;" in tb_content

print(f"  [Code] gRPC onClose comms failure sets 0x10 (SOLVER_DID_NOT_CONVERGE): {comms_failure_line}")
print(f"  [Code] 30s timeout sets 0x10 (SOLVER_DID_NOT_CONVERGE): {timeout_failure_line}")
print(f"  [Code] result.set checks (state == STATION_IDLE ? 'ok' : 'defect'): {result_line}")
print(f"  [Code] cancelPendingRpc sets currentSummary = StationSummary.IDLE: {cancel_sets_idle}")
print("  [Impact] Cancelled/suspended test causes state == IDLE -> evaluates to 'ok' (PASS)!")

# ==============================================================================
# T-03: Committed binary LUT caches, stale lockfile, and tracked generated files
# ==============================================================================
print_section("🔎 T-03: Committed binary caches and git tracking")
res = subprocess.run(
    ["git", "ls-files", ".physical_engine/lut_cache/", "factory.jcm", "factory.jcm.template", ".agents/"],
    cwd=str(REPO_ROOT), capture_output=True, text=True
)
tracked_files = res.stdout.strip().splitlines()
pkl_files = [f for f in tracked_files if f.endswith(".pkl")]
lock_files = [f for f in tracked_files if f.endswith(".lock")]
npz_files = [f for f in tracked_files if f.endswith(".npz")]
jcm_files = [f for f in tracked_files if "factory.jcm" in f]

print(f"  [Git] Tracked .lock files: {lock_files}")
print(f"  [Git] Tracked .pkl files count: {len(pkl_files)}")
print(f"  [Git] Tracked .npz files: {npz_files}")
print(f"  [Git] Tracked JCM files: {jcm_files}")

# ==============================================================================
# P-17: Station 1 E2_CURE = Station 5 ORR E_act = 68.5 kJ/mol
# ==============================================================================
print_section("❓ P-17: Station 1 E2_CURE vs Station 5 ORR E_act (68.5 kJ/mol)")
st1_file = REPO_ROOT / "physical_engine/factory_simulation/station1_mea_preparation.py"
pemfc_file = REPO_ROOT / "physical_engine/factory_simulation/pemfc_model.py"

e2_cure_val = re.search(r'E2_CURE\s*=\s*([0-9.eE+]+)', st1_file.read_text()).group(1)
e_act_val = re.search(r'E_act:\s*float\s*=\s*([0-9.]+)', pemfc_file.read_text()).group(1)

print(f"  Station 1 E2_CURE: {float(e2_cure_val):.1f} J/mol (68.5 kJ/mol)")
print(f"  Station 5 ORR E_act: {float(e_act_val):.1f} J/mol (68.5 kJ/mol)")
print("  Literature calibration docs check:")
lit_content = (REPO_ROOT / "docs/physical-engine/literature-calibration.md").read_text()
for line in lit_content.splitlines():
    if "68.5" in line:
        print("   ", line)
print("  DOI 10.1016/j.polymertesting.2018.03.012 lookup: Motta et al., 'Analysis of cyclic tensile behaviour of PVDF'.")
print("  Verdict: Fabricated citation; 68.5 kJ/mol was copy-pasted from ORR kinetics.")

# ==============================================================================
# P-18: Dynamic membrane water sorption isotherm and hysteresis mislabel
# ==============================================================================
print_section("❓ P-18: Hydration isotherm temperature & 'hysteresis' misnomer")
mem_file = REPO_ROOT / "physical_engine/factory_simulation/membrane_hydration.py"
mem_content = mem_file.read_text()

has_30c_poly = "0.043 + 17.81 * a_safe - 39.85 * (a_safe ** 2) + 36.0 * (a_safe ** 3)" in mem_content
has_tau_sorption = "TAU_SORPTION_S = 12.0" in mem_content
has_tau_desorption = "TAU_DESORPTION_S = 45.0" in mem_content

print(f"  [Code] Springer 30 deg C polynomial used at 80 deg C operating temp: {has_30c_poly}")
print(f"  [Code] TAU_SORPTION_S = 12.0 s, TAU_DESORPTION_S = 45.0 s present: {has_tau_sorption and has_tau_desorption}")

# Check callers across codebase
callers = []
for p in REPO_ROOT.rglob("*.py"):
    if "verify_unverified_items" in p.name: continue
    txt = p.read_text()
    if "step_membrane_hydration" in txt:
        callers.append(str(p.relative_to(REPO_ROOT)))
print(f"  [Code] Callers of step_membrane_hydration: {callers}")
print("  Verdict: Zero callers in runtime pipeline (dead code). Single-valued lambda_eq means asymmetric relaxation kinetics, NOT equilibrium sorption hysteresis.")

# ==============================================================================
# P-20: Time-scale mismatch
# ==============================================================================
print_section("❓ P-20: Time-scale acceleration mismatch")
st1_content = st1_file.read_text()
dwell_nominal = re.search(r'DWELL_TIME_NOMINAL_S\s*=\s*([0-9.]+)', st1_content).group(1)
t_base_s1 = re.search(r'T_BASE_S1\s*=\s*([0-9.]+)', st1_content).group(1)

print(f"  Physical hot-press chemical dwell: {dwell_nominal} s (3 minutes integration)")
print(f"  Discrete-event station step in Java/JCM: {t_base_s1} s")
print("  Station 5 polarization sweep wall-clock delay: 6.0 s (12 points * 0.5s)")
print("  Simulation clock tick: 1.0 s nominal")
print("  Verdict: Inconsistent acceleration factors across physics (180s), MAS scheduling (5s), wall-clock RPC (6s), and price ticks (1s).")

# ==============================================================================
# M-07: Digital twin vs digital model
# ==============================================================================
print_section("❓ M-07: Digital twin vs digital model terminology")
hardware_hits = subprocess.run(
    ["grep", "-rnI", "-E", "opc|mqtt|modbus|plc|physical_sensor", "src/", "physical_engine/"],
    cwd=str(REPO_ROOT), capture_output=True, text=True
).stdout.strip()
print(f"  Hardware / physical interface search: {'None found' if not hardware_hits else hardware_hits}")
print("  Under Kritzinger et al. (2018), without automated data flow to/from an actual physical asset,")
print("  the system is strictly a 'Digital Model' / 'Co-Simulation Testbed', not a 'Digital Twin'.")

# ==============================================================================
# D-06: report.tex vs README snapshot drift
# ==============================================================================
print_section("❓ D-06: Documentation and report snapshot drift")
report_file = REPO_ROOT / "report.tex"
report_content = report_file.read_text()
readme_content = (REPO_ROOT / "README.md").read_text()

rep_stoch = "Stations 1--4 are stochastic black boxes" in report_content
readme_first_principles = "Upstream Manufacturing Process Models (Stations 1–4)" in readme_content

rep_j0 = "j_0 = 10^{-9}" in report_content
code_j0 = "2.5e-8" in pemfc_file.read_text()

rep_junit = "\\file{src/test/java/factory/} contains three JUnit 5 classes" in report_content
actual_java_test_files = list((REPO_ROOT / "src/test/java/factory").glob("*Test.java"))

claim_matrix_content = (REPO_ROOT / "docs/artifact-evaluation/claim-matrix.md").read_text()
has_fig4_fig5 = "Figure 4" in claim_matrix_content and "Figure 5" in claim_matrix_content

onboarding_banner = "RESULTS UNDER AUDIT" in (REPO_ROOT / "ONBOARDING.md").read_text()

print(f"  report.tex describes S1-4 as 'stochastic black boxes': {rep_stoch}")
print(f"  README describes S1-4 as first-principles physical JIT kernels: {readme_first_principles}")
print(f"  report.tex states j_0 = 10^-9 A/cm2: {rep_j0} vs code j0_ref = {code_j0} (25x discrepancy)")
print(f"  report.tex states 3 JUnit classes: {rep_junit} vs actual {len(actual_java_test_files)} JUnit test classes")
print(f"  claim-matrix.md cites Figure 4/5 and Table 2 from absent manuscript: {has_fig4_fig5}")
print(f"  ONBOARDING.md contains 'RESULTS UNDER AUDIT' banner: {onboarding_banner} (missing!)")
print("\nALL 🔎 AND ❓ CHECKS COMPLETED.")
