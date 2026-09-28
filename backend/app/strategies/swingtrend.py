from __future__ import annotations

from .base import Context, Strategy
from ..domain import Side, Signal


class SwingTrendStrategy(Strategy):
    """
    PhoenixTrend swing-trend strategy.

    Designed for established directional trends where the
    current price still offers a reasonable swing entry.

    Uses:

    - EMA20 / EMA50 trend structure
    - EMA200 when available
    - RSI
    - VWAP
    - MACD
    - trend strength
    - chart-pattern confirmation

    Supports both bullish and bearish setups.
    """

    name = "SwingTrend"

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
                "Bullish swing trend detected",
                "Price above EMA20 and EMA50",
            ]

            if (
                ctx.ema200 is not None
                and ctx.price > ctx.ema200
            ):
                rationale.append(
                    "Price above EMA200"
                )

            if 50 < ctx.rsi < 72:
                rationale.append(
                    "RSI supports sustainable bullish trend"
                )

            if ctx.price > ctx.vwap:
                rationale.append(
                    "Price above VWAP"
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
                "Bearish swing trend detected",
                "Price below EMA20 and EMA50",
            ]

            if (
                ctx.ema200 is not None
                and ctx.price < ctx.ema200
            ):
                rationale.append(
                    "Price below EMA200"
                )

            if 28 < ctx.rsi < 50:
                rationale.append(
                    "RSI supports sustainable bearish trend"
                )

            if ctx.price < ctx.vwap:
                rationale.append(
                    "Price below VWAP"
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

        # Core swing-trend requirement.
        if not (
            ctx.price > ctx.ema20 > ctx.ema50
        ):
            return 0.0


        score = 0.35


        if 50 < ctx.rsi < 72:
            score += 0.15


        if ctx.price > ctx.vwap:
            score += 0.10


        if (
            ctx.ema200 is not None
            and ctx.ema50 > ctx.ema200
        ):
            score += 0.10


        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram > 0
        ):
            score += 0.08


        if (
            ctx.market_regime.upper()
            == "BULLISH"
        ):
            score += 0.06


        if ctx.trend_strength >= 0.50:
            score += 0.06


        if ctx.volume_ratio >= 1.0:
            score += 0.04


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

        # Core bearish swing-trend requirement.
        if not (
            ctx.price < ctx.ema20 < ctx.ema50
        ):
            return 0.0


        score = 0.35


        if 28 < ctx.rsi < 50:
            score += 0.15


        if ctx.price < ctx.vwap:
            score += 0.10


        if (
            ctx.ema200 is not None
            and ctx.ema50 < ctx.ema200
        ):
            score += 0.10


        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram < 0
        ):
            score += 0.08


        if (
            ctx.market_regime.upper()
            == "BEARISH"
        ):
            score += 0.06


        if ctx.trend_strength >= 0.50:
            score += 0.06


        if ctx.volume_ratio >= 1.0:
            score += 0.04


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
                "trend_pullback_bullish",
                "double_bottom",
            }
            if bullish
            else {
                "bear_flag",
                "trend_pullback_bearish",
                "double_top",
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


        return min(
            best * 0.06,
            0.06,
        )