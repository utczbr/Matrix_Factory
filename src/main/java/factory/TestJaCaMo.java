package factory;

import jason.infra.centralised.RunCentralisedMAS;

public class TestJaCaMo {
    public static void main(String[] args) {
        System.out.println("TESTJACAMO: STARTING");
        try {
            RunCentralisedMAS runner = new RunCentralisedMAS();
            System.out.println("TESTJACAMO: INIT");
            runner.init(new String[] { "build/phase4_jcm/factory_phase4.jcm" });
            System.out.println("TESTJACAMO: CREATE");
            runner.create();
            System.out.println("TESTJACAMO: START");
            runner.start();
            System.out.println("TESTJACAMO: WAITEND");
            runner.waitEnd();
            System.out.println("TESTJACAMO: FINISH");
            runner.finish();
        } catch (Throwable e) {
            System.out.println("TESTJACAMO: CRASHED!");
            e.printStackTrace(System.out);
        }
        System.out.println("TESTJACAMO: DONE");
    }
}
