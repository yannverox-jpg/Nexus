import asyncio
import json
import os
import sys
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(__file__))

try:
    from module1_orchestrator import NexusOrchestrator
    from module2_web3_wallet import NexusWeb3WalletManager
    from module3_microservices import NexusMicroserviceBridge
except ImportError:
    from module_mocks import NexusOrchestrator, NexusWeb3WalletManager, NexusMicroserviceBridge

from auto_task_generator import NexusAutoTaskEngine
from service_marketplace import ServiceCatalogRegistry
from web3_escrow_billing import NexusWeb3EscrowBilling
from task_persistence_db import NexusDatabaseManager
from dispute_resolution import NexusDisputeResolutionEngine

app = FastAPI(title="Nexus Task Department API", version="2.0")

# Autoriser les appels CORS depuis le Front-End
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instances globales des modules
db = NexusDatabaseManager()
orchestrator = NexusOrchestrator(max_agents=10)
catalog = ServiceCatalogRegistry()
auto_engine = NexusAutoTaskEngine(orchestrator)

wallet_mgr: Optional[NexusWeb3WalletManager] = None
escrow: Optional[NexusWeb3EscrowBilling] = None
dispute_engine: Optional[NexusDisputeResolutionEngine] = None

# Modèles Pydantic pour la validation du Front-End
class SubmitGoalRequest(BaseModel):
    goal: str
    budget_usdc: float = 0.0
    provider_address: Optional[str] = "0x0000000000000000000000000000000000000000"

class RegisterServiceRequest(BaseModel):
    name: str
    endpoint: str
    cost_usdc: float
    method: str = "POST"

@app.on_event("startup")
async def startup_event():
    global wallet_mgr, escrow, dispute_engine

    # Chargement de la configuration
    try:
        config_path = os.path.join(os.path.dirname(__file__), "config_nexus.json")
        with open(config_path, "r") as f:
            config = json.load(f)
        rpc_url = config.get("web3_wallet", {}).get("evm_rpc_url", "https://rpc.ankr.com/eth")
    except Exception:
        rpc_url = "https://rpc.ankr.com/eth"

    wallet_mgr = NexusWeb3WalletManager(evm_rpc_url=rpc_url)
    escrow = NexusWeb3EscrowBilling(wallet_mgr)
    dispute_engine = NexusDisputeResolutionEngine(escrow_system=escrow, db_manager=db)

    # Lancement des agents d'écoute
    orchestrator.spawn_agent("Worker-Alpha", "API_CONTRACT")
    orchestrator.spawn_agent("Worker-Beta", "WEB3_EXECUTION")
    asyncio.create_task(orchestrator.start_dispatcher())
    print("⚡ [NEXUS API] Serveur Backend initialisé et prêt pour le Front-End.")

@app.get("/health")
def health_check():
    return {"status": "ONLINE", "department": "TASKS_AND_SERVICES", "version": "2.0"}

@app.post("/api/v1/goals/submit")
async def submit_autonomous_goal(req: SubmitGoalRequest):
    """Soumet un objectif global. Nexus le décompose en tâches et l'enfile de manière autonome."""
    ctx = {
        "budget_usdc": req.budget_usdc,
        "provider_address": req.provider_address
    }
    task_ids = await auto_engine.decompose_and_enqueue_goal(req.goal, ctx)

    for tid in task_ids:
        db.save_task(task_id=tid, task_type="AUTONOMOUS_GOAL", priority="HIGH", status="ENQUEUED", payload=ctx)

    return {
        "status": "SUCCESS",
        "goal": req.goal,
        "task_ids": task_ids,
        "count": len(task_ids)
    }

@app.get("/api/v1/tasks")
def get_all_tasks():
    """Récupère l'historique complet des tâches pour l'affichage Front-End."""
    return {"tasks": db.get_all_tasks()}

@app.get("/api/v1/marketplace/services")
def list_services():
    """Retourne la liste des micro-services disponibles dans le catalogue."""
    return {"services": catalog.services}

@app.post("/api/v1/marketplace/services")
def register_service(req: RegisterServiceRequest):
    """Permet au Front-End d'enregistrer un nouveau micro-service exécutable."""
    catalog.register_service(req.name, req.endpoint, req.cost_usdc, req.method)
    return {"status": "REGISTERED", "service_name": req.name}

@app.post("/api/v1/wallet/generate")
def generate_wallet_key():
    """Génère une nouvelle paire de clés cryptographiques à la volée."""
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
    """Flux WebSocket en temps réel pour alimenter le Dashboard du Front-End."""
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
