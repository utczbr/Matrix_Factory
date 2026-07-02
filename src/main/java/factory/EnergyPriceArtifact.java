package factory;

import cartago.*;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.util.NavigableMap;
import java.util.TreeMap;
import java.io.InputStream;

public class EnergyPriceArtifact extends Artifact {
    private final NavigableMap<Double, Double> priceAtSimTime = new TreeMap<>();
    private final Object priceLock = new Object();

    private double currentPrice = 0.0;

    private double spikeThresholdEurMwh = 150.0;
    private boolean spikeActive = false;
    private int runId;

    @OPERATION
    void init(String csvPath, int runId) {
        this.runId = runId;
        try {
            String filename = RunManager.getSimulator(runId).priceSeriesFile != null ? RunManager.getSimulator(runId).priceSeriesFile
                    : csvPath;
            if (filename.startsWith("/"))
                filename = filename.substring(1);
            InputStream is = getClass().getResourceAsStream("/" + filename);
            if (is != null) {
                try (BufferedReader br = new BufferedReader(new InputStreamReader(is))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        if (line.trim().isEmpty() || line.startsWith("#") || line.startsWith("simTime"))
                            continue;
                        String[] parts = line.split(",");
                        if (parts.length >= 2) {
                            double t = Double.parseDouble(parts[0].trim());
                            double p = Double.parseDouble(parts[1].trim());
                            priceAtSimTime.put(t, p);
                        }
                    }
                }
            } else {
                System.err.println("price_series.csv not found in resources. Using flat 50.0 EUR/MWh.");
                priceAtSimTime.put(0.0, 50.0);
            }
        } catch (Exception e) {
            System.err.println("Failed to load price_series.csv, using flat 50.0 EUR/MWh. " + e.getMessage());
            priceAtSimTime.put(0.0, 50.0);
        }

        defineObsProperty("energy_price", 0.0);
        RunManager.getSimulator(runId).energyPriceArtifact = this;
    }

    public void updatePrice(double simTime) {
        var entry = priceAtSimTime.floorEntry(simTime);
        if (entry != null) {
            double newPrice = entry.getValue();
            if (RunManager.getSimulator(runId).forceSpikeAt != null && simTime >= RunManager.getSimulator(runId).forceSpikeAt) {
                newPrice = Math.max(newPrice, spikeThresholdEurMwh + 15.0);
            }
            if (Math.abs(newPrice - currentPrice) > 1e-6 || (!spikeActive && newPrice >= spikeThresholdEurMwh)
                    || (spikeActive && newPrice < spikeThresholdEurMwh * 0.90)) {
                try {
                    System.out.println("[EnergyPriceArtifact] Submitting internalUpdatePrice for newPrice=" + newPrice
                            + " at simT=" + simTime);
                    execInternalOp("internalUpdatePrice", newPrice, simTime);
                } catch (Exception e) {
                    System.err.println("Failed to execInternalOp in EnergyPriceArtifact: " + e);
                }
            }
        }
    }

    @INTERNAL_OPERATION
    void internalUpdatePrice(double newPrice, double simTime) {
        System.out.println("[EnergyPriceArtifact] Executing internalUpdatePrice for newPrice=" + newPrice);
        synchronized (priceLock) {
            if (Math.abs(newPrice - currentPrice) > 1e-6) {
                currentPrice = newPrice;
                if (hasObsProperty("energy_price")) {
                    updateObsProperty("energy_price", currentPrice);
                }
                signal("energy_price_changed", currentPrice);
            }

            if (!spikeActive && currentPrice >= spikeThresholdEurMwh) {
                spikeActive = true;
                defineObsProperty("energy_price_spike", currentPrice);
                signal("energy_price_spike", currentPrice);
            } else if (spikeActive && currentPrice < spikeThresholdEurMwh * 0.90) {
                spikeActive = false;
                if (hasObsProperty("energy_price_spike")) {
                    removeObsProperty("energy_price_spike");
                }
                signal("energy_price_normal", currentPrice);
            }
        }
    }
}
