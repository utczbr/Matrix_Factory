# Digital Twin of a Matrix Fuel Cell Factory: An ADACOR/PROSA Co-Simulation

**Target Scenario:** A fully decentralized, reconfigurable matrix production line for Proton Exchange Membrane Fuel Cells (PEMFCs).
**Core Objective:** Benchmark manufacturing resilience by simulating high-frequency disruptions (supply chain starvation, robotic breakdown, energy price spikes).

## Architecture Overview
This digital twin uses a hard-decoupled co-simulation architecture designed to isolate cognitive multi-agent reasoning from high-fidelity physical thermodynamics:

**1. The Cognitive Layer (JaCaMo - JVM):**
- **Jason (BDI):** Order Holons and Resource Holons negotiate machine time via Contract-Net Protocols (CNP).
- **CArtAgO:** Maps logical intentions to physical actions via a high-performance, asynchronous gRPC bridge utilizing explicit event-driven `resume()` signaling.
- **MoISE:** Structurally enforces ADACOR (Adaptive Holonic Control) schemas against PROSA (Autonomous) patterns based on external disturbance metrics.
- **TelemetryArtifact:** Routes physical state vectors to visualization dashboards utilizing a lock-free `AtomicReference` snapshot pattern and lossy queue decimation, ensuring strict preservation of the physical integration loop cadence.


**2. The Physical Layer (Python / Numba):**
- A continuous-time physics engine heavily optimized with `numba.njit` solving implicit non-linear thermodynamic equations (e.g., analytical Jacobian derivatives of Nernst potentials).
- Implements a strict Unary Time-Synchronization Barrier (AdvanceTime embedding the state vector) derived from the Distributed Co-simulation Protocol (DCP) to guarantee determinism.
- Uses strict 2D pre-allocated NRT scratchpad isolation to ensure deterministic thread-safety across `numba.prange` execution pools.
- Operates under a 1:30 (Single-JVM Fan-Out) topology for Monte Carlo scaling, utilizing explicit CPU affinity pinning and strict dynamic Thread/GIL bounds injected before module import via `multiprocessing.get_context('spawn')`.
- A dedicated, Yonkist-number-validated thermal submodel resolves internal heat generation (ohmic and activation losses) within the Station 5 stack itself, feeding the chiller's external thermal model rather than being absorbed into it.

## Integration Philosophy
To bridge the asynchronous event-driven agents with the discrete-event physical simulation:
- **No passive polling.** The JVM executes thread suspension via CArtAgO and resumes using microsecond-precision Netty NIO callbacks guarded by `AtomicBoolean` compare-and-set logic.
- **Simulation Clock Domination.** All wall-clock Java `ScheduledExecutorService` timers and 50ms aggregation deadlines have been deprecated. NextEventRequests (NER) govern the $T_{next}$ priority queue using a deterministic quorum/ACK model, maintaining pure causality. 
- **Compound Failure Representation.** Complex physical starvation patterns map cleanly to standard Jason plan contingencies via bitwise diagnostic flags.
