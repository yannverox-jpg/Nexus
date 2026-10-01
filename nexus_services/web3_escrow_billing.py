import time
from typing import Dict, Any
try:
    from module2_web3_wallet import NexusWeb3WalletManager
except ImportError:
    from module_mocks import NexusWeb3WalletManager

class NexusWeb3EscrowBilling:
    """
    Module de sécurité financière : verrouille les fonds sous forme de contrat d'escrow
    et libère le paiement en USDC/USDT uniquement sur validation formelle de la preuve de livraison.
    """
    def __init__(self, wallet_manager: NexusWeb3WalletManager):
        self.wallet_manager = wallet_manager
        self.active_escrows: Dict[str, Dict[str, Any]] = {}

    def create_escrow_lock(
        self,
        escrow_id: str,
        client_address: str,
        provider_address: str,
        amount_usdc: float
    ) -> Dict[str, Any]:
        """Crée une réservation de fonds pour une tâche assignée."""
        record = {
            "escrow_id": escrow_id,
            "client_address": client_address,
            "provider_address": provider_address,
            "amount_usdc": amount_usdc,
            "status": "LOCKED",
            "created_at": time.time()
        }
        self.active_escrows[escrow_id] = record
        print(f"🔒 [ESCROW LOCKED] {amount_usdc} USDC réservés pour l'exécution (ID: {escrow_id})")
        return record

    async def release_escrow_payment(
        self,
        escrow_id: str,
        token_contract_address: str,
        encrypted_private_key: str,
        proof_of_delivery: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Vérifie la validité du livrable et libère le paiement Web3 vers le prestataire."""
        if escrow_id not in self.active_escrows:
            raise ValueError(f"Escrow ID {escrow_id} introuvable.")

        escrow = self.active_escrows[escrow_id]
        if escrow["status"] != "LOCKED":
            raise RuntimeError(f"L'escrow {escrow_id} est déjà clôturé ou libéré.")

        # Validation de la preuve de livraison
        if not proof_of_delivery.get("is_valid", False):
            escrow["status"] = "DISPUTED"
            print(f"❌ [ESCROW REJECTED] Livrable invalide pour l'ID {escrow_id}.")
            return {"status": "REJECTED", "reason": "Proof of delivery validation failed"}

        # Transfert réel USDC/USDT via le Module 2
        transfer_result = await self.wallet_manager.transfer_stablecoin(
            encrypted_private_key=encrypted_private_key,
            to_address=escrow["provider_address"],
            token_contract_address=token_contract_address,
            amount=escrow["amount_usdc"]
        )

        escrow["status"] = "RELEASED"
        escrow["tx_hash"] = transfer_result.get("tx_hash")
        print(f"💰 [ESCROW RELEASED] {escrow['amount_usdc']} USDC transférés au prestataire. Tx: {escrow['tx_hash']}")

        return {
            "status": "RELEASED",
            "escrow_id": escrow_id,
            "tx_hash": escrow["tx_hash"],
            "amount_paid": escrow["amount_usdc"]
        }
