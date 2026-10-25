import unittest

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


if __name__ == "__main__":
    unittest.main()
