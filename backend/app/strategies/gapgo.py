from __future__ import annotations

from .base import Context, Strategy
from ..domain import Side, Signal


class GapAndGoStrategy(Strategy):
    """
    PhoenixTrend Gap-and-Go strategy.

    Detects continuation after a meaningful opening gap.

    Bullish:
        Opening price gaps above previous close and price
        continues with bullish confirmation.

    Bearish:
        Opening price gaps below previous close and price
        continues with bearish confirmation.

    The strategy requires real open and previous-close data.
    If those values are unavailable, it returns no signal.
    """

    name = "GapAndGo"

    minimum_score = 0.58
    directional_edge = 0.08

    # Minimum opening gap required.
    MIN_GAP_PCT = 0.02


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
        # BULLISH GAP-AND-GO
        # ----------------------------------------------------

        if (
            bullish >= self.minimum_score
            and bullish - bearish >= self.directional_edge
        ):

            gap_pct = self._gap_pct(ctx)

            rationale = [
                (
                    "Bullish opening gap detected "
                    f"({gap_pct * 100:.2f}%)"
                ),
                "Bullish Gap-and-Go continuation detected",
            ]

            if ctx.price >= ctx.open_price:
                rationale.append(
                    "Price holding above opening price"
                )

            if ctx.price > ctx.vwap:
                rationale.append(
                    "Price above VWAP"
                )

            if ctx.volume_ratio >= 1.5:
                rationale.append(
                    "Strong relative volume"
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
        # BEARISH GAP-AND-GO
        # ----------------------------------------------------

        if (
            bearish >= self.minimum_score
            and bearish - bullish >= self.directional_edge
        ):

            gap_pct = self._gap_pct(ctx)

            rationale = [
                (
                    "Bearish opening gap detected "
                    f"({gap_pct * 100:.2f}%)"
                ),
                "Bearish Gap-and-Go continuation detected",
            ]

            if ctx.price <= ctx.open_price:
                rationale.append(
                    "Price holding below opening price"
                )

            if ctx.price < ctx.vwap:
                rationale.append(
                    "Price below VWAP"
                )

            if ctx.volume_ratio >= 1.5:
                rationale.append(
                    "Strong relative volume"
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
    # GAP CALCULATION
    # ========================================================

    @staticmethod
    def _gap_pct(
        ctx: Context,
    ) -> float:

        if (
            ctx.open_price is None
            or ctx.previous_close is None
            or ctx.previous_close <= 0
        ):
            return 0.0

        return (
            ctx.open_price
            - ctx.previous_close
        ) / ctx.previous_close


    # ========================================================
    # BULLISH SCORE
    # ========================================================

    def _bullish_score(
        self,
        ctx: Context,
    ) -> float:

        if (
            ctx.open_price is None
            or ctx.previous_close is None
            or ctx.previous_close <= 0
        ):
            return 0.0


        gap_pct = self._gap_pct(ctx)


        # A bullish Gap-and-Go must first have a real gap up.
        if gap_pct < self.MIN_GAP_PCT:
            return 0.0


        # Price should continue rather than immediately
        # collapsing below the opening price.
        if ctx.price < ctx.open_price:
            return 0.0


        score = 0.38


        if ctx.price > ctx.vwap:
            score += 0.14


        if ctx.volume_ratio >= 1.5:
            score += 0.12


        if ctx.volume_ratio >= 2.0:
            score += 0.06


        if 55 <= ctx.rsi <= 80:
            score += 0.08


        if ctx.ema20 > ctx.ema50:
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
    # BEARISH SCORE
    # ========================================================

    def _bearish_score(
        self,
        ctx: Context,
    ) -> float:

        if (
            ctx.open_price is None
            or ctx.previous_close is None
            or ctx.previous_close <= 0
        ):
            return 0.0


        gap_pct = self._gap_pct(ctx)


        # A bearish Gap-and-Go must first have a real gap down.
        if gap_pct > -self.MIN_GAP_PCT:
            return 0.0


        if ctx.price > ctx.open_price:
            return 0.0


        score = 0.38


        if ctx.price < ctx.vwap:
            score += 0.14


        if ctx.volume_ratio >= 1.5:
            score += 0.12


        if ctx.volume_ratio >= 2.0:
            score += 0.06


        if 20 <= ctx.rsi <= 45:
            score += 0.08


        if ctx.ema20 < ctx.ema50:
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
            }
            if bullish
            else {
                "breakdown",
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
            best * 0.05,
            0.05,
        )