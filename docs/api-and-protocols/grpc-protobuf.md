# gRPC SimBridge & Protobuf Specifications (Reference)

This document provides technical specifications for the **gRPC SimBridge service** linking Java CArtAgO artifacts with the Python Numba physical engine daemon.

---

## Service & Protocol Definition

The gRPC service interface is defined in `sim_bridge.proto`.

```protobuf
syntax = "proto3";

package matrix_factory.sim_bridge;

option java_multiple_files = true;
option java_package = "com.matrixfactory.simbridge";

service SimBridgeService {
    rpc StepStation (StepRequest) returns (StepResponse);
    rpc ResetSimulation (ResetRequest) returns (ResetResponse);
    rpc HealthCheck (HealthRequest) returns (HealthResponse);
}

message StepRequest {
    string station_id = 1;
    double delta_time = 2;
    uint64 simulation_tick = 3;
    map<string, double> input_parameters = 4;
}

message StepResponse {
    string station_id = 1;
    bool success = 2;
    uint64 current_tick = 3;
    double next_event_delta = 4;
    map<string, double> output_state = 5;
    string error_message = 6;
}

message ResetRequest {
    uint64 random_seed = 1;
    string initial_mode = 2;
}

message ResetResponse {
    bool status = 1;
    string session_id = 2;
}

message HealthRequest {}

message HealthResponse {
    bool is_alive = 1;
    string version = 2;
    uint32 active_kernels = 3;
}
```

---

## Data Schema & Types

| RPC Method | Input Type | Output Type | Description |
| --- | --- | --- | --- |
| `StepStation` | `StepRequest` | `StepResponse` | Advances physical ODE integration for a station by `delta_time` and returns updated physical state vector. |
| `ResetSimulation` | `ResetRequest` | `ResetResponse` | Re-initializes Numba physical state vectors and resets stochastic RNG seeds. |
| `HealthCheck` | `HealthRequest` | `HealthResponse` | Evaluates physical daemon readiness and JIT kernel availability. |

---

## Code Reference

* Python Protobuf Bridge: [`physical_engine/sim_bridge_server.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/sim_bridge_server.py)
* Proto Index Helper: [`physical_engine/proto_index.py`](file:///home/stuart/Documentos/matrix_factory_twin/physical_engine/proto_index.py)
