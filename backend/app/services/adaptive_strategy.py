from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..config import settings
from ..domain import Side, Signal


@dataclass(slots=True)
class AdaptiveEvidence:
    """
    One auditable contribution to the Adaptive Composite.

    Adaptive evidence is analytical only. It never represents an order,
    broker instruction, risk approval, or execution authorization.
    """

    name: str
    direction: str
    contribution: float
    value: Any = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "contribution": round(
                float(self.contribution),
                6,
            ),
            "value": self.value,
            "detail": self.detail,
        }


class AdaptiveStrategyService:
    """
    PhoenixTrend Adaptive Composite strategy service.

    The Adaptive Composite is a bounded, deterministic fallback analysis
    layer built exclusively from market features already produced by the
    PhoenixTrend market / indicator / pattern pipeline.

    It does not:

        - generate Python code
        - dynamically import strategies
        - execute orders
        - submit TradeIntent objects
        - bypass DecisionEngine
        - bypass Market Safety
        - bypass RiskEngine
        - bypass broker capability checks
        - call an LLM in the trading decision path
        - fabricate unavailable indicators
        - fabricate pattern confidence
        - fabricate support/resistance
        - fabricate market prices
        - infer missing asset metadata

    The service returns an auditable Signal only when enough independent
    directional evidence exists.

    Missing indicators remain missing and contribute no score.
    """

    NAME = "Adaptive Composite"

    MIN_TOTAL_EVIDENCE = 1.10
    MIN_DIRECTIONAL_EDGE = 0.28

    MAX_PATTERN_CONTRIBUTION = 0.80
    MAX_VOLUME_CONTRIBUTION = 0.30
    MAX_TREND_STRENGTH_CONTRIBUTION = 0.25

    TREND_WEIGHT = 0.75
    REGIME_WEIGHT = 0.25
    VWAP_WEIGHT = 0.18
    MACD_WEIGHT = 0.30
    RSI_WEIGHT = 0.18
    EMA200_WEIGHT = 0.15

    MIN_STOP_PERCENT = 0.012
    ATR_STOP_MULTIPLIER = 1.50
    TARGET_RISK_MULTIPLE = 2.00

    # =====================================================================
    # PUBLIC API
    # =====================================================================

    def evaluate(
        self,
        symbol: str,
        market: dict[str, Any],
        patterns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_symbol = self._normalize_symbol(
            symbol
        )

        if not isinstance(
            market,
            Mapping,
        ):
            return self._no_signal(
                symbol=normalized_symbol,
                market={},
                evidence=[
                    "Market snapshot is unavailable",
                ],
                reason="NO_MARKET_DATA",
            )

        normalized_market = dict(
            market
        )

        normalized_patterns = [
            dict(pattern)
            for pattern in (
                patterns
                or []
            )
            if isinstance(
                pattern,
                Mapping,
            )
        ]

        price = self._positive_float(
            normalized_market.get(
                "price"
            )
        )

        if price is None:
            price = self._positive_float(
                normalized_market.get(
                    "last_price"
                )
            )

        if price is None:
            price = self._positive_float(
                normalized_market.get(
                    "last"
                )
            )

        if price is None:
            return self._no_signal(
                symbol=normalized_symbol,
                market=normalized_market,
                evidence=[
                    "Valid market price is unavailable",
                ],
                reason="INVALID_MARKET_PRICE",
            )

        bullish_score = 0.0
        bearish_score = 0.0

        evidence: list[str] = []
        evidence_details: list[AdaptiveEvidence] = []

        # =================================================================
        # MARKET FEATURES
        # =================================================================

        ema20 = self._positive_float(
            normalized_market.get(
                "ema20"
            )
        )

        ema50 = self._positive_float(
            normalized_market.get(
                "ema50"
            )
        )

        ema200 = self._positive_float(
            normalized_market.get(
                "ema200"
            )
        )

        vwap = self._positive_float(
            normalized_market.get(
                "vwap"
            )
        )

        rsi = self._bounded_float(
            normalized_market.get(
                "rsi"
            ),
            minimum=0.0,
            maximum=100.0,
        )

        macd_histogram = self._optional_float(
            normalized_market.get(
                "macd_histogram"
            )
        )

        volume_ratio = self._non_negative_float(
            normalized_market.get(
                "volume_ratio"
            )
        )

        atr_value = self._positive_float(
            normalized_market.get(
                "atr"
            )
        )

        trend_strength = self._non_negative_float(
            normalized_market.get(
                "trend_strength"
            )
        )

        regime = self._normalize_regime(
            normalized_market.get(
                "market_regime"
            )
            or normalized_market.get(
                "regime"
            )
        )

        # =================================================================
        # CHART PATTERN EVIDENCE
        # =================================================================

        bullish_pattern_score = 0.0
        bearish_pattern_score = 0.0

        for pattern in normalized_patterns:
            direction = self._normalize_direction(
                pattern.get(
                    "direction"
                )
            )

            if direction not in {
                "BULLISH",
                "BEARISH",
            }:
                continue

            confidence = self._confidence(
                pattern.get(
                    "confidence"
                )
            )

            if confidence <= 0:
                continue

            contribution = (
                confidence
                * 0.35
            )

            label = str(
                pattern.get(
                    "label"
                )
                or pattern.get(
                    "name"
                )
                or "Pattern"
            ).strip()

            if direction == "BULLISH":
                available = max(
                    0.0,
                    self.MAX_PATTERN_CONTRIBUTION
                    - bullish_pattern_score,
                )

                accepted = min(
                    contribution,
                    available,
                )

                if accepted <= 0:
                    continue

                bullish_pattern_score += accepted

            else:
                available = max(
                    0.0,
                    self.MAX_PATTERN_CONTRIBUTION
                    - bearish_pattern_score,
                )

                accepted = min(
                    contribution,
                    available,
                )

                if accepted <= 0:
                    continue

                bearish_pattern_score += accepted

            evidence.append(
                (
                    f"{label}: "
                    f"{direction} "
                    f"{confidence:.2f}"
                )
            )

            evidence_details.append(
                AdaptiveEvidence(
                    name=label,
                    direction=direction,
                    contribution=accepted,
                    value=confidence,
                    detail=(
                        "Bounded chart-pattern evidence"
                    ),
                )
            )

        bullish_score += bullish_pattern_score
        bearish_score += bearish_pattern_score

        # =================================================================
        # EMA TREND STRUCTURE
        # =================================================================

        bullish_trend = False
        bearish_trend = False

        if (
            ema20 is not None
            and ema50 is not None
        ):
            bullish_trend = (
                price
                > ema20
                > ema50
            )

            bearish_trend = (
                price
                < ema20
                < ema50
            )

        if bullish_trend:
            bullish_score += (
                self.TREND_WEIGHT
            )

            evidence.append(
                "EMA structure bullish"
            )

            evidence_details.append(
                AdaptiveEvidence(
                    name="EMA structure",
                    direction="BULLISH",
                    contribution=(
                        self.TREND_WEIGHT
                    ),
                    value={
                        "price": price,
                        "ema20": ema20,
                        "ema50": ema50,
                    },
                    detail=(
                        "Price > EMA20 > EMA50"
                    ),
                )
            )

        elif bearish_trend:
            bearish_score += (
                self.TREND_WEIGHT
            )

            evidence.append(
                "EMA structure bearish"
            )

            evidence_details.append(
                AdaptiveEvidence(
                    name="EMA structure",
                    direction="BEARISH",
                    contribution=(
                        self.TREND_WEIGHT
                    ),
                    value={
                        "price": price,
                        "ema20": ema20,
                        "ema50": ema50,
                    },
                    detail=(
                        "Price < EMA20 < EMA50"
                    ),
                )
            )

        # =================================================================
        # MARKET REGIME
        # =================================================================

        if regime == "BULLISH":
            bullish_score += (
                self.REGIME_WEIGHT
            )

            evidence.append(
                "Market regime bullish"
            )

            evidence_details.append(
                AdaptiveEvidence(
                    name="Market regime",
                    direction="BULLISH",
                    contribution=(
                        self.REGIME_WEIGHT
                    ),
                    value=regime,
                )
            )

        elif regime == "BEARISH":
            bearish_score += (
                self.REGIME_WEIGHT
            )

            evidence.append(
                "Market regime bearish"
            )

            evidence_details.append(
                AdaptiveEvidence(
                    name="Market regime",
                    direction="BEARISH",
                    contribution=(
                        self.REGIME_WEIGHT
                    ),
                    value=regime,
                )
            )

        # =================================================================
        # TREND STRENGTH
        # =================================================================

        if (
            trend_strength is not None
            and trend_strength >= 0.50
        ):
            strength_bonus = min(
                trend_strength
                * 0.25,
                self.MAX_TREND_STRENGTH_CONTRIBUTION,
            )

            if bullish_trend:
                bullish_score += (
                    strength_bonus
                )

                evidence.append(
                    (
                        "Bullish trend strength "
                        f"{trend_strength:.2f}"
                    )
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="Trend strength",
                        direction="BULLISH",
                        contribution=(
                            strength_bonus
                        ),
                        value=trend_strength,
                    )
                )

            elif bearish_trend:
                bearish_score += (
                    strength_bonus
                )

                evidence.append(
                    (
                        "Bearish trend strength "
                        f"{trend_strength:.2f}"
                    )
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="Trend strength",
                        direction="BEARISH",
                        contribution=(
                            strength_bonus
                        ),
                        value=trend_strength,
                    )
                )

        # =================================================================
        # VWAP
        # =================================================================

        if vwap is not None:
            if price > vwap:
                bullish_score += (
                    self.VWAP_WEIGHT
                )

                evidence.append(
                    "Price above VWAP"
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="VWAP",
                        direction="BULLISH",
                        contribution=(
                            self.VWAP_WEIGHT
                        ),
                        value=vwap,
                        detail="Price above VWAP",
                    )
                )

            elif price < vwap:
                bearish_score += (
                    self.VWAP_WEIGHT
                )

                evidence.append(
                    "Price below VWAP"
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="VWAP",
                        direction="BEARISH",
                        contribution=(
                            self.VWAP_WEIGHT
                        ),
                        value=vwap,
                        detail="Price below VWAP",
                    )
                )

        # =================================================================
        # MACD
        # =================================================================

        if macd_histogram is not None:
            if macd_histogram > 0:
                bullish_score += (
                    self.MACD_WEIGHT
                )

                evidence.append(
                    "MACD histogram positive"
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="MACD histogram",
                        direction="BULLISH",
                        contribution=(
                            self.MACD_WEIGHT
                        ),
                        value=macd_histogram,
                    )
                )

            elif macd_histogram < 0:
                bearish_score += (
                    self.MACD_WEIGHT
                )

                evidence.append(
                    "MACD histogram negative"
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="MACD histogram",
                        direction="BEARISH",
                        contribution=(
                            self.MACD_WEIGHT
                        ),
                        value=macd_histogram,
                    )
                )

        # =================================================================
        # RSI
        # =================================================================

        if rsi is not None:
            if 52.0 <= rsi <= 72.0:
                bullish_score += (
                    self.RSI_WEIGHT
                )

                evidence.append(
                    (
                        "RSI supports bullish "
                        f"momentum ({rsi:.1f})"
                    )
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="RSI",
                        direction="BULLISH",
                        contribution=(
                            self.RSI_WEIGHT
                        ),
                        value=rsi,
                        detail=(
                            "Healthy bullish momentum zone"
                        ),
                    )
                )

            elif 28.0 <= rsi <= 48.0:
                bearish_score += (
                    self.RSI_WEIGHT
                )

                evidence.append(
                    (
                        "RSI supports bearish "
                        f"momentum ({rsi:.1f})"
                    )
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="RSI",
                        direction="BEARISH",
                        contribution=(
                            self.RSI_WEIGHT
                        ),
                        value=rsi,
                        detail=(
                            "Healthy bearish momentum zone"
                        ),
                    )
                )

            elif rsi > 78.0:
                evidence.append(
                    (
                        "RSI extremely elevated "
                        f"({rsi:.1f}); reversal risk"
                    )
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="RSI reversal risk",
                        direction="NEUTRAL",
                        contribution=0.0,
                        value=rsi,
                        detail=(
                            "Extreme RSI is treated as risk, "
                            "not an automatic short signal"
                        ),
                    )
                )

            elif rsi < 22.0:
                evidence.append(
                    (
                        "RSI extremely depressed "
                        f"({rsi:.1f}); reversal risk"
                    )
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="RSI reversal risk",
                        direction="NEUTRAL",
                        contribution=0.0,
                        value=rsi,
                        detail=(
                            "Extreme RSI is treated as risk, "
                            "not an automatic long signal"
                        ),
                    )
                )

        # =================================================================
        # VOLUME CONFIRMATION
        # =================================================================

        if (
            volume_ratio is not None
            and volume_ratio >= 1.50
        ):
            volume_bonus = min(
                (
                    volume_ratio
                    - 1.0
                )
                * 0.15,
                self.MAX_VOLUME_CONTRIBUTION,
            )

            if bullish_score > bearish_score:
                bullish_score += (
                    volume_bonus
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="Relative volume",
                        direction="BULLISH",
                        contribution=(
                            volume_bonus
                        ),
                        value=volume_ratio,
                        detail=(
                            "Volume confirms existing "
                            "bullish directional evidence"
                        ),
                    )
                )

            elif bearish_score > bullish_score:
                bearish_score += (
                    volume_bonus
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="Relative volume",
                        direction="BEARISH",
                        contribution=(
                            volume_bonus
                        ),
                        value=volume_ratio,
                        detail=(
                            "Volume confirms existing "
                            "bearish directional evidence"
                        ),
                    )
                )

            else:
                evidence_details.append(
                    AdaptiveEvidence(
                        name="Relative volume",
                        direction="NEUTRAL",
                        contribution=0.0,
                        value=volume_ratio,
                        detail=(
                            "Volume cannot create direction "
                            "without an existing edge"
                        ),
                    )
                )

            evidence.append(
                (
                    "Relative volume "
                    f"{volume_ratio:.2f}x"
                )
            )

        # =================================================================
        # LONG-TERM EMA CONFIRMATION
        # =================================================================

        if (
            ema200 is not None
            and ema50 is not None
        ):
            if (
                bullish_trend
                and ema50 > ema200
            ):
                bullish_score += (
                    self.EMA200_WEIGHT
                )

                evidence.append(
                    "EMA50 above EMA200"
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="Long-term EMA",
                        direction="BULLISH",
                        contribution=(
                            self.EMA200_WEIGHT
                        ),
                        value={
                            "ema50": ema50,
                            "ema200": ema200,
                        },
                    )
                )

            elif (
                bearish_trend
                and ema50 < ema200
            ):
                bearish_score += (
                    self.EMA200_WEIGHT
                )

                evidence.append(
                    "EMA50 below EMA200"
                )

                evidence_details.append(
                    AdaptiveEvidence(
                        name="Long-term EMA",
                        direction="BEARISH",
                        contribution=(
                            self.EMA200_WEIGHT
                        ),
                        value={
                            "ema50": ema50,
                            "ema200": ema200,
                        },
                    )
                )

        # =================================================================
        # DIRECTIONAL EDGE
        # =================================================================

        total_score = (
            bullish_score
            + bearish_score
        )

        if total_score <= 0:
            return self._no_signal(
                symbol=normalized_symbol,
                market=normalized_market,
                evidence=evidence,
                evidence_details=evidence_details,
                reason="NO_DIRECTIONAL_EVIDENCE",
                bullish_score=bullish_score,
                bearish_score=bearish_score,
            )

        directional_difference = (
            bullish_score
            - bearish_score
        )

        directional_edge = (
            abs(
                directional_difference
            )
            / total_score
        )

        # =================================================================
        # EVIDENCE THRESHOLD
        # =================================================================

        if (
            total_score
            < self.MIN_TOTAL_EVIDENCE
            or directional_edge
            < self.MIN_DIRECTIONAL_EDGE
        ):
            return self._no_signal(
                symbol=normalized_symbol,
                market=normalized_market,
                evidence=evidence,
                evidence_details=evidence_details,
                reason="INSUFFICIENT_DIRECTIONAL_EDGE",
                confidence=directional_edge,
                bullish_score=bullish_score,
                bearish_score=bearish_score,
                total_score=total_score,
                directional_edge=directional_edge,
            )

        # =================================================================
        # SIDE
        # =================================================================

        side = (
            Side.BUY
            if bullish_score
            > bearish_score
            else Side.SELL
        )

        # =================================================================
        # CONFIDENCE
        # =================================================================

        confidence = min(
            (
                0.55
                + directional_edge
                * 0.35
            ),
            0.90,
        )

        minimum_confidence = self._minimum_confidence()

        if confidence < minimum_confidence:
            return self._no_signal(
                symbol=normalized_symbol,
                market=normalized_market,
                evidence=evidence,
                evidence_details=evidence_details,
                reason="BELOW_ADAPTIVE_CONFIDENCE_THRESHOLD",
                confidence=confidence,
                bullish_score=bullish_score,
                bearish_score=bearish_score,
                total_score=total_score,
                directional_edge=directional_edge,
            )

        # =================================================================
        # ANALYTICAL RISK REFERENCE LEVELS
        # =================================================================

        stop = None
        target = None
        stop_distance = None
        target_distance = None
        risk_reference_source = None

        if (
            atr_value is not None
            and atr_value > 0
        ):
            stop_distance = max(
                atr_value
                * self.ATR_STOP_MULTIPLIER,
                price
                * self.MIN_STOP_PERCENT,
            )

            risk_reference_source = (
                "ATR_AND_PRICE_FLOOR"
            )

        else:
            # This is a documented analytical percentage reference, not a
            # fabricated ATR value. RiskEngine remains authoritative.
            stop_distance = (
                price
                * self.MIN_STOP_PERCENT
            )

            risk_reference_source = (
                "PRICE_PERCENT_FLOOR"
            )

        if (
            stop_distance is not None
            and stop_distance > 0
        ):
            target_distance = (
                stop_distance
                * self.TARGET_RISK_MULTIPLE
            )

            if side == Side.BUY:
                stop = (
                    price
                    - stop_distance
                )

                target = (
                    price
                    + target_distance
                )

            else:
                stop = (
                    price
                    + stop_distance
                )

                target = (
                    price
                    - target_distance
                )

            if stop <= 0:
                stop = None

        # =================================================================
        # SIGNAL
        # =================================================================

        signal = Signal(
            symbol=normalized_symbol,
            side=side,
            strategy=self.NAME,
            confidence=round(
                confidence,
                4,
            ),
            rationale=evidence[:10],
            stop=(
                round(
                    stop,
                    6,
                )
                if stop is not None
                else None
            ),
            target=(
                round(
                    target,
                    6,
                )
                if target is not None
                else None
            ),
        )

        return {
            "name": self.NAME,
            "symbol": normalized_symbol,
            "signal": signal,
            "signal_side": self._side_value(
                side
            ),
            "actionable": True,
            "confidence": round(
                confidence,
                4,
            ),
            "minimum_confidence": round(
                minimum_confidence,
                4,
            ),
            "bullish_score": round(
                bullish_score,
                4,
            ),
            "bearish_score": round(
                bearish_score,
                4,
            ),
            "total_score": round(
                total_score,
                4,
            ),
            "directional_edge": round(
                directional_edge,
                4,
            ),
            "evidence": evidence,
            "evidence_details": [
                item.as_dict()
                for item
                in evidence_details
            ],
            "risk_reference": {
                "authoritative": False,
                "risk_engine_authoritative": True,
                "source": risk_reference_source,
                "atr": atr_value,
                "atr_multiplier": (
                    self.ATR_STOP_MULTIPLIER
                    if atr_value is not None
                    else None
                ),
                "minimum_stop_percent": (
                    self.MIN_STOP_PERCENT
                ),
                "target_risk_multiple": (
                    self.TARGET_RISK_MULTIPLE
                ),
                "stop_distance": (
                    round(
                        stop_distance,
                        6,
                    )
                    if stop_distance is not None
                    else None
                ),
                "target_distance": (
                    round(
                        target_distance,
                        6,
                    )
                    if target_distance is not None
                    else None
                ),
                "stop": (
                    round(
                        stop,
                        6,
                    )
                    if stop is not None
                    else None
                ),
                "target": (
                    round(
                        target,
                        6,
                    )
                    if target is not None
                    else None
                ),
            },
            "rules": self._rules(
                normalized_market
            ),
        }

    # =====================================================================
    # NO SIGNAL
    # =====================================================================

    def _no_signal(
        self,
        *,
        symbol: str,
        market: dict[str, Any],
        evidence: list[str],
        reason: str,
        evidence_details: list[AdaptiveEvidence] | None = None,
        confidence: float = 0.0,
        bullish_score: float = 0.0,
        bearish_score: float = 0.0,
        total_score: float | None = None,
        directional_edge: float | None = None,
    ) -> dict[str, Any]:
        if total_score is None:
            total_score = (
                bullish_score
                + bearish_score
            )

        if directional_edge is None:
            if total_score > 0:
                directional_edge = (
                    abs(
                        bullish_score
                        - bearish_score
                    )
                    / total_score
                )
            else:
                directional_edge = 0.0

        return {
            "name": self.NAME,
            "symbol": symbol,
            "signal": None,
            "signal_side": "HOLD",
            "actionable": False,
            "reason": reason,
            "confidence": round(
                self._confidence(
                    confidence
                ),
                4,
            ),
            "minimum_confidence": round(
                self._minimum_confidence(),
                4,
            ),
            "bullish_score": round(
                bullish_score,
                4,
            ),
            "bearish_score": round(
                bearish_score,
                4,
            ),
            "total_score": round(
                total_score,
                4,
            ),
            "directional_edge": round(
                directional_edge,
                4,
            ),
            "evidence": evidence,
            "evidence_details": [
                item.as_dict()
                for item
                in (
                    evidence_details
                    or []
                )
            ],
            "risk_reference": {
                "authoritative": False,
                "risk_engine_authoritative": True,
                "stop": None,
                "target": None,
            },
            "rules": self._rules(
                market
            ),
        }

    # =====================================================================
    # AUDITABLE RULE PROFILE
    # =====================================================================

    def _rules(
        self,
        market: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "strategy": self.NAME,
            "deterministic": True,
            "llm_in_decision_path": False,
            "executes_orders": False,
            "risk_engine_authoritative": True,
            "market_safety_authoritative": True,
            "minimum_total_evidence": (
                self.MIN_TOTAL_EVIDENCE
            ),
            "minimum_directional_edge": (
                self.MIN_DIRECTIONAL_EDGE
            ),
            "minimum_confidence": (
                self._minimum_confidence()
            ),
            "trend": (
                "Price / EMA20 / EMA50 alignment "
                "only when EMA20 and EMA50 are available"
            ),
            "long_term_trend": (
                "EMA50 / EMA200 confirmation "
                "only when EMA200 is available"
            ),
            "momentum": (
                "MACD histogram and RSI directional "
                "zones only when supplied by market analysis"
            ),
            "participation": (
                "Relative volume confirms an existing "
                "direction; it cannot create direction"
            ),
            "location": (
                "Price relative to VWAP when VWAP is available"
            ),
            "patterns": (
                "Bounded directional chart-pattern evidence"
            ),
            "maximum_pattern_contribution": (
                self.MAX_PATTERN_CONTRIBUTION
            ),
            "trend_strength": (
                "Trend-strength contribution is applied only "
                "to an existing EMA directional structure"
            ),
            "risk_reference": (
                "Analytical stop/target references only; "
                "RiskEngine remains authoritative"
            ),
            "atr_stop_multiplier": (
                self.ATR_STOP_MULTIPLIER
            ),
            "minimum_stop_percent": (
                self.MIN_STOP_PERCENT
            ),
            "target_risk_multiple": (
                self.TARGET_RISK_MULTIPLE
            ),
            "regime": self._normalize_regime(
                market.get(
                    "market_regime"
                )
                or market.get(
                    "regime"
                )
            ),
        }

    # =====================================================================
    # CONFIGURATION
    # =====================================================================

    @staticmethod
    def _minimum_confidence() -> float:
        value = getattr(
            settings,
            "adaptive_strategy_min_confidence",
            0.0,
        )

        try:
            result = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            result = 0.0

        return max(
            0.0,
            min(
                result,
                1.0,
            ),
        )

    # =====================================================================
    # NORMALIZATION
    # =====================================================================

    @staticmethod
    def _normalize_symbol(
        symbol: Any,
    ) -> str:
        normalized = str(
            symbol
            or ""
        ).strip().upper()

        if not normalized:
            raise ValueError(
                "Symbol is required"
            )

        return normalized

    @staticmethod
    def _normalize_regime(
        value: Any,
    ) -> str:
        normalized = str(
            value
            or "NEUTRAL"
        ).strip().upper()

        aliases = {
            "UPTREND": "BULLISH",
            "TREND_UP": "BULLISH",
            "BULL": "BULLISH",
            "LONG": "BULLISH",
            "DOWNTREND": "BEARISH",
            "TREND_DOWN": "BEARISH",
            "BEAR": "BEARISH",
            "SHORT": "BEARISH",
            "SIDEWAYS": "NEUTRAL",
            "RANGE": "NEUTRAL",
            "RANGING": "NEUTRAL",
            "CHOP": "NEUTRAL",
            "CHOPPY": "NEUTRAL",
            "UNKNOWN": "NEUTRAL",
            "": "NEUTRAL",
        }

        return aliases.get(
            normalized,
            normalized,
        )

    @staticmethod
    def _normalize_direction(
        value: Any,
    ) -> str:
        normalized = str(
            value
            or ""
        ).strip().upper()

        aliases = {
            "BUY": "BULLISH",
            "LONG": "BULLISH",
            "UP": "BULLISH",
            "UPWARD": "BULLISH",
            "SELL": "BEARISH",
            "SHORT": "BEARISH",
            "DOWN": "BEARISH",
            "DOWNWARD": "BEARISH",
            "HOLD": "NEUTRAL",
            "NONE": "NEUTRAL",
        }

        return aliases.get(
            normalized,
            normalized,
        )

    # =====================================================================
    # NUMERIC HELPERS
    # =====================================================================

    @staticmethod
    def _optional_float(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            result = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if result != result:
            return None

        if result in {
            float("inf"),
            float("-inf"),
        }:
            return None

        return result

    @classmethod
    def _positive_float(
        cls,
        value: Any,
    ) -> float | None:
        result = cls._optional_float(
            value
        )

        if (
            result is None
            or result <= 0
        ):
            return None

        return result

    @classmethod
    def _non_negative_float(
        cls,
        value: Any,
    ) -> float | None:
        result = cls._optional_float(
            value
        )

        if (
            result is None
            or result < 0
        ):
            return None

        return result

    @classmethod
    def _bounded_float(
        cls,
        value: Any,
        *,
        minimum: float,
        maximum: float,
    ) -> float | None:
        result = cls._optional_float(
            value
        )

        if result is None:
            return None

        if (
            result < minimum
            or result > maximum
        ):
            return None

        return result

    @staticmethod
    def _confidence(
        value: Any,
    ) -> float:
        try:
            result = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if result != result:
            return 0.0

        return max(
            0.0,
            min(
                result,
                1.0,
            ),
        )

    # =====================================================================
    # DOMAIN HELPERS
    # =====================================================================

    @staticmethod
    def _side_value(
        side: Side,
    ) -> str:
        value = getattr(
            side,
            "value",
            None,
        )

        if value is not None:
            return str(
                value
            )

        return str(
            side
        )


adaptive_strategy_service = AdaptiveStrategyService()