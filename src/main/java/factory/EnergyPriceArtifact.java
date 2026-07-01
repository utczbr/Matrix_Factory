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

    void init(String csvPath) {
        try {
            String filename = MainSimulator.INSTANCE.priceSeriesFile != null ? MainSimulator.INSTANCE.priceSeriesFile : csvPath;
            if (filename.startsWith("/")) filename = filename.substring(1);
            InputStream is = getClass().getResourceAsStream("/" + filename);
            if (is != null) {
                try (BufferedReader br = new BufferedReader(new InputStreamReader(is))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        if (line.trim().isEmpty() || line.startsWith("#") || line.startsWith("simTime")) continue;
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
        MainSimulator.INSTANCE.energyPriceArtifact = this;
    }

    public void updatePrice(double simTime) {
        var entry = priceAtSimTime.floorEntry(simTime);
        if (entry != null) {
            double newPrice = entry.getValue();
            if (MainSimulator.INSTANCE.forceSpikeAt != null && simTime >= MainSimulator.INSTANCE.forceSpikeAt) {
                newPrice = Math.max(newPrice, spikeThresholdEurMwh + 15.0);
            }
            synchronized(priceLock) {
                if (Math.abs(newPrice - currentPrice) > 1e-6) {
                    beginExtSession();
                    try {
                        currentPrice = newPrice;
                        if (hasObsProperty("energy_price")) {
                            updateObsProperty("energy_price", currentPrice);
                        }
                        signal("energy_price_changed", currentPrice);
                    } finally {
                        endExtSession();
                    }
                }
                
                if (!spikeActive && currentPrice >= spikeThresholdEurMwh) {
                    spikeActive = true;
                    beginExtSession();
                    try {
                        defineObsProperty("energy_price_spike", currentPrice);
                        signal("energy_price_spike", currentPrice);
                    } finally {
                        endExtSession();
                    }
                    log("Price spike: " + currentPrice + " EUR/MWh at simT=" + simTime);
                } else if (spikeActive && currentPrice < spikeThresholdEurMwh * 0.90) {
                    spikeActive = false;
                    beginExtSession();
                    try {
                        removeObsProperty("energy_price_spike");
                        signal("energy_price_normal", currentPrice);
                    } finally {
                        endExtSession();
                    }
                    log("Price normal: " + currentPrice + " EUR/MWh at simT=" + simTime);
                }
            }
        }
    }
}
