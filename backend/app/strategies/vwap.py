from __future__ import annotations

from .base import Context, Strategy
from ..domain import Side, Signal


class VWAPStrategy(Strategy):
    """
    PhoenixTrend VWAP strategy.

    Uses VWAP as the primary directional reference and confirms
    the setup with trend, RSI, volume and MACD.

    BUY:
        Price holds above VWAP with bullish confirmation.

    SELL:
        Price holds below VWAP with bearish confirmation.

    This strategy only generates signals.
    It never performs execution.
    """

    name = "VWAP"

    minimum_score = 0.58
    directional_edge = 0.08


    # ========================================================
    # FAST SCORE
    # ========================================================

    def score(
        self,
        ctx: Context,
    ) -> float:

        bullish = self._bullish_score(ctx)
        bearish = self._bearish_score(ctx)

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

        bullish = self._bullish_score(ctx)
        bearish = self._bearish_score(ctx)



        # ----------------------------------------------------
        # BUY
        # ----------------------------------------------------

        if (
            bullish >= self.minimum_score
            and bullish - bearish >= self.directional_edge
        ):

            rationale = [
                "Bullish VWAP setup detected",
                "Price above VWAP",
            ]

            if ctx.ema20 >= ctx.ema50:
                rationale.append(
                    "Bullish EMA structure"
                )

            if ctx.rsi > 52:
                rationale.append(
                    "RSI supports bullish direction"
                )

            if ctx.volume_ratio >= 1.2:
                rationale.append(
                    "Volume supports the move"
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
            and bearish - bullish >= self.directional_edge
        ):

            rationale = [
                "Bearish VWAP setup detected",
                "Price below VWAP",
            ]

            if ctx.ema20 <= ctx.ema50:
                rationale.append(
                    "Bearish EMA structure"
                )

            if ctx.rsi < 48:
                rationale.append(
                    "RSI supports bearish direction"
                )

            if ctx.volume_ratio >= 1.2:
                rationale.append(
                    "Volume supports the move"
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

        # VWAP is mandatory for this strategy.
        if ctx.price <= ctx.vwap:
            return 0.0

        score = 0.30


        if ctx.ema20 >= ctx.ema50:
            score += 0.18


        if ctx.rsi > 52:
            score += 0.14


        if 55 <= ctx.rsi <= 72:
            score += 0.05


        if ctx.volume_ratio >= 1.2:
            score += 0.10


        if ctx.volume_ratio >= 1.5:
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
            score += 0.03


        score += self._pattern_confirmation(
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

        # VWAP is mandatory for this strategy.
        if ctx.price >= ctx.vwap:
            return 0.0

        score = 0.30


        if ctx.ema20 <= ctx.ema50:
            score += 0.18


        if ctx.rsi < 48:
            score += 0.14


        if 28 <= ctx.rsi <= 45:
            score += 0.05


        if ctx.volume_ratio >= 1.2:
            score += 0.10


        if ctx.volume_ratio >= 1.5:
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
            score += 0.03


        score += self._pattern_confirmation(
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
    def _pattern_confirmation(
        ctx: Context,
        bullish: bool,
    ) -> float:

        wanted = (
            {
                "bull_flag",
                "double_bottom",
                "trend_pullback_bullish",
                "breakout",
            }
            if bullish
            else {
                "bear_flag",
                "double_top",
                "trend_pullback_bearish",
                "breakdown",
            }
        )

        best = 0.0

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

            best = max(
                best,
                confidence,
            )


        # Patterns are confirmation only.
        return min(
            best * 0.05,
            0.05,
        )