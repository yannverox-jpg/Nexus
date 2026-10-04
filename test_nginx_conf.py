import unittest
import os

class TestNginxConfig(unittest.TestCase):

    def test_nginx_config_file_exists(self):
        self.assertTrue(os.path.exists("nginx_nexus.conf"))
        with open("nginx_nexus.conf", "r") as f:
            content = f.read()
            self.assertIn("proxy_pass http://127.0.0.1:8000;", content)
            self.assertIn("Access-Control-Allow-Origin", content)
            self.assertIn("X-Nexus-Signature", content)

if __name__ == "__main__":
    unittest.main()
