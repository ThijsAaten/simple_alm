"""
Inflation-Linked Bond (Linker) Sleeve
======================================
Return model (Diebold-Li real yield at bond maturity):

    r_linker ≈ r_real(τ)·dt  −  D_real·Δr_real(τ)  +  ½·C_real·(Δr_real(τ))²  +  π·dt

where
    r_real(τ) = Nelson-Siegel real spot rate at the linker's average maturity τ
    D_real    = real modified duration (years)
    C_real    = real convexity ≈ D_real²
    Δr_real(τ) = r_real_t1(τ) − r_real_t(τ)  — real yield change at maturity τ
    π         = realised inflation for the period (state_t.inflation)

Using the full Diebold-Li real curve rather than the long-end ``real_rate``
state variable alone means that curvature moves (changes in curve shape) are
priced correctly.  This is most material for short-to-medium maturity linkers
where the Nelson-Siegel curvature loading is largest.

Extension points
----------------
- Separate curvature into independent real and nominal curvature factors.
- Add an inflation lag correction (linkers typically reference CPI with a lag).
- Model breakeven inflation explicitly as a separate VAR state variable.
"""

from __future__ import annotations

from scenarios.engine import MacroState, YieldCurve
from assets.base import AssetSleeve


class LinkerSleeve(AssetSleeve):
    """
    Inflation-linked government bond sleeve.

    The real yield for carry and repricing is read from the full Diebold-Li
    real yield curve at the linker's ``maturity``, so steepening/flattening
    of the real curve is correctly captured in the return.

    Parameters
    ----------
    real_duration  : float
        Modified real duration (years).  Typical long linker: 15–25 yr.
    maturity       : float or None
        Average maturity (years) used to look up the real yield on the curve.
        If ``None``, ``real_duration`` is used as a proxy.
    real_convexity : float or None
        Real convexity (yr²).  If ``None`` the par-bond approximation D² is used.
    lambda_        : float
        Nelson-Siegel shape parameter — must match the value used in
        ``LiabilityModel``.  Default 5.0 yr.
    """

    def __init__(
        self,
        name:           str              = "Linker",
        real_duration:  float            = 18.0,
        maturity:       float | None     = None,
        real_convexity: float | None     = None,
        lambda_:        float            = 5.0,
    ) -> None:
        super().__init__(name)
        self.real_duration   = real_duration
        self.maturity        = maturity if maturity is not None else real_duration
        self._real_convexity = real_convexity
        self.lambda_         = lambda_

    @property
    def real_convexity(self) -> float:
        return self._real_convexity if self._real_convexity is not None else self.real_duration ** 2

    def period_return(
        self,
        state_t:  MacroState,
        state_t1: MacroState,
        dt: float = 1.0,
    ) -> float:
        # Read real yield at this linker's maturity from the full Diebold-Li curve
        r0 = YieldCurve(state_t,  self.lambda_).real_rate(self.maturity)
        r1 = YieldCurve(state_t1, self.lambda_).real_rate(self.maturity)
        dr = r1 - r0

        real_carry        = r0 * dt
        inflation_accrual = state_t.inflation * dt
        price_chg         = -self.real_duration * dr + 0.5 * self.real_convexity * dr ** 2

        return real_carry + inflation_accrual + price_chg
