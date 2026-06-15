"""
allocations — the article's country-mosaic equity proposal, expressed in the
simple_alm vocabulary.

This package is the in-repo home of what the article actually proposes: a
bottom-up, country-level equity sleeve (China explicitly capped) rather than a
single cap-weighted "Asia" bloc. It was previously kept in the article working
bundle and reached into simple_alm via a hard-coded sys.path; it now lives in
the model itself and imports the model packages normally.

Public API (lazily loaded — see __getattr__):
    COUNTRY_INPUTS, ASIA, LONG_RUN_EPS_GROWTH, proxy_markets   inputs
    build_equity_specs(weights, ...)                           -> list[SleeveSpec]
    asia_weight(weights)
    CURRENT_EQUITY / PROPOSED_EQUITY /                         the four locked
    PROPOSED_CONSERVATIVE / PROPOSED_TIGHT_CHINA               allocations

Exports are loaded lazily so that `python -m allocations.mosaic` does not trigger
a double-import RuntimeWarning, while `from allocations import build_equity_specs`
keeps working.
"""
import importlib

__all__ = [
    "COUNTRY_INPUTS", "ASIA", "LONG_RUN_EPS_GROWTH", "proxy_markets",
    "build_equity_specs", "asia_weight",
    "CURRENT_EQUITY", "PROPOSED_EQUITY",
    "PROPOSED_CONSERVATIVE", "PROPOSED_TIGHT_CHINA",
    # bond side
    "BOND_INPUTS", "build_overlay_specs", "DEVELOPED", "EM", "MANAGED",
]

# name -> submodule that defines it
_SOURCES = {
    "COUNTRY_INPUTS": "country_inputs", "ASIA": "country_inputs",
    "LONG_RUN_EPS_GROWTH": "country_inputs", "proxy_markets": "country_inputs",
    "build_equity_specs": "mosaic", "asia_weight": "mosaic",
    "CURRENT_EQUITY": "mosaic", "PROPOSED_EQUITY": "mosaic",
    "PROPOSED_CONSERVATIVE": "mosaic", "PROPOSED_TIGHT_CHINA": "mosaic",
    "BOND_INPUTS": "bond_inputs", "build_overlay_specs": "bond_inputs",
    "DEVELOPED": "bond_inputs", "EM": "bond_inputs", "MANAGED": "bond_inputs",
}


def __getattr__(name):
    mod = _SOURCES.get(name)
    if mod is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    submodule = importlib.import_module(f"{__name__}.{mod}")
    return getattr(submodule, name)


def __dir__():
    return sorted(__all__)
