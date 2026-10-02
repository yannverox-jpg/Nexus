import asyncio
import json
import os
import sys
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from web3 import Web3

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
from nexus_autonomous_boot import NexusAutonomousBootDaemon

app = FastAPI(title="Nexus Autonomous API", version="2.0")

# Autoriser les appels CORS depuis le Front-End
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration Web3 (Polygon Mainnet)
RPC_URL = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
PRIVATE_KEY = os.getenv("NEXUS_PRIVATE_KEY", "")  # Clé privée du wallet Nexus
USDC_CONTRACT_ADDRESS = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"  # Native USDC Polygon

w3 = Web3(Web3.HTTPProvider(RPC_URL))

# ABI minimal pour le transfert de tokens ERC20 / USDC
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

# Instances globales des modules
db = NexusDatabaseManager()
orchestrator = NexusOrchestrator(max_agents=10)
catalog = ServiceCatalogRegistry()
auto_engine = NexusAutoTaskEngine(orchestrator)

wallet_mgr: Optional[NexusWeb3WalletManager] = None
escrow: Optional[NexusWeb3EscrowBilling] = None
dispute_engine: Optional[NexusDisputeResolutionEngine] = None
boot_daemon: Optional[NexusAutonomousBootDaemon] = None

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

class WithdrawRequest(BaseModel):
    to_address: str  # Adresse Polygon du destinataire
    amount_usdc: float  # Montant en USDC (ex: 50.0)

@app.on_event("startup")
async def startup_event():
    global wallet_mgr, escrow, dispute_engine, boot_daemon

    # Chargement de la configuration
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

    # Lancement des agents d'écoute
    orchestrator.spawn_agent("Worker-Alpha", "API_CONTRACT")
    orchestrator.spawn_agent("Worker-Beta", "WEB3_EXECUTION")
    asyncio.create_task(orchestrator.start_dispatcher())

    # Démarrage autonome M2M / Zero-Human-Touch Boot Daemon
    boot_daemon = NexusAutonomousBootDaemon(auto_engine, db)
    asyncio.create_task(boot_daemon.start_m2m_continuous_loop())

    print("⚡ [NEXUS API] Serveur Backend initialisé et prêt pour le Front-End.")

@app.get("/health")
def health_check():
    return {
        "status": "online",
        "department": "TASKS_AND_SERVICES",
        "version": "2.0",
        "connected": w3.is_connected()
    }

@app.post("/api/v1/treasury/withdraw")
async def withdraw_usdc(request: WithdrawRequest):
    if not PRIVATE_KEY:
        raise HTTPException(status_code=500, detail="Clé privée NEXUS_PRIVATE_KEY manquante dans l'environnement")

    if not w3.is_address(request.to_address):
        raise HTTPException(status_code=400, detail="Adresse destination invalide")

    try:
        account = w3.eth.account.from_key(PRIVATE_KEY)
        contract = w3.eth.contract(address=Web3.to_checksum_address(USDC_CONTRACT_ADDRESS), abi=ERC20_ABI)

        # USDC a 6 décimales
        amount_in_units = int(request.amount_usdc * 10**6)

        # Construction de la transaction
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.transfer(
            Web3.to_checksum_address(request.to_address),
            amount_in_units
        ).build_transaction({
            'chainId': 137,  # Polygon Mainnet
            'gas': 100000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
        })

        # Signature et envoi sur la vraie blockchain
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        return {
            "status": "success",
            "tx_hash": w3.to_hex(tx_hash),
            "amount_usdc": request.amount_usdc,
            "recipient": request.to_address,
            "network": "Polygon"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
