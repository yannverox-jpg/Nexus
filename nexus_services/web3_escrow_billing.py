"""Disabled legacy escrow adapter.

Nexus does not custody funds or create blockchain escrow wallets. Payments stay
on the external platform and any payout must be confirmed by that provider.
"""
from typing import Any, Dict


class NexusWeb3EscrowBilling:
    def __init__(self, *_args: Any, **_kwargs: Any):
        self.active_escrows: Dict[str, Dict[str, Any]] = {}

    def create_escrow_lock(
        self, escrow_id: str, client_address: str, provider_address: str, amount_usdc: float
    ) -> Dict[str, Any]:
        raise PermissionError(
            "Nexus does not hold funds or lock blockchain escrow; use the external platform's payment flow."
        )

    async def release_escrow_payment(
        self, escrow_id: str, token_contract_address: str,
        encrypted_private_key: str, proof_of_delivery: Dict[str, Any]
    ) -> Dict[str, Any]:
        raise PermissionError(
            "Nexus does not custody funds or release wallet payments; reconcile the external provider's payout."
        )
