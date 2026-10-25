import os
import unittest
from unittest.mock import patch

from nexus_services.stealth_browser_agent import BrowserAgent


class FakeLocator:
    def __init__(self, metadata):
        self.metadata = metadata
        self.value = None

    async def count(self):
        return 1

    async def evaluate(self, _script):
        return self.metadata

    async def fill(self, value):
        self.value = value


class FakePage:
    def __init__(self, metadata):
        self.locator_instance = FakeLocator(metadata)

    def locator(self, _selector):
        return self.locator_instance


class BrowserFieldSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_allows_non_sensitive_text_field_without_submission(self):
        agent = BrowserAgent()
        page = FakePage({
            "tag": "input", "type": "email", "name": "contact_email", "id": "email",
            "autocomplete": "email", "disabled": False, "readOnly": False,
        })
        agent.page = page
        result = await agent.fill_non_sensitive_field("#email", "user@example.test")
        self.assertEqual(result["status"], "FILLED")
        self.assertFalse(result["form_submitted"])
        self.assertEqual(page.locator_instance.value, "user@example.test")

    async def test_blocks_password_fields(self):
        agent = BrowserAgent()
        agent.page = FakePage({
            "tag": "input", "type": "password", "name": "password", "id": "password",
            "autocomplete": "current-password", "disabled": False, "readOnly": False,
        })
        with self.assertRaises(PermissionError):
            await agent.fill_non_sensitive_field("#password", "never-store-this")

    async def test_requires_unique_selector_match(self):
        class MultipleLocator(FakeLocator):
            async def count(self):
                return 2

        class MultiplePage:
            def locator(self, _selector):
                return MultipleLocator({})

        agent = BrowserAgent()
        agent.page = MultiplePage()
        with self.assertRaises(ValueError):
            await agent.fill_non_sensitive_field("input", "example")

    async def test_blocks_field_filling_after_challenge_detection(self):
        agent = BrowserAgent()
        agent.page = FakePage({
            "tag": "input", "type": "text", "name": "search", "id": "search",
            "autocomplete": "", "disabled": False, "readOnly": False,
        })
        agent.challenge_detected = True
        with self.assertRaisesRegex(PermissionError, "challenge detected"):
            await agent.fill_non_sensitive_field("#search", "query")

    def test_proxy_requires_supported_scheme(self):
        with patch.dict(os.environ, {"NEXUS_BROWSER_PROXY": "file:///tmp/proxy"}, clear=True):
            with self.assertRaises(ValueError):
                BrowserAgent()

    def test_proxy_credentials_use_separate_environment_variables(self):
        env = {
            "NEXUS_BROWSER_PROXY": "socks5://127.0.0.1:9050",
            "NEXUS_BROWSER_PROXY_USERNAME": "proxy-user",
            "NEXUS_BROWSER_PROXY_PASSWORD": "proxy-password",
        }
        with patch.dict(os.environ, env, clear=True):
            agent = BrowserAgent()
        self.assertEqual(agent.proxy_config["server"], "socks5://127.0.0.1:9050")
        self.assertEqual(agent.proxy_config["username"], "proxy-user")

    def test_geolocation_is_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            agent = BrowserAgent()
        self.assertIsNone(agent.geolocation)

    def test_geolocation_requires_opt_in_and_valid_coordinates(self):
        env = {
            "NEXUS_BROWSER_ALLOW_GEOLOCATION": "true",
            "NEXUS_BROWSER_LATITUDE": "48.8566",
            "NEXUS_BROWSER_LONGITUDE": "2.3522",
        }
        with patch.dict(os.environ, env, clear=True):
            agent = BrowserAgent()
        self.assertEqual(agent.geolocation, {"latitude": 48.8566, "longitude": 2.3522})
        with patch.dict(os.environ, {**env, "NEXUS_BROWSER_LATITUDE": "100"}, clear=True):
            with self.assertRaises(ValueError):
                BrowserAgent()


if __name__ == "__main__":
    unittest.main()
