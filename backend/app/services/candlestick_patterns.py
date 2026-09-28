from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass(frozen=True, slots=True)
class Candle:
    index: int
    open: float
    high: float
    low: float
    close: float

    @property
    def span(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def body_high(self) -> float:
        return max(self.open, self.close)

    @property
    def body_low(self) -> float:
        return min(self.open, self.close)

    @property
    def upper_wick(self) -> float:
        return max(
            0.0,
            self.high - self.body_high,
        )

    @property
    def lower_wick(self) -> float:
        return max(
            0.0,
            self.body_low - self.low,
        )

    @property
    def body_ratio(self) -> float:
        if self.span <= 0:
            return 0.0

        return self.body / self.span

    @property
    def upper_wick_ratio(self) -> float:
        if self.span <= 0:
            return 0.0

        return self.upper_wick / self.span

    @property
    def lower_wick_ratio(self) -> float:
        if self.span <= 0:
            return 0.0

        return self.lower_wick / self.span

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def neutral(self) -> bool:
        return self.close == self.open

    @property
    def midpoint(self) -> float:
        return (
            self.open
            + self.close
        ) / 2.0

    @property
    def range_midpoint(self) -> float:
        return (
            self.high
            + self.low
        ) / 2.0


@dataclass(frozen=True, slots=True)
class CandlestickPattern:
    name: str
    direction: str
    confidence: float
    start_index: int
    end_index: int
    evidence: str
    candle_count: int
    metadata: dict[str, Any]

    def dump(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "direction": self.direction,
            "confidence": self.confidence,
            "bar_index": self.end_index,
            "start_bar_index": self.start_index,
            "end_bar_index": self.end_index,
            "candle_count": self.candle_count,
            "evidence": self.evidence,
            "metadata": dict(self.metadata),
        }


# =============================================================================
# SERVICE
# =============================================================================


class CandlestickPatternService:
    """
    PhoenixTrend candlestick-pattern detector.

    The detector operates ONLY on supplied OHLC bars.

    It does not:

        - fabricate missing candles
        - fabricate OHLC values
        - interpolate invalid bars
        - convert patterns into trade orders
        - declare BUY/SELL decisions
        - declare execution safety
        - perform risk approval
        - infer market regime without supplied price history

    Pattern confidence is deterministic pattern-quality scoring based on
    actual supplied candle geometry. It is not a probability of profit.

    Invalid bars are rejected rather than silently converted into valid data.

    Supported single-candle patterns include:

        Doji
        Long-Legged Doji
        Dragonfly Doji
        Gravestone Doji
        Spinning Top
        Hammer
        Hanging Man
        Inverted Hammer
        Shooting Star
        Bullish Marubozu
        Bearish Marubozu

    Supported two-candle patterns include:

        Bullish Engulfing
        Bearish Engulfing
        Bullish Harami
        Bearish Harami
        Harami Cross
        Piercing Line
        Dark Cloud Cover
        Tweezer Bottom
        Tweezer Top
        Bullish Kicker
        Bearish Kicker

    Supported three-candle patterns include:

        Morning Star
        Evening Star
        Morning Doji Star
        Evening Doji Star
        Three White Soldiers
        Three Black Crows
        Three Inside Up
        Three Inside Down
        Three Outside Up
        Three Outside Down

    Additional continuation / multi-candle structures include:

        Rising Three Methods
        Falling Three Methods

    Trend-dependent reversal names are emitted only when enough prior bars
    exist to establish a deterministic local trend from supplied closes.
    """

    DIRECTION_BULLISH = "BULLISH"
    DIRECTION_BEARISH = "BEARISH"
    DIRECTION_NEUTRAL = "NEUTRAL"

    # -------------------------------------------------------------------------
    # Candle geometry thresholds
    # -------------------------------------------------------------------------

    DOJI_BODY_RATIO = 0.08
    VERY_SMALL_BODY_RATIO = 0.12
    SMALL_BODY_RATIO = 0.30
    LARGE_BODY_RATIO = 0.55
    VERY_LARGE_BODY_RATIO = 0.72

    SMALL_WICK_RATIO = 0.10
    MARUBOZU_MAX_WICK_RATIO = 0.08

    HAMMER_MIN_LOWER_WICK_BODY_MULTIPLE = 2.0
    HAMMER_MIN_LOWER_WICK_RANGE_RATIO = 0.45
    HAMMER_MAX_UPPER_WICK_RANGE_RATIO = 0.15

    STAR_MAX_BODY_RATIO = 0.35

    TREND_LOOKBACK = 5
    TREND_MIN_BARS = 3

    # -------------------------------------------------------------------------
    # Confidence bounds
    # -------------------------------------------------------------------------

    MIN_CONFIDENCE = 0.0
    MAX_CONFIDENCE = 1.0

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def analyze(
        self,
        bars: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Analyze the latest valid contiguous candle sequence.

        If an invalid bar occurs, bars before that invalid point are not joined
        to bars after it for multi-candle pattern detection. This prevents a
        missing/invalid candle from being silently removed and creating a false
        adjacent-candle pattern.
        """

        parsed = self._parse_contiguous_tail(
            bars
        )

        if not parsed:
            return []

        patterns: list[CandlestickPattern] = []

        patterns.extend(
            self._single_candle_patterns(
                parsed
            )
        )

        if len(parsed) >= 2:
            patterns.extend(
                self._two_candle_patterns(
                    parsed
                )
            )

        if len(parsed) >= 3:
            patterns.extend(
                self._three_candle_patterns(
                    parsed
                )
            )

        if len(parsed) >= 5:
            patterns.extend(
                self._five_candle_patterns(
                    parsed
                )
            )

        patterns = self._deduplicate(
            patterns
        )

        patterns.sort(
            key=lambda pattern: (
                -pattern.confidence,
                pattern.name,
                pattern.start_index,
                pattern.end_index,
            )
        )

        return [
            pattern.dump()
            for pattern in patterns
        ]

    def analyze_all(
        self,
        bars: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Analyze every valid contiguous window in supplied history.

        Unlike analyze(), which focuses on the latest candle, this method
        returns historical detections across the supplied bars.

        Invalid bars break continuity.
        """

        if not bars:
            return []

        parsed: list[Candle | None] = [
            self._parse_bar(
                raw,
                index,
            )
            for index, raw in enumerate(
                bars
            )
        ]

        output: list[CandlestickPattern] = []
        contiguous: list[Candle] = []

        for candle in parsed:
            if candle is None:
                contiguous = []
                continue

            contiguous.append(
                candle
            )

            output.extend(
                self._single_candle_patterns(
                    contiguous
                )
            )

            if len(contiguous) >= 2:
                output.extend(
                    self._two_candle_patterns(
                        contiguous
                    )
                )

            if len(contiguous) >= 3:
                output.extend(
                    self._three_candle_patterns(
                        contiguous
                    )
                )

            if len(contiguous) >= 5:
                output.extend(
                    self._five_candle_patterns(
                        contiguous
                    )
                )

        output = self._deduplicate(
            output
        )

        output.sort(
            key=lambda pattern: (
                pattern.end_index,
                -pattern.confidence,
                pattern.name,
            )
        )

        return [
            pattern.dump()
            for pattern in output
        ]

    # =========================================================================
    # PARSING
    # =========================================================================

    def _parse_contiguous_tail(
        self,
        bars: Sequence[Mapping[str, Any]],
    ) -> list[Candle]:
        if not bars:
            return []

        output: list[Candle] = []

        for index in range(
            len(bars) - 1,
            -1,
            -1,
        ):
            candle = self._parse_bar(
                bars[index],
                index,
            )

            if candle is None:
                break

            output.append(
                candle
            )

        output.reverse()

        return output

    def _parse_bar(
        self,
        raw: Mapping[str, Any],
        index: int,
    ) -> Candle | None:
        if not isinstance(
            raw,
            Mapping,
        ):
            return None

        open_value = self._number(
            self._first(
                raw,
                "open",
                "o",
            )
        )

        high_value = self._number(
            self._first(
                raw,
                "high",
                "h",
            )
        )

        low_value = self._number(
            self._first(
                raw,
                "low",
                "l",
            )
        )

        close_value = self._number(
            self._first(
                raw,
                "close",
                "c",
            )
        )

        if any(
            value is None
            for value in (
                open_value,
                high_value,
                low_value,
                close_value,
            )
        ):
            return None

        assert open_value is not None
        assert high_value is not None
        assert low_value is not None
        assert close_value is not None

        if any(
            value <= 0
            for value in (
                open_value,
                high_value,
                low_value,
                close_value,
            )
        ):
            return None

        if high_value < low_value:
            return None

        if high_value < max(
            open_value,
            close_value,
        ):
            return None

        if low_value > min(
            open_value,
            close_value,
        ):
            return None

        return Candle(
            index=index,
            open=open_value,
            high=high_value,
            low=low_value,
            close=close_value,
        )

    # =========================================================================
    # SINGLE-CANDLE PATTERNS
    # =========================================================================

    def _single_candle_patterns(
        self,
        bars: Sequence[Candle],
    ) -> list[CandlestickPattern]:
        current = bars[-1]

        output: list[CandlestickPattern] = []

        trend = self._prior_trend(
            bars,
            exclude_latest=1,
        )

        # ---------------------------------------------------------------------
        # DOJI FAMILY
        # ---------------------------------------------------------------------

        if self._is_doji(
            current
        ):
            wick_balance = self._wick_balance(
                current
            )

            confidence = self._quality(
                base=0.56,
                components=(
                    1.0 - self._bounded_ratio(
                        current.body_ratio,
                        self.DOJI_BODY_RATIO,
                    ),
                    wick_balance,
                ),
                bonus=0.10,
            )

            output.append(
                self._pattern(
                    name="Doji",
                    direction=self.DIRECTION_NEUTRAL,
                    confidence=confidence,
                    candles=(current,),
                    evidence=(
                        "Real body is very small relative to the "
                        "supplied candle range"
                    ),
                    metadata=self._geometry_metadata(
                        current
                    ),
                )
            )

            if (
                current.lower_wick_ratio >= 0.60
                and current.upper_wick_ratio <= 0.12
            ):
                confidence = self._quality(
                    base=0.62,
                    components=(
                        current.lower_wick_ratio,
                        1.0 - current.upper_wick_ratio,
                    ),
                    bonus=0.12,
                )

                output.append(
                    self._pattern(
                        name="Dragonfly Doji",
                        direction=(
                            self.DIRECTION_BULLISH
                            if trend == "DOWN"
                            else self.DIRECTION_NEUTRAL
                        ),
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Doji body with dominant lower wick and "
                            "minimal upper wick"
                        ),
                        metadata={
                            **self._geometry_metadata(
                                current
                            ),
                            "prior_trend": trend,
                        },
                    )
                )

            if (
                current.upper_wick_ratio >= 0.60
                and current.lower_wick_ratio <= 0.12
            ):
                confidence = self._quality(
                    base=0.62,
                    components=(
                        current.upper_wick_ratio,
                        1.0 - current.lower_wick_ratio,
                    ),
                    bonus=0.12,
                )

                output.append(
                    self._pattern(
                        name="Gravestone Doji",
                        direction=(
                            self.DIRECTION_BEARISH
                            if trend == "UP"
                            else self.DIRECTION_NEUTRAL
                        ),
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Doji body with dominant upper wick and "
                            "minimal lower wick"
                        ),
                        metadata={
                            **self._geometry_metadata(
                                current
                            ),
                            "prior_trend": trend,
                        },
                    )
                )

            if (
                current.upper_wick_ratio >= 0.30
                and current.lower_wick_ratio >= 0.30
            ):
                confidence = self._quality(
                    base=0.58,
                    components=(
                        current.upper_wick_ratio,
                        current.lower_wick_ratio,
                    ),
                    bonus=0.08,
                )

                output.append(
                    self._pattern(
                        name="Long-Legged Doji",
                        direction=self.DIRECTION_NEUTRAL,
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Doji body with substantial upper and lower wicks"
                        ),
                        metadata=self._geometry_metadata(
                            current
                        ),
                    )
                )

        # ---------------------------------------------------------------------
        # SPINNING TOP
        # ---------------------------------------------------------------------

        if (
            not self._is_doji(
                current
            )
            and current.body_ratio <= self.SMALL_BODY_RATIO
            and current.upper_wick_ratio >= 0.20
            and current.lower_wick_ratio >= 0.20
        ):
            confidence = self._quality(
                base=0.54,
                components=(
                    1.0 - current.body_ratio,
                    current.upper_wick_ratio,
                    current.lower_wick_ratio,
                ),
                bonus=0.08,
            )

            output.append(
                self._pattern(
                    name="Spinning Top",
                    direction=self.DIRECTION_NEUTRAL,
                    confidence=confidence,
                    candles=(current,),
                    evidence=(
                        "Small real body with meaningful upper and lower wicks"
                    ),
                    metadata=self._geometry_metadata(
                        current
                    ),
                )
            )

        # ---------------------------------------------------------------------
        # HAMMER / HANGING MAN
        # ---------------------------------------------------------------------

        hammer_shape = (
            current.lower_wick
            >= max(
                current.body
                * self.HAMMER_MIN_LOWER_WICK_BODY_MULTIPLE,
                current.span
                * self.HAMMER_MIN_LOWER_WICK_RANGE_RATIO,
            )
            and current.upper_wick
            <= current.span
            * self.HAMMER_MAX_UPPER_WICK_RANGE_RATIO
            and current.body_ratio
            <= 0.45
        )

        if hammer_shape:
            confidence = self._quality(
                base=0.62,
                components=(
                    current.lower_wick_ratio,
                    1.0 - current.upper_wick_ratio,
                    1.0 - current.body_ratio,
                ),
                bonus=0.14,
            )

            if trend == "DOWN":
                output.append(
                    self._pattern(
                        name="Hammer",
                        direction=self.DIRECTION_BULLISH,
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Long lower rejection wick after supplied "
                            "price history indicates a local downtrend"
                        ),
                        metadata={
                            **self._geometry_metadata(
                                current
                            ),
                            "prior_trend": trend,
                        },
                    )
                )

            elif trend == "UP":
                output.append(
                    self._pattern(
                        name="Hanging Man",
                        direction=self.DIRECTION_BEARISH,
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Long lower rejection wick after supplied "
                            "price history indicates a local uptrend"
                        ),
                        metadata={
                            **self._geometry_metadata(
                                current
                            ),
                            "prior_trend": trend,
                        },
                    )
                )

            else:
                output.append(
                    self._pattern(
                        name="Hammer-Shaped Candle",
                        direction=self.DIRECTION_NEUTRAL,
                        confidence=self._cap(
                            confidence - 0.10
                        ),
                        candles=(current,),
                        evidence=(
                            "Hammer geometry detected but supplied history "
                            "does not establish the trend required for a "
                            "directional reversal label"
                        ),
                        metadata={
                            **self._geometry_metadata(
                                current
                            ),
                            "prior_trend": trend,
                        },
                    )
                )

        # ---------------------------------------------------------------------
        # INVERTED HAMMER / SHOOTING STAR
        # ---------------------------------------------------------------------

        inverted_shape = (
            current.upper_wick
            >= max(
                current.body
                * self.HAMMER_MIN_LOWER_WICK_BODY_MULTIPLE,
                current.span
                * self.HAMMER_MIN_LOWER_WICK_RANGE_RATIO,
            )
            and current.lower_wick
            <= current.span
            * self.HAMMER_MAX_UPPER_WICK_RANGE_RATIO
            and current.body_ratio
            <= 0.45
        )

        if inverted_shape:
            confidence = self._quality(
                base=0.62,
                components=(
                    current.upper_wick_ratio,
                    1.0 - current.lower_wick_ratio,
                    1.0 - current.body_ratio,
                ),
                bonus=0.14,
            )

            if trend == "DOWN":
                output.append(
                    self._pattern(
                        name="Inverted Hammer",
                        direction=self.DIRECTION_BULLISH,
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Long upper rejection wick after supplied "
                            "price history indicates a local downtrend"
                        ),
                        metadata={
                            **self._geometry_metadata(
                                current
                            ),
                            "prior_trend": trend,
                        },
                    )
                )

            elif trend == "UP":
                output.append(
                    self._pattern(
                        name="Shooting Star",
                        direction=self.DIRECTION_BEARISH,
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Long upper rejection wick after supplied "
                            "price history indicates a local uptrend"
                        ),
                        metadata={
                            **self._geometry_metadata(
                                current
                            ),
                            "prior_trend": trend,
                        },
                    )
                )

            else:
                output.append(
                    self._pattern(
                        name="Inverted-Hammer-Shaped Candle",
                        direction=self.DIRECTION_NEUTRAL,
                        confidence=self._cap(
                            confidence - 0.10
                        ),
                        candles=(current,),
                        evidence=(
                            "Inverted-hammer geometry detected but supplied "
                            "history does not establish the trend required "
                            "for a directional reversal label"
                        ),
                        metadata={
                            **self._geometry_metadata(
                                current
                            ),
                            "prior_trend": trend,
                        },
                    )
                )

        # ---------------------------------------------------------------------
        # MARUBOZU
        # ---------------------------------------------------------------------

        if (
            current.body_ratio >= self.VERY_LARGE_BODY_RATIO
            and current.upper_wick_ratio
            <= self.MARUBOZU_MAX_WICK_RATIO
            and current.lower_wick_ratio
            <= self.MARUBOZU_MAX_WICK_RATIO
        ):
            confidence = self._quality(
                base=0.68,
                components=(
                    current.body_ratio,
                    1.0 - current.upper_wick_ratio,
                    1.0 - current.lower_wick_ratio,
                ),
                bonus=0.12,
            )

            if current.bullish:
                output.append(
                    self._pattern(
                        name="Bullish Marubozu",
                        direction=self.DIRECTION_BULLISH,
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Large bullish body with minimal upper "
                            "and lower wicks"
                        ),
                        metadata=self._geometry_metadata(
                            current
                        ),
                    )
                )

            elif current.bearish:
                output.append(
                    self._pattern(
                        name="Bearish Marubozu",
                        direction=self.DIRECTION_BEARISH,
                        confidence=confidence,
                        candles=(current,),
                        evidence=(
                            "Large bearish body with minimal upper "
                            "and lower wicks"
                        ),
                        metadata=self._geometry_metadata(
                            current
                        ),
                    )
                )

        return output

    # =========================================================================
    # TWO-CANDLE PATTERNS
    # =========================================================================

    def _two_candle_patterns(
        self,
        bars: Sequence[Candle],
    ) -> list[CandlestickPattern]:
        previous = bars[-2]
        current = bars[-1]

        output: list[CandlestickPattern] = []

        trend = self._prior_trend(
            bars,
            exclude_latest=2,
        )

        # ---------------------------------------------------------------------
        # BULLISH ENGULFING
        # ---------------------------------------------------------------------

        bullish_engulfing = (
            previous.bearish
            and current.bullish
            and current.body_low <= previous.body_low
            and current.body_high >= previous.body_high
            and current.body > previous.body
        )

        if bullish_engulfing:
            engulf_ratio = self._safe_ratio(
                current.body,
                previous.body,
            )

            confidence = self._quality(
                base=0.70,
                components=(
                    self._clamp01(
                        engulf_ratio / 1.5
                    ),
                    current.body_ratio,
                    previous.body_ratio,
                ),
                bonus=(
                    0.08
                    if trend == "DOWN"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Bullish Engulfing",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        previous,
                        current,
                    ),
                    evidence=(
                        "Current bullish real body fully engulfs the "
                        "previous bearish real body"
                    ),
                    metadata={
                        "prior_trend": trend,
                        "engulf_ratio": round(
                            engulf_ratio,
                            6,
                        ),
                    },
                )
            )

        # ---------------------------------------------------------------------
        # BEARISH ENGULFING
        # ---------------------------------------------------------------------

        bearish_engulfing = (
            previous.bullish
            and current.bearish
            and current.body_low <= previous.body_low
            and current.body_high >= previous.body_high
            and current.body > previous.body
        )

        if bearish_engulfing:
            engulf_ratio = self._safe_ratio(
                current.body,
                previous.body,
            )

            confidence = self._quality(
                base=0.70,
                components=(
                    self._clamp01(
                        engulf_ratio / 1.5
                    ),
                    current.body_ratio,
                    previous.body_ratio,
                ),
                bonus=(
                    0.08
                    if trend == "UP"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Bearish Engulfing",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        previous,
                        current,
                    ),
                    evidence=(
                        "Current bearish real body fully engulfs the "
                        "previous bullish real body"
                    ),
                    metadata={
                        "prior_trend": trend,
                        "engulf_ratio": round(
                            engulf_ratio,
                            6,
                        ),
                    },
                )
            )

        # ---------------------------------------------------------------------
        # HARAMI / HARAMI CROSS
        # ---------------------------------------------------------------------

        inside_body = (
            current.body_high
            <= previous.body_high
            and current.body_low
            >= previous.body_low
        )

        if (
            inside_body
            and current.body
            < previous.body
            and previous.body_ratio
            >= self.LARGE_BODY_RATIO
        ):
            if self._is_doji(
                current
            ):
                if previous.bearish:
                    direction = self.DIRECTION_BULLISH
                elif previous.bullish:
                    direction = self.DIRECTION_BEARISH
                else:
                    direction = self.DIRECTION_NEUTRAL

                confidence = self._quality(
                    base=0.64,
                    components=(
                        previous.body_ratio,
                        1.0 - current.body_ratio,
                    ),
                    bonus=0.08,
                )

                output.append(
                    self._pattern(
                        name="Harami Cross",
                        direction=direction,
                        confidence=confidence,
                        candles=(
                            previous,
                            current,
                        ),
                        evidence=(
                            "Doji real body is contained within the "
                            "previous large real body"
                        ),
                        metadata={
                            "prior_trend": trend,
                        },
                    )
                )

            elif previous.bearish and current.bullish:
                confidence = self._quality(
                    base=0.61,
                    components=(
                        previous.body_ratio,
                        1.0 - current.body_ratio,
                    ),
                    bonus=(
                        0.06
                        if trend == "DOWN"
                        else 0.0
                    ),
                )

                output.append(
                    self._pattern(
                        name="Bullish Harami",
                        direction=self.DIRECTION_BULLISH,
                        confidence=confidence,
                        candles=(
                            previous,
                            current,
                        ),
                        evidence=(
                            "Smaller bullish real body is contained "
                            "within the previous bearish body"
                        ),
                        metadata={
                            "prior_trend": trend,
                        },
                    )
                )

            elif previous.bullish and current.bearish:
                confidence = self._quality(
                    base=0.61,
                    components=(
                        previous.body_ratio,
                        1.0 - current.body_ratio,
                    ),
                    bonus=(
                        0.06
                        if trend == "UP"
                        else 0.0
                    ),
                )

                output.append(
                    self._pattern(
                        name="Bearish Harami",
                        direction=self.DIRECTION_BEARISH,
                        confidence=confidence,
                        candles=(
                            previous,
                            current,
                        ),
                        evidence=(
                            "Smaller bearish real body is contained "
                            "within the previous bullish body"
                        ),
                        metadata={
                            "prior_trend": trend,
                        },
                    )
                )

        # ---------------------------------------------------------------------
        # PIERCING LINE
        # ---------------------------------------------------------------------

        if (
            previous.bearish
            and previous.body_ratio
            >= self.LARGE_BODY_RATIO
            and current.bullish
            and current.open
            <= previous.close
            and current.close
            > previous.midpoint
            and current.close
            < previous.open
        ):
            penetration = self._safe_ratio(
                current.close
                - previous.close,
                previous.body,
            )

            confidence = self._quality(
                base=0.66,
                components=(
                    self._clamp01(
                        penetration
                    ),
                    previous.body_ratio,
                    current.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "DOWN"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Piercing Line",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        previous,
                        current,
                    ),
                    evidence=(
                        "Bullish candle closes above the midpoint of "
                        "the previous large bearish body"
                    ),
                    metadata={
                        "prior_trend": trend,
                        "penetration_ratio": round(
                            penetration,
                            6,
                        ),
                    },
                )
            )

        # ---------------------------------------------------------------------
        # DARK CLOUD COVER
        # ---------------------------------------------------------------------

        if (
            previous.bullish
            and previous.body_ratio
            >= self.LARGE_BODY_RATIO
            and current.bearish
            and current.open
            >= previous.close
            and current.close
            < previous.midpoint
            and current.close
            > previous.open
        ):
            penetration = self._safe_ratio(
                previous.close
                - current.close,
                previous.body,
            )

            confidence = self._quality(
                base=0.66,
                components=(
                    self._clamp01(
                        penetration
                    ),
                    previous.body_ratio,
                    current.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "UP"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Dark Cloud Cover",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        previous,
                        current,
                    ),
                    evidence=(
                        "Bearish candle closes below the midpoint of "
                        "the previous large bullish body"
                    ),
                    metadata={
                        "prior_trend": trend,
                        "penetration_ratio": round(
                            penetration,
                            6,
                        ),
                    },
                )
            )

        # ---------------------------------------------------------------------
        # TWEEZERS
        # ---------------------------------------------------------------------

        tolerance = self._price_tolerance(
            previous,
            current,
        )

        if (
            previous.bearish
            and current.bullish
            and abs(
                previous.low
                - current.low
            )
            <= tolerance
        ):
            confidence = self._quality(
                base=0.60,
                components=(
                    self._similarity(
                        previous.low,
                        current.low,
                        tolerance,
                    ),
                    current.body_ratio,
                    previous.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "DOWN"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Tweezer Bottom",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        previous,
                        current,
                    ),
                    evidence=(
                        "Adjacent opposite-direction candles reject "
                        "approximately the same supplied low"
                    ),
                    metadata={
                        "prior_trend": trend,
                        "price_tolerance": tolerance,
                    },
                )
            )

        if (
            previous.bullish
            and current.bearish
            and abs(
                previous.high
                - current.high
            )
            <= tolerance
        ):
            confidence = self._quality(
                base=0.60,
                components=(
                    self._similarity(
                        previous.high,
                        current.high,
                        tolerance,
                    ),
                    current.body_ratio,
                    previous.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "UP"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Tweezer Top",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        previous,
                        current,
                    ),
                    evidence=(
                        "Adjacent opposite-direction candles reject "
                        "approximately the same supplied high"
                    ),
                    metadata={
                        "prior_trend": trend,
                        "price_tolerance": tolerance,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # KICKERS
        # ---------------------------------------------------------------------

        if (
            previous.bearish
            and current.bullish
            and previous.body_ratio
            >= self.LARGE_BODY_RATIO
            and current.body_ratio
            >= self.LARGE_BODY_RATIO
            and current.body_low
            > previous.body_high
        ):
            confidence = self._quality(
                base=0.76,
                components=(
                    previous.body_ratio,
                    current.body_ratio,
                ),
                bonus=0.10,
            )

            output.append(
                self._pattern(
                    name="Bullish Kicker",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        previous,
                        current,
                    ),
                    evidence=(
                        "Large bearish candle is followed by a large "
                        "bullish candle whose real body gaps above it"
                    ),
                    metadata={
                        "prior_trend": trend,
                        "body_gap": (
                            current.body_low
                            - previous.body_high
                        ),
                    },
                )
            )

        if (
            previous.bullish
            and current.bearish
            and previous.body_ratio
            >= self.LARGE_BODY_RATIO
            and current.body_ratio
            >= self.LARGE_BODY_RATIO
            and current.body_high
            < previous.body_low
        ):
            confidence = self._quality(
                base=0.76,
                components=(
                    previous.body_ratio,
                    current.body_ratio,
                ),
                bonus=0.10,
            )

            output.append(
                self._pattern(
                    name="Bearish Kicker",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        previous,
                        current,
                    ),
                    evidence=(
                        "Large bullish candle is followed by a large "
                        "bearish candle whose real body gaps below it"
                    ),
                    metadata={
                        "prior_trend": trend,
                        "body_gap": (
                            previous.body_low
                            - current.body_high
                        ),
                    },
                )
            )

        return output

    # =========================================================================
    # THREE-CANDLE PATTERNS
    # =========================================================================

    def _three_candle_patterns(
        self,
        bars: Sequence[Candle],
    ) -> list[CandlestickPattern]:
        first = bars[-3]
        second = bars[-2]
        third = bars[-1]

        output: list[CandlestickPattern] = []

        trend = self._prior_trend(
            bars,
            exclude_latest=3,
        )

        # ---------------------------------------------------------------------
        # MORNING STAR / MORNING DOJI STAR
        # ---------------------------------------------------------------------

        morning_structure = (
            first.bearish
            and first.body_ratio
            >= self.LARGE_BODY_RATIO
            and second.body_ratio
            <= self.STAR_MAX_BODY_RATIO
            and third.bullish
            and third.close
            > first.midpoint
        )

        if morning_structure:
            name = (
                "Morning Doji Star"
                if self._is_doji(
                    second
                )
                else "Morning Star"
            )

            confidence = self._quality(
                base=(
                    0.75
                    if name == "Morning Doji Star"
                    else 0.72
                ),
                components=(
                    first.body_ratio,
                    1.0 - second.body_ratio,
                    third.body_ratio,
                    self._clamp01(
                        self._safe_ratio(
                            third.close
                            - first.close,
                            first.body,
                        )
                    ),
                ),
                bonus=(
                    0.07
                    if trend == "DOWN"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name=name,
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                    ),
                    evidence=(
                        "Large bearish candle, small-bodied transition "
                        "candle, then bullish recovery above the first "
                        "body midpoint"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # EVENING STAR / EVENING DOJI STAR
        # ---------------------------------------------------------------------

        evening_structure = (
            first.bullish
            and first.body_ratio
            >= self.LARGE_BODY_RATIO
            and second.body_ratio
            <= self.STAR_MAX_BODY_RATIO
            and third.bearish
            and third.close
            < first.midpoint
        )

        if evening_structure:
            name = (
                "Evening Doji Star"
                if self._is_doji(
                    second
                )
                else "Evening Star"
            )

            confidence = self._quality(
                base=(
                    0.75
                    if name == "Evening Doji Star"
                    else 0.72
                ),
                components=(
                    first.body_ratio,
                    1.0 - second.body_ratio,
                    third.body_ratio,
                    self._clamp01(
                        self._safe_ratio(
                            first.close
                            - third.close,
                            first.body,
                        )
                    ),
                ),
                bonus=(
                    0.07
                    if trend == "UP"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name=name,
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                    ),
                    evidence=(
                        "Large bullish candle, small-bodied transition "
                        "candle, then bearish decline below the first "
                        "body midpoint"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # THREE WHITE SOLDIERS
        # ---------------------------------------------------------------------

        if (
            first.bullish
            and second.bullish
            and third.bullish
            and first.body_ratio
            >= self.LARGE_BODY_RATIO
            and second.body_ratio
            >= self.LARGE_BODY_RATIO
            and third.body_ratio
            >= self.LARGE_BODY_RATIO
            and second.close
            > first.close
            and third.close
            > second.close
            and self._opens_within_body(
                second,
                first,
            )
            and self._opens_within_body(
                third,
                second,
            )
        ):
            confidence = self._quality(
                base=0.73,
                components=(
                    first.body_ratio,
                    second.body_ratio,
                    third.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "DOWN"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Three White Soldiers",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                    ),
                    evidence=(
                        "Three consecutive large bullish candles close "
                        "progressively higher with opens inside prior bodies"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # THREE BLACK CROWS
        # ---------------------------------------------------------------------

        if (
            first.bearish
            and second.bearish
            and third.bearish
            and first.body_ratio
            >= self.LARGE_BODY_RATIO
            and second.body_ratio
            >= self.LARGE_BODY_RATIO
            and third.body_ratio
            >= self.LARGE_BODY_RATIO
            and second.close
            < first.close
            and third.close
            < second.close
            and self._opens_within_body(
                second,
                first,
            )
            and self._opens_within_body(
                third,
                second,
            )
        ):
            confidence = self._quality(
                base=0.73,
                components=(
                    first.body_ratio,
                    second.body_ratio,
                    third.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "UP"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Three Black Crows",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                    ),
                    evidence=(
                        "Three consecutive large bearish candles close "
                        "progressively lower with opens inside prior bodies"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # THREE INSIDE UP
        # ---------------------------------------------------------------------

        bullish_harami = (
            first.bearish
            and first.body_ratio
            >= self.LARGE_BODY_RATIO
            and second.bullish
            and second.body_high
            <= first.body_high
            and second.body_low
            >= first.body_low
            and second.body
            < first.body
        )

        if (
            bullish_harami
            and third.bullish
            and third.close
            > first.open
        ):
            confidence = self._quality(
                base=0.70,
                components=(
                    first.body_ratio,
                    second.body_ratio,
                    third.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "DOWN"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Three Inside Up",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                    ),
                    evidence=(
                        "Bullish harami structure is confirmed by a "
                        "third bullish close above the first candle body"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # THREE INSIDE DOWN
        # ---------------------------------------------------------------------

        bearish_harami = (
            first.bullish
            and first.body_ratio
            >= self.LARGE_BODY_RATIO
            and second.bearish
            and second.body_high
            <= first.body_high
            and second.body_low
            >= first.body_low
            and second.body
            < first.body
        )

        if (
            bearish_harami
            and third.bearish
            and third.close
            < first.open
        ):
            confidence = self._quality(
                base=0.70,
                components=(
                    first.body_ratio,
                    second.body_ratio,
                    third.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "UP"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Three Inside Down",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                    ),
                    evidence=(
                        "Bearish harami structure is confirmed by a "
                        "third bearish close below the first candle body"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # THREE OUTSIDE UP
        # ---------------------------------------------------------------------

        second_bullish_engulfing = (
            first.bearish
            and second.bullish
            and second.body_low
            <= first.body_low
            and second.body_high
            >= first.body_high
            and second.body
            > first.body
        )

        if (
            second_bullish_engulfing
            and third.bullish
            and third.close
            > second.close
        ):
            confidence = self._quality(
                base=0.73,
                components=(
                    first.body_ratio,
                    second.body_ratio,
                    third.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "DOWN"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Three Outside Up",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                    ),
                    evidence=(
                        "Bullish engulfing structure is followed by "
                        "another higher bullish close"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # THREE OUTSIDE DOWN
        # ---------------------------------------------------------------------

        second_bearish_engulfing = (
            first.bullish
            and second.bearish
            and second.body_low
            <= first.body_low
            and second.body_high
            >= first.body_high
            and second.body
            > first.body
        )

        if (
            second_bearish_engulfing
            and third.bearish
            and third.close
            < second.close
        ):
            confidence = self._quality(
                base=0.73,
                components=(
                    first.body_ratio,
                    second.body_ratio,
                    third.body_ratio,
                ),
                bonus=(
                    0.06
                    if trend == "UP"
                    else 0.0
                ),
            )

            output.append(
                self._pattern(
                    name="Three Outside Down",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                    ),
                    evidence=(
                        "Bearish engulfing structure is followed by "
                        "another lower bearish close"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        return output

    # =========================================================================
    # FIVE-CANDLE PATTERNS
    # =========================================================================

    def _five_candle_patterns(
        self,
        bars: Sequence[Candle],
    ) -> list[CandlestickPattern]:
        first, second, third, fourth, fifth = bars[-5:]

        output: list[CandlestickPattern] = []

        trend = self._prior_trend(
            bars,
            exclude_latest=5,
        )

        middle = (
            second,
            third,
            fourth,
        )

        # ---------------------------------------------------------------------
        # RISING THREE METHODS
        # ---------------------------------------------------------------------

        rising_middle_inside = all(
            candle.high <= first.high
            and candle.low >= first.low
            for candle in middle
        )

        rising_middle_small = all(
            candle.body_ratio
            <= self.SMALL_BODY_RATIO
            for candle in middle
        )

        if (
            first.bullish
            and first.body_ratio
            >= self.LARGE_BODY_RATIO
            and rising_middle_inside
            and rising_middle_small
            and fifth.bullish
            and fifth.body_ratio
            >= self.LARGE_BODY_RATIO
            and fifth.close
            > first.close
        ):
            confidence = self._quality(
                base=0.70,
                components=(
                    first.body_ratio,
                    fifth.body_ratio,
                    self._clamp01(
                        self._safe_ratio(
                            fifth.close
                            - first.close,
                            first.body,
                        )
                    ),
                ),
                bonus=0.08,
            )

            output.append(
                self._pattern(
                    name="Rising Three Methods",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                        fourth,
                        fifth,
                    ),
                    evidence=(
                        "Large bullish candle is followed by three "
                        "small contained candles and a bullish breakout "
                        "above the first close"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        # ---------------------------------------------------------------------
        # FALLING THREE METHODS
        # ---------------------------------------------------------------------

        falling_middle_inside = all(
            candle.high <= first.high
            and candle.low >= first.low
            for candle in middle
        )

        falling_middle_small = all(
            candle.body_ratio
            <= self.SMALL_BODY_RATIO
            for candle in middle
        )

        if (
            first.bearish
            and first.body_ratio
            >= self.LARGE_BODY_RATIO
            and falling_middle_inside
            and falling_middle_small
            and fifth.bearish
            and fifth.body_ratio
            >= self.LARGE_BODY_RATIO
            and fifth.close
            < first.close
        ):
            confidence = self._quality(
                base=0.70,
                components=(
                    first.body_ratio,
                    fifth.body_ratio,
                    self._clamp01(
                        self._safe_ratio(
                            first.close
                            - fifth.close,
                            first.body,
                        )
                    ),
                ),
                bonus=0.08,
            )

            output.append(
                self._pattern(
                    name="Falling Three Methods",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    candles=(
                        first,
                        second,
                        third,
                        fourth,
                        fifth,
                    ),
                    evidence=(
                        "Large bearish candle is followed by three "
                        "small contained candles and a bearish breakdown "
                        "below the first close"
                    ),
                    metadata={
                        "prior_trend": trend,
                    },
                )
            )

        return output

    # =========================================================================
    # TREND
    # =========================================================================

    def _prior_trend(
        self,
        bars: Sequence[Candle],
        *,
        exclude_latest: int,
    ) -> str | None:
        """
        Determine a small local trend using only supplied closes.

        This is not a market-regime detector. It exists only to avoid labeling
        trend-dependent candlestick shapes as directional reversals without
        prior price context.
        """

        if exclude_latest < 0:
            return None

        end = (
            len(bars)
            - exclude_latest
        )

        if end <= 0:
            return None

        history = list(
            bars[
                max(
                    0,
                    end - self.TREND_LOOKBACK,
                ):
                end
            ]
        )

        if len(history) < self.TREND_MIN_BARS:
            return None

        closes = [
            candle.close
            for candle in history
        ]

        first = closes[0]
        last = closes[-1]

        if first <= 0:
            return None

        net_change = (
            last - first
        ) / first

        rising_steps = sum(
            1
            for left, right in zip(
                closes,
                closes[1:],
            )
            if right > left
        )

        falling_steps = sum(
            1
            for left, right in zip(
                closes,
                closes[1:],
            )
            if right < left
        )

        steps = len(closes) - 1

        if steps <= 0:
            return None

        if (
            net_change > 0
            and rising_steps
            > falling_steps
        ):
            return "UP"

        if (
            net_change < 0
            and falling_steps
            > rising_steps
        ):
            return "DOWN"

        return "SIDEWAYS"

    # =========================================================================
    # PATTERN HELPERS
    # =========================================================================

    def _pattern(
        self,
        *,
        name: str,
        direction: str,
        confidence: float,
        candles: Sequence[Candle],
        evidence: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> CandlestickPattern:
        first = candles[0]
        last = candles[-1]

        return CandlestickPattern(
            name=name,
            direction=direction,
            confidence=round(
                self._cap(
                    confidence
                ),
                6,
            ),
            start_index=first.index,
            end_index=last.index,
            evidence=evidence,
            candle_count=len(candles),
            metadata=dict(
                metadata
                or {}
            ),
        )

    def _is_doji(
        self,
        candle: Candle,
    ) -> bool:
        return (
            candle.body_ratio
            <= self.DOJI_BODY_RATIO
        )

    @staticmethod
    def _opens_within_body(
        candle: Candle,
        previous: Candle,
    ) -> bool:
        return (
            previous.body_low
            <= candle.open
            <= previous.body_high
        )

    @staticmethod
    def _geometry_metadata(
        candle: Candle,
    ) -> dict[str, Any]:
        return {
            "body_ratio": round(
                candle.body_ratio,
                6,
            ),
            "upper_wick_ratio": round(
                candle.upper_wick_ratio,
                6,
            ),
            "lower_wick_ratio": round(
                candle.lower_wick_ratio,
                6,
            ),
        }

    @staticmethod
    def _wick_balance(
        candle: Candle,
    ) -> float:
        total = (
            candle.upper_wick
            + candle.lower_wick
        )

        if total <= 0:
            return 0.0

        difference = abs(
            candle.upper_wick
            - candle.lower_wick
        )

        return max(
            0.0,
            1.0 - difference / total,
        )

    @staticmethod
    def _price_tolerance(
        first: Candle,
        second: Candle,
    ) -> float:
        """
        Geometry-relative tolerance.

        The tolerance is derived from the supplied candle ranges rather than
        from an invented fixed tick size.
        """

        reference_range = max(
            first.span,
            second.span,
        )

        if reference_range <= 0:
            return 0.0

        return (
            reference_range
            * 0.08
        )

    @staticmethod
    def _similarity(
        first: float,
        second: float,
        tolerance: float,
    ) -> float:
        if tolerance <= 0:
            return (
                1.0
                if first == second
                else 0.0
            )

        difference = abs(
            first - second
        )

        return max(
            0.0,
            min(
                1.0,
                1.0
                - difference / tolerance,
            ),
        )

    # =========================================================================
    # CONFIDENCE
    # =========================================================================

    def _quality(
        self,
        *,
        base: float,
        components: Iterable[float],
        bonus: float = 0.0,
    ) -> float:
        values = [
            self._cap(
                value
            )
            for value in components
            if self._finite(
                value
            )
        ]

        if not values:
            return self._cap(
                base + bonus
            )

        average = (
            sum(values)
            / len(values)
        )

        # Confidence is pattern-shape quality, not predicted return.
        quality_adjustment = (
            average
            * 0.12
        )

        return self._cap(
            base
            + quality_adjustment
            + bonus
        )

    # =========================================================================
    # DEDUPLICATION
    # =========================================================================

    @staticmethod
    def _deduplicate(
        patterns: Sequence[CandlestickPattern],
    ) -> list[CandlestickPattern]:
        selected: dict[
            tuple[
                str,
                int,
                int,
            ],
            CandlestickPattern,
        ] = {}

        for pattern in patterns:
            key = (
                pattern.name,
                pattern.start_index,
                pattern.end_index,
            )

            current = selected.get(
                key
            )

            if (
                current is None
                or pattern.confidence
                > current.confidence
            ):
                selected[key] = pattern

        return list(
            selected.values()
        )

    # =========================================================================
    # NUMERIC HELPERS
    # =========================================================================

    @staticmethod
    def _first(
        raw: Mapping[str, Any],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key not in raw:
                continue

            value = raw.get(
                key
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _number(
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
            number = float(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(
            number
        ):
            return None

        return number

    @staticmethod
    def _finite(
        value: Any,
    ) -> bool:
        try:
            return isfinite(
                float(
                    value
                )
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return False

    @classmethod
    def _cap(
        cls,
        value: float,
    ) -> float:
        return max(
            cls.MIN_CONFIDENCE,
            min(
                cls.MAX_CONFIDENCE,
                float(
                    value
                ),
            ),
        )

    @classmethod
    def _clamp01(
        cls,
        value: float,
    ) -> float:
        return cls._cap(
            value
        )

    @staticmethod
    def _safe_ratio(
        numerator: float,
        denominator: float,
    ) -> float:
        if denominator <= 0:
            return 0.0

        return numerator / denominator

    @classmethod
    def _bounded_ratio(
        cls,
        value: float,
        reference: float,
    ) -> float:
        if reference <= 0:
            return 0.0

        return cls._clamp01(
            value / reference
        )


candlestick_pattern_service = CandlestickPatternService()


__all__ = [
    "Candle",
    "CandlestickPattern",
    "CandlestickPatternService",
    "candlestick_pattern_service",
]