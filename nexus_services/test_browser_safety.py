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


    async def test_select_requires_native_select_and_returns_selected_value(self):
        class SelectLocator(FakeLocator):
            async def select_option(self, value):
                self.selected = value
                return [value]
        class SelectPage:
            url = "https://example.test/form"
            def __init__(self):
                self.target = SelectLocator({
                    "tag": "select", "type": "", "name": "country", "id": "country",
                    "autocomplete": "", "aria": "", "text": "", "href": "",
                    "formAssociated": True, "disabled": False, "readOnly": False,
                })
            def locator(self, _selector): return self.target
        agent = BrowserAgent(allowed_domains=["example.test"])
        agent.page = SelectPage()
        result = await agent.select_non_sensitive_option("#country", "NL")
        self.assertEqual(result["status"], "SELECTED")
        self.assertFalse(result["form_submitted"])

    async def test_blocks_submit_button_click(self):
        class ClickLocator(FakeLocator):
            async def click(self): self.clicked = True
        class ClickPage:
            url = "https://example.test/form"
            def locator(self, _selector):
                return ClickLocator({
                    "tag": "button", "type": "submit", "name": "", "id": "submit",
                    "autocomplete": "", "aria": "continue", "text": "continue", "href": "",
                    "formAssociated": True, "disabled": False, "readOnly": False,
                })
        agent = BrowserAgent(allowed_domains=["example.test"])
        agent.page = ClickPage()
        with self.assertRaises(PermissionError):
            await agent.click_non_sensitive_element("#submit")

    async def test_blocks_unallowlisted_current_host_for_actions(self):
        class Page:
            url = "https://evil.example.test/"
            def locator(self, _selector): raise AssertionError("must reject before locator")
        agent = BrowserAgent(allowed_domains=["example.test"])
        agent.page = Page()
        with self.assertRaises(PermissionError):
            await agent.select_non_sensitive_option("#country", "NL")

    async def test_blocks_checkbox_with_payment_related_name(self):
        class CheckLocator(FakeLocator):
            async def set_checked(self, checked): self.checked = checked
        class CheckPage:
            url = "https://example.test/form"
            def locator(self, _selector):
                return CheckLocator({
                    "tag": "input", "type": "checkbox", "name": "payment_authorize",
                    "id": "authorize", "autocomplete": "", "aria": "", "text": "",
                    "href": "", "formAssociated": True, "disabled": False, "readOnly": False,
                })
        agent = BrowserAgent(allowed_domains=["example.test"])
        agent.page = CheckPage()
        with self.assertRaises(PermissionError):
            await agent.set_non_sensitive_checkable("#authorize", True)

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


class HttpProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_probe_returns_read_only_static_html(self):
        class Response:
            status_code = 200
            headers = {"content-type": "text/html; charset=utf-8"}
            text = "<html><head><title>Public page</title></head><body><h1>Hello Nexus</h1></body></html>"
            url = "https://example.test/"
        class Client:
            def __init__(self, **_kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_args): return False
            async def get(self, _url): return Response()

        agent = BrowserAgent(allowed_domains=["example.test"])
        with patch("nexus_services.stealth_browser_agent.httpx.AsyncClient", Client):
            result = await agent.probe_http("https://example.test/")
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(result["execution_mode"], "HTTP_READ_ONLY")
        self.assertEqual(result["title"], "Public page")
        self.assertIn("Hello Nexus", result["text_excerpt"])
        self.assertFalse(result["actions_enabled"])
        self.assertIsNone(agent.page)

    async def test_http_probe_stops_on_access_challenge(self):
        class Response:
            status_code = 403
            headers = {"content-type": "text/html"}
            text = "<html><body>Verify you are human</body></html>"
            url = "https://example.test/"
        class Client:
            def __init__(self, **_kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_args): return False
            async def get(self, _url): return Response()

        agent = BrowserAgent(allowed_domains=["example.test"])
        with patch("nexus_services.stealth_browser_agent.httpx.AsyncClient", Client):
            result = await agent.probe_http("https://example.test/")
        self.assertEqual(result["status"], "HUMAN_INTERVENTION_REQUIRED")
        self.assertTrue(result["challenge"]["detected"])
        self.assertTrue(agent.challenge_detected)
        self.assertIsNone(agent.page)

    async def test_http_probe_falls_back_for_javascript_app_shell(self):
        class Response:
            status_code = 200
            headers = {"content-type": "text/html"}
            text = '<html><head><title>App</title></head><body><div id="root"></div><script src="a.js"></script><script src="b.js"></script><script src="c.js"></script></body></html>'
            url = "https://example.test/"
        class Client:
            def __init__(self, **_kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *_args): return False
            async def get(self, _url): return Response()

        agent = BrowserAgent(allowed_domains=["example.test"])
        with patch("nexus_services.stealth_browser_agent.httpx.AsyncClient", Client):
            result = await agent.probe_http("https://example.test/")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
