from __future__ import annotations

from .base import Context, Strategy
from ..domain import Side, Signal


class PullbackStrategy(Strategy):
    """
    PhoenixTrend trend-pullback strategy.

    Looks for controlled retracements toward EMA20 inside
    an already-established bullish or bearish trend.

    BUY:
        Bullish trend + price pulls back near EMA20.

    SELL:
        Bearish trend + price rallies back near EMA20.

    The pullback itself is not enough. The underlying trend
    must still be intact.
    """

    name = "Pullback"

    minimum_score = 0.58
    directional_edge = 0.08

    # Maximum default distance from EMA20.
    MAX_EMA20_DISTANCE_PCT = 0.015


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
        # BUY PULLBACK
        # ----------------------------------------------------

        if (
            bullish >= self.minimum_score
            and bullish - bearish >= self.directional_edge
        ):

            distance = self._ema20_distance(ctx)

            rationale = [
                "Bullish trend pullback detected",
                (
                    "Price near EMA20 "
                    f"({distance * 100:.2f}% distance)"
                ),
                "EMA20 remains above EMA50",
            ]

            if ctx.rsi > 45:
                rationale.append(
                    "RSI remains supportive"
                )

            if ctx.price >= ctx.vwap:
                rationale.append(
                    "Price holding at or above VWAP"
                )

            if (
                ctx.macd_histogram is not None
                and ctx.macd_histogram >= 0
            ):
                rationale.append(
                    "MACD remains supportive"
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
        # SELL PULLBACK
        # ----------------------------------------------------

        if (
            bearish >= self.minimum_score
            and bearish - bullish >= self.directional_edge
        ):

            distance = self._ema20_distance(ctx)

            rationale = [
                "Bearish trend pullback detected",
                (
                    "Price near EMA20 "
                    f"({distance * 100:.2f}% distance)"
                ),
                "EMA20 remains below EMA50",
            ]

            if ctx.rsi < 55:
                rationale.append(
                    "RSI remains bearish"
                )

            if ctx.price <= ctx.vwap:
                rationale.append(
                    "Price holding at or below VWAP"
                )

            if (
                ctx.macd_histogram is not None
                and ctx.macd_histogram <= 0
            ):
                rationale.append(
                    "MACD remains bearish"
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
    def _ema20_distance(
        ctx: Context,
    ) -> float:

        if ctx.ema20 <= 0:
            return float("inf")

        return (
            abs(
                ctx.price - ctx.ema20
            )
            / ctx.ema20
        )


    # ========================================================
    # DYNAMIC PULLBACK TOLERANCE
    # ========================================================

    def _pullback_tolerance(
        self,
        ctx: Context,
    ) -> float:
        """
        Use ATR when available so volatile stocks receive a
        slightly wider pullback zone.

        The tolerance is capped so a large move cannot be
        incorrectly classified as a normal pullback.
        """

        tolerance = (
            self.MAX_EMA20_DISTANCE_PCT
        )

        if (
            ctx.atr_pct is not None
            and ctx.atr_pct > 0
        ):
            tolerance = max(
                tolerance,
                min(
                    ctx.atr_pct * 0.75,
                    0.03,
                ),
            )

        return tolerance


    # ========================================================
    # BULLISH SCORE
    # ========================================================

    def _bullish_score(
        self,
        ctx: Context,
    ) -> float:

        # Existing bullish trend is mandatory.
        if ctx.ema20 <= ctx.ema50:
            return 0.0


        distance = self._ema20_distance(ctx)

        tolerance = self._pullback_tolerance(ctx)


        # Price must actually be near EMA20.
        if distance > tolerance:
            return 0.0


        # Avoid treating a deep structural failure as a
        # healthy bullish pullback.
        if ctx.price < ctx.ema50:
            return 0.0


        score = 0.36


        # Closer to EMA20 receives stronger pullback evidence.
        if distance <= tolerance * 0.50:
            score += 0.10
        else:
            score += 0.05


        if 45 < ctx.rsi < 65:
            score += 0.12


        if ctx.price >= ctx.vwap:
            score += 0.08


        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram >= 0
        ):
            score += 0.08


        if (
            ctx.market_regime.upper()
            == "BULLISH"
        ):
            score += 0.06


        if ctx.trend_strength >= 0.50:
            score += 0.06


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

        # Existing bearish trend is mandatory.
        if ctx.ema20 >= ctx.ema50:
            return 0.0


        distance = self._ema20_distance(ctx)

        tolerance = self._pullback_tolerance(ctx)


        if distance > tolerance:
            return 0.0


        # Avoid treating a structural bullish reversal as a
        # normal bearish pullback.
        if ctx.price > ctx.ema50:
            return 0.0


        score = 0.36


        if distance <= tolerance * 0.50:
            score += 0.10
        else:
            score += 0.05


        if 35 < ctx.rsi < 55:
            score += 0.12


        if ctx.price <= ctx.vwap:
            score += 0.08


        if (
            ctx.macd_histogram is not None
            and ctx.macd_histogram <= 0
        ):
            score += 0.08


        if (
            ctx.market_regime.upper()
            == "BEARISH"
        ):
            score += 0.06


        if ctx.trend_strength >= 0.50:
            score += 0.06


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
                "trend_pullback_bullish",
                "bull_flag",
            }
            if bullish
            else {
                "trend_pullback_bearish",
                "bear_flag",
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