package factory;

import cartago.OpFeedbackParam;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class DatabaseArtifactTest {

    private DatabaseArtifact databaseArtifact;

    @BeforeEach
    void setUp() {
        databaseArtifact = new DatabaseArtifact();
    }

    @Test
    void testPeekQualityProfileIsNonDestructive() {
        String stackId = "STACK_TEST_001";

        // Record quality events from stations 1 and 2
        databaseArtifact.recordStationQuality(1, stackId, "S1", true, 6.0, 5.0, 10.0);
        databaseArtifact.recordStationQuality(1, stackId, "S2", false, 12.0, 12.0, 20.0);

        OpFeedbackParam<Integer> defectCountParam1 = new OpFeedbackParam<>();
        OpFeedbackParam<Integer> stationsVisitedParam1 = new OpFeedbackParam<>();
        OpFeedbackParam<Double> varianceRatioParam1 = new OpFeedbackParam<>();

        // First read using peekQualityProfile
        databaseArtifact.peekQualityProfile(stackId, defectCountParam1, stationsVisitedParam1, varianceRatioParam1);

        assertEquals(1, defectCountParam1.get());
        assertEquals(2, stationsVisitedParam1.get());
        assertEquals(0.2, varianceRatioParam1.get(), 1e-6);

        // Second read using peekQualityProfile (should yield identical result, non-destructive)
        OpFeedbackParam<Integer> defectCountParam2 = new OpFeedbackParam<>();
        OpFeedbackParam<Integer> stationsVisitedParam2 = new OpFeedbackParam<>();
        OpFeedbackParam<Double> varianceRatioParam2 = new OpFeedbackParam<>();

        databaseArtifact.peekQualityProfile(stackId, defectCountParam2, stationsVisitedParam2, varianceRatioParam2);

        assertEquals(1, defectCountParam2.get());
        assertEquals(2, stationsVisitedParam2.get());
        assertEquals(0.2, varianceRatioParam2.get(), 1e-6);
    }

    @Test
    void testExplicitInvalidateQualityProfile() {
        String stackId = "STACK_TEST_002";

        databaseArtifact.recordStationQuality(1, stackId, "S1", true, 6.0, 5.0, 10.0);

        OpFeedbackParam<Integer> defectCountParam = new OpFeedbackParam<>();
        OpFeedbackParam<Integer> stationsVisitedParam = new OpFeedbackParam<>();
        OpFeedbackParam<Double> varianceRatioParam = new OpFeedbackParam<>();

        databaseArtifact.peekQualityProfile(stackId, defectCountParam, stationsVisitedParam, varianceRatioParam);
        assertEquals(1, defectCountParam.get());

        // Explicitly invalidate cache
        databaseArtifact.invalidateQualityProfile(stackId);

        // Subsquent peek should yield EMPTY profile (0 defects, 0 stations)
        OpFeedbackParam<Integer> defectCountParamAfter = new OpFeedbackParam<>();
        OpFeedbackParam<Integer> stationsVisitedParamAfter = new OpFeedbackParam<>();
        OpFeedbackParam<Double> varianceRatioParamAfter = new OpFeedbackParam<>();

        databaseArtifact.peekQualityProfile(stackId, defectCountParamAfter, stationsVisitedParamAfter, varianceRatioParamAfter);
        assertEquals(0, defectCountParamAfter.get());
        assertEquals(0, stationsVisitedParamAfter.get());
        assertEquals(0.0, varianceRatioParamAfter.get(), 1e-6);
    }

    @Test
    void testExposureNormalizedVariancePenalty() {
        String stackId1 = "STACK_1_STATION";
        String stackId4 = "STACK_4_STATIONS";

        // Stack 1: 1 station visited with variance = 0.4
        databaseArtifact.recordStationQuality(1, stackId1, "S1", false, 7.0, 5.0, 10.0);

        // Stack 4: 4 stations visited with cumulative variance = 0.4 (0.1 per station)
        databaseArtifact.recordStationQuality(1, stackId4, "S1", false, 5.5, 5.0, 10.0);
        databaseArtifact.recordStationQuality(1, stackId4, "S2", false, 13.2, 12.0, 20.0);
        databaseArtifact.recordStationQuality(1, stackId4, "S3", false, 3.3, 3.0, 30.0);
        databaseArtifact.recordStationQuality(1, stackId4, "S4", false, 26.4, 24.0, 40.0);

        OpFeedbackParam<Integer> defects1 = new OpFeedbackParam<>(), defects4 = new OpFeedbackParam<>();
        OpFeedbackParam<Integer> visited1 = new OpFeedbackParam<>(), visited4 = new OpFeedbackParam<>();
        OpFeedbackParam<Double> var1 = new OpFeedbackParam<>(), var4 = new OpFeedbackParam<>();

        databaseArtifact.peekQualityProfile(stackId1, defects1, visited1, var1);
        databaseArtifact.peekQualityProfile(stackId4, defects4, visited4, var4);

        assertEquals(1, visited1.get());
        assertEquals(4, visited4.get());
        assertEquals(0.4, var1.get(), 1e-6);
        assertEquals(0.4, var4.get(), 1e-6);

        // Normalized penalty calculation check
        double penalty1 = (var1.get() * 0.02) / Math.max(visited1.get(), 1);
        double penalty4 = (var4.get() * 0.02) / Math.max(visited4.get(), 1);

        assertEquals(0.008, penalty1, 1e-6);
        assertEquals(0.002, penalty4, 1e-6);
        assertTrue(penalty4 < penalty1, "4-station normalized penalty must be strictly less than 1-station penalty");
    }
}
