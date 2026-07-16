import jacamo.project.parser.JaCaMoProjectParser;
import jacamo.project.JaCaMoProject;
import java.io.File;

public class TestParser {
    public static void main(String[] args) {
        try {
            JaCaMoProject megaJcm = new JaCaMoProjectParser().parse("build/phase4_jcm/factory_phase4.jcm");
            System.out.println("Parsed successfully!");
            System.out.println("Agents: " + megaJcm.getAgents().size());
            System.out.println("Workspaces: " + megaJcm.getWorkspaces().size());
        } catch (Exception e) {
            System.out.println("ERROR PARSING!");
            e.printStackTrace(System.out);
        }
    }
}
