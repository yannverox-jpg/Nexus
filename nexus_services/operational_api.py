"""Loopback-only operational status API for the Streamlit service."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .agent_roles import build_agent_system_context, get_provider_status, get_role_assignments
from .ai_connectors import CONNECTORS
from .connection_manager import ConnectionManager
from .platform_catalog import get_platform_catalog
from .stealth_browser_agent import BrowserAgent, async_playwright
from .operational_dashboard import dashboard_overview, mission_detail, task_detail
from .memory_store import configured_database_path
from .payout_ledger import PayoutLedger
from .runtime_contracts import OperationalJournal

database_path = configured_database_path()
journal = OperationalJournal(database_path)
payout_ledger = PayoutLedger(database_path)
connection_manager = ConnectionManager(database_path)
_browser_agent: BrowserAgent | None = None


class BrowserNavigationRequest(BaseModel):
    url: str
    browser: str = "chromium"


class AdvisoryChatRequest(BaseModel):
    message: str
    system: str = ""
    domain: str = "general"


class StrictRequest(BaseModel):
    class Config:
        extra = "forbid"


class PayoutDestinationRequest(StrictRequest):
    provider: str
    destination_type: str
    label: str
    currency: str
    last4: str | None = None


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
    """Ask a configured provider for advice; never dispatches an external action."""
    provider_id = {"gpt": "codex_gpt", "codex": "codex_gpt", "gemini": "gemini", "claude": "claude"}.get(agent_name.casefold())
    if provider_id is None:
        raise HTTPException(status_code=400, detail="Agent non reconnu")
    if not CONNECTORS[provider_id].status()["connector_available"]:
        raise HTTPException(status_code=503, detail=f"{provider_id} provider is not configured")
    try:
        system_context = build_agent_system_context(provider_id, request.domain, request.system)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        return CONNECTORS[provider_id].complete(request.message, system=system_context)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
        title = await _browser_agent.page.title()
        body = await _browser_agent.page.locator("body").inner_text(timeout=5000)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Browser navigation unavailable: {type(exc).__name__}") from exc
    return {
        "status": "OBSERVED",
        "url": _browser_agent.page.url,
        "title": title[:300],
        "text_excerpt": body[:2000],
        "content_persisted": False,
        "actions_enabled": False,
    }


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
