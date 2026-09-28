from __future__ import annotations

"""
PhoenixTrend engine-layer compatibility bridge for the shared Risk Engine.

The authoritative risk implementation lives in:

    backend.app.services.risk

This module intentionally does not duplicate portfolio, position-sizing,
drawdown, exposure, stop-loss, concentration, account, or trade-risk logic.

Keeping one authoritative RiskEngine implementation prevents the Automation,
Manual Trade, ExecutionService, API and UI layers from evaluating different
risk rules.

Execution path:

    Decision
        ↓
    Market Safety
        ↓
    TradeIntent
        ↓
    ExecutionService
        ↓
    RiskEngine
        ↓
    Broker capability
        ↓
    Broker
"""

from typing import Final

from ..services.risk import (
    RiskEngine as _RiskEngine,
    risk_engine as _risk_engine,
)


# =============================================================================
# AUTHORITATIVE EXPORTS
# =============================================================================

RiskEngine: Final = _RiskEngine
risk_engine: Final = _risk_engine


# =============================================================================
# ACCESSOR
# =============================================================================

def get_risk_engine() -> _RiskEngine:
    """
    Return the shared PhoenixTrend RiskEngine singleton.

    Callers should use the shared instance whenever they participate in the
    normal PhoenixTrend execution path. Creating independent risk-engine
    instances in Automation, Manual Trade or API handlers can cause divergent
    limits and is therefore intentionally discouraged.
    """
    return risk_engine


# =============================================================================
# INTEGRITY
# =============================================================================

def is_shared_risk_engine(
    instance: object,
) -> bool:
    """
    Return True only when ``instance`` is the authoritative shared singleton.
    """
    return instance is risk_engine


def risk_engine_type() -> type:
    """
    Return the concrete RiskEngine class used by the shared service.
    """
    return _RiskEngine


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    "RiskEngine",
    "risk_engine",
    "get_risk_engine",
    "is_shared_risk_engine",
    "risk_engine_type",
]