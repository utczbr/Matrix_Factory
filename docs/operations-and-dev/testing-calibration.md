# Testing & Calibration Protocols (How-To Guide)

This how-to guide details how to run unit tests, physical station integration tests, Pytest verification suites, and model calibration scripts.

---

## Running Python Physics Unit Tests

Execute Pytest across all physical station modules (Stations 1–5):

```bash
# Run full Pytest suite with coverage
pytest physical_engine/factory_simulation/ -v --cov=physical_engine
```

Targeted Station Test Suites:
* **Station 1 & 2 Mechanistic Tests:** `pytest physical_engine/factory_simulation/station_mechanistic_test.py`
* **Station 3 & 4 Calibration Tests:** `pytest physical_engine/factory_simulation/quality_bridge_test.py`
* **Station 5 PEMFC Electrochemistry Tests:** `pytest physical_engine/factory_simulation/pemfc_test.py`
* **Thermal & Hydration Coupling Tests:** `pytest physical_engine/factory_simulation/test_stack_thermal.py`

---

## Executing Parameter Calibration Scripts

To re-calibrate Station 3 ductile damage parameters ($C_{\text{crit,NCL}}$) and Station 4 clamping pressure torque curves:

```bash
python3 physical_engine/scripts/calibrate_stamping_clamping.py
```

Expected output:
```text
[CalibrationEngine] Fitting Cockcroft-Latham damage integral for SS316L...
[CalibrationEngine] Optimal C_threshold = 0.4214 (R^2 = 0.994)
[CalibrationEngine] Fitting VDI 2230 bolt clamping torque vs contact resistance...
[CalibrationEngine] Optimal R_contact_0 = 4.200 mOhm*cm^2
[CalibrationEngine] Calibration report saved to analysis/calibration_summary.json
```

---

## Java MAS Integration Verification

Run Java JUnit integration tests validating CArtAgO artifacts and gRPC IPC message serialization:

```bash
./gradlew test
```
