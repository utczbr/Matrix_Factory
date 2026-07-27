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
* **Station 3 & 4 Quality Bridge Tests:** `pytest physical_engine/factory_simulation/quality_bridge_test.py`
* **Station 5 PEMFC Electrochemistry Tests:** `pytest physical_engine/factory_simulation/pemfc_test.py`
* **Thermal & Hydration Coupling Tests:** `pytest physical_engine/factory_simulation/test_stack_thermal.py`

---

## Executing Parameter Calibration & Sanity Checks

To run standalone calibration sanity check functions across physical station JIT kernels:

```bash
python3 physical_engine/factory_simulation/station1_mea_preparation.py
python3 physical_engine/factory_simulation/station2_catalyst_deposition.py
python3 physical_engine/factory_simulation/station3_bipolar_plate_stamping.py
python3 physical_engine/factory_simulation/station4_stack_clamping.py
```

Expected output (Station 3 Example):
```text
============================================================
STATION 3 STAMPING CALIBRATION SANITY CHECKS
============================================================
[PASSOU] stage1_nominal_nao_defeituoso
          damage_index: 0.8636844400249464
          esperado: damage_index < 1.0 (~0.863), is_defective=False
[PASSOU] stage1_taxa_defeito_proxima_do_alvo_real_S3
          taxa_empirica: 0.180%
          alvo: 0.20%
```

---

## Java MAS Integration Verification

Run Java JUnit integration tests validating CArtAgO artifacts and gRPC IPC message serialization:

```bash
./gradlew test
```
