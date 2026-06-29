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

    public GrpcClientBridge(int port) {
        int threads = Math.max(1, Runtime.getRuntime().availableProcessors() / 30);
        this.executor = new ThreadPoolExecutor(
            threads, threads, 0L, TimeUnit.MILLISECONDS,
            new LinkedBlockingQueue<>(256),
            new ThreadPoolExecutor.CallerRunsPolicy()
        );
        this.channel = NettyChannelBuilder.forAddress("127.0.0.1", port)
            .usePlaintext()
            .executor(this.executor)
            .build();
        this.blockingStub = SimBridgeGrpc.newBlockingStub(channel);
        this.asyncStub = SimBridgeGrpc.newStub(channel);
    }

    public void pollUntilReady() {
        logger.info("Polling gRPC server on port 50051 until ready...");
        while (true) {
            try {
                SimBridgeProto.HealthStatus status = blockingStub.healthCheck(SimBridgeProto.Empty.getDefaultInstance());
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
