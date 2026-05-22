"""
Cash / Money-Market Sleeve
==========================
Return model:

    r_cash ≈ r_short × dt

The cash sleeve earns the short-term risk-free rate with no duration risk.
It is typically used as the residual / liquidity buffer inside either sub-portfolio.
"""

from __future__ import annotations

from scenarios.engine import MacroState
from assets.base import AssetSleeve


class CashSleeve(AssetSleeve):
    """Cash and money-market instruments."""

    def __init__(self, name: str = "Cash") -> None:
        super().__init__(name)

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        # Simple accrual at the starting short rate
        return state_t.short_rate * dt
