import unittest
import re
from generate_factory_jcm import rewrite_content, CANONICAL_TOKENS

class TestJCMGeneration(unittest.TestCase):
    def test_rewrite_content(self):
        content = """
        agent supervisor : supervisor_agent.asl {
            beliefs: active_schema(prosa)
        }
        workspace factory_ws {
            artifact database: factory.DatabaseArtifact
        }
        """
        rewritten = rewrite_content(content, run_id=5)
        
        self.assertIn("supervisor_5", rewritten)
        self.assertIn("factory_ws_5", rewritten)
        self.assertNotIn("supervisor :", rewritten)
        self.assertNotIn("factory_ws {", rewritten)
        
        # Ensure that non-canonical tokens aren't rewritten
        self.assertIn("active_schema(prosa)", rewritten)
        self.assertIn("factory.DatabaseArtifact", rewritten)

if __name__ == '__main__':
    unittest.main()
