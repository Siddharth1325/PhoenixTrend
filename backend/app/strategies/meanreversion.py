from __future__ import annotations

from .base import Context, Strategy
from ..domain import Side, Signal


class MeanReversionStrategy(Strategy):
    """
    PhoenixTrend Mean Reversion strategy.

    Looks for statistically stretched price conditions where
    price may revert toward its short-term mean.

    BUY:
        Oversold + price stretched below EMA20.

    SELL:
        Overbought + price stretched above EMA20.

    Confirmation can come from:

        - RSI
        - EMA20 distance
        - Bollinger Bands
        - VWAP
        - MACD
        - chart patterns

    This strategy only generates a Signal.
    It never executes an order.
    """

    name = "MeanReversion"

    minimum_score = 0.58
    directional_edge = 0.08

    OVERSOLD_RSI = 32.0
    OVERBOUGHT_RSI = 68.0

    MIN_STRETCH_PCT = 0.01


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
        # BUY REVERSION
        # ----------------------------------------------------

        if (
            bullish >= self.minimum_score
            and bullish - bearish >= self.directional_edge
        ):

            rationale = [
                "Bullish mean-reversion setup detected",
                "Price stretched below EMA20",
                "RSI indicates oversold conditions",
            ]

            if (
                ctx.bb_lower is not None
                and ctx.price <= ctx.bb_lower
            ):
                rationale.append(
                    "Price at or below lower Bollinger Band"
                )

            if ctx.price < ctx.vwap:
                rationale.append(
                    "Price below VWAP"
                )

            if (
                ctx.macd_histogram is not None
                and ctx.macd_histogram > 0
            ):
                rationale.append(
                    "MACD shows improving bullish momentum"
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
        # SELL REVERSION
        # ----------------------------------------------------

        if (
            bearish >= self.minimum_score
            and bearish - bullish >= self.directional_edge
        ):

            rationale = [
                "Bearish mean-reversion setup detected",
                "Price stretched above EMA20",
                "RSI indicates overbought conditions",
            ]

            if (
                ctx.bb_upper is not None
                and ctx.price >= ctx.bb_upper
            ):
                rationale.append(
                    "Price at or above upper Bollinger Band"
                )

            if ctx.price > ctx.vwap:
                rationale.append(
                    "Price above VWAP"
                )

            if (
                ctx.macd_histogram is not None
                and ctx.macd_histogram < 0
            ):
                rationale.append(
                    "MACD shows weakening bullish momentum"
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
    # EMA20 DISTANCE
    # ========================================================

    @staticmethod
    def _ema20_distance_pct(
        ctx: Context,
    ) -> float:

        if ctx.ema20 <= 0:
            return 0.0

        return (
            ctx.price - ctx.ema20
        ) / ctx.ema20


    # ========================================================
    # BULLISH SCORE
    # ========================================================

    def _bullish_score(
        self,
        ctx: Context,
    ) -> float:

        distance = self._ema20_distance_pct(ctx)


        # Mean reversion requires an actual downside stretch.
        if (
            ctx.rsi >= self.OVERSOLD_RSI
            or distance > -self.MIN_STRETCH_PCT
        ):
            return 0.0


        score = 0.38


        # Stronger RSI exhaustion.
        if ctx.rsi <= 28:
            score += 0.10
        else:
            score += 0.06


        # Larger downside stretch.
        if distance <= -0.02:
            score += 0.08
        else:
            score += 0.04


        if (
            ctx.bb_lower is not None
            and ctx.price <= ctx.bb_lower
        ):
            score += 0.14


        if ctx.price < ctx.vwap:
            score += 0.05


        # Momentum beginning to turn back upward is useful
        # confirmation for a reversion.
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
    # BEARISH SCORE
    # ========================================================

    def _bearish_score(
        self,
        ctx: Context,
    ) -> float:

        distance = self._ema20_distance_pct(ctx)


        # Mean reversion requires an actual upside stretch.
        if (
            ctx.rsi <= self.OVERBOUGHT_RSI
            or distance < self.MIN_STRETCH_PCT
        ):
            return 0.0


        score = 0.38


        if ctx.rsi >= 72:
            score += 0.10
        else:
            score += 0.06


        if distance >= 0.02:
            score += 0.08
        else:
            score += 0.04


        if (
            ctx.bb_upper is not None
            and ctx.price >= ctx.bb_upper
        ):
            score += 0.14


        if ctx.price > ctx.vwap:
            score += 0.05


        # Momentum turning downward helps confirm the
        # overbought reversion.
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
                "double_bottom",
            }
            if bullish
            else {
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
            best * 0.08,
            0.08,
        )