from __future__ import annotations

from .base import Context, Strategy
from ..domain import Side, Signal


class TrendFollowingStrategy(Strategy):
    """
    PhoenixTrend Trend Following strategy.

    Designed to participate in established directional trends.

    Unlike SwingTrend, this strategy places more weight on:

        - market regime
        - EMA alignment
        - trend strength
        - MACD direction
        - sustained price structure

    Supports both bullish and bearish trends.

    This strategy only generates signals.
    It never executes orders.
    """

    name = "TrendFollowing"

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
                "Established bullish trend detected",
                "Bullish EMA structure",
                "Bullish market regime",
            ]

            if ctx.price > ctx.vwap:
                rationale.append(
                    "Price above VWAP"
                )

            if ctx.trend_strength >= 0.50:
                rationale.append(
                    "Trend strength supports continuation"
                )

            if (
                ctx.ema200 is not None
                and ctx.ema50 > ctx.ema200
            ):
                rationale.append(
                    "Long-term EMA structure bullish"
                )

            if (
                ctx.macd_histogram is not None
                and ctx.macd_histogram > 0
            ):
                rationale.append(
                    "MACD momentum positive"
                )

            if ctx.volume_ratio >= 1.0:
                rationale.append(
                    "Volume supports trend"
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
                "Established bearish trend detected",
                "Bearish EMA structure",
                "Bearish market regime",
            ]

            if ctx.price < ctx.vwap:
                rationale.append(
                    "Price below VWAP"
                )

            if ctx.trend_strength >= 0.50:
                rationale.append(
                    "Trend strength supports continuation"
                )

            if (
                ctx.ema200 is not None
                and ctx.ema50 < ctx.ema200
            ):
                rationale.append(
                    "Long-term EMA structure bearish"
                )

            if (
                ctx.macd_histogram is not None
                and ctx.macd_histogram < 0
            ):
                rationale.append(
                    "MACD momentum negative"
                )

            if ctx.volume_ratio >= 1.0:
                rationale.append(
                    "Volume supports trend"
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
    # BULLISH TREND SCORE
    # ========================================================

    def _bullish_score(
        self,
        ctx: Context,
    ) -> float:

        # Trend Following requires an actual bullish regime.
        if ctx.market_regime.upper() != "BULLISH":
            return 0.0


        # Core directional structure is mandatory.
        if not (
            ctx.price > ctx.ema20 > ctx.ema50
        ):
            return 0.0


        score = 0.40


        if ctx.trend_strength >= 0.50:
            score += 0.12


        if ctx.trend_strength >= 0.70:
            score += 0.05


        if ctx.price > ctx.vwap:
            score += 0.08


        if 50 < ctx.rsi < 75:
            score += 0.08


        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram > 0
        ):
            score += 0.08


        if (
            ctx.ema200 is not None
            and ctx.ema50 > ctx.ema200
        ):
            score += 0.08


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
    # BEARISH TREND SCORE
    # ========================================================

    def _bearish_score(
        self,
        ctx: Context,
    ) -> float:

        # Trend Following requires an actual bearish regime.
        if ctx.market_regime.upper() != "BEARISH":
            return 0.0


        # Core directional structure is mandatory.
        if not (
            ctx.price < ctx.ema20 < ctx.ema50
        ):
            return 0.0


        score = 0.40


        if ctx.trend_strength >= 0.50:
            score += 0.12


        if ctx.trend_strength >= 0.70:
            score += 0.05


        if ctx.price < ctx.vwap:
            score += 0.08


        if 25 < ctx.rsi < 50:
            score += 0.08


        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram < 0
        ):
            score += 0.08


        if (
            ctx.ema200 is not None
            and ctx.ema50 < ctx.ema200
        ):
            score += 0.08


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
                "breakout",
                "trend_pullback_bullish",
            }
            if bullish
            else {
                "bear_flag",
                "breakdown",
                "trend_pullback_bearish",
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
            best * 0.07,
            0.07,
        )