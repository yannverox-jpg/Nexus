"""Disabled legacy stablecoin liquidation path.

Nexus has no proprietary wallet or treasury. External platform balances are
tracked as snapshots and payouts are handled by the platform to the prepaid Visa.
"""
from typing import Any, Dict


class NexusStablecoinLiquidationEngine:
    def __init__(self, *_args: Any, **_kwargs: Any):
        pass

    async def execute_automated_swap(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        raise PermissionError(
            "Stablecoin swaps are disabled: Nexus does not custody or trade wallet assets."
        )

    def stage_funds_for_human_withdrawal(self, *_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        raise PermissionError(
            "Nexus has no treasury or vault. Request payouts through the external platform to the prepaid Visa."
        )
