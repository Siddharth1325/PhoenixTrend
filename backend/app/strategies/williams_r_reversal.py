from __future__ import annotations

import math
from typing import Any

from .base import Context
from .configurable import ConfigurableStrategy, ScoreCard


class WilliamsRReversalStrategy(ConfigurableStrategy):
    """Williams %R Reversal strategy using normalized PhoenixTrend market context.

    This implementation intentionally keeps the complete strategy contract in
    its own module. Market data is supplied by PhoenixTrend's market-data and
    indicator pipeline; this class never fabricates candles, prices, volume,
    trades, or performance. The methods below expose configuration,
    validation, readiness checks, regime context, evidence and diagnostics so
    the strategy can be inspected safely by the API/UI and automatic engine.
    """

    name = 'Williams %R Reversal'
    oversold = -80.0
    overbought = -20.0


    @classmethod
    def configuration_schema(cls) -> dict[str, dict[str, Any]]:
        """Describe editable numeric parameters without inventing UI values."""
        return {
            "oversold": {"type": "number", "default": cls.oversold, "editable": True},
            "overbought": {"type": "number", "default": cls.overbought, "editable": True},
        }

    def configuration(self) -> dict[str, float]:
        """Return the effective runtime configuration for diagnostics."""
        return {
            "oversold": float(self.oversold),
            "overbought": float(self.overbought),
        }

    @staticmethod
    def _require_finite(key: str, value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be numeric")
        if not math.isfinite(float(value)):
            raise ValueError(f"{key} must be finite")

    def validate_configuration(self) -> None:
        """Fail closed when a persisted custom value is malformed."""
        self._require_finite("oversold", self.oversold)
        self._require_finite("overbought", self.overbought)
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be below overbought")
        if not 0.0 <= float(self.minimum_score) <= 1.0:
            raise ValueError("minimum_score must be between 0 and 1")
        if not 0.0 <= float(self.directional_edge) <= 1.0:
            raise ValueError("directional_edge must be between 0 and 1")

    @staticmethod
    def _finite(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))

    def required_market_fields(self) -> tuple[str, ...]:
        """Core normalized fields required before any directional decision."""
        return (
            "price",
            "ema20",
            "ema50",
            "rsi",
            "vwap",
            "volume_ratio",
        )

    def readiness(self, c: Context) -> tuple[bool, tuple[str, ...]]:
        """Check only real normalized context values; never synthesize gaps."""
        missing: list[str] = []
        for field in self.required_market_fields():
            if not hasattr(c, field):
                missing.append(field)
                continue
            if not self._finite(getattr(c, field)):
                missing.append(field)
        return not missing, tuple(missing)

    def market_snapshot(self, c: Context) -> dict[str, Any]:
        """Create a compact explainability snapshot from the supplied context."""
        keys = (
            "symbol", "price", "ema20", "ema50", "ema200", "rsi", "vwap",
            "volume_ratio", "atr", "macd", "macd_signal", "adx", "plus_di",
            "minus_di", "bollinger_upper", "bollinger_middle", "bollinger_lower",
            "stochastic_k", "stochastic_d", "cci", "williams_r", "roc",
            "donchian_upper", "donchian_lower", "keltner_upper", "keltner_lower",
            "supertrend", "parabolic_sar",
        )
        snapshot: dict[str, Any] = {}
        for key in keys:
            if hasattr(c, key):
                value = getattr(c, key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    snapshot[key] = float(value) if math.isfinite(float(value)) else None
                else:
                    snapshot[key] = value
        return snapshot

    def regime_assessment(self, c: Context) -> dict[str, Any]:
        """Describe trend/volume/volatility context without changing the signal."""
        trend = "neutral"
        if self._finite(getattr(c, "ema20", None)) and self._finite(getattr(c, "ema50", None)):
            if c.ema20 > c.ema50:
                trend = "bullish"
            elif c.ema20 < c.ema50:
                trend = "bearish"

        volume = "normal"
        if self._finite(getattr(c, "volume_ratio", None)):
            if c.volume_ratio >= 1.5:
                volume = "expanded"
            elif c.volume_ratio < 0.8:
                volume = "thin"

        momentum = "neutral"
        if self._finite(getattr(c, "rsi", None)):
            if c.rsi >= 60:
                momentum = "bullish"
            elif c.rsi <= 40:
                momentum = "bearish"

        return {"trend": trend, "volume": volume, "momentum": momentum}

    def evidence(self, c: Context) -> dict[str, Any]:
        """Return the exact score card used by the strategy for explainability."""
        card = self.evaluate(c)
        return {
            "bullish_score": round(self.clamp(card.bullish), 6),
            "bearish_score": round(self.clamp(card.bearish), 6),
            "bullish_reasons": list(card.bullish_reasons),
            "bearish_reasons": list(card.bearish_reasons),
            "directional_edge": round(abs(card.bullish - card.bearish), 6),
        }

    def diagnostics(self, c: Context) -> dict[str, Any]:
        """Full non-execution diagnostic payload for logs, tests and UI inspection."""
        self.validate_configuration()
        ready, missing = self.readiness(c)
        payload: dict[str, Any] = {
            "strategy": self.name,
            "ready": ready,
            "missing_fields": list(missing),
            "configuration": self.configuration(),
            "regime": self.regime_assessment(c),
            "market": self.market_snapshot(c),
        }
        if ready:
            payload["evidence"] = self.evidence(c)
        return payload

    def evaluate(self, c: Context) -> ScoreCard:
            x=c.williams_r
            if x is None: return ScoreCard(0.0,0.0)
            b=s=0.0; br=[]; sr=[]
            b=self.add(b,x<=self.oversold,0.48); s=self.add(s,x>=self.overbought,0.48)
            b=self.add(b,c.rsi<42,0.22); s=self.add(s,c.rsi>58,0.22)
            b=self.add(b,c.price<c.vwap,0.16); s=self.add(s,c.price>c.vwap,0.16)
            b=self.add(b,c.market_regime!="BEARISH",0.14); s=self.add(s,c.market_regime!="BULLISH",0.14)
            if x<=self.oversold: br.append("Williams %R is oversold")
            if x>=self.overbought: sr.append("Williams %R is overbought")
            return ScoreCard(b,s,tuple(br),tuple(sr))

    def score(self, ctx: Context) -> float:
        """Validate configuration and data readiness before scoring."""
        self.validate_configuration()
        ready, _ = self.readiness(ctx)
        if not ready:
            return 0.0
        return super().score(ctx)

    def signal(self, ctx: Context):
        """Fail closed on incomplete real data, then use shared signal discipline."""
        self.validate_configuration()
        ready, _ = self.readiness(ctx)
        if not ready:
            return None
        return super().signal(ctx)

    def long_setup(self, c: Context) -> dict[str, Any]:
        """Explain whether the current real context qualifies as a long setup."""
        ready, missing = self.readiness(c)
        if not ready:
            return {
                "qualified": False,
                "score": 0.0,
                "reasons": [],
                "missing_fields": list(missing),
            }
        card = self.evaluate(c)
        bullish = self.clamp(card.bullish)
        bearish = self.clamp(card.bearish)
        edge = bullish - bearish
        return {
            "qualified": bullish >= self.minimum_score and edge >= self.directional_edge,
            "score": round(bullish, 6),
            "opposing_score": round(bearish, 6),
            "edge": round(edge, 6),
            "reasons": list(card.bullish_reasons),
            "minimum_score": float(self.minimum_score),
            "minimum_edge": float(self.directional_edge),
        }

    def short_setup(self, c: Context) -> dict[str, Any]:
        """Explain whether the current real context qualifies as a short setup."""
        ready, missing = self.readiness(c)
        if not ready:
            return {
                "qualified": False,
                "score": 0.0,
                "reasons": [],
                "missing_fields": list(missing),
            }
        card = self.evaluate(c)
        bullish = self.clamp(card.bullish)
        bearish = self.clamp(card.bearish)
        edge = bearish - bullish
        return {
            "qualified": bearish >= self.minimum_score and edge >= self.directional_edge,
            "score": round(bearish, 6),
            "opposing_score": round(bullish, 6),
            "edge": round(edge, 6),
            "reasons": list(card.bearish_reasons),
            "minimum_score": float(self.minimum_score),
            "minimum_edge": float(self.directional_edge),
        }

    def volatility_context(self, c: Context) -> dict[str, Any]:
        """Expose ATR-derived context without inventing a stop or target price."""
        atr = getattr(c, "atr", None)
        price = getattr(c, "price", None)
        if not self._finite(atr) or not self._finite(price) or float(price) <= 0.0:
            return {"available": False, "atr": None, "atr_percent": None}
        atr_value = abs(float(atr))
        price_value = float(price)
        return {
            "available": True,
            "atr": atr_value,
            "atr_percent": round((atr_value / price_value) * 100.0, 6),
        }

    def trend_context(self, c: Context) -> dict[str, Any]:
        """Describe normalized moving-average structure used as context."""
        ema20 = getattr(c, "ema20", None)
        ema50 = getattr(c, "ema50", None)
        ema200 = getattr(c, "ema200", None)
        price = getattr(c, "price", None)
        return {
            "price_above_ema20": bool(self._finite(price) and self._finite(ema20) and price > ema20),
            "price_above_ema50": bool(self._finite(price) and self._finite(ema50) and price > ema50),
            "ema20_above_ema50": bool(self._finite(ema20) and self._finite(ema50) and ema20 > ema50),
            "ema50_above_ema200": bool(self._finite(ema50) and self._finite(ema200) and ema50 > ema200),
        }

    def volume_context(self, c: Context) -> dict[str, Any]:
        """Describe volume participation using only normalized provider data."""
        ratio = getattr(c, "volume_ratio", None)
        volume = getattr(c, "volume", None)
        average = getattr(c, "average_volume", None)
        return {
            "volume": float(volume) if self._finite(volume) else None,
            "average_volume": float(average) if self._finite(average) else None,
            "volume_ratio": float(ratio) if self._finite(ratio) else None,
            "above_average": bool(self._finite(ratio) and ratio >= 1.0),
            "strong_participation": bool(self._finite(ratio) and ratio >= 1.5),
        }

    def momentum_context(self, c: Context) -> dict[str, Any]:
        """Describe RSI/MACD state without converting missing values to fake zeros."""
        rsi = getattr(c, "rsi", None)
        macd = getattr(c, "macd", None)
        signal = getattr(c, "macd_signal", None)
        histogram = getattr(c, "macd_histogram", None)
        return {
            "rsi": float(rsi) if self._finite(rsi) else None,
            "macd": float(macd) if self._finite(macd) else None,
            "macd_signal": float(signal) if self._finite(signal) else None,
            "macd_histogram": float(histogram) if self._finite(histogram) else None,
            "macd_bullish": bool(self._finite(macd) and self._finite(signal) and macd > signal),
            "macd_bearish": bool(self._finite(macd) and self._finite(signal) and macd < signal),
        }

    def decision_report(self, c: Context) -> dict[str, Any]:
        """Build a deterministic report suitable for API logs and UI inspection."""
        self.validate_configuration()
        ready, missing = self.readiness(c)
        report: dict[str, Any] = {
            "strategy": self.name,
            "ready": ready,
            "missing_fields": list(missing),
            "configuration": self.configuration(),
            "regime": self.regime_assessment(c),
            "trend": self.trend_context(c),
            "momentum": self.momentum_context(c),
            "volume": self.volume_context(c),
            "volatility": self.volatility_context(c),
        }
        if not ready:
            report["decision"] = "NO_SIGNAL"
            return report
        long_setup = self.long_setup(c)
        short_setup = self.short_setup(c)
        report["long_setup"] = long_setup
        report["short_setup"] = short_setup
        if long_setup["qualified"]:
            report["decision"] = "BUY"
        elif short_setup["qualified"]:
            report["decision"] = "SELL"
        else:
            report["decision"] = "NO_SIGNAL"
        return report

    def audit_payload(self, c: Context) -> dict[str, Any]:
        """Return stable fields for PhoenixTrend audit/event persistence."""
        report = self.decision_report(c)
        return {
            "strategy": self.name,
            "symbol": getattr(c, "symbol", ""),
            "decision": report.get("decision", "NO_SIGNAL"),
            "ready": report.get("ready", False),
            "missing_fields": report.get("missing_fields", []),
            "regime": report.get("regime", {}),
            "long_setup": report.get("long_setup"),
            "short_setup": report.get("short_setup"),
        }

    def configuration_health(self) -> dict[str, Any]:
        """Validate persisted values and expose a machine-readable health result."""
        try:
            self.validate_configuration()
        except (TypeError, ValueError) as exc:
            return {"valid": False, "error": str(exc), "configuration": self.configuration()}
        return {"valid": True, "error": None, "configuration": self.configuration()}

