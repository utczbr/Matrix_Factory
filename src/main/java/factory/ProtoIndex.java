package factory;

public final class ProtoIndex {
    public static final int H2_TANK_PRESSURE_BAR    = 0;
    public static final int H2_TANK_FILL_FRACTION   = 1;
    public static final int CHILLER_TEMP_K          = 2;
    public static final int COMPRESSOR_POWER_KW     = 3;
    public static final int STACK_VOLTAGE_V         = 4;
    public static final int STACK_CURRENT_A_CM2     = 5;
    public static final int STACK_TEMP_K            = 6;
    public static final int STACK_CORE_TEMP_K       = 7;
    public static final int STACK_SKIN_TEMP_K       = 8;

    public static final int VECTOR_LENGTH = 9;

    private ProtoIndex() {}

    public static void validateVectorLength(int actualLength) {
        if (actualLength != VECTOR_LENGTH) {
            throw new IllegalStateException(
                "thermo_state_vector length mismatch: expected "
                + VECTOR_LENGTH + ", got " + actualLength
                + ". Sync proto_index.py with ProtoIndex.java and redeploy all daemons."
            );
        }
    }
}
