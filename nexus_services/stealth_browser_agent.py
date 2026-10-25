"""Policy-aware Playwright browsing without stealth or human impersonation."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None


class BrowserAgent:
    """Read-only browser navigation for explicitly allowlisted domains."""

    def __init__(
        self,
        headless: bool = True,
        browser_name: str = "chromium",
        allowed_domains: Optional[list[str]] = None,
    ):
        if browser_name not in {"chromium", "firefox"}:
            raise ValueError("browser_name must be chromium or firefox")
        self.headless = headless
        self.browser_name = browser_name
        configured_domains = os.getenv("NEXUS_BROWSER_ALLOWED_HOSTS", "").split(",")
        self.allowed_domains = frozenset(
            domain.strip().casefold().lstrip(".")
            for domain in (allowed_domains or configured_domains)
            if domain.strip()
        )
        self.proxy_config = self._load_proxy_config()
        self.locale = os.getenv("NEXUS_BROWSER_LOCALE", "fr-FR").strip() or "fr-FR"
        self.timezone_id = os.getenv("NEXUS_BROWSER_TIMEZONE", "Europe/Amsterdam").strip() or "Europe/Amsterdam"
        self.geolocation = self._load_geolocation()
        self.challenge_detected = False
        self.challenge_reason: Optional[str] = None
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.execution_mode = "UNAVAILABLE"
        self._journal_context = None

    @staticmethod
    def _load_proxy_config() -> Optional[Dict[str, str]]:
        """Load one explicitly configured proxy; never rotate or evade controls."""
        raw = os.getenv("NEXUS_BROWSER_PROXY", "").strip()
        if not raw:
            return None
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https", "socks5"} or not parsed.hostname:
            raise ValueError("NEXUS_BROWSER_PROXY must be an HTTP(S) or SOCKS5 proxy URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Put proxy credentials in dedicated environment variables, not the proxy URL")
        config: Dict[str, str] = {"server": raw}
        username = os.getenv("NEXUS_BROWSER_PROXY_USERNAME", "").strip()
        password = os.getenv("NEXUS_BROWSER_PROXY_PASSWORD", "")
        if bool(username) != bool(password):
            raise ValueError("Both proxy username and password must be configured together")
        if username:
            config["username"] = username
            config["password"] = password
        return config

    @staticmethod
    def _load_geolocation() -> Optional[Dict[str, float]]:
        """Geolocation emulation is opt-in and requires explicit coordinates."""
        enabled = os.getenv("NEXUS_BROWSER_ALLOW_GEOLOCATION", "").strip().casefold()
        if enabled not in {"1", "true", "yes"}:
            return None
        try:
            latitude = float(os.environ["NEXUS_BROWSER_LATITUDE"])
            longitude = float(os.environ["NEXUS_BROWSER_LONGITUDE"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Geolocation requires NEXUS_BROWSER_LATITUDE and NEXUS_BROWSER_LONGITUDE") from exc
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError("Geolocation coordinates are out of range")
        return {"latitude": latitude, "longitude": longitude}

    def bind_journal(
        self, journal: Any, task_id: str, attempt_id: str,
        execution_mode: str, source: str = "BrowserAgent",
    ) -> None:
        mode = execution_mode.upper()
        if mode not in ("REAL", "SIMULATED"):
            raise ValueError("Browser execution mode must be REAL or SIMULATED")
        self._journal_context = {
            "journal": journal,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "execution_mode": mode,
            "source": source,
        }

    def clear_journal(self) -> None:
        self._journal_context = None

    async def _journaled_operation(
        self, operation: str, target: Optional[str], request: Dict[str, Any],
        callback: Callable[[], Any], *,
        response: Optional[Callable[[Any], Optional[Dict[str, Any]]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Any:
        context = self._journal_context
        if context is None:
            result = callback()
            return await result if hasattr(result, "__await__") else result

        journal = context["journal"]
        call_id = journal.start_tool_call(
            context["task_id"], context["attempt_id"], "playwright", operation,
            execution_mode=context["execution_mode"], target=target,
            request=request, source=context["source"], metadata=metadata or {},
        )
        try:
            result = callback()
            if hasattr(result, "__await__"):
                result = await result
        except Exception as exc:
            journal.finish_tool_call(
                call_id, status="FAILED", error=str(exc), source=context["source"],
            )
            raise
        response_data = response(result) if response else None
        journal.finish_tool_call(
            call_id, status="COMPLETED", response=response_data,
            source=context["source"],
        )
        return result

    async def initialize(self) -> None:
        if async_playwright is None:
            self.execution_mode = "UNAVAILABLE"
            raise RuntimeError("Playwright is not installed; browser navigation is unavailable")

        # Render's native Python build installs the Playwright package but does not
        # download browser binaries. The user explicitly enables browser access;
        # fetch the selected official binary lazily on first use instead of claiming
        # that package installation alone made browsing ready.
        manager = async_playwright()
        probe = await manager.start()
        executable = Path(getattr(probe, self.browser_name).executable_path)
        await probe.stop()
        if not executable.is_file():
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "playwright", "install", self.browser_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                output, _ = await asyncio.wait_for(process.communicate(), timeout=180)
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.wait()
                raise RuntimeError("Playwright browser download timed out") from exc
            if process.returncode != 0 or not executable.is_file():
                detail = output.decode("utf-8", errors="replace")[-1200:]
                raise RuntimeError(f"Playwright browser setup failed: {detail}")

        self.playwright = await self._journaled_operation(
            "launch_driver", "playwright", {"headless": self.headless},
            lambda: async_playwright().start(),
        )
        engine = getattr(self.playwright, self.browser_name)
        self.browser = await self._journaled_operation(
            "launch_browser", self.browser_name,
            {"headless": self.headless, "proxy_configured": bool(self.proxy_config)},
            lambda: engine.launch(headless=self.headless, proxy=self.proxy_config),
        )
        context_options: Dict[str, Any] = {
            "locale": self.locale,
            "timezone_id": self.timezone_id,
        }
        if self.geolocation is not None:
            context_options["geolocation"] = self.geolocation
            context_options["permissions"] = ["geolocation"]
        self.context = await self._journaled_operation(
            "create_context", self.browser_name,
            {"locale": self.locale, "timezone_id": self.timezone_id,
             "geolocation_enabled": self.geolocation is not None},
            lambda: self.browser.new_context(**context_options),
        )
        self.page = await self._journaled_operation(
            "create_page", "browser_context", {},
            lambda: self.context.new_page(),
        )
        self.execution_mode = "REAL"

    def _assert_allowed_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or not host:
            raise ValueError("Only absolute HTTP(S) URLs are supported")
        if not self.allowed_domains:
            raise PermissionError("Browser navigation is disabled until an allowed-host list is configured")
        if not any(host == domain or host.endswith("." + domain) for domain in self.allowed_domains):
            raise PermissionError(f"The host {host} is not in NEXUS_BROWSER_ALLOWED_HOSTS")

    async def detect_challenge(self) -> Dict[str, Any]:
        """Detect common CAPTCHA/challenge signals and pause; never solve them."""
        if not self.page:
            return {"detected": False, "reason": None}
        selectors = (
            'iframe[src*="captcha" i]', 'iframe[title*="challenge" i]',
            '[data-sitekey]', '[id*="captcha" i]', 'textarea[name*="captcha" i]',
            '#challenge-running', '#cf-challenge-running',
        )
        for selector in selectors:
            try:
                if await self.page.locator(selector).count():
                    self.challenge_detected = True
                    self.challenge_reason = "CAPTCHA_OR_ANTI_BOT_CHALLENGE"
                    return {"detected": True, "reason": self.challenge_reason}
            except Exception:
                continue
        try:
            body = (await self.page.locator("body").inner_text(timeout=1500)).casefold()
        except Exception:
            body = ""
        phrases = (
            "verify you are human", "checking your browser", "complete the captcha",
            "unusual traffic", "security challenge", "verify that you are human",
        )
        if any(phrase in body for phrase in phrases):
            self.challenge_detected = True
            self.challenge_reason = "CAPTCHA_OR_ANTI_BOT_CHALLENGE"
        return {"detected": self.challenge_detected, "reason": self.challenge_reason}

    async def navigate(self, url: str) -> Optional[str]:
        self._assert_allowed_url(url)
        if not self.page:
            self.execution_mode = "UNAVAILABLE"
            raise RuntimeError("Browser is not initialized")
        self.challenge_detected = False
        self.challenge_reason = None
        await self._journaled_operation(
            "navigate", url, {"wait_until": "page_default"},
            lambda: self.page.goto(url),
            response=lambda _: {"url": self.page.url},
        )
        await self.detect_challenge()
        return self.page.url

    async def capture_screen_for_vision(self) -> Optional[bytes]:
        if not self.page:
            return None
        return await self._journaled_operation(
            "capture_screenshot", "current_page", {"full_page": False},
            lambda: self.page.screenshot(full_page=False),
            response=lambda _: None,
            metadata={"content_persisted": False},
        )

    async def navigate_and_act(self, url: str) -> Optional[bytes]:
        """Compatibility entry point; navigates and captures, but performs no page actions."""
        await self.navigate(url)
        return await self.capture_screen_for_vision()

    async def human_move_to(self, target_x: float, target_y: float) -> None:
        """Deprecated compatibility wrapper; moves directly without human simulation."""
        if not self.page:
            raise RuntimeError("Browser is not initialized")
        await self._journaled_operation(
            "move_pointer", "current_page", {"x": target_x, "y": target_y},
            lambda: self.page.mouse.move(target_x, target_y),
        )

    async def human_type(self, selector: str, text: str) -> None:
        """Legacy entry point remains blocked; use fill_non_sensitive_field for safe fields."""
        raise PermissionError("Use fill_non_sensitive_field for non-sensitive fields; sensitive steps remain manual")

    async def fill_non_sensitive_field(self, selector: str, value: str) -> Dict[str, Any]:
        """Fill one uniquely identified non-sensitive text field; never submit it."""
        if not self.page:
            raise RuntimeError("Browser is not initialized")
        if self.challenge_detected:
            raise PermissionError("CAPTCHA or anti-bot challenge detected; automation paused for authorized human intervention")
        if not isinstance(selector, str) or not selector.strip() or len(selector) > 300:
            raise ValueError("A valid CSS selector is required")
        if not isinstance(value, str) or len(value) > 2000:
            raise ValueError("Field value must be text of at most 2000 characters")
        locator = self.page.locator(selector)
        count = await locator.count()
        if count != 1:
            raise ValueError("Selector must match exactly one field")
        metadata = await locator.evaluate("""el => ({
            tag: (el.tagName || '').toLowerCase(),
            type: (el.getAttribute('type') || 'text').toLowerCase(),
            name: (el.getAttribute('name') || '').toLowerCase(),
            id: (el.id || '').toLowerCase(),
            autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase(),
            disabled: !!el.disabled,
            readOnly: !!el.readOnly
        })""")
        tag = metadata["tag"]
        field_type = metadata["type"]
        sensitive = ("password", "hidden", "submit", "button", "image", "file", "reset")
        sensitive_words = ("password", "passwd", "secret", "token", "card", "cvv", "cvc",
                           "iban", "routing", "bank", "otp", "mfa", "authenticator",
                           "security_code", "private_key")
        identity = " ".join((metadata["name"], metadata["id"], metadata["autocomplete"]))
        if (tag not in {"input", "textarea"} or field_type in sensitive
                or any(word in identity for word in sensitive_words)
                or metadata["autocomplete"] in {"cc-number", "cc-csc", "cc-exp", "current-password",
                                                "new-password", "one-time-code"}
                or metadata["disabled"] or metadata["readOnly"]):
            raise PermissionError("Sensitive or non-editable field blocked; complete it manually")
        await self._journaled_operation(
            "fill_non_sensitive_field", selector,
            {"value_length": len(value), "field_type": field_type},
            lambda: locator.fill(value),
            response=lambda _: {"field_filled": True, "value_persisted": False},
            metadata={"sensitive_fields_allowed": False, "form_submitted": False},
        )
        return {"selector": selector, "status": "FILLED", "form_submitted": False}

    async def close(self) -> None:
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
        finally:
            if self.playwright:
                await self.playwright.stop()
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            self.execution_mode = "UNAVAILABLE"


# Keep the old import name available while removing its stealth behavior.
HumanAgent = BrowserAgent
