from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class RegimeEvidence:
    name: str
    value: float | str | bool | None
    direction: str
    weight: float
    description: str

    def dump(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "direction": self.direction,
            "weight": self.weight,
            "description": self.description,
        }


class MarketRegimeService:
    """
    PhoenixTrend market-regime classifier.

    The classifier operates only on market/indicator values supplied by the
    caller. Missing indicators remain missing and are never replaced with
    fabricated defaults.

    Classification dimensions:

        trend:
            BULLISH
            BEARISH
            RANGE
            UNKNOWN

        trend strength:
            STRONG
            MODERATE
            WEAK
            UNKNOWN

        volatility:
            HIGH
            NORMAL
            LOW
            UNKNOWN

        momentum:
            OVERBOUGHT
            BULLISH
            NEUTRAL
            BEARISH
            OVERSOLD
            UNKNOWN

        composite regime examples:
            STRONG_BULL_TREND
            BULL_TREND
            STRONG_BEAR_TREND
            BEAR_TREND
            HIGH_VOLATILITY_RANGE
            RANGE
            UNKNOWN

    This service does not generate trading orders. It supplies deterministic
    regime context for strategy selection and the Decision Engine.
    """

    TREND_BULLISH = "BULLISH"
    TREND_BEARISH = "BEARISH"
    TREND_RANGE = "RANGE"
    TREND_UNKNOWN = "UNKNOWN"

    STRENGTH_STRONG = "STRONG"
    STRENGTH_MODERATE = "MODERATE"
    STRENGTH_WEAK = "WEAK"
    STRENGTH_UNKNOWN = "UNKNOWN"

    VOLATILITY_HIGH = "HIGH"
    VOLATILITY_NORMAL = "NORMAL"
    VOLATILITY_LOW = "LOW"
    VOLATILITY_UNKNOWN = "UNKNOWN"

    MOMENTUM_OVERBOUGHT = "OVERBOUGHT"
    MOMENTUM_BULLISH = "BULLISH"
    MOMENTUM_NEUTRAL = "NEUTRAL"
    MOMENTUM_BEARISH = "BEARISH"
    MOMENTUM_OVERSOLD = "OVERSOLD"
    MOMENTUM_UNKNOWN = "UNKNOWN"

    def classify(self, market: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(market, dict):
            raise TypeError("market must be a dictionary")

        indicators = self._indicator_source(market)

        price = self._first_num(
            market,
            indicators,
            keys=(
                "price",
                "close",
                "regular_market_price",
                "last",
                "last_price",
            ),
        )

        ema9 = self._num(
            indicators,
            "ema9",
            "ema_9",
            "ema9_value",
        )

        ema20 = self._num(
            indicators,
            "ema20",
            "ema_20",
            "ema20_value",
        )

        ema50 = self._num(
            indicators,
            "ema50",
            "ema_50",
            "ema50_value",
        )

        ema200 = self._num(
            indicators,
            "ema200",
            "ema_200",
            "ema200_value",
        )

        sma20 = self._num(
            indicators,
            "sma20",
            "sma_20",
            "sma20_value",
        )

        sma50 = self._num(
            indicators,
            "sma50",
            "sma_50",
            "sma50_value",
        )

        sma200 = self._num(
            indicators,
            "sma200",
            "sma_200",
            "sma200_value",
        )

        adx = self._num(
            indicators,
            "adx",
            "adx14",
            "adx_14",
        )

        plus_di = self._num(
            indicators,
            "plus_di",
            "di_plus",
            "positive_di",
            "pdi",
        )

        minus_di = self._num(
            indicators,
            "minus_di",
            "di_minus",
            "negative_di",
            "mdi",
        )

        atr = self._num(
            indicators,
            "atr",
            "atr14",
            "atr_14",
        )

        atr_percent = self._num(
            indicators,
            "atr_percent",
            "atr_pct",
            "atr_percentage",
        )

        if (
            atr_percent is None
            and atr is not None
            and price is not None
            and price > 0
        ):
            atr_percent = (atr / price) * 100.0

        rsi = self._num(
            indicators,
            "rsi",
            "rsi14",
            "rsi_14",
        )

        macd = self._num(
            indicators,
            "macd",
            "macd_line",
        )

        macd_signal = self._num(
            indicators,
            "macd_signal",
            "signal_line",
            "macd_signal_line",
        )

        macd_histogram = self._num(
            indicators,
            "macd_histogram",
            "macd_hist",
            "histogram",
        )

        roc = self._num(
            indicators,
            "roc",
            "rate_of_change",
            "momentum_percent",
        )

        stochastic_k = self._num(
            indicators,
            "stochastic_k",
            "stoch_k",
            "percent_k",
        )

        stochastic_d = self._num(
            indicators,
            "stochastic_d",
            "stoch_d",
            "percent_d",
        )

        bollinger_upper = self._num(
            indicators,
            "bollinger_upper",
            "bb_upper",
            "upper_band",
        )

        bollinger_middle = self._num(
            indicators,
            "bollinger_middle",
            "bb_middle",
            "middle_band",
        )

        bollinger_lower = self._num(
            indicators,
            "bollinger_lower",
            "bb_lower",
            "lower_band",
        )

        bollinger_width = self._num(
            indicators,
            "bollinger_width",
            "bb_width",
            "bandwidth",
        )

        volume = self._first_num(
            market,
            indicators,
            keys=(
                "volume",
                "regular_market_volume",
            ),
        )

        average_volume = self._first_num(
            market,
            indicators,
            keys=(
                "average_volume",
                "avg_volume",
                "average_daily_volume",
            ),
        )

        relative_volume = self._first_num(
            market,
            indicators,
            keys=(
                "volume_ratio",
                "relative_volume",
                "relative_volume_ratio",
                "rvol",
            ),
        )

        if (
            relative_volume is None
            and volume is not None
            and average_volume is not None
            and average_volume > 0
        ):
            relative_volume = volume / average_volume

        change_percent = self._first_num(
            market,
            indicators,
            keys=(
                "change_percent",
                "change_pct",
                "regular_market_change_percent",
                "percent_change",
            ),
        )

        previous_close = self._first_num(
            market,
            indicators,
            keys=(
                "previous_close",
                "regular_market_previous_close",
                "prev_close",
            ),
        )

        if (
            change_percent is None
            and price is not None
            and previous_close is not None
            and previous_close != 0
        ):
            change_percent = (
                (price - previous_close)
                / previous_close
            ) * 100.0

        trend_result = self._classify_trend(
            price=price,
            ema9=ema9,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            sma20=sma20,
            sma50=sma50,
            sma200=sma200,
            plus_di=plus_di,
            minus_di=minus_di,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            change_percent=change_percent,
        )

        strength_result = self._classify_strength(
            trend=trend_result["trend"],
            adx=adx,
            plus_di=plus_di,
            minus_di=minus_di,
            relative_volume=relative_volume,
            trend_score=trend_result["trend_score"],
            available_trend_weight=trend_result[
                "available_trend_weight"
            ],
        )

        volatility_result = self._classify_volatility(
            atr_percent=atr_percent,
            bollinger_width=bollinger_width,
            change_percent=change_percent,
        )

        momentum_result = self._classify_momentum(
            rsi=rsi,
            macd=macd,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            roc=roc,
            stochastic_k=stochastic_k,
            stochastic_d=stochastic_d,
        )

        composite_regime = self._composite_regime(
            trend=trend_result["trend"],
            strength=strength_result["trend_strength"],
            volatility=volatility_result["volatility"],
        )

        confidence = self._classification_confidence(
            trend_result=trend_result,
            strength_result=strength_result,
            volatility_result=volatility_result,
            momentum_result=momentum_result,
        )

        evidence = (
            trend_result["evidence"]
            + strength_result["evidence"]
            + volatility_result["evidence"]
            + momentum_result["evidence"]
        )

        conflicts = self._detect_conflicts(
            trend=trend_result["trend"],
            momentum=momentum_result["momentum"],
            price=price,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            macd_histogram=macd_histogram,
            rsi=rsi,
            plus_di=plus_di,
            minus_di=minus_di,
        )

        available_fields = self._available_fields(
            {
                "price": price,
                "ema9": ema9,
                "ema20": ema20,
                "ema50": ema50,
                "ema200": ema200,
                "sma20": sma20,
                "sma50": sma50,
                "sma200": sma200,
                "adx": adx,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "atr": atr,
                "atr_percent": atr_percent,
                "rsi": rsi,
                "macd": macd,
                "macd_signal": macd_signal,
                "macd_histogram": macd_histogram,
                "roc": roc,
                "stochastic_k": stochastic_k,
                "stochastic_d": stochastic_d,
                "bollinger_upper": bollinger_upper,
                "bollinger_middle": bollinger_middle,
                "bollinger_lower": bollinger_lower,
                "bollinger_width": bollinger_width,
                "volume": volume,
                "average_volume": average_volume,
                "relative_volume": relative_volume,
                "change_percent": change_percent,
                "previous_close": previous_close,
            }
        )

        return {
            "regime": composite_regime,
            "trend": trend_result["trend"],
            "trend_strength": strength_result[
                "trend_strength"
            ],
            "volatility": volatility_result["volatility"],
            "momentum": momentum_result["momentum"],
            "confidence": confidence,
            "trend_score": trend_result["trend_score"],
            "normalized_trend_score": trend_result[
                "normalized_trend_score"
            ],
            "available_trend_weight": trend_result[
                "available_trend_weight"
            ],
            "evidence": [
                item.dump()
                for item in evidence
            ],
            "conflicts": conflicts,
            "available_fields": available_fields,
            "metrics": {
                "price": price,
                "previous_close": previous_close,
                "change_percent": change_percent,
                "ema9": ema9,
                "ema20": ema20,
                "ema50": ema50,
                "ema200": ema200,
                "sma20": sma20,
                "sma50": sma50,
                "sma200": sma200,
                "adx": adx,
                "plus_di": plus_di,
                "minus_di": minus_di,
                "atr": atr,
                "atr_percent": atr_percent,
                "rsi": rsi,
                "macd": macd,
                "macd_signal": macd_signal,
                "macd_histogram": macd_histogram,
                "roc": roc,
                "stochastic_k": stochastic_k,
                "stochastic_d": stochastic_d,
                "bollinger_upper": bollinger_upper,
                "bollinger_middle": bollinger_middle,
                "bollinger_lower": bollinger_lower,
                "bollinger_width": bollinger_width,
                "volume": volume,
                "average_volume": average_volume,
                "relative_volume": relative_volume,
            },
        }

    def _classify_trend(
        self,
        *,
        price: float | None,
        ema9: float | None,
        ema20: float | None,
        ema50: float | None,
        ema200: float | None,
        sma20: float | None,
        sma50: float | None,
        sma200: float | None,
        plus_di: float | None,
        minus_di: float | None,
        macd: float | None,
        macd_signal: float | None,
        macd_histogram: float | None,
        change_percent: float | None,
    ) -> dict[str, Any]:
        score = 0.0
        available_weight = 0.0
        evidence: list[RegimeEvidence] = []

        def vote(
            *,
            name: str,
            bullish: bool,
            bearish: bool,
            weight: float,
            value: float | str | bool | None,
            bullish_text: str,
            bearish_text: str,
            neutral_text: str,
        ) -> None:
            nonlocal score
            nonlocal available_weight

            available_weight += weight

            if bullish:
                score += weight
                evidence.append(
                    RegimeEvidence(
                        name=name,
                        value=value,
                        direction=self.TREND_BULLISH,
                        weight=weight,
                        description=bullish_text,
                    )
                )
                return

            if bearish:
                score -= weight
                evidence.append(
                    RegimeEvidence(
                        name=name,
                        value=value,
                        direction=self.TREND_BEARISH,
                        weight=weight,
                        description=bearish_text,
                    )
                )
                return

            evidence.append(
                RegimeEvidence(
                    name=name,
                    value=value,
                    direction=self.TREND_RANGE,
                    weight=weight,
                    description=neutral_text,
                )
            )

        if price is not None and ema20 is not None:
            vote(
                name="price_vs_ema20",
                bullish=price > ema20,
                bearish=price < ema20,
                weight=1.0,
                value=price - ema20,
                bullish_text="Price is above EMA20.",
                bearish_text="Price is below EMA20.",
                neutral_text="Price is equal to EMA20.",
            )

        if price is not None and ema50 is not None:
            vote(
                name="price_vs_ema50",
                bullish=price > ema50,
                bearish=price < ema50,
                weight=1.25,
                value=price - ema50,
                bullish_text="Price is above EMA50.",
                bearish_text="Price is below EMA50.",
                neutral_text="Price is equal to EMA50.",
            )

        if price is not None and ema200 is not None:
            vote(
                name="price_vs_ema200",
                bullish=price > ema200,
                bearish=price < ema200,
                weight=1.5,
                value=price - ema200,
                bullish_text="Price is above EMA200.",
                bearish_text="Price is below EMA200.",
                neutral_text="Price is equal to EMA200.",
            )

        if ema9 is not None and ema20 is not None:
            vote(
                name="ema9_vs_ema20",
                bullish=ema9 > ema20,
                bearish=ema9 < ema20,
                weight=0.75,
                value=ema9 - ema20,
                bullish_text="EMA9 is above EMA20.",
                bearish_text="EMA9 is below EMA20.",
                neutral_text="EMA9 equals EMA20.",
            )

        if ema20 is not None and ema50 is not None:
            vote(
                name="ema20_vs_ema50",
                bullish=ema20 > ema50,
                bearish=ema20 < ema50,
                weight=1.25,
                value=ema20 - ema50,
                bullish_text="EMA20 is above EMA50.",
                bearish_text="EMA20 is below EMA50.",
                neutral_text="EMA20 equals EMA50.",
            )

        if ema50 is not None and ema200 is not None:
            vote(
                name="ema50_vs_ema200",
                bullish=ema50 > ema200,
                bearish=ema50 < ema200,
                weight=1.5,
                value=ema50 - ema200,
                bullish_text="EMA50 is above EMA200.",
                bearish_text="EMA50 is below EMA200.",
                neutral_text="EMA50 equals EMA200.",
            )

        if price is not None and sma20 is not None:
            vote(
                name="price_vs_sma20",
                bullish=price > sma20,
                bearish=price < sma20,
                weight=0.5,
                value=price - sma20,
                bullish_text="Price is above SMA20.",
                bearish_text="Price is below SMA20.",
                neutral_text="Price equals SMA20.",
            )

        if sma20 is not None and sma50 is not None:
            vote(
                name="sma20_vs_sma50",
                bullish=sma20 > sma50,
                bearish=sma20 < sma50,
                weight=0.75,
                value=sma20 - sma50,
                bullish_text="SMA20 is above SMA50.",
                bearish_text="SMA20 is below SMA50.",
                neutral_text="SMA20 equals SMA50.",
            )

        if sma50 is not None and sma200 is not None:
            vote(
                name="sma50_vs_sma200",
                bullish=sma50 > sma200,
                bearish=sma50 < sma200,
                weight=1.0,
                value=sma50 - sma200,
                bullish_text="SMA50 is above SMA200.",
                bearish_text="SMA50 is below SMA200.",
                neutral_text="SMA50 equals SMA200.",
            )

        if plus_di is not None and minus_di is not None:
            vote(
                name="directional_index",
                bullish=plus_di > minus_di,
                bearish=minus_di > plus_di,
                weight=1.0,
                value=plus_di - minus_di,
                bullish_text="+DI is above -DI.",
                bearish_text="-DI is above +DI.",
                neutral_text="+DI and -DI are equal.",
            )

        if macd is not None and macd_signal is not None:
            vote(
                name="macd_vs_signal",
                bullish=macd > macd_signal,
                bearish=macd < macd_signal,
                weight=0.75,
                value=macd - macd_signal,
                bullish_text="MACD is above its signal line.",
                bearish_text="MACD is below its signal line.",
                neutral_text="MACD equals its signal line.",
            )

        if macd_histogram is not None:
            vote(
                name="macd_histogram",
                bullish=macd_histogram > 0,
                bearish=macd_histogram < 0,
                weight=0.5,
                value=macd_histogram,
                bullish_text="MACD histogram is positive.",
                bearish_text="MACD histogram is negative.",
                neutral_text="MACD histogram is neutral.",
            )

        if change_percent is not None:
            vote(
                name="price_change",
                bullish=change_percent > 0,
                bearish=change_percent < 0,
                weight=0.25,
                value=change_percent,
                bullish_text="Observed price change is positive.",
                bearish_text="Observed price change is negative.",
                neutral_text="Observed price change is flat.",
            )

        if available_weight <= 0:
            return {
                "trend": self.TREND_UNKNOWN,
                "trend_score": 0.0,
                "normalized_trend_score": 0.0,
                "available_trend_weight": 0.0,
                "evidence": evidence,
            }

        normalized_score = score / available_weight

        if normalized_score >= 0.35:
            trend = self.TREND_BULLISH
        elif normalized_score <= -0.35:
            trend = self.TREND_BEARISH
        else:
            trend = self.TREND_RANGE

        return {
            "trend": trend,
            "trend_score": round(score, 6),
            "normalized_trend_score": round(
                normalized_score,
                6,
            ),
            "available_trend_weight": round(
                available_weight,
                6,
            ),
            "evidence": evidence,
        }

    def _classify_strength(
        self,
        *,
        trend: str,
        adx: float | None,
        plus_di: float | None,
        minus_di: float | None,
        relative_volume: float | None,
        trend_score: float,
        available_trend_weight: float,
    ) -> dict[str, Any]:
        evidence: list[RegimeEvidence] = []

        if trend == self.TREND_UNKNOWN:
            return {
                "trend_strength": self.STRENGTH_UNKNOWN,
                "strength_score": None,
                "evidence": evidence,
            }

        strength_score = 0.0
        observed_weight = 0.0

        if adx is not None:
            observed_weight += 3.0

            if adx >= 25.0:
                strength_score += 3.0
                description = (
                    "ADX indicates a strong directional market."
                )
                direction = self.STRENGTH_STRONG
            elif adx >= 20.0:
                strength_score += 2.0
                description = (
                    "ADX indicates moderate directional strength."
                )
                direction = self.STRENGTH_MODERATE
            else:
                strength_score += 0.5
                description = (
                    "ADX indicates weak directional strength."
                )
                direction = self.STRENGTH_WEAK

            evidence.append(
                RegimeEvidence(
                    name="adx",
                    value=adx,
                    direction=direction,
                    weight=3.0,
                    description=description,
                )
            )

        if (
            plus_di is not None
            and minus_di is not None
        ):
            observed_weight += 1.0

            directional_gap = abs(
                plus_di - minus_di
            )

            if directional_gap >= 10.0:
                strength_score += 1.0
                direction = self.STRENGTH_STRONG
                description = (
                    "Directional indicators show clear separation."
                )
            elif directional_gap >= 5.0:
                strength_score += 0.6
                direction = self.STRENGTH_MODERATE
                description = (
                    "Directional indicators show moderate separation."
                )
            else:
                strength_score += 0.2
                direction = self.STRENGTH_WEAK
                description = (
                    "Directional indicators show limited separation."
                )

            evidence.append(
                RegimeEvidence(
                    name="di_separation",
                    value=directional_gap,
                    direction=direction,
                    weight=1.0,
                    description=description,
                )
            )

        if (
            available_trend_weight > 0
            and trend
            in {
                self.TREND_BULLISH,
                self.TREND_BEARISH,
            }
        ):
            observed_weight += 1.0

            alignment = min(
                1.0,
                abs(trend_score)
                / available_trend_weight,
            )

            strength_score += alignment

            evidence.append(
                RegimeEvidence(
                    name="trend_alignment",
                    value=alignment,
                    direction=(
                        self.STRENGTH_STRONG
                        if alignment >= 0.7
                        else self.STRENGTH_MODERATE
                        if alignment >= 0.45
                        else self.STRENGTH_WEAK
                    ),
                    weight=1.0,
                    description=(
                        "Trend-indicator alignment measured from "
                        "available directional evidence."
                    ),
                )
            )

        if relative_volume is not None:
            observed_weight += 0.5

            if relative_volume >= 1.5:
                strength_score += 0.5
                direction = self.STRENGTH_STRONG
                description = (
                    "Relative volume supports stronger market participation."
                )
            elif relative_volume >= 1.0:
                strength_score += 0.3
                direction = self.STRENGTH_MODERATE
                description = (
                    "Relative volume indicates normal market participation."
                )
            else:
                strength_score += 0.1
                direction = self.STRENGTH_WEAK
                description = (
                    "Relative volume indicates lighter market participation."
                )

            evidence.append(
                RegimeEvidence(
                    name="relative_volume",
                    value=relative_volume,
                    direction=direction,
                    weight=0.5,
                    description=description,
                )
            )

        if observed_weight <= 0:
            return {
                "trend_strength": self.STRENGTH_UNKNOWN,
                "strength_score": None,
                "evidence": evidence,
            }

        normalized = (
            strength_score
            / observed_weight
        )

        if normalized >= 0.72:
            strength = self.STRENGTH_STRONG
        elif normalized >= 0.42:
            strength = self.STRENGTH_MODERATE
        else:
            strength = self.STRENGTH_WEAK

        if trend == self.TREND_RANGE:
            if (
                adx is not None
                and adx < 20.0
            ):
                strength = self.STRENGTH_WEAK

        return {
            "trend_strength": strength,
            "strength_score": round(
                normalized,
                6,
            ),
            "evidence": evidence,
        }

    def _classify_volatility(
        self,
        *,
        atr_percent: float | None,
        bollinger_width: float | None,
        change_percent: float | None,
    ) -> dict[str, Any]:
        evidence: list[RegimeEvidence] = []

        votes: list[str] = []

        if atr_percent is not None:
            if atr_percent >= 3.0:
                classification = self.VOLATILITY_HIGH
            elif atr_percent <= 1.0:
                classification = self.VOLATILITY_LOW
            else:
                classification = self.VOLATILITY_NORMAL

            votes.append(
                classification
            )

            evidence.append(
                RegimeEvidence(
                    name="atr_percent",
                    value=atr_percent,
                    direction=classification,
                    weight=1.0,
                    description=(
                        "Volatility classification from observed ATR "
                        "as a percentage of price."
                    ),
                )
            )

        if bollinger_width is not None:
            if bollinger_width >= 0:
                evidence.append(
                    RegimeEvidence(
                        name="bollinger_width",
                        value=bollinger_width,
                        direction="OBSERVED",
                        weight=0.5,
                        description=(
                            "Bollinger bandwidth is available as supporting "
                            "volatility context; no universal absolute "
                            "threshold is assumed."
                        ),
                    )
                )

        if change_percent is not None:
            evidence.append(
                RegimeEvidence(
                    name="absolute_price_change",
                    value=abs(change_percent),
                    direction="OBSERVED",
                    weight=0.25,
                    description=(
                        "Absolute observed price change is available as "
                        "supporting volatility context."
                    ),
                )
            )

        if not votes:
            volatility = self.VOLATILITY_UNKNOWN
        elif self.VOLATILITY_HIGH in votes:
            volatility = self.VOLATILITY_HIGH
        elif self.VOLATILITY_LOW in votes:
            volatility = self.VOLATILITY_LOW
        else:
            volatility = self.VOLATILITY_NORMAL

        return {
            "volatility": volatility,
            "evidence": evidence,
        }

    def _classify_momentum(
        self,
        *,
        rsi: float | None,
        macd: float | None,
        macd_signal: float | None,
        macd_histogram: float | None,
        roc: float | None,
        stochastic_k: float | None,
        stochastic_d: float | None,
    ) -> dict[str, Any]:
        evidence: list[RegimeEvidence] = []

        if rsi is not None:
            if rsi >= 70.0:
                rsi_state = self.MOMENTUM_OVERBOUGHT
            elif rsi <= 30.0:
                rsi_state = self.MOMENTUM_OVERSOLD
            elif rsi >= 55.0:
                rsi_state = self.MOMENTUM_BULLISH
            elif rsi <= 45.0:
                rsi_state = self.MOMENTUM_BEARISH
            else:
                rsi_state = self.MOMENTUM_NEUTRAL

            evidence.append(
                RegimeEvidence(
                    name="rsi",
                    value=rsi,
                    direction=rsi_state,
                    weight=1.5,
                    description=(
                        f"RSI momentum state is {rsi_state.lower()}."
                    ),
                )
            )

            if rsi_state in {
                self.MOMENTUM_OVERBOUGHT,
                self.MOMENTUM_OVERSOLD,
            }:
                return {
                    "momentum": rsi_state,
                    "momentum_score": None,
                    "evidence": evidence,
                }

        score = 0.0
        weight = 0.0

        if rsi is not None:
            weight += 1.5

            if rsi >= 55.0:
                score += 1.5
            elif rsi <= 45.0:
                score -= 1.5

        if (
            macd is not None
            and macd_signal is not None
        ):
            weight += 1.0

            if macd > macd_signal:
                score += 1.0
                direction = self.MOMENTUM_BULLISH
                description = (
                    "MACD is above its signal line."
                )
            elif macd < macd_signal:
                score -= 1.0
                direction = self.MOMENTUM_BEARISH
                description = (
                    "MACD is below its signal line."
                )
            else:
                direction = self.MOMENTUM_NEUTRAL
                description = (
                    "MACD equals its signal line."
                )

            evidence.append(
                RegimeEvidence(
                    name="macd",
                    value=macd - macd_signal,
                    direction=direction,
                    weight=1.0,
                    description=description,
                )
            )

        if macd_histogram is not None:
            weight += 0.75

            if macd_histogram > 0:
                score += 0.75
                direction = self.MOMENTUM_BULLISH
            elif macd_histogram < 0:
                score -= 0.75
                direction = self.MOMENTUM_BEARISH
            else:
                direction = self.MOMENTUM_NEUTRAL

            evidence.append(
                RegimeEvidence(
                    name="macd_histogram",
                    value=macd_histogram,
                    direction=direction,
                    weight=0.75,
                    description=(
                        "MACD histogram provides observed momentum direction."
                    ),
                )
            )

        if roc is not None:
            weight += 0.75

            if roc > 0:
                score += 0.75
                direction = self.MOMENTUM_BULLISH
            elif roc < 0:
                score -= 0.75
                direction = self.MOMENTUM_BEARISH
            else:
                direction = self.MOMENTUM_NEUTRAL

            evidence.append(
                RegimeEvidence(
                    name="rate_of_change",
                    value=roc,
                    direction=direction,
                    weight=0.75,
                    description=(
                        "Observed rate of change contributes to momentum."
                    ),
                )
            )

        if (
            stochastic_k is not None
            and stochastic_d is not None
        ):
            weight += 0.5

            if stochastic_k > stochastic_d:
                score += 0.5
                direction = self.MOMENTUM_BULLISH
            elif stochastic_k < stochastic_d:
                score -= 0.5
                direction = self.MOMENTUM_BEARISH
            else:
                direction = self.MOMENTUM_NEUTRAL

            evidence.append(
                RegimeEvidence(
                    name="stochastic_cross",
                    value=stochastic_k - stochastic_d,
                    direction=direction,
                    weight=0.5,
                    description=(
                        "Stochastic K/D relationship contributes to momentum."
                    ),
                )
            )

        if weight <= 0:
            return {
                "momentum": self.MOMENTUM_UNKNOWN,
                "momentum_score": None,
                "evidence": evidence,
            }

        normalized = score / weight

        if normalized >= 0.3:
            momentum = self.MOMENTUM_BULLISH
        elif normalized <= -0.3:
            momentum = self.MOMENTUM_BEARISH
        else:
            momentum = self.MOMENTUM_NEUTRAL

        return {
            "momentum": momentum,
            "momentum_score": round(
                normalized,
                6,
            ),
            "evidence": evidence,
        }

    def _composite_regime(
        self,
        *,
        trend: str,
        strength: str,
        volatility: str,
    ) -> str:
        if trend == self.TREND_UNKNOWN:
            return "UNKNOWN"

        if trend == self.TREND_BULLISH:
            if strength == self.STRENGTH_STRONG:
                return "STRONG_BULL_TREND"

            if strength == self.STRENGTH_MODERATE:
                return "BULL_TREND"

            if volatility == self.VOLATILITY_HIGH:
                return "HIGH_VOLATILITY_BULLISH"

            return "BULLISH"

        if trend == self.TREND_BEARISH:
            if strength == self.STRENGTH_STRONG:
                return "STRONG_BEAR_TREND"

            if strength == self.STRENGTH_MODERATE:
                return "BEAR_TREND"

            if volatility == self.VOLATILITY_HIGH:
                return "HIGH_VOLATILITY_BEARISH"

            return "BEARISH"

        if trend == self.TREND_RANGE:
            if volatility == self.VOLATILITY_HIGH:
                return "HIGH_VOLATILITY_RANGE"

            if volatility == self.VOLATILITY_LOW:
                return "LOW_VOLATILITY_RANGE"

            return "RANGE"

        return "UNKNOWN"

    def _classification_confidence(
        self,
        *,
        trend_result: Mapping[str, Any],
        strength_result: Mapping[str, Any],
        volatility_result: Mapping[str, Any],
        momentum_result: Mapping[str, Any],
    ) -> float:
        trend = str(
            trend_result.get(
                "trend",
                self.TREND_UNKNOWN,
            )
        )

        available_weight = self._safe_float(
            trend_result.get(
                "available_trend_weight"
            )
        )

        normalized_trend = self._safe_float(
            trend_result.get(
                "normalized_trend_score"
            )
        )

        components: list[float] = []

        if (
            available_weight is not None
            and available_weight > 0
            and normalized_trend is not None
        ):
            evidence_coverage = min(
                1.0,
                available_weight / 8.0,
            )

            directional_clarity = min(
                1.0,
                abs(normalized_trend),
            )

            if trend == self.TREND_RANGE:
                directional_clarity = (
                    1.0
                    - directional_clarity
                )

            components.append(
                (
                    evidence_coverage
                    + directional_clarity
                )
                / 2.0
            )

        strength = strength_result.get(
            "trend_strength"
        )

        if strength != self.STRENGTH_UNKNOWN:
            components.append(0.75)

        volatility = volatility_result.get(
            "volatility"
        )

        if volatility != self.VOLATILITY_UNKNOWN:
            components.append(0.65)

        momentum = momentum_result.get(
            "momentum"
        )

        if momentum != self.MOMENTUM_UNKNOWN:
            components.append(0.75)

        if not components:
            return 0.0

        return round(
            sum(components)
            / len(components),
            6,
        )

    def _detect_conflicts(
        self,
        *,
        trend: str,
        momentum: str,
        price: float | None,
        ema20: float | None,
        ema50: float | None,
        ema200: float | None,
        macd_histogram: float | None,
        rsi: float | None,
        plus_di: float | None,
        minus_di: float | None,
    ) -> list[str]:
        conflicts: list[str] = []

        if (
            trend == self.TREND_BULLISH
            and momentum
            in {
                self.MOMENTUM_BEARISH,
                self.MOMENTUM_OVERSOLD,
            }
        ):
            conflicts.append(
                "Bullish trend classification conflicts with bearish momentum."
            )

        if (
            trend == self.TREND_BEARISH
            and momentum
            in {
                self.MOMENTUM_BULLISH,
                self.MOMENTUM_OVERBOUGHT,
            }
        ):
            conflicts.append(
                "Bearish trend classification conflicts with bullish momentum."
            )

        if (
            price is not None
            and ema20 is not None
            and ema50 is not None
        ):
            if (
                price > ema20
                and ema20 < ema50
            ):
                conflicts.append(
                    "Price is above EMA20 while EMA20 remains below EMA50."
                )

            if (
                price < ema20
                and ema20 > ema50
            ):
                conflicts.append(
                    "Price is below EMA20 while EMA20 remains above EMA50."
                )

        if (
            price is not None
            and ema200 is not None
        ):
            if (
                trend == self.TREND_BULLISH
                and price < ema200
            ):
                conflicts.append(
                    "Bullish short-term evidence remains below EMA200."
                )

            if (
                trend == self.TREND_BEARISH
                and price > ema200
            ):
                conflicts.append(
                    "Bearish short-term evidence remains above EMA200."
                )

        if macd_histogram is not None:
            if (
                trend == self.TREND_BULLISH
                and macd_histogram < 0
            ):
                conflicts.append(
                    "Bullish trend conflicts with a negative MACD histogram."
                )

            if (
                trend == self.TREND_BEARISH
                and macd_histogram > 0
            ):
                conflicts.append(
                    "Bearish trend conflicts with a positive MACD histogram."
                )

        if (
            plus_di is not None
            and minus_di is not None
        ):
            if (
                trend == self.TREND_BULLISH
                and minus_di > plus_di
            ):
                conflicts.append(
                    "Bullish trend conflicts with -DI above +DI."
                )

            if (
                trend == self.TREND_BEARISH
                and plus_di > minus_di
            ):
                conflicts.append(
                    "Bearish trend conflicts with +DI above -DI."
                )

        if rsi is not None:
            if (
                trend == self.TREND_BULLISH
                and rsi >= 70
            ):
                conflicts.append(
                    "Bullish trend is currently accompanied by overbought RSI."
                )

            if (
                trend == self.TREND_BEARISH
                and rsi <= 30
            ):
                conflicts.append(
                    "Bearish trend is currently accompanied by oversold RSI."
                )

        return conflicts

    @staticmethod
    def _indicator_source(
        market: Mapping[str, Any],
    ) -> dict[str, Any]:
        indicators = market.get(
            "indicators"
        )

        if isinstance(
            indicators,
            Mapping,
        ):
            combined = dict(
                market
            )

            combined.update(
                dict(
                    indicators
                )
            )

            return combined

        return dict(
            market
        )

    @classmethod
    def _first_num(
        cls,
        primary: Mapping[str, Any],
        secondary: Mapping[str, Any],
        *,
        keys: Sequence[str],
    ) -> float | None:
        value = cls._num(
            primary,
            *keys,
        )

        if value is not None:
            return value

        return cls._num(
            secondary,
            *keys,
        )

    @staticmethod
    def _num(
        source: Any,
        *keys: str,
    ) -> float | None:
        if not isinstance(
            source,
            Mapping,
        ):
            return None

        for key in keys:
            if key not in source:
                continue

            raw = source.get(
                key
            )

            if raw is None:
                continue

            if isinstance(
                raw,
                bool,
            ):
                continue

            try:
                value = float(
                    raw
                )
            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                continue

            if not isfinite(
                value
            ):
                continue

            return value

        return None

    @staticmethod
    def _safe_float(
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
            OverflowError,
        ):
            return None

        if not isfinite(
            result
        ):
            return None

        return result

    @staticmethod
    def _available_fields(
        values: Mapping[str, Any],
    ) -> list[str]:
        return [
            key
            for key, value in values.items()
            if value is not None
        ]


market_regime_service = MarketRegimeService()


__all__ = [
    "RegimeEvidence",
    "MarketRegimeService",
    "market_regime_service",
]