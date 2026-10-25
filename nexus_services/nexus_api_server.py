import asyncio
import json
import os
import sys
import time
import secrets
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from web3 import Web3

sys.path.insert(0, os.path.dirname(__file__))

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

from auto_task_generator import NexusAutoTaskEngine
from service_marketplace import ServiceCatalogRegistry
from web3_escrow_billing import NexusWeb3EscrowBilling
from task_persistence_db import NexusDatabaseManager
from dispute_resolution import NexusDisputeResolutionEngine
from nexus_autonomous_boot import NexusAutonomousBootDaemon
from ghost_meta_kernel import (
    CognitivePipeline,
    LLMTryptychController,
    HumanInTheLoopGateway,
    DynamicCapabilityRegistry
)
from multi_agent_orchestrator import coordinate_advisors
from ghost_institutional_predictive_engine import (
    TopologicalCointegrationGraph,
    MCPTryptychOrchestrator,
    CognitiveReadinessManager
)
from nexus_websocket_proxy import router as ws_proxy_router

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
    if request.url.path == "/health":
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

# Configuration Web3 (Polygon Mainnet)
RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
PRIVATE_KEY = os.getenv("NEXUS_PRIVATE_KEY", "")  # Clé privée du wallet Nexus
USDC_CONTRACT_ADDRESS = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # Native USDC Polygon

w3 = Web3(Web3.HTTPProvider(RPC_URL))

ERC20_ABI = [
    {
        "constant": False,
        "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

# Instances globales des modules & GHOST Kernel
db = NexusDatabaseManager()
from legacy_runtime_adapter import NexusOrchestrator, NexusWeb3WalletManager

orchestrator = NexusOrchestrator(max_agents=10)
catalog = ServiceCatalogRegistry()
auto_engine = NexusAutoTaskEngine(orchestrator)

ghost_capability_registry = DynamicCapabilityRegistry()
ghost_cognitive_pipeline = CognitivePipeline()
ghost_hitl_gateway = HumanInTheLoopGateway()
ghost_llm_tryptych = LLMTryptychController()

ghost_topological_graph = TopologicalCointegrationGraph()
ghost_mcp_orchestrator = MCPTryptychOrchestrator(ghost_topological_graph)
ghost_readiness_manager = CognitiveReadinessManager()

wallet_mgr: Optional[NexusWeb3WalletManager] = None
escrow: Optional[NexusWeb3EscrowBilling] = None
dispute_engine: Optional[NexusDisputeResolutionEngine] = None
boot_daemon: Optional[NexusAutonomousBootDaemon] = None

# Modèles Pydantic
class SubmitGoalRequest(BaseModel):
    goal: str
    budget_usdc: float = 0.0
    provider_address: Optional[str] = "0x0000000000000000000000000000000000000000"

class RegisterServiceRequest(BaseModel):
    name: str
    endpoint: str
    cost_usdc: float
    method: str = "POST"

class WithdrawRequest(BaseModel):
    to_address: str
    amount_usdc: float

class BrokerWithdrawRequest(BaseModel):
    to_address: str
    amount_usd: float

class HITLApprovalRequest(BaseModel):
    hitl_id: str

class AgentChatRequest(BaseModel):
    message: str

@app.on_event("startup")
async def startup_event():
    global wallet_mgr, escrow, dispute_engine, boot_daemon

    try:
        config_path = os.path.join(os.path.dirname(__file__), "config_nexus.json")
        with open(config_path, "r") as f:
            config = json.load(f)
        rpc_url = config.get("web3_wallet", {}).get("evm_rpc_url", RPC_URL)
    except Exception:
        rpc_url = RPC_URL

    wallet_mgr = NexusWeb3WalletManager(evm_rpc_url=rpc_url)
    escrow = NexusWeb3EscrowBilling(wallet_mgr)
    dispute_engine = NexusDisputeResolutionEngine(escrow_system=escrow, db_manager=db)

    orchestrator.spawn_agent("Worker-Alpha", "API_CONTRACT")
    orchestrator.spawn_agent("Worker-Beta", "TRADING_EXECUTION")
    asyncio.create_task(orchestrator.start_dispatcher())

    boot_daemon = NexusAutonomousBootDaemon(auto_engine, db)
    asyncio.create_task(boot_daemon.start_m2m_continuous_loop())

    print("👑 [NFX-GHOST v2.5] Serveur Backend initialisé et prêt sur Nexus.")

@app.get("/health")
def health_check():
    mt5_status = mt5.initialize() if mt5 else False
    return {
        "status": "online",
        "department": "NFX_GHOST_v2.5_SENTINEL",
        "version": "3.5",
        "broker_connected": mt5_status,
        "connected": w3.is_connected()
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
    """Appelle un fournisseur réel configuré ; aucune réponse simulée n'est renvoyée."""
    provider_aliases = {"GPT": "codex_gpt", "GEMINI": "gemini", "CLAUDE": "claude"}
    provider_id = provider_aliases.get(agent_name.upper())
    if provider_id is None:
        raise HTTPException(status_code=400, detail="Agent non reconnu. Choisir parmi GPT, Gemini, Claude.")
    connector = __import__("ai_connectors", fromlist=["CONNECTORS"]).CONNECTORS[provider_id]
    try:
        result = await asyncio.to_thread(
            connector.complete,
            req.message,
            system="Nexus advisory only. Do not claim to execute external actions.",
            google_search=(provider_id == "gemini"),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail={
            "status": "PROVIDER_UNAVAILABLE",
            "provider": provider_id,
            "error_type": type(exc).__name__,
        }) from exc
    return {"agent": provider_id, "response": result["text"], "data": result}


@app.post("/api/v1/ghost/orchestrate")
async def orchestrate_ai_advisors(req: AgentChatRequest):
    """Demande une revue parallèle aux trois fournisseurs et persiste le résultat."""
    readiness = ghost_readiness_manager.calculate_readiness_maturity()
    result = await coordinate_advisors(
        req.message,
        domain="ghost",
        db_manager=db,
        readiness_pct=float(readiness.get("m_global_pct", 0.0)),
    )
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

# --- ENDPOINTS BROKER & TRADING ---

@app.get("/api/v1/broker/account")
def get_broker_account():
    if mt5 and mt5.initialize():
        info = mt5.account_info()
        if info:
            return {
                "balance": info.balance,
                "equity": info.equity,
                "margin": info.margin_free,
                "currency": info.currency,
                "login": info.login
            }
    raise HTTPException(
        status_code=503,
        detail="MetaTrader 5 is not connected; Nexus will not fabricate account balances.",
    )

@app.get("/api/v1/broker/positions")
def get_broker_positions():
    if mt5 and mt5.initialize():
        positions = mt5.positions_get(group="*")
        if positions:
            pos_list = []
            for pos in positions:
                tick = mt5.symbol_info_tick(pos.symbol)
                curr_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
                multiplier = 100.0 if "JPY" in pos.symbol or "XAU" in pos.symbol else 10000.0
                direction_factor = 1 if pos.type == mt5.POSITION_TYPE_BUY else -1
                profit_pips = (curr_price - pos.price_open) * direction_factor * multiplier
                pos_list.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                    "volume": pos.volume,
                    "price_open": pos.price_open,
                    "current_price": curr_price,
                    "profit_pips": profit_pips
                })
            return {"positions": pos_list}
    return {"positions": []}

@app.get("/api/v1/broker/history")
def get_arbitrage_history():
    return {"arbitrages": db.get_all_tasks()}

@app.post("/api/v1/broker/withdraw")
def request_broker_withdrawal(req: BrokerWithdrawRequest):
    if req.amount_usd <= 0:
        raise HTTPException(status_code=400, detail="Montant invalide.")

    tx_id = f"withdraw_{int(time.time())}"
    db.save_escrow(tx_id, "NEXUS_VAULT", req.to_address, req.amount_usd, "WITHDRAWAL_REQUESTED")
    return {
        "status": "REQUESTED",
        "request_id": tx_id,
        "amount_usd": req.amount_usd,
        "destination": req.to_address
    }

@app.post("/api/v1/treasury/withdraw")
async def withdraw_usdc(request: WithdrawRequest):
    # Disabled until a separate treasury service has scoped authorization,
    # transaction limits, replay protection, human approval, and audit proof.
    # Merely setting a private key must never activate money movement.
    raise HTTPException(
        status_code=410,
        detail="Treasury withdrawals are disabled pending a separately secured approval workflow.",
    )

@app.post("/api/v1/goals/submit")
async def submit_autonomous_goal(req: SubmitGoalRequest):
    ctx = {"budget_usdc": req.budget_usdc, "provider_address": req.provider_address}
    task_ids = await auto_engine.decompose_and_enqueue_goal(req.goal, ctx)
    for tid in task_ids:
        db.save_task(task_id=tid, task_type="AUTONOMOUS_GOAL", priority="HIGH", status="ENQUEUED", payload=ctx)
    return {"status": "SUCCESS", "goal": req.goal, "task_ids": task_ids, "count": len(task_ids)}

@app.get("/api/v1/tasks")
def get_all_tasks():
    return {"tasks": db.get_all_tasks()}

@app.get("/api/v1/marketplace/services")
def list_services():
    return {"services": catalog.services}

@app.post("/api/v1/marketplace/services")
def register_service(req: RegisterServiceRequest):
    catalog.register_service(req.name, req.endpoint, req.cost_usdc, req.method)
    return {"status": "REGISTERED", "service_name": req.name}

@app.post("/api/v1/wallet/generate")
def generate_wallet_key():
    if not wallet_mgr:
        raise HTTPException(status_code=500, detail="Wallet manager non initialisé.")
    keypair = wallet_mgr.generate_encrypted_keypair()
    return {
        "status": "CREATED",
        "address": keypair["address"],
        "encrypted_private_key": keypair["encrypted_private_key"]
    }

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
            tasks = db.get_all_tasks()
            data = {
                "timestamp": asyncio.get_event_loop().time(),
                "active_agents": len(orchestrator.agents),
                "tasks_summary": tasks[:10]
            }
            await websocket.send_json(data)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        print("🔌 [WEBSOCKET] Front-End déconnecté du monitoring.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
