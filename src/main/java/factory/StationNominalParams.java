package factory;

/**
 * Nominal parameter constants for Stations 1-4.
 * Mirrors the Python physical engine nominal values in:
 * - physical_engine/factory_simulation/station1_mea_preparation.py
 * - physical_engine/factory_simulation/station2_catalyst_deposition.py
 * - physical_engine/factory_simulation/station3_bipolar_plate_stamping.py
 * - physical_engine/factory_simulation/station4_stack_clamping.py
 */
public final class StationNominalParams {
    public static final double S1_T_PRESS_NOMINAL_K = 433.15;
    public static final double S1_DWELL_TIME_NOMINAL_S = 180.0;
    public static final double S2_V_COAT_NOMINAL_M_S = 0.15;
    public static final double S2_MU_SLURRY_NOMINAL_PA_S = 0.050;
    public static final double S3_PRESS_FORCE_NOMINAL_KN = 120.0;
    public static final double S4_TORQUE_NOMINAL_NM = 46.0;

    private StationNominalParams() {}
}
