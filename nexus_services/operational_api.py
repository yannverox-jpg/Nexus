"""Loopback-only operational status API for the Streamlit service."""

from __future__ import annotations

import os
import uuid
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .agent_roles import build_agent_system_context, get_provider_status, get_role_assignments
from .ai_connectors import CONNECTORS
from .connection_manager import ConnectionManager
from .platform_catalog import get_platform_catalog
from .stealth_browser_agent import BrowserAgent, async_playwright
from .operational_dashboard import dashboard_overview, mission_detail, task_detail
from .memory_store import ConversationMemory, configured_database_path
from .payout_ledger import PayoutLedger
from .runtime_contracts import OperationalJournal

database_path = configured_database_path()
journal = OperationalJournal(database_path)
conversation_memory = ConversationMemory(database_path)
payout_ledger = PayoutLedger(database_path)
connection_manager = ConnectionManager(database_path)
_browser_agent: BrowserAgent | None = None


class BrowserNavigationRequest(BaseModel):
    url: str
    browser: str = "chromium"


class BrowserFormField(BaseModel):
    selector: str
    value: str


class BrowserFormFillRequest(BaseModel):
    fields: list[BrowserFormField]


class AdvisoryChatRequest(BaseModel):
    message: str
    system: str = ""
    domain: str = "general"
    conversation_id: str | None = None


class StrictRequest(BaseModel):
    class Config:
        extra = "forbid"


class PlatformAccountRequest(StrictRequest):
    platform: str
    account_reference: str
    currency: str
    balance: str
    evidence_reference: str
    observed_at: str | None = None


class PayoutDestinationRequest(StrictRequest):
    provider: str
    destination_type: str = "CARD"
    label: str
    currency: str
    last4: str


class RevenueEntryRequest(StrictRequest):
    source: str
    category: str
    amount: str
    currency: str
    earned_at: str | None = None


class ConfirmRevenueRequest(StrictRequest):
    evidence_reference: str


class PayoutOrderRequest(StrictRequest):
    destination_id: str
    amount: str
    currency: str


class PayoutUpdateRequest(StrictRequest):
    status: str
    external_reference: str


class OAuthStartRequest(StrictRequest):
    remember_me: bool = False


class OAuthCallbackRequest(StrictRequest):
    code: str
    state: str


app = FastAPI(
    title="Nexus Operational API",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "online", "mode": "read-only"}


@app.get("/api/v1/operational/overview")
def get_overview():
    return dashboard_overview(journal)


@app.get("/api/v1/payouts/overview")
def get_payout_overview():
    return payout_ledger.overview()


@app.get("/api/v1/platform-accounts")
def list_platform_accounts():
    return {
        "ownership": "EXTERNAL_PLATFORM_ACCOUNTS",
        "nexus_owned_wallet": False,
        "accounts": payout_ledger.list_platform_accounts(),
    }


@app.post("/api/v1/platform-accounts")
def register_platform_account(request: PlatformAccountRequest):
    try:
        return payout_ledger.register_platform_account(**request.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/payouts/destinations")
def create_payout_destination(request: PayoutDestinationRequest):
    try:
        return payout_ledger.add_destination(**request.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/payouts/destinations/{destination_id}/confirm")
def confirm_payout_destination(destination_id: str, request: ConfirmRevenueRequest):
    try:
        return payout_ledger.confirm_destination(
            destination_id, request.evidence_reference,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/payouts/revenue")
def report_revenue(request: RevenueEntryRequest):
    try:
        return payout_ledger.add_revenue(**request.dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/payouts/revenue/{entry_id}/confirm")
def confirm_revenue(entry_id: str, request: ConfirmRevenueRequest):
    try:
        return payout_ledger.confirm_revenue(entry_id, request.evidence_reference)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/payouts/orders")
def create_payout_order(request: PayoutOrderRequest):
    try:
        return payout_ledger.create_payout_order(**request.dict())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/payouts/orders/{order_id}/status")
def update_payout_order(order_id: str, request: PayoutUpdateRequest):
    try:
        return payout_ledger.update_payout_order(
            order_id, status=request.status,
            external_reference=request.external_reference,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/operational/missions/{mission_id}")
def get_mission(mission_id: str):
    mission = mission_detail(journal, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found in OperationalJournal")
    return mission


@app.get("/api/v1/operational/tasks/{task_id}")
def get_task(task_id: str):
    task = task_detail(journal, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found in OperationalJournal")
    return task


@app.get("/api/v1/integrations/status")
def get_integration_status():
    allowed_hosts = os.getenv("NEXUS_BROWSER_ALLOWED_HOSTS", "")
    domains = [host.strip() for host in allowed_hosts.split(",") if host.strip()]
    return {
        "agent_roles": get_role_assignments(),
        "ai_providers": get_provider_status(),
        "browser": {
            "playwright_package_available": async_playwright is not None,
            "allowed_hosts_configured": bool(domains),
            "allowed_host_count": len(domains),
            "navigation_configured": async_playwright is not None and bool(domains),
        },
        "platform_catalog": get_platform_catalog(),
        "connections": connection_manager.list_connections(),
    }


@app.post("/api/v1/connections/{provider_id}/oauth/start")
def start_provider_oauth(provider_id: str, request: OAuthStartRequest):
    try:
        return connection_manager.start_oauth(provider_id, request.remember_me)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/connections/oauth/callback")
def finish_provider_oauth(request: OAuthCallbackRequest):
    try:
        return connection_manager.complete_oauth(request.code, request.state)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/connections/{provider_id}")
def disconnect_provider(provider_id: str):
    try:
        return connection_manager.disconnect(provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/advisory/{agent_name}")
def advisory_chat(agent_name: str, request: AdvisoryChatRequest):
    """Ask a configured provider; persist redacted conversation history, never actions."""
    provider_id = {"gpt": "codex_gpt", "codex": "codex_gpt", "gemini": "gemini", "claude": "claude"}.get(agent_name.casefold())
    if provider_id is None:
        raise HTTPException(status_code=400, detail="Agent non reconnu")
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    if not CONNECTORS[provider_id].status()["connector_available"]:
        raise HTTPException(status_code=503, detail=f"{provider_id} provider is not configured")
    try:
        system_context = build_agent_system_context(provider_id, request.domain, request.system)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    conversation_id = request.conversation_id or uuid.uuid4().hex
    prior_messages = conversation_memory.recent_messages(conversation_id, limit=12)
    conversation_memory.add_message(
        conversation_id, "user", request.message, provider_id,
        os.getenv(CONNECTORS[provider_id].model_env, CONNECTORS[provider_id].default_model),
    )
    history = "\\n".join(
        f"{item['role']}: {item['content']}" for item in prior_messages[-10:]
    )
    prompt = (
        f"Prior conversation (context only):\\n{history}\\n\\nCurrent user message:\\n{request.message}"
        if history else request.message
    )
    try:
        result = CONNECTORS[provider_id].complete(
            prompt,
            system=system_context,
            google_search=provider_id == "gemini" and request.domain == "sports",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"{provider_id} provider request failed") from exc

    conversation_memory.add_message(
        conversation_id, "assistant", result["text"], provider_id, result["model"]
    )
    return {**result, "conversation_id": conversation_id, "memory_persisted": True}


@app.get("/api/v1/memory/conversations/{conversation_id}")
def get_conversation_memory(conversation_id: str, limit: int = 40):
    """Return redacted persisted messages for a single conversation."""
    return {
        "conversation_id": conversation_id,
        "messages": conversation_memory.recent_messages(conversation_id, limit=limit),
        "storage": "configured_operational_database",
    }


@app.post("/api/v1/browser/navigate")
async def navigate_browser(request: BrowserNavigationRequest):
    """Open an allowlisted page for observation; never logs in or submits forms."""
    global _browser_agent
    if async_playwright is None:
        raise HTTPException(status_code=503, detail="Playwright is unavailable")
    parsed = urlparse(request.url)
    if request.browser not in {"chromium", "firefox"}:
        raise HTTPException(status_code=400, detail="Browser must be chromium or firefox")
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise HTTPException(status_code=400, detail="Use an absolute URL without credentials, query, or fragment")
    allowed_hosts = {
        host.strip().casefold().lstrip(".")
        for host in os.getenv("NEXUS_BROWSER_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    }
    host = parsed.hostname.casefold()
    if not any(host == domain or host.endswith("." + domain) for domain in allowed_hosts):
        raise HTTPException(status_code=403, detail="Host is not in NEXUS_BROWSER_ALLOWED_HOSTS")
    if _browser_agent is not None and _browser_agent.browser_name != request.browser:
        await _browser_agent.close()
        _browser_agent = None
    if _browser_agent is None:
        _browser_agent = BrowserAgent(headless=True, browser_name=request.browser)
    try:
        if _browser_agent.page is None:
            await _browser_agent.initialize()
        await _browser_agent.navigate(request.url)
        challenge = await _browser_agent.detect_challenge()
        title = await _browser_agent.page.title()
        body = "" if challenge["detected"] else await _browser_agent.page.locator("body").inner_text(timeout=5000)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Browser navigation unavailable: {type(exc).__name__}") from exc
    return {
        "status": "HUMAN_INTERVENTION_REQUIRED" if challenge["detected"] else "OBSERVED",
        "url": _browser_agent.page.url,
        "title": title[:300],
        "text_excerpt": body[:2000],
        "challenge": challenge,
        "proxy_configured": bool(_browser_agent.proxy_config),
        "geolocation_emulation_enabled": _browser_agent.geolocation is not None,
        "content_persisted": False,
        "actions_enabled": False,
    }


@app.post("/api/v1/browser/fill")
async def fill_browser_form(request: BrowserFormFillRequest):
    """Fill only non-sensitive fields on the already-open allowlisted page.
    This endpoint never submits forms or handles passwords, payments, CAPTCHAs,
    or anti-bot challenges; those remain manual human steps.
    """
    if _browser_agent is None or _browser_agent.page is None:
        raise HTTPException(status_code=409, detail="Navigate to an allowlisted page first")
    if not request.fields or len(request.fields) > 20:
        raise HTTPException(status_code=400, detail="Provide between 1 and 20 fields")
    try:
        results = []
        for field in request.fields:
            if not field.selector.strip() or len(field.selector) > 300 or len(field.value) > 2000:
                raise ValueError("Invalid selector or field value length")
            results.append(await _browser_agent.fill_non_sensitive_field(field.selector, field.value))
        return {"status": "FIELDS_FILLED", "fields": results, "form_submitted": False,
                "sensitive_steps": "manual_human_required"}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Form fill failed: {type(exc).__name__}") from exc


@app.on_event("shutdown")
async def close_browser_agent() -> None:
    if _browser_agent is not None:
        await _browser_agent.close()


@app.get("/api/v1/storage")
def get_storage_status():
    path = configured_database_path()
    persistent = os.path.ismount("/var/data")
    return {
        "database_path": path,
        "persistent_disk_attached": persistent,
        "durable_on_render": persistent and path.startswith("/var/data/"),
    }
