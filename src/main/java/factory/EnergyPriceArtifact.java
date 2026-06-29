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
            InputStream is = getClass().getResourceAsStream("/price_series.csv");
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
            synchronized(priceLock) {
                if (Math.abs(newPrice - currentPrice) > 1e-6) {
                    currentPrice = newPrice;
                    updateObsProperty("energy_price", currentPrice);
                    signal("energy_price_changed", currentPrice);
                }
                
                if (!spikeActive && currentPrice >= spikeThresholdEurMwh) {
                    spikeActive = true;
                    defineObsProperty("energy_price_spike", currentPrice);
                    signal("energy_price_spike", currentPrice);
                    log("Price spike: " + currentPrice + " EUR/MWh at simT=" + simTime);
                } else if (spikeActive && currentPrice < spikeThresholdEurMwh * 0.90) {
                    spikeActive = false;
                    removeObsProperty("energy_price_spike");
                    signal("energy_price_normal", currentPrice);
                    log("Price normal: " + currentPrice + " EUR/MWh at simT=" + simTime);
                }
            }
        }
    }
}
