import unittest
import requests
import time
from metrics.telemetry_exporter import export_nexus_telemetry, update_telemetry_snapshot

class TestNexusTelemetry(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        export_nexus_telemetry(port=9099)
        time.sleep(0.5)

    def test_metrics_exporter_endpoint(self):
        update_telemetry_snapshot()
        res = requests.get("http://localhost:9099/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("nexus_gpu_vram_usage_bytes", res.text)
        self.assertIn("nexus_active_leases", res.text)
        self.assertIn("nexus_circuit_breaker_status", res.text)

if __name__ == "__main__":
    unittest.main()
