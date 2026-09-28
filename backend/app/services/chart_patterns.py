from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence

from .indicators import atr, ema


@dataclass(frozen=True, slots=True)
class PatternMatch:
    name: str
    label: str
    direction: str
    confidence: float
    evidence: list[str]
    preferred_strategies: list[str]
    start_index: int | None = None
    end_index: int | None = None
    breakout_level: float | None = None
    support_level: float | None = None
    resistance_level: float | None = None
    neckline: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SwingPoint:
    index: int
    price: float

    def dump(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "price": self.price,
        }


class ChartPatternService:
    """
    Deterministic PhoenixTrend OHLCV structural-pattern detector.

    The service operates only on supplied OHLCV bars.

    Missing values are never replaced with invented market values.
    Missing volume means volume-based confirmation is omitted.
    Missing/invalid ATR means ATR-dependent comparisons are omitted.

    Pattern confidence represents deterministic structural quality only.
    It is not a probability of profit and does not authorize execution.
    """

    MIN_CONFIDENCE = 0.55
    MAX_PATTERNS = 12

    MIN_BARS = 20
    EMA50_BARS = 50

    DIRECTION_BULLISH = "BULLISH"
    DIRECTION_BEARISH = "BEARISH"
    DIRECTION_NEUTRAL = "NEUTRAL"

    def analyze(
        self,
        bars: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        parsed = self._parse_bars(bars)

        if len(parsed) < self.MIN_BARS:
            return []

        closes = [
            bar["close"]
            for bar in parsed
        ]
        highs = [
            bar["high"]
            for bar in parsed
        ]
        lows = [
            bar["low"]
            for bar in parsed
        ]

        volumes = [
            bar.get("volume")
            for bar in parsed
        ]

        price = closes[-1]

        if price <= 0:
            return []

        atr_value = self._atr_value(
            parsed
        )

        results: list[PatternMatch] = []

        def add(
            *,
            name: str,
            label: str,
            direction: str,
            confidence: float,
            evidence: Iterable[str],
            preferred_strategies: Iterable[str],
            start_index: int | None = None,
            end_index: int | None = None,
            breakout_level: float | None = None,
            support_level: float | None = None,
            resistance_level: float | None = None,
            neckline: float | None = None,
            metadata: Mapping[str, Any] | None = None,
        ) -> None:
            confidence = self._clamp(
                confidence
            )

            if confidence < self.MIN_CONFIDENCE:
                return

            results.append(
                PatternMatch(
                    name=name,
                    label=label,
                    direction=direction,
                    confidence=round(
                        confidence,
                        4,
                    ),
                    evidence=[
                        str(item)
                        for item in evidence
                        if str(item).strip()
                    ],
                    preferred_strategies=self._unique_strings(
                        preferred_strategies
                    ),
                    start_index=start_index,
                    end_index=end_index,
                    breakout_level=breakout_level,
                    support_level=support_level,
                    resistance_level=resistance_level,
                    neckline=neckline,
                    metadata=dict(
                        metadata
                        or {}
                    ),
                )
            )

        self._detect_breakout_breakdown(
            parsed,
            atr_value,
            add,
        )

        self._detect_trend_structure(
            parsed,
            atr_value,
            add,
        )

        self._detect_double_patterns(
            parsed,
            atr_value,
            add,
        )

        self._detect_triple_patterns(
            parsed,
            atr_value,
            add,
        )

        self._detect_head_shoulders(
            parsed,
            atr_value,
            add,
        )

        self._detect_triangles(
            parsed,
            atr_value,
            add,
        )

        self._detect_wedges(
            parsed,
            atr_value,
            add,
        )

        self._detect_rectangles(
            parsed,
            atr_value,
            add,
        )

        self._detect_channels(
            parsed,
            atr_value,
            add,
        )

        self._detect_flags_pennants(
            parsed,
            atr_value,
            add,
        )

        self._detect_cup_handle(
            parsed,
            atr_value,
            add,
        )

        self._detect_rounding_patterns(
            parsed,
            add,
        )

        self._detect_broadening(
            parsed,
            atr_value,
            add,
        )

        self._detect_v_reversal(
            parsed,
            atr_value,
            add,
        )

        self._detect_gaps(
            parsed,
            atr_value,
            add,
        )

        self._detect_volatility_compression(
            parsed,
            add,
        )

        results = self._deduplicate(
            results
        )

        results.sort(
            key=lambda match: (
                -match.confidence,
                match.name,
            )
        )

        return [
            match.dump()
            for match in results[
                : self.MAX_PATTERNS
            ]
        ]

    # =========================================================================
    # BREAKOUT / BREAKDOWN
    # =========================================================================

    def _detect_breakout_breakdown(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 21:
            return

        closes = self._series(
            bars,
            "close",
        )
        highs = self._series(
            bars,
            "high",
        )
        lows = self._series(
            bars,
            "low",
        )

        price = closes[-1]

        previous_high = max(
            highs[-21:-1]
        )
        previous_low = min(
            lows[-21:-1]
        )

        volume_ratio = self._volume_ratio(
            bars,
            lookback=20,
        )

        if price > previous_high:
            confidence = 0.62
            evidence = [
                "Price closed above recent resistance",
            ]

            if atr_value is not None:
                distance_atr = self._clamp(
                    (
                        price
                        - previous_high
                    )
                    / atr_value
                )

                confidence += (
                    distance_atr
                    * 0.16
                )

                evidence.append(
                    f"Breakout distance {distance_atr:.2f} ATR"
                )

            if volume_ratio is not None:
                volume_bonus = min(
                    max(
                        volume_ratio
                        - 1.0,
                        0.0,
                    ),
                    2.0,
                )

                confidence += (
                    volume_bonus
                    * 0.08
                )

                evidence.append(
                    f"Relative volume {volume_ratio:.2f}x"
                )

            add(
                name="breakout",
                label="Resistance Breakout",
                direction=self.DIRECTION_BULLISH,
                confidence=confidence,
                evidence=evidence,
                preferred_strategies=[
                    "Breakout",
                    "Momentum",
                    "TrendFollowing",
                ],
                start_index=len(
                    bars
                ) - 21,
                end_index=len(
                    bars
                ) - 1,
                breakout_level=previous_high,
                resistance_level=previous_high,
                metadata={
                    "relative_volume": volume_ratio,
                },
            )

        if price < previous_low:
            confidence = 0.62
            evidence = [
                "Price closed below recent support",
            ]

            if atr_value is not None:
                distance_atr = self._clamp(
                    (
                        previous_low
                        - price
                    )
                    / atr_value
                )

                confidence += (
                    distance_atr
                    * 0.16
                )

                evidence.append(
                    f"Breakdown distance {distance_atr:.2f} ATR"
                )

            if volume_ratio is not None:
                volume_bonus = min(
                    max(
                        volume_ratio
                        - 1.0,
                        0.0,
                    ),
                    2.0,
                )

                confidence += (
                    volume_bonus
                    * 0.08
                )

                evidence.append(
                    f"Relative volume {volume_ratio:.2f}x"
                )

            add(
                name="breakdown",
                label="Support Breakdown",
                direction=self.DIRECTION_BEARISH,
                confidence=confidence,
                evidence=evidence,
                preferred_strategies=[
                    "Breakout",
                    "Momentum",
                    "TrendFollowing",
                ],
                start_index=len(
                    bars
                ) - 21,
                end_index=len(
                    bars
                ) - 1,
                breakout_level=previous_low,
                support_level=previous_low,
                metadata={
                    "relative_volume": volume_ratio,
                },
            )

    # =========================================================================
    # TREND / PULLBACK
    # =========================================================================

    def _detect_trend_structure(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < self.EMA50_BARS:
            return

        closes = self._series(
            bars,
            "close",
        )

        price = closes[-1]

        try:
            ema20_value = float(
                ema(
                    closes,
                    20,
                )
            )
            ema50_value = float(
                ema(
                    closes,
                    50,
                )
            )
        except Exception:
            return

        if not all(
            isfinite(value)
            and value > 0
            for value in (
                ema20_value,
                ema50_value,
            )
        ):
            return

        if (
            price
            > ema20_value
            > ema50_value
        ):
            separation = (
                ema20_value
                - ema50_value
            ) / price

            confidence = (
                0.67
                + min(
                    max(
                        separation,
                        0.0,
                    )
                    * 4.0,
                    0.10,
                )
            )

            add(
                name="bull_trend",
                label="Bull Trend",
                direction=self.DIRECTION_BULLISH,
                confidence=confidence,
                evidence=[
                    "Price > EMA20 > EMA50",
                ],
                preferred_strategies=[
                    "TrendFollowing",
                    "SwingTrend",
                    "Momentum",
                ],
                start_index=len(
                    bars
                ) - 50,
                end_index=len(
                    bars
                ) - 1,
                metadata={
                    "ema20": ema20_value,
                    "ema50": ema50_value,
                },
            )

            if (
                atr_value is not None
                and abs(
                    price
                    - ema20_value
                )
                <= 0.75
                * atr_value
            ):
                add(
                    name="trend_pullback_bullish",
                    label="Bull Trend Pullback",
                    direction=self.DIRECTION_BULLISH,
                    confidence=0.76,
                    evidence=[
                        "Bullish EMA structure remains intact",
                        "Price is retesting the EMA20 area",
                    ],
                    preferred_strategies=[
                        "Pullback",
                        "SwingTrend",
                    ],
                    start_index=len(
                        bars
                    ) - 50,
                    end_index=len(
                        bars
                    ) - 1,
                    support_level=ema20_value,
                    metadata={
                        "ema20": ema20_value,
                        "ema50": ema50_value,
                        "distance_to_ema20_atr": (
                            abs(
                                price
                                - ema20_value
                            )
                            / atr_value
                        ),
                    },
                )

        if (
            price
            < ema20_value
            < ema50_value
        ):
            separation = (
                ema50_value
                - ema20_value
            ) / price

            confidence = (
                0.67
                + min(
                    max(
                        separation,
                        0.0,
                    )
                    * 4.0,
                    0.10,
                )
            )

            add(
                name="bear_trend",
                label="Bear Trend",
                direction=self.DIRECTION_BEARISH,
                confidence=confidence,
                evidence=[
                    "Price < EMA20 < EMA50",
                ],
                preferred_strategies=[
                    "TrendFollowing",
                    "SwingTrend",
                    "Momentum",
                ],
                start_index=len(
                    bars
                ) - 50,
                end_index=len(
                    bars
                ) - 1,
                metadata={
                    "ema20": ema20_value,
                    "ema50": ema50_value,
                },
            )

            if (
                atr_value is not None
                and abs(
                    price
                    - ema20_value
                )
                <= 0.75
                * atr_value
            ):
                add(
                    name="trend_pullback_bearish",
                    label="Bear Trend Pullback",
                    direction=self.DIRECTION_BEARISH,
                    confidence=0.76,
                    evidence=[
                        "Bearish EMA structure remains intact",
                        "Price is retesting the EMA20 area",
                    ],
                    preferred_strategies=[
                        "Pullback",
                        "SwingTrend",
                    ],
                    start_index=len(
                        bars
                    ) - 50,
                    end_index=len(
                        bars
                    ) - 1,
                    resistance_level=ema20_value,
                    metadata={
                        "ema20": ema20_value,
                        "ema50": ema50_value,
                        "distance_to_ema20_atr": (
                            abs(
                                price
                                - ema20_value
                            )
                            / atr_value
                        ),
                    },
                )

    # =========================================================================
    # DOUBLE TOP / BOTTOM
    # =========================================================================

    def _detect_double_patterns(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 20:
            return

        window_size = min(
            40,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        highs = self._series(
            bars[-window_size:],
            "high",
        )
        lows = self._series(
            bars[-window_size:],
            "low",
        )
        closes = self._series(
            bars[-window_size:],
            "close",
        )

        peaks = self._local_peaks(
            highs
        )
        troughs = self._local_troughs(
            lows
        )

        tolerance = self._structural_tolerance(
            closes[-1],
            atr_value,
            highs,
            lows,
        )

        if (
            tolerance is not None
            and len(peaks) >= 2
        ):
            first_index = peaks[-2]
            second_index = peaks[-1]

            first_peak = highs[
                first_index
            ]
            second_peak = highs[
                second_index
            ]

            separation = (
                second_index
                - first_index
            )

            if (
                separation >= 4
                and abs(
                    first_peak
                    - second_peak
                )
                <= tolerance
            ):
                valley_slice = lows[
                    first_index:
                    second_index + 1
                ]

                neckline = (
                    min(
                        valley_slice
                    )
                    if valley_slice
                    else None
                )

                similarity = self._similarity(
                    first_peak,
                    second_peak,
                    tolerance,
                )

                confidence = (
                    0.62
                    + similarity
                    * 0.10
                )

                if (
                    neckline is not None
                    and closes[-1]
                    < neckline
                ):
                    confidence += 0.10

                add(
                    name="double_top",
                    label="Double Top",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    evidence=[
                        "Two similar recent swing highs detected",
                        (
                            "Price is below the intervening neckline"
                            if (
                                neckline is not None
                                and closes[-1]
                                < neckline
                            )
                            else "Neckline break not yet confirmed"
                        ),
                    ],
                    preferred_strategies=[
                        "MeanReversion",
                        "Breakout",
                        "SwingTrend",
                    ],
                    start_index=(
                        offset
                        + first_index
                    ),
                    end_index=(
                        offset
                        + second_index
                    ),
                    resistance_level=(
                        first_peak
                        + second_peak
                    )
                    / 2.0,
                    neckline=neckline,
                    metadata={
                        "first_peak": first_peak,
                        "second_peak": second_peak,
                        "swing_separation": separation,
                    },
                )

        if (
            tolerance is not None
            and len(troughs) >= 2
        ):
            first_index = troughs[-2]
            second_index = troughs[-1]

            first_trough = lows[
                first_index
            ]
            second_trough = lows[
                second_index
            ]

            separation = (
                second_index
                - first_index
            )

            if (
                separation >= 4
                and abs(
                    first_trough
                    - second_trough
                )
                <= tolerance
            ):
                peak_slice = highs[
                    first_index:
                    second_index + 1
                ]

                neckline = (
                    max(
                        peak_slice
                    )
                    if peak_slice
                    else None
                )

                similarity = self._similarity(
                    first_trough,
                    second_trough,
                    tolerance,
                )

                confidence = (
                    0.62
                    + similarity
                    * 0.10
                )

                if (
                    neckline is not None
                    and closes[-1]
                    > neckline
                ):
                    confidence += 0.10

                add(
                    name="double_bottom",
                    label="Double Bottom",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    evidence=[
                        "Two similar recent swing lows detected",
                        (
                            "Price is above the intervening neckline"
                            if (
                                neckline is not None
                                and closes[-1]
                                > neckline
                            )
                            else "Neckline break not yet confirmed"
                        ),
                    ],
                    preferred_strategies=[
                        "MeanReversion",
                        "SwingTrend",
                        "Breakout",
                    ],
                    start_index=(
                        offset
                        + first_index
                    ),
                    end_index=(
                        offset
                        + second_index
                    ),
                    support_level=(
                        first_trough
                        + second_trough
                    )
                    / 2.0,
                    neckline=neckline,
                    metadata={
                        "first_trough": first_trough,
                        "second_trough": second_trough,
                        "swing_separation": separation,
                    },
                )

    # =========================================================================
    # TRIPLE TOP / BOTTOM
    # =========================================================================

    def _detect_triple_patterns(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 25:
            return

        window_size = min(
            50,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        window = bars[
            -window_size:
        ]

        highs = self._series(
            window,
            "high",
        )
        lows = self._series(
            window,
            "low",
        )
        closes = self._series(
            window,
            "close",
        )

        peaks = self._local_peaks(
            highs
        )
        troughs = self._local_troughs(
            lows
        )

        tolerance = self._structural_tolerance(
            closes[-1],
            atr_value,
            highs,
            lows,
        )

        if tolerance is None:
            return

        if len(peaks) >= 3:
            selected = peaks[-3:]

            prices = [
                highs[index]
                for index in selected
            ]

            if (
                selected[1]
                - selected[0]
                >= 3
                and selected[2]
                - selected[1]
                >= 3
                and max(prices)
                - min(prices)
                <= tolerance
            ):
                neckline = min(
                    lows[
                        selected[0]:
                        selected[2] + 1
                    ]
                )

                confirmed = (
                    closes[-1]
                    < neckline
                )

                confidence = (
                    0.65
                    + (
                        0.10
                        if confirmed
                        else 0.0
                    )
                )

                add(
                    name="triple_top",
                    label="Triple Top",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    evidence=[
                        "Three comparable swing highs detected",
                        (
                            "Price broke below the structure neckline"
                            if confirmed
                            else "Neckline break not yet confirmed"
                        ),
                    ],
                    preferred_strategies=[
                        "MeanReversion",
                        "Breakout",
                        "SwingTrend",
                    ],
                    start_index=(
                        offset
                        + selected[0]
                    ),
                    end_index=(
                        offset
                        + selected[2]
                    ),
                    resistance_level=sum(
                        prices
                    )
                    / len(prices),
                    neckline=neckline,
                    metadata={
                        "peaks": prices,
                    },
                )

        if len(troughs) >= 3:
            selected = troughs[-3:]

            prices = [
                lows[index]
                for index in selected
            ]

            if (
                selected[1]
                - selected[0]
                >= 3
                and selected[2]
                - selected[1]
                >= 3
                and max(prices)
                - min(prices)
                <= tolerance
            ):
                neckline = max(
                    highs[
                        selected[0]:
                        selected[2] + 1
                    ]
                )

                confirmed = (
                    closes[-1]
                    > neckline
                )

                confidence = (
                    0.65
                    + (
                        0.10
                        if confirmed
                        else 0.0
                    )
                )

                add(
                    name="triple_bottom",
                    label="Triple Bottom",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    evidence=[
                        "Three comparable swing lows detected",
                        (
                            "Price broke above the structure neckline"
                            if confirmed
                            else "Neckline break not yet confirmed"
                        ),
                    ],
                    preferred_strategies=[
                        "MeanReversion",
                        "Breakout",
                        "SwingTrend",
                    ],
                    start_index=(
                        offset
                        + selected[0]
                    ),
                    end_index=(
                        offset
                        + selected[2]
                    ),
                    support_level=sum(
                        prices
                    )
                    / len(prices),
                    neckline=neckline,
                    metadata={
                        "troughs": prices,
                    },
                )

    # =========================================================================
    # HEAD AND SHOULDERS
    # =========================================================================

    def _detect_head_shoulders(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 30:
            return

        window_size = min(
            60,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        window = bars[
            -window_size:
        ]

        highs = self._series(
            window,
            "high",
        )
        lows = self._series(
            window,
            "low",
        )
        closes = self._series(
            window,
            "close",
        )

        peaks = self._local_peaks(
            highs
        )
        troughs = self._local_troughs(
            lows
        )

        tolerance = self._structural_tolerance(
            closes[-1],
            atr_value,
            highs,
            lows,
        )

        if tolerance is None:
            return

        if len(peaks) >= 3:
            left_index, head_index, right_index = peaks[
                -3:
            ]

            left = highs[
                left_index
            ]
            head = highs[
                head_index
            ]
            right = highs[
                right_index
            ]

            shoulders_similar = (
                abs(
                    left
                    - right
                )
                <= tolerance
            )

            head_higher = (
                head
                > max(
                    left,
                    right,
                )
                + tolerance
                * 0.25
            )

            if (
                shoulders_similar
                and head_higher
            ):
                left_valley = min(
                    lows[
                        left_index:
                        head_index + 1
                    ]
                )

                right_valley = min(
                    lows[
                        head_index:
                        right_index + 1
                    ]
                )

                neckline = (
                    left_valley
                    + right_valley
                ) / 2.0

                confirmed = (
                    closes[-1]
                    < neckline
                )

                confidence = (
                    0.69
                    + (
                        0.10
                        if confirmed
                        else 0.0
                    )
                )

                add(
                    name="head_shoulders",
                    label="Head and Shoulders",
                    direction=self.DIRECTION_BEARISH,
                    confidence=confidence,
                    evidence=[
                        "Three-peak structure with a higher central peak",
                        "Left and right shoulders are structurally similar",
                        (
                            "Price is below the estimated neckline"
                            if confirmed
                            else "Neckline break not yet confirmed"
                        ),
                    ],
                    preferred_strategies=[
                        "Breakout",
                        "SwingTrend",
                        "MeanReversion",
                    ],
                    start_index=(
                        offset
                        + left_index
                    ),
                    end_index=(
                        offset
                        + right_index
                    ),
                    neckline=neckline,
                    resistance_level=head,
                    metadata={
                        "left_shoulder": left,
                        "head": head,
                        "right_shoulder": right,
                        "left_neckline_point": left_valley,
                        "right_neckline_point": right_valley,
                    },
                )

        if len(troughs) >= 3:
            left_index, head_index, right_index = troughs[
                -3:
            ]

            left = lows[
                left_index
            ]
            head = lows[
                head_index
            ]
            right = lows[
                right_index
            ]

            shoulders_similar = (
                abs(
                    left
                    - right
                )
                <= tolerance
            )

            head_lower = (
                head
                < min(
                    left,
                    right,
                )
                - tolerance
                * 0.25
            )

            if (
                shoulders_similar
                and head_lower
            ):
                left_peak = max(
                    highs[
                        left_index:
                        head_index + 1
                    ]
                )

                right_peak = max(
                    highs[
                        head_index:
                        right_index + 1
                    ]
                )

                neckline = (
                    left_peak
                    + right_peak
                ) / 2.0

                confirmed = (
                    closes[-1]
                    > neckline
                )

                confidence = (
                    0.69
                    + (
                        0.10
                        if confirmed
                        else 0.0
                    )
                )

                add(
                    name="inverse_head_shoulders",
                    label="Inverse Head and Shoulders",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    evidence=[
                        "Three-trough structure with a lower central trough",
                        "Left and right shoulders are structurally similar",
                        (
                            "Price is above the estimated neckline"
                            if confirmed
                            else "Neckline break not yet confirmed"
                        ),
                    ],
                    preferred_strategies=[
                        "Breakout",
                        "SwingTrend",
                        "MeanReversion",
                    ],
                    start_index=(
                        offset
                        + left_index
                    ),
                    end_index=(
                        offset
                        + right_index
                    ),
                    neckline=neckline,
                    support_level=head,
                    metadata={
                        "left_shoulder": left,
                        "head": head,
                        "right_shoulder": right,
                        "left_neckline_point": left_peak,
                        "right_neckline_point": right_peak,
                    },
                )

    # =========================================================================
    # TRIANGLES
    # =========================================================================

    def _detect_triangles(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 18:
            return

        window_size = min(
            30,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        window = bars[
            -window_size:
        ]

        highs = self._series(
            window,
            "high",
        )
        lows = self._series(
            window,
            "low",
        )
        closes = self._series(
            window,
            "close",
        )

        peaks = self._local_peaks(
            highs
        )
        troughs = self._local_troughs(
            lows
        )

        if (
            len(peaks) < 2
            or len(troughs) < 2
        ):
            return

        peak_points = [
            SwingPoint(
                index=index,
                price=highs[index],
            )
            for index in peaks[-3:]
        ]

        trough_points = [
            SwingPoint(
                index=index,
                price=lows[index],
            )
            for index in troughs[-3:]
        ]

        upper_slope = self._slope(
            peak_points
        )
        lower_slope = self._slope(
            trough_points
        )

        tolerance = self._structural_tolerance(
            closes[-1],
            atr_value,
            highs,
            lows,
        )

        if tolerance is None:
            return

        upper_flat = (
            abs(
                peak_points[-1].price
                - peak_points[0].price
            )
            <= tolerance
        )

        lower_flat = (
            abs(
                trough_points[-1].price
                - trough_points[0].price
            )
            <= tolerance
        )

        if (
            upper_flat
            and lower_slope > 0
        ):
            resistance = sum(
                point.price
                for point in peak_points
            ) / len(
                peak_points
            )

            confidence = 0.68

            if closes[-1] > resistance:
                confidence += 0.09

            add(
                name="ascending_triangle",
                label="Ascending Triangle",
                direction=self.DIRECTION_BULLISH,
                confidence=confidence,
                evidence=[
                    "Recent swing highs form approximately flat resistance",
                    "Recent swing lows are rising",
                ],
                preferred_strategies=[
                    "Breakout",
                    "Momentum",
                    "TrendFollowing",
                ],
                start_index=offset,
                end_index=len(
                    bars
                ) - 1,
                resistance_level=resistance,
                metadata={
                    "upper_slope": upper_slope,
                    "lower_slope": lower_slope,
                    "peaks": [
                        point.dump()
                        for point in peak_points
                    ],
                    "troughs": [
                        point.dump()
                        for point in trough_points
                    ],
                },
            )

        if (
            lower_flat
            and upper_slope < 0
        ):
            support = sum(
                point.price
                for point in trough_points
            ) / len(
                trough_points
            )

            confidence = 0.68

            if closes[-1] < support:
                confidence += 0.09

            add(
                name="descending_triangle",
                label="Descending Triangle",
                direction=self.DIRECTION_BEARISH,
                confidence=confidence,
                evidence=[
                    "Recent swing lows form approximately flat support",
                    "Recent swing highs are falling",
                ],
                preferred_strategies=[
                    "Breakout",
                    "Momentum",
                    "TrendFollowing",
                ],
                start_index=offset,
                end_index=len(
                    bars
                ) - 1,
                support_level=support,
                metadata={
                    "upper_slope": upper_slope,
                    "lower_slope": lower_slope,
                    "peaks": [
                        point.dump()
                        for point in peak_points
                    ],
                    "troughs": [
                        point.dump()
                        for point in trough_points
                    ],
                },
            )

        if (
            upper_slope < 0
            and lower_slope > 0
        ):
            first_width = (
                peak_points[0].price
                - trough_points[0].price
            )

            last_width = (
                peak_points[-1].price
                - trough_points[-1].price
            )

            if (
                first_width > 0
                and last_width > 0
                and last_width
                < first_width
            ):
                direction = self._recent_direction(
                    closes
                )

                add(
                    name="symmetrical_triangle",
                    label="Symmetrical Triangle",
                    direction=direction,
                    confidence=0.66,
                    evidence=[
                        "Recent swing highs are falling",
                        "Recent swing lows are rising",
                        "Price range is converging",
                    ],
                    preferred_strategies=[
                        "Breakout",
                        "Momentum",
                    ],
                    start_index=offset,
                    end_index=len(
                        bars
                    ) - 1,
                    metadata={
                        "upper_slope": upper_slope,
                        "lower_slope": lower_slope,
                        "initial_width": first_width,
                        "recent_width": last_width,
                    },
                )

    # =========================================================================
    # WEDGES
    # =========================================================================

    def _detect_wedges(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 18:
            return

        window_size = min(
            30,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        window = bars[
            -window_size:
        ]

        highs = self._series(
            window,
            "high",
        )
        lows = self._series(
            window,
            "low",
        )

        peaks = self._local_peaks(
            highs
        )
        troughs = self._local_troughs(
            lows
        )

        if (
            len(peaks) < 2
            or len(troughs) < 2
        ):
            return

        peak_points = [
            SwingPoint(
                index=index,
                price=highs[index],
            )
            for index in peaks[-3:]
        ]

        trough_points = [
            SwingPoint(
                index=index,
                price=lows[index],
            )
            for index in troughs[-3:]
        ]

        upper_slope = self._slope(
            peak_points
        )
        lower_slope = self._slope(
            trough_points
        )

        first_width = (
            peak_points[0].price
            - trough_points[0].price
        )

        last_width = (
            peak_points[-1].price
            - trough_points[-1].price
        )

        converging = (
            first_width > 0
            and last_width > 0
            and last_width
            < first_width
        )

        if not converging:
            return

        if (
            upper_slope > 0
            and lower_slope > 0
            and lower_slope
            > upper_slope
        ):
            add(
                name="rising_wedge",
                label="Rising Wedge",
                direction=self.DIRECTION_BEARISH,
                confidence=0.66,
                evidence=[
                    "Upper and lower swing boundaries are rising",
                    "Lower boundary is rising faster and the range is converging",
                ],
                preferred_strategies=[
                    "Breakout",
                    "MeanReversion",
                    "SwingTrend",
                ],
                start_index=offset,
                end_index=len(
                    bars
                ) - 1,
                metadata={
                    "upper_slope": upper_slope,
                    "lower_slope": lower_slope,
                    "initial_width": first_width,
                    "recent_width": last_width,
                },
            )

        if (
            upper_slope < 0
            and lower_slope < 0
            and upper_slope
            < lower_slope
        ):
            add(
                name="falling_wedge",
                label="Falling Wedge",
                direction=self.DIRECTION_BULLISH,
                confidence=0.66,
                evidence=[
                    "Upper and lower swing boundaries are falling",
                    "Upper boundary is falling faster and the range is converging",
                ],
                preferred_strategies=[
                    "Breakout",
                    "MeanReversion",
                    "SwingTrend",
                ],
                start_index=offset,
                end_index=len(
                    bars
                ) - 1,
                metadata={
                    "upper_slope": upper_slope,
                    "lower_slope": lower_slope,
                    "initial_width": first_width,
                    "recent_width": last_width,
                },
            )

    # =========================================================================
    # RECTANGLES
    # =========================================================================

    def _detect_rectangles(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 16:
            return

        window_size = min(
            24,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        window = bars[
            -window_size:
        ]

        highs = self._series(
            window,
            "high",
        )
        lows = self._series(
            window,
            "low",
        )
        closes = self._series(
            window,
            "close",
        )

        peaks = self._local_peaks(
            highs
        )
        troughs = self._local_troughs(
            lows
        )

        if (
            len(peaks) < 2
            or len(troughs) < 2
        ):
            return

        peak_prices = [
            highs[index]
            for index in peaks[-3:]
        ]

        trough_prices = [
            lows[index]
            for index in troughs[-3:]
        ]

        tolerance = self._structural_tolerance(
            closes[-1],
            atr_value,
            highs,
            lows,
        )

        if tolerance is None:
            return

        if (
            max(
                peak_prices
            )
            - min(
                peak_prices
            )
            <= tolerance
            and max(
                trough_prices
            )
            - min(
                trough_prices
            )
            <= tolerance
        ):
            resistance = sum(
                peak_prices
            ) / len(
                peak_prices
            )

            support = sum(
                trough_prices
            ) / len(
                trough_prices
            )

            if resistance <= support:
                return

            direction = self._recent_direction(
                closes
            )

            add(
                name="rectangle",
                label="Rectangle Consolidation",
                direction=direction,
                confidence=0.63,
                evidence=[
                    "Multiple swing highs cluster near a common resistance",
                    "Multiple swing lows cluster near a common support",
                ],
                preferred_strategies=[
                    "Breakout",
                    "MeanReversion",
                    "VWAP",
                ],
                start_index=offset,
                end_index=len(
                    bars
                ) - 1,
                support_level=support,
                resistance_level=resistance,
                metadata={
                    "range_width": (
                        resistance
                        - support
                    ),
                },
            )

    # =========================================================================
    # CHANNELS
    # =========================================================================

    def _detect_channels(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 20:
            return

        window_size = min(
            35,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        window = bars[
            -window_size:
        ]

        highs = self._series(
            window,
            "high",
        )
        lows = self._series(
            window,
            "low",
        )

        peaks = self._local_peaks(
            highs
        )
        troughs = self._local_troughs(
            lows
        )

        if (
            len(peaks) < 2
            or len(troughs) < 2
        ):
            return

        peak_points = [
            SwingPoint(
                index=index,
                price=highs[index],
            )
            for index in peaks[-3:]
        ]

        trough_points = [
            SwingPoint(
                index=index,
                price=lows[index],
            )
            for index in troughs[-3:]
        ]

        upper_slope = self._slope(
            peak_points
        )
        lower_slope = self._slope(
            trough_points
        )

        slope_scale = max(
            abs(
                upper_slope
            ),
            abs(
                lower_slope
            ),
            1e-12,
        )

        parallel_difference = (
            abs(
                upper_slope
                - lower_slope
            )
            / slope_scale
        )

        if parallel_difference > 0.40:
            return

        if (
            upper_slope > 0
            and lower_slope > 0
        ):
            add(
                name="ascending_channel",
                label="Ascending Channel",
                direction=self.DIRECTION_BULLISH,
                confidence=0.64,
                evidence=[
                    "Recent swing highs and lows are rising",
                    "Upper and lower boundaries have similar positive slopes",
                ],
                preferred_strategies=[
                    "TrendFollowing",
                    "SwingTrend",
                    "Pullback",
                ],
                start_index=offset,
                end_index=len(
                    bars
                ) - 1,
                metadata={
                    "upper_slope": upper_slope,
                    "lower_slope": lower_slope,
                },
            )

        elif (
            upper_slope < 0
            and lower_slope < 0
        ):
            add(
                name="descending_channel",
                label="Descending Channel",
                direction=self.DIRECTION_BEARISH,
                confidence=0.64,
                evidence=[
                    "Recent swing highs and lows are falling",
                    "Upper and lower boundaries have similar negative slopes",
                ],
                preferred_strategies=[
                    "TrendFollowing",
                    "SwingTrend",
                    "Pullback",
                ],
                start_index=offset,
                end_index=len(
                    bars
                ) - 1,
                metadata={
                    "upper_slope": upper_slope,
                    "lower_slope": lower_slope,
                },
            )

        else:
            add(
                name="horizontal_channel",
                label="Horizontal Channel",
                direction=self.DIRECTION_NEUTRAL,
                confidence=0.60,
                evidence=[
                    "Recent swing boundaries are approximately parallel",
                    "No clear directional channel slope is established",
                ],
                preferred_strategies=[
                    "MeanReversion",
                    "VWAP",
                    "Breakout",
                ],
                start_index=offset,
                end_index=len(
                    bars
                ) - 1,
                metadata={
                    "upper_slope": upper_slope,
                    "lower_slope": lower_slope,
                },
            )

    # =========================================================================
    # FLAGS / PENNANTS
    # =========================================================================

    def _detect_flags_pennants(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 16:
            return

        closes = self._series(
            bars,
            "close",
        )

        impulse_start = closes[
            -16
        ]

        impulse_end = closes[
            -6
        ]

        if impulse_start <= 0:
            return

        impulse = (
            impulse_end
            - impulse_start
        ) / impulse_start

        consolidation_closes = closes[
            -6:
        ]

        consolidation_base = abs(
            consolidation_closes[0]
        )

        if consolidation_base <= 0:
            return

        consolidation_range = (
            max(
                consolidation_closes
            )
            - min(
                consolidation_closes
            )
        ) / consolidation_base

        consolidation_slope = self._linear_slope(
            consolidation_closes
        )

        if (
            impulse > 0.06
            and consolidation_range
            < abs(
                impulse
            )
            * 0.55
        ):
            if consolidation_slope <= 0:
                add(
                    name="bull_flag",
                    label="Bull Flag",
                    direction=self.DIRECTION_BULLISH,
                    confidence=0.72,
                    evidence=[
                        "Strong upward impulse detected",
                        "Tight consolidation followed the impulse",
                        "Consolidation is flat or counter-trend",
                    ],
                    preferred_strategies=[
                        "Momentum",
                        "Breakout",
                        "TrendFollowing",
                    ],
                    start_index=len(
                        bars
                    ) - 16,
                    end_index=len(
                        bars
                    ) - 1,
                    metadata={
                        "impulse_return": impulse,
                        "consolidation_range": consolidation_range,
                        "consolidation_slope": consolidation_slope,
                    },
                )

            if self._converging_recent_range(
                bars[-6:]
            ):
                add(
                    name="bull_pennant",
                    label="Bull Pennant",
                    direction=self.DIRECTION_BULLISH,
                    confidence=0.70,
                    evidence=[
                        "Strong upward impulse detected",
                        "Post-impulse range is converging",
                    ],
                    preferred_strategies=[
                        "Momentum",
                        "Breakout",
                    ],
                    start_index=len(
                        bars
                    ) - 16,
                    end_index=len(
                        bars
                    ) - 1,
                    metadata={
                        "impulse_return": impulse,
                    },
                )

        if (
            impulse < -0.06
            and consolidation_range
            < abs(
                impulse
            )
            * 0.55
        ):
            if consolidation_slope >= 0:
                add(
                    name="bear_flag",
                    label="Bear Flag",
                    direction=self.DIRECTION_BEARISH,
                    confidence=0.72,
                    evidence=[
                        "Strong downward impulse detected",
                        "Tight consolidation followed the impulse",
                        "Consolidation is flat or counter-trend",
                    ],
                    preferred_strategies=[
                        "Momentum",
                        "Breakout",
                        "TrendFollowing",
                    ],
                    start_index=len(
                        bars
                    ) - 16,
                    end_index=len(
                        bars
                    ) - 1,
                    metadata={
                        "impulse_return": impulse,
                        "consolidation_range": consolidation_range,
                        "consolidation_slope": consolidation_slope,
                    },
                )

            if self._converging_recent_range(
                bars[-6:]
            ):
                add(
                    name="bear_pennant",
                    label="Bear Pennant",
                    direction=self.DIRECTION_BEARISH,
                    confidence=0.70,
                    evidence=[
                        "Strong downward impulse detected",
                        "Post-impulse range is converging",
                    ],
                    preferred_strategies=[
                        "Momentum",
                        "Breakout",
                    ],
                    start_index=len(
                        bars
                    ) - 16,
                    end_index=len(
                        bars
                    ) - 1,
                    metadata={
                        "impulse_return": impulse,
                    },
                )

    # =========================================================================
    # CUP AND HANDLE
    # =========================================================================

    def _detect_cup_handle(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 35:
            return

        window_size = min(
            60,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        window = bars[
            -window_size:
        ]

        closes = self._series(
            window,
            "close",
        )

        split = int(
            len(
                closes
            )
            * 0.75
        )

        if split < 20:
            return

        cup = closes[
            :split
        ]

        handle = closes[
            split:
        ]

        if len(
            handle
        ) < 5:
            return

        bottom_index = min(
            range(
                len(
                    cup
                )
            ),
            key=lambda index: cup[
                index
            ],
        )

        if (
            bottom_index
            < len(
                cup
            )
            * 0.20
            or bottom_index
            > len(
                cup
            )
            * 0.80
        ):
            return

        left_rim = max(
            cup[
                : max(
                    1,
                    bottom_index,
                )
            ]
        )

        right_rim = max(
            cup[
                bottom_index + 1:
            ]
        )

        bottom = cup[
            bottom_index
        ]

        if bottom <= 0:
            return

        rim_average = (
            left_rim
            + right_rim
        ) / 2.0

        if rim_average <= 0:
            return

        rim_difference = abs(
            left_rim
            - right_rim
        ) / rim_average

        depth = (
            rim_average
            - bottom
        ) / rim_average

        if (
            rim_difference <= 0.06
            and 0.08
            <= depth
            <= 0.45
        ):
            handle_high = max(
                handle
            )
            handle_low = min(
                handle
            )

            handle_depth = (
                handle_high
                - handle_low
            ) / rim_average

            if (
                handle_depth
                <= depth
                * 0.50
            ):
                confirmed = (
                    closes[-1]
                    > max(
                        left_rim,
                        right_rim,
                    )
                )

                confidence = (
                    0.67
                    + (
                        0.10
                        if confirmed
                        else 0.0
                    )
                )

                add(
                    name="cup_handle",
                    label="Cup and Handle",
                    direction=self.DIRECTION_BULLISH,
                    confidence=confidence,
                    evidence=[
                        "Rounded recovery formed between comparable rim levels",
                        "Handle retracement is materially smaller than cup depth",
                        (
                            "Price closed above the rim"
                            if confirmed
                            else "Rim breakout not yet confirmed"
                        ),
                    ],
                    preferred_strategies=[
                        "Breakout",
                        "SwingTrend",
                        "Momentum",
                    ],
                    start_index=offset,
                    end_index=len(
                        bars
                    ) - 1,
                    resistance_level=max(
                        left_rim,
                        right_rim,
                    ),
                    metadata={
                        "left_rim": left_rim,
                        "right_rim": right_rim,
                        "cup_bottom": bottom,
                        "cup_depth": depth,
                        "handle_depth": handle_depth,
                    },
                )

    # =========================================================================
    # ROUNDING TOP / BOTTOM
    # =========================================================================

    def _detect_rounding_patterns(
        self,
        bars: list[dict[str, float | None]],
        add: Any,
    ) -> None:
        if len(bars) < 30:
            return

        window_size = min(
            45,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        closes = self._series(
            bars[
                -window_size:
            ],
            "close",
        )

        third = len(
            closes
        ) // 3

        if third < 5:
            return

        left = closes[
            :third
        ]
        middle = closes[
            third:
            2 * third
        ]
        right = closes[
            2 * third:
        ]

        left_mean = self._mean(
            left
        )
        middle_mean = self._mean(
            middle
        )
        right_mean = self._mean(
            right
        )

        if min(
            left_mean,
            middle_mean,
            right_mean,
        ) <= 0:
            return

        side_average = (
            left_mean
            + right_mean
        ) / 2.0

        side_similarity = (
            abs(
                left_mean
                - right_mean
            )
            / side_average
        )

        if (
            middle_mean
            < min(
                left_mean,
                right_mean,
            )
            and side_similarity
            <= 0.08
        ):
            depth = (
                side_average
                - middle_mean
            ) / side_average

            if depth >= 0.04:
                add(
                    name="rounding_bottom",
                    label="Rounding Bottom",
                    direction=self.DIRECTION_BULLISH,
                    confidence=0.61,
                    evidence=[
                        "Middle portion of the supplied window trades below both outer portions",
                        "Left and right portions recovered to comparable levels",
                    ],
                    preferred_strategies=[
                        "SwingTrend",
                        "MeanReversion",
                        "Breakout",
                    ],
                    start_index=offset,
                    end_index=len(
                        bars
                    ) - 1,
                    metadata={
                        "depth": depth,
                        "side_similarity": side_similarity,
                    },
                )

        if (
            middle_mean
            > max(
                left_mean,
                right_mean,
            )
            and side_similarity
            <= 0.08
        ):
            height = (
                middle_mean
                - side_average
            ) / side_average

            if height >= 0.04:
                add(
                    name="rounding_top",
                    label="Rounding Top",
                    direction=self.DIRECTION_BEARISH,
                    confidence=0.61,
                    evidence=[
                        "Middle portion of the supplied window trades above both outer portions",
                        "Left and right portions returned to comparable levels",
                    ],
                    preferred_strategies=[
                        "SwingTrend",
                        "MeanReversion",
                        "Breakout",
                    ],
                    start_index=offset,
                    end_index=len(
                        bars
                    ) - 1,
                    metadata={
                        "height": height,
                        "side_similarity": side_similarity,
                    },
                )

    # =========================================================================
    # BROADENING / MEGAPHONE
    # =========================================================================

    def _detect_broadening(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 18:
            return

        window_size = min(
            30,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        window = bars[
            -window_size:
        ]

        highs = self._series(
            window,
            "high",
        )
        lows = self._series(
            window,
            "low",
        )
        closes = self._series(
            window,
            "close",
        )

        peaks = self._local_peaks(
            highs
        )
        troughs = self._local_troughs(
            lows
        )

        if (
            len(peaks) < 2
            or len(troughs) < 2
        ):
            return

        peak_points = [
            SwingPoint(
                index=index,
                price=highs[index],
            )
            for index in peaks[-3:]
        ]

        trough_points = [
            SwingPoint(
                index=index,
                price=lows[index],
            )
            for index in troughs[-3:]
        ]

        upper_slope = self._slope(
            peak_points
        )
        lower_slope = self._slope(
            trough_points
        )

        if (
            upper_slope > 0
            and lower_slope < 0
        ):
            first_width = (
                peak_points[0].price
                - trough_points[0].price
            )

            last_width = (
                peak_points[-1].price
                - trough_points[-1].price
            )

            if (
                first_width > 0
                and last_width
                > first_width
            ):
                add(
                    name="broadening_formation",
                    label="Broadening / Megaphone",
                    direction=self._recent_direction(
                        closes
                    ),
                    confidence=0.62,
                    evidence=[
                        "Recent swing highs are rising",
                        "Recent swing lows are falling",
                        "Price range is expanding",
                    ],
                    preferred_strategies=[
                        "Breakout",
                        "Volatility",
                        "SwingTrend",
                    ],
                    start_index=offset,
                    end_index=len(
                        bars
                    ) - 1,
                    metadata={
                        "upper_slope": upper_slope,
                        "lower_slope": lower_slope,
                        "initial_width": first_width,
                        "recent_width": last_width,
                    },
                )

    # =========================================================================
    # V REVERSALS
    # =========================================================================

    def _detect_v_reversal(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 12:
            return

        window_size = min(
            20,
            len(bars),
        )

        offset = (
            len(bars)
            - window_size
        )

        closes = self._series(
            bars[
                -window_size:
            ],
            "close",
        )

        low_index = min(
            range(
                len(
                    closes
                )
            ),
            key=lambda index: closes[
                index
            ],
        )

        high_index = max(
            range(
                len(
                    closes
                )
            ),
            key=lambda index: closes[
                index
            ],
        )

        if (
            2
            <= low_index
            <= len(
                closes
            ) - 4
        ):
            left = closes[
                0
            ]
            bottom = closes[
                low_index
            ]
            last = closes[
                -1
            ]

            if (
                left > 0
                and bottom > 0
            ):
                decline = (
                    left
                    - bottom
                ) / left

                recovery = (
                    last
                    - bottom
                ) / bottom

                if (
                    decline >= 0.05
                    and recovery >= 0.05
                    and last
                    >= left
                    * 0.97
                ):
                    add(
                        name="v_bottom",
                        label="V Bottom",
                        direction=self.DIRECTION_BULLISH,
                        confidence=0.66,
                        evidence=[
                            "Sharp decline into a central low",
                            "Sharp recovery returned price near the pre-decline level",
                        ],
                        preferred_strategies=[
                            "MeanReversion",
                            "Momentum",
                            "SwingTrend",
                        ],
                        start_index=offset,
                        end_index=len(
                            bars
                        ) - 1,
                        support_level=bottom,
                        metadata={
                            "decline": decline,
                            "recovery": recovery,
                        },
                    )

        if (
            2
            <= high_index
            <= len(
                closes
            ) - 4
        ):
            left = closes[
                0
            ]
            top = closes[
                high_index
            ]
            last = closes[
                -1
            ]

            if (
                left > 0
                and top > 0
            ):
                advance = (
                    top
                    - left
                ) / left

                reversal = (
                    top
                    - last
                ) / top

                if (
                    advance >= 0.05
                    and reversal >= 0.05
                    and last
                    <= left
                    * 1.03
                ):
                    add(
                        name="v_top",
                        label="V Top",
                        direction=self.DIRECTION_BEARISH,
                        confidence=0.66,
                        evidence=[
                            "Sharp advance into a central high",
                            "Sharp reversal returned price near the pre-advance level",
                        ],
                        preferred_strategies=[
                            "MeanReversion",
                            "Momentum",
                            "SwingTrend",
                        ],
                        start_index=offset,
                        end_index=len(
                            bars
                        ) - 1,
                        resistance_level=top,
                        metadata={
                            "advance": advance,
                            "reversal": reversal,
                        },
                    )

    # =========================================================================
    # GAPS
    # =========================================================================

    def _detect_gaps(
        self,
        bars: list[dict[str, float | None]],
        atr_value: float | None,
        add: Any,
    ) -> None:
        if len(bars) < 2:
            return

        previous = bars[
            -2
        ]
        current = bars[
            -1
        ]

        previous_high = self._required(
            previous,
            "high",
        )
        previous_low = self._required(
            previous,
            "low",
        )
        current_high = self._required(
            current,
            "high",
        )
        current_low = self._required(
            current,
            "low",
        )

        if current_low > previous_high:
            gap = (
                current_low
                - previous_high
            )

            confidence = 0.58
            evidence = [
                "Current candle low is above the previous candle high",
            ]

            if atr_value is not None:
                ratio = (
                    gap
                    / atr_value
                )

                confidence += min(
                    ratio
                    * 0.08,
                    0.12,
                )

                evidence.append(
                    f"Gap size {ratio:.2f} ATR"
                )

            add(
                name="gap_up",
                label="Gap Up",
                direction=self.DIRECTION_BULLISH,
                confidence=confidence,
                evidence=evidence,
                preferred_strategies=[
                    "Momentum",
                    "Breakout",
                    "Gap",
                ],
                start_index=len(
                    bars
                ) - 2,
                end_index=len(
                    bars
                ) - 1,
                support_level=previous_high,
                metadata={
                    "gap_size": gap,
                },
            )

        if current_high < previous_low:
            gap = (
                previous_low
                - current_high
            )

            confidence = 0.58
            evidence = [
                "Current candle high is below the previous candle low",
            ]

            if atr_value is not None:
                ratio = (
                    gap
                    / atr_value
                )

                confidence += min(
                    ratio
                    * 0.08,
                    0.12,
                )

                evidence.append(
                    f"Gap size {ratio:.2f} ATR"
                )

            add(
                name="gap_down",
                label="Gap Down",
                direction=self.DIRECTION_BEARISH,
                confidence=confidence,
                evidence=evidence,
                preferred_strategies=[
                    "Momentum",
                    "Breakout",
                    "Gap",
                ],
                start_index=len(
                    bars
                ) - 2,
                end_index=len(
                    bars
                ) - 1,
                resistance_level=previous_low,
                metadata={
                    "gap_size": gap,
                },
            )

    # =========================================================================
    # VOLATILITY COMPRESSION
    # =========================================================================

    def _detect_volatility_compression(
        self,
        bars: list[dict[str, float | None]],
        add: Any,
    ) -> None:
        if len(bars) < 12:
            return

        recent = bars[
            -12:
        ]

        highs = self._series(
            recent,
            "high",
        )
        lows = self._series(
            recent,
            "low",
        )
        closes = self._series(
            recent,
            "close",
        )

        first_range = (
            max(
                highs[:6]
            )
            - min(
                lows[:6]
            )
        )

        second_range = (
            max(
                highs[6:]
            )
            - min(
                lows[6:]
            )
        )

        if (
            first_range > 0
            and second_range
            < first_range
            * 0.72
        ):
            compression_ratio = (
                second_range
                / first_range
            )

            direction = self._recent_direction(
                closes
            )

            confidence = (
                0.60
                + (
                    1.0
                    - compression_ratio
                )
                * 0.12
            )

            add(
                name="volatility_compression",
                label="Volatility Compression",
                direction=direction,
                confidence=confidence,
                evidence=[
                    "Recent trading range contracted materially",
                ],
                preferred_strategies=[
                    "Breakout",
                    "VWAP",
                    "Momentum",
                ],
                start_index=len(
                    bars
                ) - 12,
                end_index=len(
                    bars
                ) - 1,
                metadata={
                    "previous_range": first_range,
                    "recent_range": second_range,
                    "compression_ratio": compression_ratio,
                },
            )

    # =========================================================================
    # PARSING / VALIDATION
    # =========================================================================

    def _parse_bars(
        self,
        bars: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, float | None]]:
        output: list[
            dict[
                str,
                float | None,
            ]
        ] = []

        for raw in bars:
            if not isinstance(
                raw,
                Mapping,
            ):
                continue

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
                continue

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
                continue

            if high_value < low_value:
                continue

            if high_value < max(
                open_value,
                close_value,
            ):
                continue

            if low_value > min(
                open_value,
                close_value,
            ):
                continue

            volume = self._number(
                self._first(
                    raw,
                    "volume",
                    "v",
                )
            )

            if (
                volume is not None
                and volume < 0
            ):
                volume = None

            output.append(
                {
                    "open": open_value,
                    "high": high_value,
                    "low": low_value,
                    "close": close_value,
                    "volume": volume,
                }
            )

        return output

    def _atr_value(
        self,
        bars: list[dict[str, float | None]],
    ) -> float | None:
        if len(bars) < 2:
            return None

        clean_bars = [
            {
                "open": self._required(
                    bar,
                    "open",
                ),
                "high": self._required(
                    bar,
                    "high",
                ),
                "low": self._required(
                    bar,
                    "low",
                ),
                "close": self._required(
                    bar,
                    "close",
                ),
                **(
                    {
                        "volume": bar[
                            "volume"
                        ]
                    }
                    if bar.get(
                        "volume"
                    )
                    is not None
                    else {}
                ),
            }
            for bar in bars
        ]

        try:
            value = float(
                atr(
                    clean_bars
                )
            )
        except Exception:
            return None

        if (
            not isfinite(
                value
            )
            or value <= 0
        ):
            return None

        return value

    # =========================================================================
    # VOLUME
    # =========================================================================

    def _volume_ratio(
        self,
        bars: list[dict[str, float | None]],
        *,
        lookback: int,
    ) -> float | None:
        if len(bars) < 2:
            return None

        current = bars[
            -1
        ].get(
            "volume"
        )

        if current is None:
            return None

        historical = [
            bar.get(
                "volume"
            )
            for bar in bars[
                -(
                    lookback
                    + 1
                ):
                -1
            ]
        ]

        valid = [
            float(
                value
            )
            for value in historical
            if (
                value is not None
                and value >= 0
            )
        ]

        if not valid:
            return None

        average = (
            sum(
                valid
            )
            / len(
                valid
            )
        )

        if average <= 0:
            return None

        return float(
            current
        ) / average

    # =========================================================================
    # SWING HELPERS
    # =========================================================================

    @staticmethod
    def _local_peaks(
        values: list[float],
    ) -> list[int]:
        if len(
            values
        ) < 5:
            return []

        output: list[int] = []

        for index in range(
            2,
            len(
                values
            ) - 2,
        ):
            center = values[
                index
            ]

            neighbors = (
                values[
                    index - 2:
                    index
                ]
                + values[
                    index + 1:
                    index + 3
                ]
            )

            if center >= max(
                neighbors
            ):
                output.append(
                    index
                )

        return output

    @staticmethod
    def _local_troughs(
        values: list[float],
    ) -> list[int]:
        if len(
            values
        ) < 5:
            return []

        output: list[int] = []

        for index in range(
            2,
            len(
                values
            ) - 2,
        ):
            center = values[
                index
            ]

            neighbors = (
                values[
                    index - 2:
                    index
                ]
                + values[
                    index + 1:
                    index + 3
                ]
            )

            if center <= min(
                neighbors
            ):
                output.append(
                    index
                )

        return output

    @staticmethod
    def _slope(
        points: Sequence[SwingPoint],
    ) -> float:
        if len(
            points
        ) < 2:
            return 0.0

        x_values = [
            float(
                point.index
            )
            for point in points
        ]

        y_values = [
            point.price
            for point in points
        ]

        x_mean = sum(
            x_values
        ) / len(
            x_values
        )

        y_mean = sum(
            y_values
        ) / len(
            y_values
        )

        numerator = sum(
            (
                x
                - x_mean
            )
            * (
                y
                - y_mean
            )
            for x, y in zip(
                x_values,
                y_values,
            )
        )

        denominator = sum(
            (
                x
                - x_mean
            )
            ** 2
            for x in x_values
        )

        if denominator <= 0:
            return 0.0

        return (
            numerator
            / denominator
        )

    @staticmethod
    def _linear_slope(
        values: Sequence[float],
    ) -> float:
        if len(
            values
        ) < 2:
            return 0.0

        x_mean = (
            len(
                values
            )
            - 1
        ) / 2.0

        y_mean = sum(
            values
        ) / len(
            values
        )

        numerator = 0.0
        denominator = 0.0

        for index, value in enumerate(
            values
        ):
            dx = (
                index
                - x_mean
            )

            numerator += (
                dx
                * (
                    value
                    - y_mean
                )
            )

            denominator += (
                dx
                * dx
            )

        if denominator <= 0:
            return 0.0

        return (
            numerator
            / denominator
        )

    # =========================================================================
    # STRUCTURAL HELPERS
    # =========================================================================

    def _structural_tolerance(
        self,
        price: float,
        atr_value: float | None,
        highs: Sequence[float],
        lows: Sequence[float],
    ) -> float | None:
        if (
            atr_value is not None
            and atr_value > 0
        ):
            return (
                atr_value
                * 0.80
            )

        if (
            not highs
            or not lows
        ):
            return None

        observed_range = (
            max(
                highs
            )
            - min(
                lows
            )
        )

        if observed_range <= 0:
            return None

        # Derived only from the supplied observed range. This is not an
        # invented market tick or ATR substitute.
        return (
            observed_range
            * 0.08
        )

    @staticmethod
    def _converging_recent_range(
        bars: Sequence[
            Mapping[
                str,
                float | None,
            ]
        ],
    ) -> bool:
        if len(
            bars
        ) < 6:
            return False

        midpoint = len(
            bars
        ) // 2

        first = bars[
            :midpoint
        ]
        second = bars[
            midpoint:
        ]

        first_high = max(
            float(
                bar[
                    "high"
                ]
            )
            for bar in first
            if bar.get(
                "high"
            )
            is not None
        )

        first_low = min(
            float(
                bar[
                    "low"
                ]
            )
            for bar in first
            if bar.get(
                "low"
            )
            is not None
        )

        second_high = max(
            float(
                bar[
                    "high"
                ]
            )
            for bar in second
            if bar.get(
                "high"
            )
            is not None
        )

        second_low = min(
            float(
                bar[
                    "low"
                ]
            )
            for bar in second
            if bar.get(
                "low"
            )
            is not None
        )

        first_range = (
            first_high
            - first_low
        )

        second_range = (
            second_high
            - second_low
        )

        return (
            first_range > 0
            and second_range
            < first_range
        )

    @staticmethod
    def _recent_direction(
        closes: Sequence[float],
    ) -> str:
        if len(
            closes
        ) < 2:
            return (
                ChartPatternService.DIRECTION_NEUTRAL
            )

        lookback = min(
            6,
            len(
                closes
            ),
        )

        start = closes[
            -lookback
        ]

        end = closes[
            -1
        ]

        if end > start:
            return (
                ChartPatternService.DIRECTION_BULLISH
            )

        if end < start:
            return (
                ChartPatternService.DIRECTION_BEARISH
            )

        return (
            ChartPatternService.DIRECTION_NEUTRAL
        )

    # =========================================================================
    # DEDUPLICATION
    # =========================================================================

    @staticmethod
    def _deduplicate(
        results: Sequence[
            PatternMatch
        ],
    ) -> list[PatternMatch]:
        selected: dict[
            tuple[
                str,
                int | None,
                int | None,
            ],
            PatternMatch,
        ] = {}

        for result in results:
            key = (
                result.name,
                result.start_index,
                result.end_index,
            )

            current = selected.get(
                key
            )

            if (
                current is None
                or result.confidence
                > current.confidence
            ):
                selected[
                    key
                ] = result

        return list(
            selected.values()
        )

    # =========================================================================
    # GENERIC HELPERS
    # =========================================================================

    @staticmethod
    def _series(
        bars: Sequence[
            Mapping[
                str,
                float | None,
            ]
        ],
        key: str,
    ) -> list[float]:
        output: list[float] = []

        for bar in bars:
            value = bar.get(
                key
            )

            if value is None:
                continue

            output.append(
                float(
                    value
                )
            )

        return output

    @staticmethod
    def _required(
        bar: Mapping[
            str,
            float | None,
        ],
        key: str,
    ) -> float:
        value = bar.get(
            key
        )

        if value is None:
            raise ValueError(
                f"Missing required OHLC field: {key}"
            )

        return float(
            value
        )

    @staticmethod
    def _first(
        mapping: Mapping[
            str,
            Any,
        ],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key not in mapping:
                continue

            value = mapping.get(
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
    def _mean(
        values: Sequence[
            float
        ],
    ) -> float:
        if not values:
            return 0.0

        return (
            sum(
                values
            )
            / len(
                values
            )
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
            first
            - second
        )

        return max(
            0.0,
            min(
                1.0,
                1.0
                - difference
                / tolerance,
            ),
        )

    @staticmethod
    def _unique_strings(
        values: Iterable[
            str
        ],
    ) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()

        for raw in values:
            value = str(
                raw
            ).strip()

            if (
                not value
                or value in seen
            ):
                continue

            seen.add(
                value
            )
            output.append(
                value
            )

        return output

    @staticmethod
    def _clamp(
        value: float,
    ) -> float:
        try:
            number = float(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return 0.0

        if not isfinite(
            number
        ):
            return 0.0

        return max(
            0.0,
            min(
                0.99,
                number,
            ),
        )


chart_pattern_service = ChartPatternService()


__all__ = [
    "PatternMatch",
    "SwingPoint",
    "ChartPatternService",
    "chart_pattern_service",
]
