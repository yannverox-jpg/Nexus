import unittest
import asyncio
from stealth_browser_agent import HumanAgent

class TestHumanAgent(unittest.IsolatedAsyncioTestCase):

    async def test_human_agent_simulation_mode(self):
        agent = HumanAgent(headless=True)
        await agent.initialize()

        screenshot = await agent.capture_screen_for_vision()
        self.assertIsNotNone(screenshot)

        await agent.navigate_and_act("https://example.com")
        await agent.close()

if __name__ == "__main__":
    unittest.main()
