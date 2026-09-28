from __future__ import annotations

from .base import Context, Strategy
from ..domain import Side, Signal


class MomentumStrategy(Strategy):
    """
    PhoenixTrend momentum strategy.

    Detects strong directional continuation using:

    - Price structure
    - EMA alignment
    - VWAP
    - RSI
    - Relative volume
    - MACD when available
    - Detected chart patterns when available

    This strategy does NOT fetch market data or place orders.
    """

    name = "Momentum"

    # ========================================================
    # CONFIGURATION
    # ========================================================

    minimum_score = 0.58
    directional_edge = 0.08

    bullish_rsi_min = 55.0
    bullish_rsi_max = 78.0

    bearish_rsi_min = 22.0
    bearish_rsi_max = 45.0

    relative_volume_min = 1.5
    strong_volume_min = 2.0

    # ========================================================
    # FAST SCORE
    # ========================================================

    def score(
        self,
        ctx: Context,
    ) -> float:
        """
        Fast ranking score used by StrategySelector.

        Returns the stronger bullish/bearish score.
        """

        bullish = self._bullish_score(
            ctx
        )

        bearish = self._bearish_score(
            ctx
        )

        return max(
            bullish,
            bearish,
        )

    # ========================================================
    # SIGNAL
    # ========================================================

    def signal(
        self,
        ctx: Context,
    ) -> Signal | None:
        bullish = self._bullish_score(
            ctx
        )

        bearish = self._bearish_score(
            ctx
        )

        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        if (
            bullish >= self.minimum_score
            and bullish - bearish
            >= self.directional_edge
        ):
            rationale = [
                "Bullish momentum detected",
            ]

            if ctx.price > ctx.ema20:
                rationale.append(
                    "Price above EMA20"
                )

            if ctx.ema20 > ctx.ema50:
                rationale.append(
                    "EMA20 above EMA50"
                )

            if ctx.price > ctx.vwap:
                rationale.append(
                    "Price above VWAP"
                )

            if (
                ctx.volume_ratio
                >= self.relative_volume_min
            ):
                rationale.append(
                    "Strong relative volume"
                )

            if (
                ctx.rsi
                >= self.bullish_rsi_min
            ):
                rationale.append(
                    "RSI confirms bullish momentum"
                )

            if (
                ctx.macd_histogram is not None
                and ctx.macd_histogram > 0
            ):
                rationale.append(
                    "MACD momentum positive"
                )

            return Signal(
                symbol=ctx.symbol,
                side=Side.BUY,
                strategy=self.name,
                confidence=round(
                    bullish,
                    4,
                ),
                rationale=rationale,
            )

        # ----------------------------------------------------
        # SELL
        # ----------------------------------------------------

        if (
            bearish >= self.minimum_score
            and bearish - bullish
            >= self.directional_edge
        ):
            rationale = [
                "Bearish momentum detected",
            ]

            if ctx.price < ctx.ema20:
                rationale.append(
                    "Price below EMA20"
                )

            if ctx.ema20 < ctx.ema50:
                rationale.append(
                    "EMA20 below EMA50"
                )

            if ctx.price < ctx.vwap:
                rationale.append(
                    "Price below VWAP"
                )

            if (
                ctx.volume_ratio
                >= self.relative_volume_min
            ):
                rationale.append(
                    "Strong relative volume"
                )

            if (
                ctx.rsi
                <= self.bearish_rsi_max
            ):
                rationale.append(
                    "RSI confirms bearish momentum"
                )

            if (
                ctx.macd_histogram is not None
                and ctx.macd_histogram < 0
            ):
                rationale.append(
                    "MACD momentum negative"
                )

            return Signal(
                symbol=ctx.symbol,
                side=Side.SELL,
                strategy=self.name,
                confidence=round(
                    bearish,
                    4,
                ),
                rationale=rationale,
            )

        return None

    # ========================================================
    # BULLISH SCORE
    # ========================================================

    def _bullish_score(
        self,
        ctx: Context,
    ) -> float:
        score = 0.0

        if ctx.price > ctx.ema20:
            score += 0.18

        if ctx.ema20 > ctx.ema50:
            score += 0.18

        if ctx.price > ctx.vwap:
            score += 0.14

        if (
            self.bullish_rsi_min
            <= ctx.rsi
            <= self.bullish_rsi_max
        ):
            score += 0.16

        if (
            ctx.volume_ratio
            >= self.relative_volume_min
        ):
            score += 0.12

        if (
            ctx.volume_ratio
            >= self.strong_volume_min
        ):
            score += 0.05

        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram > 0
        ):
            score += 0.10

        if (
            ctx.market_regime.upper()
            == "BULLISH"
        ):
            score += 0.04

        score += self._pattern_score(
            ctx,
            bullish=True,
        )

        return min(
            score,
            1.0,
        )

    # ========================================================
    # BEARISH SCORE
    # ========================================================

    def _bearish_score(
        self,
        ctx: Context,
    ) -> float:
        score = 0.0

        if ctx.price < ctx.ema20:
            score += 0.18

        if ctx.ema20 < ctx.ema50:
            score += 0.18

        if ctx.price < ctx.vwap:
            score += 0.14

        if (
            self.bearish_rsi_min
            <= ctx.rsi
            <= self.bearish_rsi_max
        ):
            score += 0.16

        if (
            ctx.volume_ratio
            >= self.relative_volume_min
        ):
            score += 0.12

        if (
            ctx.volume_ratio
            >= self.strong_volume_min
        ):
            score += 0.05

        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram < 0
        ):
            score += 0.10

        if (
            ctx.market_regime.upper()
            == "BEARISH"
        ):
            score += 0.04

        score += self._pattern_score(
            ctx,
            bullish=False,
        )

        return min(
            score,
            1.0,
        )

    # ========================================================
    # PATTERN CONFIRMATION
    # ========================================================

    @staticmethod
    def _pattern_score(
        ctx: Context,
        bullish: bool,
    ) -> float:
        bullish_patterns = {
            "breakout",
            "bull_flag",
            "double_bottom",
            "trend_pullback_bullish",
        }

        bearish_patterns = {
            "breakdown",
            "bear_flag",
            "double_top",
            "trend_pullback_bearish",
        }

        wanted = (
            bullish_patterns
            if bullish
            else bearish_patterns
        )

        best_confidence = 0.0

        for pattern in ctx.patterns:
            name = str(
                pattern.get(
                    "name",
                    "",
                )
            ).strip().lower()

            if name not in wanted:
                continue

            try:
                confidence = float(
                    pattern.get(
                        "confidence",
                        0.0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                confidence = 0.0

            best_confidence = max(
                best_confidence,
                confidence,
            )

        # Pattern evidence is confirmation only.
        # It cannot dominate the momentum decision.

        return min(
            best_confidence * 0.10,
            0.10,
        )