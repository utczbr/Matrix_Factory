# Claim-to-Code Traceability Matrix (Artifact Evaluation)

This matrix maps every empirical claim, figure, table, and statistical result presented in the manuscript to its corresponding source code file, script, and physical solver module.

---

## Claim Traceability Table

| Manuscript Reference | Empirical Claim / Result Summary | Reproduction Script Command | Source Artifact / Code File |
| --- | --- | --- | --- |
| **Figure 4** | Station 3 Tool Wear & Ductile Damage ($C_{\text{crit,NCL}}$) | `python3 physical_engine/scripts/calibrate_stamping_clamping.py` | [`physical_engine/station3_bipolar_plate_stamping.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/station3_bipolar_plate_stamping.py) |
| **Figure 5** | Station 5 Polarization Curve & Membrane Hydration ($\lambda$) | `pytest physical_engine/factory_simulation/pemfc_test.py` | [`physical_engine/pemfc_model.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/factory_simulation/pemfc_model.py) |
| **Table 2** | PROSA vs. ADACOR baseline under energy price spikes | `python3 experiments/run_prosa_vs_adacor.py` | [`src/agt/supervisor_agent.asl`](file:///home/stuart/Documentos/matrix_factory_twin/src/agt/supervisor_agent.asl) |
| **Table 3** | Single-JVM Multi-Run Fan-out Performance (30 runs) | `./gradlew runMonteCarloBatch` | [`src/agt/order_holon.asl`](file:///home/stuart/Documentos/matrix_factory_twin/src/agt/order_holon.asl) |
| **Section 4.2** | Lock-Stepped NER Time Sync determinism ($0$ drift) | `./gradlew test` | `MainSimulator.java` |
| **Section 5.1** | Statistical significance ($p < 0.001$, Mann-Whitney U) | `python3 experiments/analyze_results.py analysis/results.csv` | `experiments/stats.py` |
| **Section 5.3** | gRPC mTLS security & certificate verification | `python3 physical_engine/factory_simulation/test_grpc_security.py` | [`physical_engine/sim_bridge_server.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/sim_bridge_server.py) |
