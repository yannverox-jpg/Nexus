import unittest
import asyncio
from nexus_dashboard import async_send_command, async_fetch_telemetry

class TestNexusDashboard(unittest.IsolatedAsyncioTestCase):

    async def test_async_fetch_telemetry_offline(self):
        # Fetching telemetry from non-existent port returns None
        res = await async_fetch_telemetry()
        self.assertIsNone(res)

    async def test_async_send_command_offline(self):
        res = await async_send_command("webhook", {"action": "TEST"})
        self.assertIn(res["status"], ["offline", "error"])

if __name__ == "__main__":
    unittest.main()
