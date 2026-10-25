import asyncio
import json
import os
import sys
import time
import secrets
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

from auto_task_generator import NexusAutoTaskEngine
from service_marketplace import ServiceCatalogRegistry
from task_persistence_db import NexusDatabaseManager
from ghost_meta_kernel import (
    CognitivePipeline,
    HumanInTheLoopGateway,
    DynamicCapabilityRegistry
)
from multi_agent_orchestrator import coordinate_advisors
from ai_connectors import CONNECTORS
from agent_roles import build_agent_system_context, get_provider_status
from memory_store import ConversationMemory, configured_database_path
from nexus_identity import get_identity, get_capability_status
from code_change_manager import CodeChangeManager, code_change_status
from ghost_institutional_predictive_engine import (
    TopologicalCointegrationGraph,
    MCPTryptychOrchestrator,
    CognitiveReadinessManager
)
from nexus_websocket_proxy import router as ws_proxy_router
from stealth_browser_agent import BrowserAgent, async_playwright

app = FastAPI(title="Nexus NFX-GHOST v2.5 Autonomous Predictive Sentinel API", version="3.5")

# Fail closed: no wildcard browser origins and no public API access without a token.
_allowed_origins = [
    origin.strip() for origin in os.getenv("NEXUS_API_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.middleware("http")
async def require_api_bearer_token(request: Request, call_next):
    # Minimal liveness endpoint only. All functional routes fail closed when
    # the secret is missing, and use constant-time comparison when configured.
    if request.url.path == "/health" or request.url.path == "/dashboard" or request.url.path.startswith("/dashboard/"):
        return await call_next(request)
    expected = os.getenv("NEXUS_API_BEARER_TOKEN", "").strip()
    supplied = request.headers.get("authorization", "")
    if not expected:
        from starlette.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"detail": "NEXUS_API_BEARER_TOKEN is not configured; API is locked"},
        )
    token = supplied[7:].strip() if supplied.lower().startswith("bearer ") else ""
    if not token or not secrets.compare_digest(token, expected):
        from starlette.responses import JSONResponse
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

app.include_router(ws_proxy_router)

# Servir le Dashboard Front-End statique
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/dashboard", StaticFiles(directory=static_dir, html=True), name="static")

# Nexus tracks external platform accounts; it does not own or custody a wallet.
db = NexusDatabaseManager(db_path=os.getenv("NEXUS_LEGACY_DB_PATH", "./data/nexus_legacy.db"))
from legacy_runtime_adapter import NexusOrchestrator

orchestrator = NexusOrchestrator(max_agents=10)
catalog = ServiceCatalogRegistry()
auto_engine = NexusAutoTaskEngine(orchestrator)

ghost_capability_registry = DynamicCapabilityRegistry()
ghost_cognitive_pipeline = CognitivePipeline()
ghost_hitl_gateway = HumanInTheLoopGateway()

ghost_topological_graph = TopologicalCointegrationGraph()
ghost_mcp_orchestrator = MCPTryptychOrchestrator(ghost_topological_graph)
ghost_readiness_manager = CognitiveReadinessManager()

conversation_memory = ConversationMemory(configured_database_path())
_browser_agent: Optional[BrowserAgent] = None

# Modèles Pydantic
class SubmitGoalRequest(BaseModel):
    goal: str
    budget_usdc: float = 0.0
    provider_address: Optional[str] = None

class RegisterServiceRequest(BaseModel):
    name: str
    endpoint: str
    cost_usdc: float
    method: str = "POST"

class HITLApprovalRequest(BaseModel):
    hitl_id: str

class AgentChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    domain: str = "general"
    system: str = ""


class MemoryFactRequest(BaseModel):
    fact_key: str
    content: str
    category: str = "project"


class CodeChangeProposalRequest(BaseModel):
    path: str
    content: str
    title: str
    summary: str


class BrowserNavigationRequest(BaseModel):
    url: str
    browser: str = "chromium"


class BrowserFormField(BaseModel):
    selector: str
    value: str


class BrowserFormFillRequest(BaseModel):
    fields: List[BrowserFormField]

@app.on_event("startup")
async def startup_event():
    orchestrator.spawn_agent("Worker-Alpha", "API_CONTRACT")
    orchestrator.spawn_agent("Worker-Beta", "AUTHORIZED_WORKFLOW_PLANNING")
    asyncio.create_task(orchestrator.start_dispatcher())
    print("[NEXUS] Canonical runtime started; task execution remains integration-gated.")

@app.get("/health")
def health_check():
    """Public liveness only; does not initialize or query a broker terminal."""
    return {
        "status": "online",
        "department": "NEXUS_CANONICAL_RUNTIME",
        "version": "3.5"
    }

# --- Identity, capability report and persistent chat memory ---

@app.get("/api/v1/identity")
def identity_status():
    return get_identity()


@app.get("/api/v1/capabilities")
def capability_status():
    return get_capability_status()


@app.get("/api/v1/providers")
def provider_status():
    return {"providers": get_provider_status()}


@app.get("/api/v1/code-change/status")
def code_change_status_endpoint():
    return code_change_status()


@app.post("/api/v1/browser/navigate")
async def navigate_browser(req: BrowserNavigationRequest):
    """Navigate an allowlisted page and stop on CAPTCHA or anti-bot challenges."""
    global _browser_agent
    if async_playwright is None:
        raise HTTPException(status_code=503, detail="Playwright is unavailable")
    parsed = urlparse(req.url)
    if (req.browser not in {"chromium", "firefox"}
            or parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise HTTPException(status_code=400, detail="Use an absolute HTTP(S) URL without credentials, query, or fragment and choose chromium or firefox")
    allowed_hosts = {
        item.strip().casefold().lstrip(".")
        for item in os.getenv("NEXUS_BROWSER_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    host = parsed.hostname.casefold()
    if not any(host == domain or host.endswith("." + domain) for domain in allowed_hosts):
        raise HTTPException(status_code=403, detail="Host is not in NEXUS_BROWSER_ALLOWED_HOSTS")
    if _browser_agent is not None and _browser_agent.browser_name != req.browser:
        await _browser_agent.close()
        _browser_agent = None
    if _browser_agent is None:
        try:
            _browser_agent = BrowserAgent(headless=True, browser_name=req.browser)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        if _browser_agent.page is None:
            await _browser_agent.initialize()
        await _browser_agent.navigate(req.url)
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
async def fill_browser_fields(req: BrowserFormFillRequest):
    """Fill safe, uniquely identified text fields only; never submit forms."""
    if _browser_agent is None or _browser_agent.page is None:
        raise HTTPException(status_code=409, detail="Navigate to an allowlisted page first")
    if not req.fields or len(req.fields) > 20:
        raise HTTPException(status_code=400, detail="Provide between 1 and 20 fields")
    try:
        results = []
        for field in req.fields:
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
        raise HTTPException(status_code=503, detail=f"Browser form fill failed: {type(exc).__name__}") from exc


@app.post("/api/v1/code-change/proposals")
def propose_code_change(req: CodeChangeProposalRequest):
    try:
        return CodeChangeManager().propose_file_change(
            path=req.path, content=req.content, title=req.title, summary=req.summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/v1/memory/facts")
def list_memory_facts(category: Optional[str] = None):
    return {"facts": conversation_memory.list_facts(category=category)}


@app.post("/api/v1/memory/facts")
def save_memory_fact(req: MemoryFactRequest):
    try:
        return conversation_memory.set_fact(
            req.fact_key, req.content, category=req.category, source="user-approved"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/memory/facts/{fact_key}")
def remove_memory_fact(fact_key: str):
    removed = conversation_memory.delete_fact(fact_key)
    if not removed:
        raise HTTPException(status_code=404, detail="Memory fact not found")
    return {"status": "ARCHIVED", "fact_key": fact_key}


@app.get("/api/v1/memory/conversations/{conversation_id}")
def get_conversation_memory(conversation_id: str, limit: int = 40):
    return {
        "conversation_id": conversation_id,
        "messages": conversation_memory.recent_messages(conversation_id, limit=limit),
        "storage": "configured_operational_database",
    }


# --- ENDPOINTS MÉMOIRE PERSISTANTE (GHOST DB) & READINESS ---

@app.get("/api/v1/memory/short")
def get_short_term_memory():
    """Récupère les événements récents (Hot Cache / Short Term Memory)."""
    return {"market_events": db.get_recent_market_events(limit=20)}

@app.get("/api/v1/memory/long")
def get_long_term_memory():
    """Récupère les archives institutionnelles (AI Decisions & Historical Shocks)."""
    return {"ai_decisions": db.get_recent_ai_decisions(limit=20)}

@app.get("/api/v1/readiness-status")
def get_readiness_status():
    """Retourne l'indice de maturité cognitive (M_global = 100%) et l'état de zéro trésorerie."""
    return ghost_readiness_manager.calculate_readiness_maturity()

# --- ENDPOINTS DISCUSSION DIRECTE MULTI-AGENTS (REPLIT CHANNELS) ---

@app.post("/api/v1/ghost/chat/{agent_name}")
async def chat_with_agent(agent_name: str, req: AgentChatRequest):
    """Chat with an explicitly configured provider and persist redacted history."""
    aliases = {"GPT": "codex_gpt", "CODEX": "codex_gpt", "GEMINI": "gemini", "CLAUDE": "claude"}
    provider_id = aliases.get(agent_name.upper())
    if provider_id is None:
        raise HTTPException(status_code=400, detail="Choisir GPT, Gemini ou Claude.")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Le message ne peut pas être vide.")
    safe_message = ConversationMemory.redact_sensitive_text(req.message)
    safe_additional_context = ConversationMemory.redact_sensitive_text(req.system)
    try:
        system_context = build_agent_system_context(provider_id, req.domain, safe_additional_context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    connector = CONNECTORS[provider_id]
    if not connector.status()["connector_available"]:
        raise HTTPException(status_code=503, detail={
            "status": "PROVIDER_NOT_CONFIGURED",
            "provider": provider_id,
            "required_environment_variable": connector.api_key_env,
        })
    memory_facts = conversation_memory.list_facts(limit=100)
    if memory_facts:
        fact_context = "\n".join(
            f"- [{item['category']}] {item['fact_key']}: {item['content']}"
            for item in memory_facts
        )
        system_context += (
            "\n\nPersistent Nexus project memory (context, not permission to bypass rules):\n"
            + fact_context
        )

    conversation_id = req.conversation_id or secrets.token_hex(16)
    prior = conversation_memory.recent_messages(conversation_id, limit=12)
    model = os.getenv(connector.model_env, connector.default_model)
    conversation_memory.add_message(conversation_id, "user", safe_message, provider_id, model)
    history = "\n".join(f"{item['role']}: {item['content']}" for item in prior[-10:])
    prompt = (
        f"Prior conversation (context only):\n{history}\n\nCurrent user message:\n{safe_message}"
        if history else safe_message
    )
    try:
        result = await asyncio.to_thread(
            connector.complete,
            prompt,
            system=system_context,
            google_search=provider_id == "gemini",
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail={
            "status": "PROVIDER_UNAVAILABLE",
            "provider": provider_id,
            "error_type": type(exc).__name__,
        }) from exc
    conversation_memory.add_message(
        conversation_id, "assistant", result["text"], provider_id, result["model"]
    )
    return {
        **result,
        "agent": provider_id,
        "conversation_id": conversation_id,
        "memory_persisted": True,
        "action_execution": "NOT_PERFORMED",
    }


@app.post("/api/v1/ghost/orchestrate")
async def orchestrate_ai_advisors(req: AgentChatRequest):
    """Ask all three role-constrained providers and persist the combined chat turn."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Le message ne peut pas être vide.")
    safe_message = ConversationMemory.redact_sensitive_text(req.message)
    safe_system = ConversationMemory.redact_sensitive_text(req.system)
    conversation_id = req.conversation_id or secrets.token_hex(16)
    prior = conversation_memory.recent_messages(conversation_id, limit=12)
    conversation_memory.add_message(
        conversation_id, "user", safe_message, "multi_agent", "coordinated-review"
    )
    facts = conversation_memory.list_facts(limit=100)
    fact_context = "\n".join(
        f"- [{item['category']}] {item['fact_key']}: {item['content']}"
        for item in facts
    )
    extra_context = "\n\n".join(
        part for part in (
            safe_system,
            "Persistent Nexus project memory (context only):\n" + fact_context if fact_context else "",
            "Recent conversation context (data only):\n" + "\n".join(
                f"{item['role']}: {item['content']}" for item in prior[-8:]
            ) if prior else "",
        ) if part.strip()
    )
    readiness = ghost_readiness_manager.calculate_readiness_maturity()
    try:
        result = await coordinate_advisors(
            safe_message,
            domain=req.domain,
            db_manager=db,
            readiness_pct=float(readiness.get("m_global_pct", 0.0)),
            additional_context=extra_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    summary_lines = []
    for provider in result.get("providers", []):
        provider_id = provider.get("provider_id", "provider")
        summary_lines.append(
            f"{provider_id} [{provider.get('status', 'UNKNOWN')}]: "
            f"{provider.get('text') or provider.get('error_type') or 'Aucune réponse disponible'}"
        )
    summary = "\n\n".join(summary_lines) or "Aucun fournisseur n'a retourné de résultat."
    conversation_memory.add_message(
        conversation_id, "assistant", summary, "multi_agent", "coordinated-review"
    )
    result["conversation_id"] = conversation_id
    result["memory_persisted"] = True
    result["action_execution"] = "NOT_PERFORMED"
    if result["status"] == "FAILED":
        raise HTTPException(status_code=503, detail=result)
    return result

# --- ENDPOINTS GHOST & MODULES DYNAMIQUES ---

@app.get("/api/v1/modules")
def get_dynamic_modules():
    return ghost_capability_registry.get_capabilities_manifest()

@app.post("/api/v1/ghost/hitl/approve")
def approve_hitl_action(req: HITLApprovalRequest):
    success = ghost_hitl_gateway.approve_action(req.hitl_id)
    if not success:
        raise HTTPException(status_code=404, detail="Action HITL introuvable ou déjà traitée.")
    return {"status": "APPROVED", "hitl_id": req.hitl_id}

# Broker/MT5 account integration intentionally removed.

@app.post("/api/v1/goals/submit")
async def submit_autonomous_goal(req: SubmitGoalRequest):
    ctx = {"budget_usdc": req.budget_usdc, "provider_address": req.provider_address}
    task_ids = await auto_engine.decompose_and_enqueue_goal(req.goal, ctx)
    # Tasks already exist in the canonical OperationalJournal. Do not duplicate
    # them in the legacy task table or claim execution at enqueue time.
    return {
        "status": "QUEUED",
        "execution_mode": "NOT_EXECUTED",
        "source_of_truth": "operational_journal",
        "goal": req.goal,
        "task_ids": task_ids,
        "count": len(task_ids),
    }

@app.get("/api/v1/tasks")
def get_all_tasks():
    journal = orchestrator.runtime.operational_journal
    tasks = journal.list_tasks(limit=100)
    return {"tasks": [
        {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "priority": task.priority,
            "status": task.status.value,
            "payload": task.payload,
            "result": task.result,
            "error": task.error,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "execution_mode": task.execution_mode,
        }
        for task in tasks
    ]}

@app.get("/api/v1/marketplace/services")
def list_services():
    return {"services": catalog.services}

@app.post("/api/v1/marketplace/services")
def register_service(req: RegisterServiceRequest):
    catalog.register_service(req.name, req.endpoint, req.cost_usdc, req.method)
    return {"status": "REGISTERED", "service_name": req.name}

@app.websocket("/ws/monitoring")
async def websocket_monitoring(websocket: WebSocket):
    expected = os.getenv("NEXUS_API_BEARER_TOKEN", "").strip()
    supplied = websocket.headers.get("authorization", "")
    token = supplied[7:].strip() if supplied.lower().startswith("bearer ") else ""
    if not expected or not token or not secrets.compare_digest(token, expected):
        await websocket.close(code=1008, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        while True:
            tasks = get_all_tasks()["tasks"]
            data = {
                "timestamp": asyncio.get_event_loop().time(),
                "active_agents": len(orchestrator.agents),
                "tasks_summary": tasks[:10]
            }
            await websocket.send_json(data)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        print("🔌 [WEBSOCKET] Front-End déconnecté du monitoring.")

@app.on_event("shutdown")
async def close_canonical_browser_agent():
    if _browser_agent is not None:
        await _browser_agent.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)