package factory;

public class TestMinimal {
    public static void main(String[] args) {
        System.out.println("TestMinimal: STARTING");
        try {
            jacamo.infra.JaCaMoLauncher.main(new String[] { "build/phase4_jcm/test.jcm" });
        } catch (Throwable e) {
            e.printStackTrace();
        }
    }
}
