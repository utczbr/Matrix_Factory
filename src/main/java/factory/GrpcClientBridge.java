package factory;

import io.grpc.ManagedChannel;
import io.grpc.netty.shaded.io.grpc.netty.NettyChannelBuilder;
import factory.SimBridgeGrpc.SimBridgeBlockingStub;
import factory.SimBridgeGrpc.SimBridgeStub;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class GrpcClientBridge {
    private static final Logger logger = LoggerFactory.getLogger(GrpcClientBridge.class);
    private final ManagedChannel channel;
    private final SimBridgeBlockingStub blockingStub;
    private final SimBridgeStub asyncStub;
    private final ExecutorService executor;
    private final int port;

    public GrpcClientBridge(int port) {
        this.port = port;
        // BUG FIX (mirrors the Python-side sim_bridge_server.py `max_workers`
        // fix): this was previously `availableProcessors() / 30`, sized for
        // the 30-daemon-per-machine Phase-4 production topology. In that
        // divisor, any single-daemon dev/test run (e.g. `./gradlew run
        // --args="0 50051 ..."` against one manually-launched Python
        // process) collapses to exactly 1 thread on any machine with <60
        // cores.
        //
        // This executor backs the Netty ManagedChannel's callback dispatch
        // for EVERY RPC on this channel — both MainSimulator's blocking
        // AdvanceTime calls (the tick loop) and TestBenchArtifact's
        // long-lived RunBatchTest streaming call share the same channel.
        // With only 1 thread here, a slow/queued callback on one RPC can
        // starve the other's completion callback, which is exactly the
        // client-side mirror of the server-side gRPC threadpool bug that
        // caused AdvanceTime to stall (and telemetry/live-state to freeze)
        // for the duration of a RunBatchTest sweep. Keep at least 2,
        // independent of the /30 production heuristic.
        int threads = Math.max(2, Runtime.getRuntime().availableProcessors() / 30);
        this.executor = new ThreadPoolExecutor(
                threads, threads, 0L, TimeUnit.MILLISECONDS,
                new LinkedBlockingQueue<>(256),
                new ThreadPoolExecutor.CallerRunsPolicy());

        NettyChannelBuilder builder = NettyChannelBuilder.forAddress("127.0.0.1", port)
                .executor(this.executor);

        boolean secureMode = "true".equalsIgnoreCase(System.getenv("GRPC_SECURE_MODE"));
        if (secureMode) {
            String certDir = System.getenv().getOrDefault("GRPC_CERT_DIR", "certs");
            java.io.File caCert = new java.io.File(certDir, "ca.crt");
            java.io.File clientCert = new java.io.File(certDir, "client.crt");
            java.io.File clientKey = new java.io.File(certDir, "client.key");
            try {
                io.grpc.netty.shaded.io.netty.handler.ssl.SslContext sslContext =
                    io.grpc.netty.shaded.io.grpc.netty.GrpcSslContexts.forClient()
                        .trustManager(caCert)
                        .keyManager(clientCert, clientKey)
                        .build();
                builder.sslContext(sslContext);
                logger.info("GrpcClientBridge port {} initialized with mTLS (secure mode)", port);
            } catch (Exception e) {
                logger.error("Failed to load mTLS certificates from {}: {}", certDir, e.getMessage(), e);
                throw new RuntimeException("Failed to initialize secure gRPC client context", e);
            }
        } else {
            builder.usePlaintext();
        }

        this.channel = builder.build();
        this.blockingStub = SimBridgeGrpc.newBlockingStub(channel);
        this.asyncStub = SimBridgeGrpc.newStub(channel);
    }

    public void pollUntilReady() {
        logger.info("Polling gRPC server on port {} until ready...", port);
        while (true) {
            try {
                SimBridgeProto.HealthStatus status = blockingStub
                        .healthCheck(SimBridgeProto.Empty.getDefaultInstance());
                if (status.getReady()) {
                    logger.info("gRPC server is ready.");
                    break;
                }
            } catch (Exception e) {
                // Ignore and retry
            }
            try {
                Thread.sleep(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            }
        }
    }

    public SimBridgeProto.StepReady advanceTime(double t, double dt, int schemaEpoch) {
        SimBridgeProto.TimeStep req = SimBridgeProto.TimeStep.newBuilder()
                .setCurrentTime(t)
                .setDt(dt)
                .setSchemaEpoch(schemaEpoch)
                .build();
        return blockingStub.advanceTime(req);
    }

    public SimBridgeProto.StationProcessResponse simulateStationProcess(SimBridgeProto.StationProcessRequest req) {
        return blockingStub.withDeadlineAfter(10, TimeUnit.SECONDS).simulateStationProcess(req);
    }


    public ManagedChannel getChannel() {
        return channel;
    }

    public SimBridgeStub getAsyncStub() {
        return asyncStub;
    }

    public void shutdown() {
        try {
            channel.shutdown().awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        executor.shutdown();
    }
}
