import time
from typing import Dict, Any, Optional
from web3_escrow_billing import NexusWeb3EscrowBilling
from task_persistence_db import NexusDatabaseManager

class NexusDisputeResolutionEngine:
    """
    Gestionnaire automatique de litiges et de politique de Retry/Refund.
    Rembourse le wallet client si le timeout expire ou si la qualité du livrable est insuffisante.
    """
    def __init__(self, escrow_system: NexusWeb3EscrowBilling, db_manager: NexusDatabaseManager, max_retries: int = 2):
        self.escrow_system = escrow_system
        self.db = db_manager
        self.max_retries = max_retries
        self.retry_counters: Dict[str, int] = {}

    def evaluate_and_handle_failure(
        self,
        escrow_id: str,
        reason: str,
        task_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Évalue s'il faut relancer la tâche (retry) ou arbitrer un litige en remboursant l'escrow.
        """
        current_retries = self.retry_counters.get(escrow_id, 0)

        if current_retries < self.max_retries:
            self.retry_counters[escrow_id] = current_retries + 1
            print(f"🔄 [AUTO-RETRY] Tentative {current_retries + 1}/{self.max_retries} pour Escrow ID: {escrow_id}. Raison: {reason}")
            return {
                "action": "RETRY",
                "attempt": current_retries + 1,
                "escrow_id": escrow_id
            }
        else:
            # Échec définitif -> Remboursement automatique de l'escrow
            refund_res = self._execute_refund(escrow_id, reason)
            return {
                "action": "REFUNDED",
                "reason": reason,
                "refund_details": refund_res
            }

    def _execute_refund(self, escrow_id: str, reason: str) -> Dict[str, Any]:
        """Annule l'escrow et libère les fonds réservés vers le wallet client."""
        if escrow_id in self.escrow_system.active_escrows:
            escrow_data = self.escrow_system.active_escrows[escrow_id]
            escrow_data["status"] = "REFUNDED"
            escrow_data["refund_reason"] = reason

            # Mise à jour en base de données
            self.db.save_escrow(
                escrow_id=escrow_id,
                client=escrow_data["client_address"],
                provider=escrow_data["provider_address"],
                amount=escrow_data["amount_usdc"],
                status="REFUNDED"
            )

            print(f"🛡️ [DISPUTE ARBITRATION] Litige tranché. Escrow {escrow_id} REMBOURSÉ au client ({escrow_data['amount_usdc']} USDC). Raison: {reason}")
            return {
                "status": "REFUNDED",
                "escrow_id": escrow_id,
                "refunded_amount": escrow_data["amount_usdc"],
                "client": escrow_data["client_address"]
            }

        return {"status": "ERROR", "message": "Escrow introuvable pour remboursement."}
