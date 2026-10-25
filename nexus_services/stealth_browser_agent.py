"""Policy-aware Playwright browsing without stealth or human impersonation."""

from __future__ import annotations

import asyncio
import os
import sys
import re
import html
import httpx
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urljoin, urlparse

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

    async def probe_http(self, url: str) -> Optional[Dict[str, Any]]:
        """Try a bounded, read-only HTTP request before launching a browser.

        Returns an observation for ordinary static HTML, None when a browser
        is needed, and a human-intervention result when an access challenge is
        detected. Redirects and non-HTML responses are delegated to Playwright.
        The HTTP fast path is disabled when a proxy is configured so transport
        settings are not silently changed between modes.
        """
        self._assert_allowed_url(url)
        if self.proxy_config:
            return None

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(8.0, connect=4.0),
                follow_redirects=False,
                headers={"User-Agent": "NexusBrowser/1.0"},
            ) as client:
                response = await client.get(url)
        except (httpx.HTTPError, TimeoutError):
            return None

        content_type = response.headers.get("content-type", "").casefold()
        body = response.text[:1_000_000]
        lower_body = body.casefold()
        challenge_phrases = (
            "verify you are human", "checking your browser",
            "complete the captcha", "unusual traffic", "security challenge",
            "verify that you are human", "cf-chl-", "challenge-platform",
        )
        if response.status_code in {403, 429} or any(
            phrase in lower_body for phrase in challenge_phrases
        ):
            self.challenge_detected = True
            self.challenge_reason = "HTTP_ACCESS_CHALLENGE"
            return {
                "status": "HUMAN_INTERVENTION_REQUIRED",
                "url": str(response.url),
                "title": "",
                "text_excerpt": "",
                "challenge": {"detected": True, "reason": self.challenge_reason},
                "execution_mode": "HTTP",
                "http_status": response.status_code,
                "content_persisted": False,
                "actions_enabled": False,
            }

        if response.status_code != 200 or "html" not in content_type:
            return None

        title_match = re.search(r"<title[^>]*>(.*?)</title\s*>", body, re.I | re.S)
        title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else ""
        visible = re.sub(r"(?is)<(script|style|noscript)\b[^>]*>.*?</\1\s*>", " ", body)
        visible = re.sub(r"(?s)<[^>]+>", " ", visible)
        visible = re.sub(r"\s+", " ", html.unescape(visible)).strip()

        # App shells with little readable text usually need JavaScript rendering.
        script_count = len(re.findall(r"<script\b", body, re.I))
        if script_count >= 3 and len(visible) < 120:
            return None

        self.execution_mode = "HTTP_READ_ONLY"
        return {
            "status": "OBSERVED",
            "url": str(response.url),
            "title": title[:300],
            "text_excerpt": visible[:2000],
            "challenge": {"detected": False, "reason": None},
            "execution_mode": "HTTP_READ_ONLY",
            "http_status": response.status_code,
            "proxy_configured": False,
            "geolocation_emulation_enabled": False,
            "content_persisted": False,
            "actions_enabled": False,
        }

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


    _SENSITIVE_ACTION_WORDS = (
        "pay", "payment", "checkout", "purchase", "buy now", "withdraw", "transfer",
        "payout", "send money", "submit", "confirm order", "place order", "delete",
        "remove account", "sign in", "log in", "login", "authenticate", "authorize",
        "password", "passcode", "security code", "one-time code", "otp", "iban",
        "credit card", "debit card", "cvv", "cvc", "bank account",
    )
    _SENSITIVE_FIELD_WORDS = (
        "password", "passwd", "secret", "token", "card", "cvv", "cvc", "iban",
        "routing", "bank", "otp", "mfa", "authenticator", "security_code",
        "private_key", "payment", "amount", "withdraw", "transfer",
    )
    _UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".txt", ".csv", ".docx", ".xlsx"}

    def _require_action_page(self) -> None:
        if not self.page:
            raise RuntimeError("Browser is not initialized")
        if self.challenge_detected:
            raise PermissionError(
                "CAPTCHA or anti-bot challenge detected; automation paused for authorized human intervention"
            )
        self._assert_allowed_url(self.page.url)

    async def _unique_action_target(self, selector: str):
        if not isinstance(selector, str) or not selector.strip() or len(selector) > 300:
            raise ValueError("A valid CSS selector is required")
        locator = self.page.locator(selector)
        if await locator.count() != 1:
            raise ValueError("Selector must match exactly one element")
        return locator

    async def _action_metadata(self, locator) -> Dict[str, Any]:
        return await locator.evaluate("""el => {
            const form = el.form || el.closest('form');
            const label = el.labels ? Array.from(el.labels).map(x => x.innerText || '').join(' ') : '';
            return {
                tag: (el.tagName || '').toLowerCase(),
                type: (el.getAttribute('type') || '').toLowerCase(),
                name: (el.getAttribute('name') || '').toLowerCase(),
                id: (el.id || '').toLowerCase(),
                autocomplete: (el.getAttribute('autocomplete') || '').toLowerCase(),
                aria: (el.getAttribute('aria-label') || '').toLowerCase(),
                text: (el.innerText || el.value || '').toLowerCase().slice(0, 300),
                href: el.href || '',
                formAssociated: !!form,
                disabled: !!el.disabled,
                readOnly: !!el.readOnly,
                accept: (el.getAttribute('accept') || '').toLowerCase()
            };
        }""")

    def _assert_non_sensitive_metadata(self, metadata: Dict[str, Any]) -> None:
        identity = " ".join(str(metadata.get(key, "")) for key in (
            "name", "id", "autocomplete", "aria", "text"
        )).casefold()
        if any(word in identity for word in self._SENSITIVE_FIELD_WORDS + self._SENSITIVE_ACTION_WORDS):
            raise PermissionError("Potentially sensitive action or field blocked; complete it manually")
        if metadata.get("disabled") or metadata.get("readOnly"):
            raise PermissionError("Disabled or read-only elements cannot be changed")

    async def select_non_sensitive_option(self, selector: str, value: str) -> Dict[str, Any]:
        self._require_action_page()
        if not isinstance(value, str) or len(value) > 300:
            raise ValueError("Option value must be text of at most 300 characters")
        locator = await self._unique_action_target(selector)
        metadata = await self._action_metadata(locator)
        if metadata["tag"] != "select":
            raise ValueError("Target must be a native select element")
        self._assert_non_sensitive_metadata(metadata)
        selected = await self._journaled_operation(
            "select_non_sensitive_option", selector, {"option_length": len(value)},
            lambda: locator.select_option(value=value),
            response=lambda result: {"selected": result},
            metadata={"form_submitted": False},
        )
        return {"selector": selector, "status": "SELECTED", "selected": selected, "form_submitted": False}

    async def set_non_sensitive_checkable(self, selector: str, checked: bool = True) -> Dict[str, Any]:
        self._require_action_page()
        if not isinstance(checked, bool):
            raise ValueError("checked must be a boolean")
        locator = await self._unique_action_target(selector)
        metadata = await self._action_metadata(locator)
        if metadata["tag"] != "input" or metadata["type"] not in {"checkbox", "radio"}:
            raise ValueError("Target must be a checkbox or radio input")
        self._assert_non_sensitive_metadata(metadata)
        await self._journaled_operation(
            "set_non_sensitive_checkable", selector, {"checked": checked},
            lambda: locator.set_checked(checked),
            response=lambda _: {"checked": checked},
            metadata={"form_submitted": False},
        )
        return {"selector": selector, "status": "UPDATED", "checked": checked, "form_submitted": False}

    async def click_non_sensitive_element(self, selector: str) -> Dict[str, Any]:
        self._require_action_page()
        locator = await self._unique_action_target(selector)
        metadata = await self._action_metadata(locator)
        self._assert_non_sensitive_metadata(metadata)
        tag, element_type = metadata["tag"], metadata["type"]
        if tag == "a":
            href = metadata.get("href", "")
            if not href:
                raise PermissionError("Link without a destination is blocked")
            destination = urljoin(self.page.url, href)
            self._assert_allowed_url(destination)
        elif tag == "button":
            if element_type == "submit" or metadata.get("formAssociated"):
                raise PermissionError("Form submission is disabled; complete the action manually")
            if element_type not in {"", "button"}:
                raise PermissionError("This button type is not allowed")
        elif tag == "input" and element_type in {"button"}:
            if metadata.get("formAssociated"):
                raise PermissionError("Form-associated controls are blocked")
        else:
            raise PermissionError("Only allowlisted links and non-submitting buttons can be clicked")
        await self._journaled_operation(
            "click_non_sensitive_element", selector, {"tag": tag, "type": element_type},
            lambda: locator.click(),
            response=lambda _: {"clicked": True},
            metadata={"form_submitted": False, "sensitive_actions_allowed": False},
        )
        await self.detect_challenge()
        return {"selector": selector, "status": "CLICKED", "form_submitted": False}

    async def upload_allowlisted_file(self, selector: str, file_path: str) -> Dict[str, Any]:
        self._require_action_page()
        upload_root_raw = os.getenv("NEXUS_BROWSER_UPLOAD_DIR", "").strip()
        if not upload_root_raw:
            raise PermissionError("File uploads are disabled until NEXUS_BROWSER_UPLOAD_DIR is configured")
        root = Path(upload_root_raw).expanduser().resolve()
        candidate = Path(file_path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise PermissionError("Upload path must remain inside NEXUS_BROWSER_UPLOAD_DIR") from exc
        if not resolved.is_file() or resolved.is_symlink():
            raise ValueError("Upload target must be a regular file inside the configured upload directory")
        if resolved.suffix.casefold() not in self._UPLOAD_EXTENSIONS:
            raise PermissionError("File extension is not allowlisted for upload")
        if resolved.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Upload file exceeds the 10 MiB limit")
        locator = await self._unique_action_target(selector)
        metadata = await self._action_metadata(locator)
        if metadata["tag"] != "input" or metadata["type"] != "file":
            raise ValueError("Target must be an input[type=file]")
        self._assert_non_sensitive_metadata(metadata)
        await self._journaled_operation(
            "upload_allowlisted_file", selector,
            {"filename": resolved.name, "size_bytes": resolved.stat().st_size},
            lambda: locator.set_input_files(str(resolved)),
            response=lambda _: {"uploaded": True},
            metadata={"file_contents_persisted": False},
        )
        return {"selector": selector, "status": "FILE_SELECTED", "filename": resolved.name}

    async def capture_screenshot_bytes(self, full_page: bool = False) -> bytes:
        self._require_action_page()
        if not isinstance(full_page, bool):
            raise ValueError("full_page must be a boolean")
        return await self._journaled_operation(
            "capture_screenshot", "current_page", {"full_page": full_page},
            lambda: self.page.screenshot(full_page=full_page),
            response=lambda _: None,
            metadata={"content_persisted": False},
        )

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
