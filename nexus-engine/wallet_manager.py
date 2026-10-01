import logging
from typing import Dict, Any, Optional
from solders.keypair import Keypair
from solana.rpc.api import Client
from config import Config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - [NEXUS-WALLET] - %(message)s")

class NexusWalletManager:
    """Gestionnaire de trésorerie autonome pour Nexus (Solana / USDC)."""

    def __init__(self):
        self.rpc_client = Client(Config.SOLANA_RPC_URL)

        # Chargement ou génération de la clé maître
        if hasattr(Config, "NEXUS_PRIVATE_KEY") and Config.NEXUS_PRIVATE_KEY:
            secret_bytes = bytes.fromhex(Config.NEXUS_PRIVATE_KEY)
            self._keypair = Keypair.from_bytes(secret_bytes)
            logging.info("Clé maître Nexus chargée depuis les variables d'environnement.")
        else:
            self._keypair = Keypair()
            logging.warning("Nouvelle paire de clés générée pour Nexus.")

        self.public_key = str(self._keypair.pubkey())
        logging.info(f"Adresse publique active de Nexus : {self.public_key}")

    def get_public_address(self) -> str:
        """Renvoie l'adresse d'encaissement active."""
        return self.public_key

    def get_sol_balance(self) -> float:
        """Vérifie le solde de la réserve réseau (SOL) pour les frais de Gas."""
        try:
            response = self.rpc_client.get_balance(self._keypair.pubkey())
            return response.value / 1_000_000_000
        except Exception as e:
            logging.error(f"Erreur lors de la vérification du solde SOL : {e}")
            return 0.0

wallet_manager = NexusWalletManager()

def get_wallet_info() -> Dict[str, Any]:
    """Outil MCP exposant les informations du portefeuille Web3 de Nexus."""
    return {
        "public_address": wallet_manager.get_public_address(),
        "sol_balance": wallet_manager.get_sol_balance()
    }
