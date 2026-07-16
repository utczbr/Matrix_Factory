package factory;

public class LaunchTest {
    public static void main(String[] args) {
        System.out.println("BEFORE JACAMO");
        try {
            jacamo.infra.JaCaMoLauncher.main(new String[] { "build/phase4_jcm/factory_phase4.jcm" });
            System.out.println("JACAMO RETURNED NORMALLY");
        } catch (Throwable t) {
            t.printStackTrace(System.out);
        }
        System.out.println("AFTER JACAMO");
    }
}
