# Claim-to-Code Traceability Matrix (Artifact Evaluation)

This matrix maps every empirical claim, figure, table, and statistical result presented in the manuscript to its corresponding source code file, script, and physical solver module.

---

## Claim Traceability Table

| Manuscript Reference | Empirical Claim / Result Summary | Reproduction Script Command | Source Artifact / Code File |
| --- | --- | --- | --- |
| **Figure 4** | Station 3 Tool Wear & Ductile Damage ($C_{\mathrm{crit,NCL}} = 0.35$) | `python3 physical_engine/factory_simulation/station3_bipolar_plate_stamping.py` | [`physical_engine/factory_simulation/station3_bipolar_plate_stamping.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/station3_bipolar_plate_stamping.py) |
| **Figure 5** | Station 5 Polarization Curve & Membrane Hydration ($\lambda = 14$) | `pytest physical_engine/factory_simulation/pemfc_test.py` | [`physical_engine/factory_simulation/pemfc_model.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/factory_simulation/pemfc_model.py) |
| **Table 2** | PROSA vs. ADACOR baseline under energy price spikes | `python3 experiments/run_prosa_vs_adacor.py` | [`src/agt/supervisor_agent.asl`](https://github.com/utczbr/Matrix_Factory/blob/main/src/agt/supervisor_agent.asl) |
| **Section 4.2** | Lock-Stepped NER Time Sync determinism ($0$ drift) | `./gradlew test` | `MainSimulator.java` |
| **Section 5.1** | Statistical significance ($p < 0.001$, Mann-Whitney U) | `python3 experiments/analyze_results.py analysis/results.csv` | `experiments/analyze_results.py` |
| **Section 5.3** | gRPC mTLS security & certificate verification | `python3 physical_engine/factory_simulation/test_grpc_security.py` | [`physical_engine/sim_bridge_server.py`](https://github.com/utczbr/Matrix_Factory/blob/main/physical_engine/sim_bridge_server.py) |
