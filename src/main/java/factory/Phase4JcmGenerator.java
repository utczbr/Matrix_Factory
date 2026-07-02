package factory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Pattern;

final class Phase4JcmGenerator {
    private static final Pattern RUN_ID_PATTERN = Pattern.compile("run_id\\(\\{\\{RUN_ID\\}\\}\\)");

    private Phase4JcmGenerator() {
    }

    static List<String> discoverJcmPaths(int runCount, String phase4JcmDir) {
        if (phase4JcmDir == null || phase4JcmDir.isBlank()) {
            List<String> defaults = new ArrayList<>(runCount);
            for (int i = 0; i < runCount; i++) {
                defaults.add("factory.jcm");
            }
            return defaults;
        }

        try {
            return Files.list(Path.of(phase4JcmDir))
                    .filter(path -> path.getFileName().toString().endsWith(".jcm"))
                    .sorted(Comparator.comparing(Path::toString))
                    .map(Path::toString)
                    .limit(runCount)
                    .toList();
        } catch (IOException e) {
            throw new IllegalStateException("Failed to discover Phase 4 JCM files in " + phase4JcmDir, e);
        }
    }

    static void generate(Path templatePath, Path outputDir, int runCount) throws IOException {
        String template = Files.readString(templatePath, StandardCharsets.UTF_8);
        Files.createDirectories(outputDir);

        for (int runId = 0; runId < runCount; runId++) {
            String rendered = template.replace("{{RUN_ID}}", Integer.toString(runId));
            rendered = RUN_ID_PATTERN.matcher(rendered).replaceAll("run_id(" + runId + ")");
            Path targetPath = outputDir.resolve(String.format("factory_run_%02d.jcm", runId));
            Files.writeString(targetPath, rendered, StandardCharsets.UTF_8);
        }
    }
}