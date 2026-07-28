# gRPC SimBridge & Protobuf Specifications (Reference)

This document provides technical specifications for the **gRPC SimBridge service** linking Java CArtAgO artifacts with the Python Numba physical engine daemon.

---

## Service & Protocol Definition

The gRPC service interface is defined in `sim_bridge.proto`.

```protobuf
syntax = "proto3";

package factory;

option java_multiple_files = false;
option java_outer_classname = "SimBridgeProto";

service SimBridge {
  rpc AdvanceTime (TimeStep) returns (StepReady);
  rpc RunBatchTest (BatchTestRequest) returns (BatchTestResponse);
  rpc HealthCheck (Empty) returns (HealthStatus);
}

message TimeStep {
  double current_time = 1;
  double dt = 2;
  int32 schema_epoch = 3;
}

message StepReady {
  double target_time = 1;
  bool success = 2;
  repeated double state_vector = 3 [packed = true];
}

message BatchTestRequest {
  string stack_id = 1;
  int32 num_cells = 2;
  double operating_temp_k = 3;
  double inlet_pressure_h2_bar = 4;
  double inlet_pressure_o2_bar = 5;
  repeated double current_densities = 6 [packed = true];

  // Manufacturing-quality bridge (Stations 1-4 -> Station 5)
  double r_internal_penalty_ohm_cm2 = 7;
  double activity_derate_fraction = 8;
  double rh_anode = 9;
  double ecsa_ratio = 10;
  double p_clamp_mpa = 11;
  double gdl_porosity = 12;
  double j_lim_derate_fraction = 13;
}

message BatchTestResponse {
  bool passed = 1;
  repeated double measured_voltages = 2 [packed = true];
  // bit 0 = OHMIC_DEGRADATION, bit 1 = MASS_TRANSPORT_STARVATION,
  // bit 2 = THERMAL_SHUTDOWN, bit 3 = LOW_ACTIVATION,
  // bit 4 = SOLVER_DID_NOT_CONVERGE
  uint32 failure_flags = 3;
}

message Empty {}

message HealthStatus {
  bool ready = 1;
}
```

---

## Data Schema & Types

| RPC Method | Input Type | Output Type | Description |
| --- | --- | --- | --- |
| `AdvanceTime` | `TimeStep` | `StepReady` | Unary time-synchronization barrier; advances all physical station ODE integrators to `current_time + dt` and returns the embedded state vector. |
| `RunBatchTest` | `BatchTestRequest` | `BatchTestResponse` | Runs a Station 5 polarization-curve sweep (Newton–Raphson current-density solve) incorporating upstream manufacturing-quality penalties. |
| `HealthCheck` | `Empty` | `HealthStatus` | Reports whether the physical daemon's JIT kernels have finished warming up. |

---

## Code Reference

* Proto Source File: [`src/main/proto/sim_bridge.proto`](file:///home/stuart/Documentos/matrix_factory_twin/src/main/proto/sim_bridge.proto)
* Python Protobuf Bridge: [`physical_engine/sim_bridge_server.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/sim_bridge_server.py)
* Proto Index Helper: [`physical_engine/proto_index.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/proto_index.py)

