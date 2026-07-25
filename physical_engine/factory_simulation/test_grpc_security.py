import os
import time
import socket
import pytest
import grpc
from concurrent import futures

from physical_engine.sim_bridge_server import SimBridgeServicer
from physical_engine.protos import sim_bridge_pb2, sim_bridge_pb2_grpc

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

@pytest.fixture(scope="module")
def cert_dir(tmp_path_factory):
    """Fixture that generates test certificates using scripts/generate_certs.sh."""
    out_dir = tmp_path_factory.mktemp("test_certs")
    os.system(f"bash scripts/generate_certs.sh {out_dir}")
    return out_dir

def test_insecure_grpc_connection():
    port = find_free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    servicer = SimBridgeServicer(run_id=0)
    sim_bridge_pb2_grpc.add_SimBridgeServicer_to_server(servicer, server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()

    try:
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = sim_bridge_pb2_grpc.SimBridgeStub(channel)
        res = stub.HealthCheck(sim_bridge_pb2.Empty(), timeout=2)
        assert res.ready is True
    finally:
        server.stop(grace=0)

def test_secure_mtls_grpc_connection(cert_dir):
    port = find_free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    servicer = SimBridgeServicer(run_id=0)
    sim_bridge_pb2_grpc.add_SimBridgeServicer_to_server(servicer, server)

    ca_crt = (cert_dir / "ca.crt").read_bytes()
    server_crt = (cert_dir / "server.crt").read_bytes()
    server_key = (cert_dir / "server.key").read_bytes()
    client_crt = (cert_dir / "client.crt").read_bytes()
    client_key = (cert_dir / "client.key").read_bytes()

    server_creds = grpc.ssl_server_credentials(
        [(server_key, server_crt)],
        root_certificates=ca_crt,
        require_client_auth=True,
    )
    server.add_secure_port(f"127.0.0.1:{port}", server_creds)
    server.start()

    try:
        client_creds = grpc.ssl_channel_credentials(
            root_certificates=ca_crt,
            private_key=client_key,
            certificate_chain=client_crt,
        )
        channel = grpc.secure_channel(f"127.0.0.1:{port}", client_creds)
        stub = sim_bridge_pb2_grpc.SimBridgeStub(channel)
        res = stub.HealthCheck(sim_bridge_pb2.Empty(), timeout=2)
        assert res.ready is True
    finally:
        server.stop(grace=0)

def test_unauthenticated_client_rejected(cert_dir):
    port = find_free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    servicer = SimBridgeServicer(run_id=0)
    sim_bridge_pb2_grpc.add_SimBridgeServicer_to_server(servicer, server)

    ca_crt = (cert_dir / "ca.crt").read_bytes()
    server_crt = (cert_dir / "server.crt").read_bytes()
    server_key = (cert_dir / "server.key").read_bytes()

    server_creds = grpc.ssl_server_credentials(
        [(server_key, server_crt)],
        root_certificates=ca_crt,
        require_client_auth=True,
    )
    server.add_secure_port(f"127.0.0.1:{port}", server_creds)
    server.start()

    try:
        # Attempt connecting with plaintext channel
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = sim_bridge_pb2_grpc.SimBridgeStub(channel)
        with pytest.raises(grpc.RpcError):
            stub.HealthCheck(sim_bridge_pb2.Empty(), timeout=2)
    finally:
        server.stop(grace=0)
