# Matrix Factory Twin

[![CI Build](https://img.shields.io/github/actions/workflow/status/utczbr/Matrix_Factory/ci.yml?branch=main&label=CI&style=flat-square)](https://github.com/utczbr/Matrix_Factory/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg?style=flat-square)](https://www.python.org/)
[![Java Version](https://img.shields.io/badge/java-17%2B-orange.svg?style=flat-square)](https://www.oracle.com/java/)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)
[![Architecture](https://img.shields.io/badge/MAS-JaCaMo%20%2B%20Numba%20gRPC-purple.svg?style=flat-square)](#visual-architecture--system-flow)

**An event-driven, hybrid multi-agent digital twin framework for modular hydrogen fuel-cell manufacturing, coupling BDI agent cognitive reasoning in Java with first-principles electrochemical physics in Python via a lock-stepped gRPC simulation bridge.**

---

## Visual Architecture & System Flow

```mermaid
graph TD
    subgraph MAS ["Java Multi-Agent System (JaCaMo / Jason BDI)"]
        SA["supervisor_agent.asl"] -->|"2-Phase Commit (Drain/Suspend)"| OH["order_holon.asl (1..5)"]
        SA --> RH["resource_holon.asl (1..5)"]
        OH -->|"Contract-Net Bidding"| RH
        OH -->|"Dispatch"| AMR["amr_agent.asl (1..2)"]
        RH -->|"Execute Step"| CA["CArtAgO Artifacts"]
    end

    subgraph Sync ["Tick Engine & Interfaces"]
        MS["MainSimulator.java"] -->|"Lock-Stepped Tick Loop"| CA
        DB["DatabaseArtifact.java"] -->|"Async Queue + WAL"| SQLite[("factory_history.db")]
        WS["TelemetryHub.java"] -->|"HMAC WebSocket :8080"| Client["Live Dashboard"]
    end

    subgraph Physics ["Python Physical Engine"]
        gRPC["SimBridge gRPC (:50051..50080)"] <-->|"StepReady / Telemetry"| MS
        PEMFC["Stack Thermal & PEMFC Model"] --> LUT["Numba JIT & CoolProp EOS"]
    end
```

---

## Key Features

* **Hybrid BDI & First-Principles Physics**: Combines Jason/CArtAgO agent cognitive reasoning in Java 17 with Numba-accelerated PEMFC fuel cell electrochemistry, Springer membrane hydration ($\lambda \in [1, 14]$), real-gas fugacity EOS (CoolProp LUT), two-lump thermal capacitance, and cathode air BOP dynamics in Python.
* **Manufacturing-to-Performance Multiphysics Coupling**: Connects upstream manufacturing physics—non-linear Archard tool wear, Cockcroft-Latham ductile fracture ($C_{crit,NCL} = 0.35$), and VDI 2230 stack clamping GDL compaction ($E_0 = 2.80\text{ MPa}, K_s = 28.5$)—directly into downstream electrochemical polarization sweeps via Bruggeman effective medium conductivity and interfacial contact resistance ($R_{contact,0} = 4.20\text{ m}\Omega\cdot\text{cm}^2$).
* **Dynamic Control Schema Transitions**: Real-time Two-Phase Commit (Phase 0 Drain, Phase 1 Suspend) switching between PROSA (peer-negotiated) and ADACOR (hierarchical) upon energy price spikes.
* **Deterministic Lock-Stepped Simulator (TMC)**: Replaces non-deterministic wall-clock sleeps (`Thread.sleep`) with a synchronous Next Event Request (NER) engine in `MainSimulator.java`.
* **Single-JVM Fan-Out Monte Carlo Scale**: Orchestrates up to 30 parallel, fully isolated simulation runs inside a single JVM instance via source-level agent namespace rewriting.
* **Configurable gRPC Security & Async Telemetry**: Optional mutual TLS (mTLS) authentication between Java clients and Python daemons, paired with authenticated HMAC-signed WebSocket streaming (`ws://127.0.0.1:8080/telemetry`).

---

## Primary Literature Physical Calibration

All physical parameters in the digital twin are ground-truth calibrated against peer-reviewed primary literature across 5 physical domains:

| Domain | Key Formulations | Primary Literature Citations & DOIs |
| :--- | :--- | :--- |
| **Tool Tribology** | Non-linear Archard wear law ($K_{wear,PVD} = 3.50 \times 10^{-6}\text{ mm}^3/\text{N}\cdot\text{m}$, $K_{wear,Duplex} = 1.47 \times 10^{-10}\text{ mm}^3/\text{N}\cdot\text{m}$, $\gamma = 1.35$) | Fernandes et al. (2017) [`10.1016/j.surfcoat.2017.10.052`], Bitay et al. (2021) [`10.1007/s00170-024-13800-x`] |
| **Foil Formability** | Cockcroft-Latham ductile fracture ($C_{crit,NCL} = 0.35$), Hollomon strain hardening ($K = 1280\text{ MPa}, n = 0.43$) | Modanloo et al. (2018) [`10.1007/s00170-018-2210-y`], Blandford et al. (2007) [`10.2172/918231`] |
| **GDL Mechanics & ICR** | Kleemann non-linear tangent modulus ($E_0 = 2.80\text{ MPa}, K_s = 28.5$), Interfacial contact resistance ($R_{contact,0} = 4.20\text{ m}\Omega\cdot\text{cm}^2$) | Kleemann et al. (2009) [`10.1016/j.jpowsour.2008.09.026`], Mason et al. (2012) [`10.1016/j.jpowsour.2012.07.021`] |
| **Electrochemistry & Transport**| Multi-parameter Butler-Volmer kinetics ($E_{act} = 68.5\text{ kJ/mol}$, $j_{0,ref} = 2.50 \times 10^{-8}\text{ A/cm}^2$), Springer hydration ($\lambda$) | Neyerlin et al. (2006) [`10.1149/1.2266294`], Gasteiger et al. (2005) [`10.1016/j.apcatb.2004.06.021`] |

---

## Quick Start / Installation

### Prerequisites
Make sure your system meets the following version requirements:
* **Java Development Kit (JDK)** $\ge$ 17.0.0
* **Python** $\ge$ 3.11.0
* **Gradle** $\ge$ 8.7.0 (or use included `./gradlew` wrapper)
* **OpenSSL** (optional, for mTLS certificate generation)

### Setup in Under 2 Minutes

```bash
# 1. Clone the repository
git clone https://github.com/utczbr/Matrix_Factory.git
cd Matrix_Factory

# 2. Set up environment variables
cp .env.example .env

# 3. Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Build Java multi-agent components
./gradlew build
```

---

## Usage & Code Examples

### 1. Running a Single Interactive Simulation
Start the Python physical daemon, then launch the Java MAS engine:

```bash
# Terminal 1: Launch Python physical engine daemon on port 50051
.venv/bin/python3 -m physical_engine.sim_bridge_server --port=50051 --run-id=0

# Terminal 2: Launch Java Multi-Agent System (1000 ticks)
./gradlew run --args="0 50051 --max-ticks=1000"
```

### 2. Running a Monte Carlo Experiment (PROSA vs. ADACOR)
Execute a 15-replication Monte Carlo experiment comparing the PROSA baseline against ADACOR dynamic schema switching under energy price disturbances:

```bash
# Runs 15 PROSA + 15 ADACOR simulations and outputs analysis/results.csv
python3 experiments/run_prosa_vs_adacor.py
```

### 3. Statistical Analysis & Report Generation
Compute 95% bootstrap confidence intervals, Shapiro-Wilk normality tests, and Mann-Whitney U significance metrics from experiment results:

```bash
python3 experiments/analyze_results.py analysis/results.csv
```

### 4. Running in Secure Mode (TLS / mTLS)
Enable production-grade Mutual TLS authentication between Java artifacts and Python daemons:

```bash
# 1. Generate local 2048-bit RSA certificates
bash scripts/generate_certs.sh certs/

# 2. Start Python server in secure mode
GRPC_SECURE_MODE=true .venv/bin/python3 -m physical_engine.sim_bridge_server --port=50051 --run-id=0

# 3. Start Java MAS in secure mode
GRPC_SECURE_MODE=true ./gradlew run --args="0 50051 --max-ticks=1000"
```

### 5. Running Test Suites

```bash
# Run Python physical engine unit, integration & security test suite (74 tests)
.venv/bin/pytest physical_engine/

# Run Java MAS integration test suite
./gradlew test
```

---

## Tech Stack & Prerequisites

| Layer | Technologies & Frameworks | Minimum Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Multi-Agent System (MAS)** | Java, JaCaMo (Jason BDI, CArtAgO, MoISE), Gradle | Java 17+, Gradle 8.7+ | BDI agent reasoning, organizational roles, and Contract-Net negotiations. |
| **Physical Engine** | Python, gRPC / Protobuf, Numba, NumPy, SciPy, CoolProp | Python 3.11+ | First-principles PEMFC electrochemistry, thermal models, and JIT sweeps. |
| **Security & Interfaces** | OpenSSL TLS/mTLS, Tyrus WebSocket, HMAC SHA-256 | OpenSSL 1.1+ | Encrypted gRPC daemon channels and authenticated browser telemetry. |
| **Persistence** | SQLite JDBC (WAL mode), `ArrayBlockingQueue` | SQLite 3+ | Thread-safe, lock-free historic event and process variation logging. |
| **Analysis & Reporting** | Pandas, SciPy (`shapiro`, `mannwhitneyu`), LaTeX | Python 3.11+ | Statistical hypothesis testing, confidence interval extraction, and manuscript builds. |

---

## Contributing & License

Contributions are welcome! Please feel free to open Issues or submit Pull Requests for bug fixes, physical model expansions, and algorithmic improvements.

### License
This project is open-source software licensed under the **[MIT License](LICENSE)**.
