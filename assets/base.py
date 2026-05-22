"""
Asset Sleeve — Abstract Base
=============================
All asset sleeves share a common interface: given the macro state at the
start and end of a period they return the total return for that period.

Extension points
----------------
- Override ``period_return`` for any new asset class.
- Add transaction costs, liquidity haircuts, or leverage constraints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from scenarios.engine import MacroState


class AssetSleeve(ABC):
    """
    Base class for a homogeneous bucket of assets.

    Parameters
    ----------
    name : str
        Human-readable identifier used in reports and DataFrame columns.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        # Unhedged currency exposures: {currency_code: unhedged_fraction}.
        # E.g. {"USD": 0.35, "JPY": 0.05} means 35 % unhedged USD exposure
        # (after any hedging the user has already accounted for).
        # Applied by SubPortfolio via an attached FXModel; default is no exposure.
        self.fx_exposures: dict[str, float] = {}

    @abstractmethod
    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        """
        Total return earned over the period [t, t + dt].

        Parameters
        ----------
        state_t  : macro state at the beginning of the period.
        state_t1 : macro state at the end of the period.
        dt       : period length in years.

        Returns
        -------
        r : float
            Total return as a decimal (e.g. 0.05 = 5 %).
        """

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
