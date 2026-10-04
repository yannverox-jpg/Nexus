import unittest
import subprocess
import os

class TestJulesDeployScript(unittest.TestCase):

    def test_jules_deploy_execution(self):
        result = subprocess.run(["./jules_deploy.sh"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("[JULES DEPLOY] Initialisation", result.stdout)
        self.assertIn("[SUCCESS] Nexus est officiellement sur la toile", result.stdout)

if __name__ == "__main__":
    unittest.main()
