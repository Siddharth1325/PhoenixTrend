from __future__ import annotations

from .base import Context, Strategy
from ..domain import Side, Signal


class ORBStrategy(Strategy):
    """
    PhoenixTrend Opening Range Breakout strategy.

    Detects:

        BUY:
            Price breaks above opening range high.

        SELL:
            Price breaks below opening range low.

    Confirmation:

        - relative volume
        - VWAP
        - EMA structure
        - RSI
        - MACD
        - chart patterns

    Opening-range levels must be calculated by the market
    analysis layer. This strategy never invents them.
    """

    name = "ORB"

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
                "Bullish opening-range breakout detected",
                "Price broke above opening range high",
            ]

            if ctx.volume_ratio >= 1.5:
                rationale.append(
                    "Relative volume confirms breakout"
                )

            if ctx.price > ctx.vwap:
                rationale.append(
                    "Price above VWAP"
                )

            if ctx.ema20 > ctx.ema50:
                rationale.append(
                    "Bullish EMA structure"
                )

            if ctx.rsi >= 55:
                rationale.append(
                    "RSI supports bullish momentum"
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
                "Bearish opening-range breakdown detected",
                "Price broke below opening range low",
            ]

            if ctx.volume_ratio >= 1.5:
                rationale.append(
                    "Relative volume confirms breakdown"
                )

            if ctx.price < ctx.vwap:
                rationale.append(
                    "Price below VWAP"
                )

            if ctx.ema20 < ctx.ema50:
                rationale.append(
                    "Bearish EMA structure"
                )

            if ctx.rsi <= 45:
                rationale.append(
                    "RSI supports bearish momentum"
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
    # BULLISH ORB SCORE
    # ========================================================

    def _bullish_score(
        self,
        ctx: Context,
    ) -> float:

        opening_high = (
            ctx.opening_range_high
        )

        # No valid opening range = ORB cannot trigger.
        if (
            opening_high is None
            or opening_high <= 0
            or ctx.price <= opening_high
        ):
            return 0.0


        score = 0.38


        if ctx.volume_ratio >= 1.5:
            score += 0.15


        if ctx.volume_ratio >= 2.0:
            score += 0.07


        if ctx.price > ctx.vwap:
            score += 0.12


        if ctx.ema20 > ctx.ema50:
            score += 0.08


        if 55 <= ctx.rsi <= 80:
            score += 0.07


        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram > 0
        ):
            score += 0.08


        score += self._pattern_confirmation(
            ctx,
            bullish=True,
        )


        return min(
            score,
            1.0,
        )


    # ========================================================
    # BEARISH ORB SCORE
    # ========================================================

    def _bearish_score(
        self,
        ctx: Context,
    ) -> float:

        opening_low = (
            ctx.opening_range_low
        )

        # No valid opening range = ORB cannot trigger.
        if (
            opening_low is None
            or opening_low <= 0
            or ctx.price >= opening_low
        ):
            return 0.0


        score = 0.38


        if ctx.volume_ratio >= 1.5:
            score += 0.15


        if ctx.volume_ratio >= 2.0:
            score += 0.07


        if ctx.price < ctx.vwap:
            score += 0.12


        if ctx.ema20 < ctx.ema50:
            score += 0.08


        if 20 <= ctx.rsi <= 45:
            score += 0.07


        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram < 0
        ):
            score += 0.08


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
                "breakout",
                "bull_flag",
                "volatility_compression",
            }
            if bullish
            else {
                "breakdown",
                "bear_flag",
                "volatility_compression",
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
            best * 0.05,
            0.05,
        )