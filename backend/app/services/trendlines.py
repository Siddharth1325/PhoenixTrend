from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite, sqrt
from statistics import median
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class TrendPivot:
    index: int
    price: float
    kind: str
    timestamp: str | None = None


@dataclass(frozen=True)
class FittedLine:
    slope: float
    intercept: float
    current: float
    start: float
    touches: int
    r_squared: float | None
    source: str
    first_index: int | None = None
    last_index: int | None = None


class TrendlineService:
    """
    PhoenixTrend trendline and price-channel analysis service.

    The service derives trend information exclusively from supplied OHLC
    history.

    It does not:
        - fabricate missing prices
        - fabricate timestamps
        - fabricate trendlines when history is insufficient
        - generate BUY/SELL decisions
        - replace chart-pattern detection
        - replace support/resistance analysis
        - authorize execution

    Analysis includes:
        - OHLC normalization and validation
        - close-price regression
        - swing-high / swing-low detection
        - pivot-based support trendlines
        - pivot-based resistance trendlines
        - channel geometry
        - channel direction
        - channel width
        - normalized slope
        - regression quality
        - trend consistency
        - breakout / breakdown observations
        - trendline proximity
        - rising/falling/sideways structural classification
    """

    DEFAULT_LOOKBACK = 80
    DEFAULT_PIVOT_WINDOW = 2
    DEFAULT_MIN_PIVOTS = 2

    MIN_BARS = 5

    def analyze(
        self,
        bars: list[dict[str, Any]],
        *,
        lookback: int = 80,
        pivot_window: int = 2,
    ) -> dict[str, Any]:
        normalized_lookback = self._positive_int(
            lookback,
            default=self.DEFAULT_LOOKBACK,
        )

        normalized_pivot_window = self._positive_int(
            pivot_window,
            default=self.DEFAULT_PIVOT_WINDOW,
        )

        rows = self._normalize_bars(
            bars,
            lookback=normalized_lookback,
        )

        if len(rows) < self.MIN_BARS:
            return self._unavailable(
                bar_count=len(rows),
                lookback=normalized_lookback,
                pivot_window=normalized_pivot_window,
                reason="Insufficient valid OHLC history",
            )

        closes = [
            row["close"]
            for row in rows
        ]

        highs = [
            row["high"]
            for row in rows
        ]

        lows = [
            row["low"]
            for row in rows
        ]

        current_price = closes[-1]

        close_line = self._regression(
            closes
        )

        if close_line is None:
            return self._unavailable(
                bar_count=len(rows),
                lookback=normalized_lookback,
                pivot_window=normalized_pivot_window,
                reason="Unable to calculate close-price trend regression",
                price=current_price,
            )

        close_slope = close_line[
            0
        ]

        close_intercept = close_line[
            1
        ]

        close_r_squared = (
            self._r_squared(
                closes,
                close_slope,
                close_intercept,
            )
        )

        close_current = (
            close_slope
            * (
                len(rows)
                - 1
            )
            + close_intercept
        )

        close_start = (
            close_intercept
        )

        slope_percent = (
            self._slope_percent(
                close_slope,
                current_price,
            )
        )

        total_change_percent = (
            self._percent_change(
                closes[0],
                closes[-1],
            )
        )

        swing_lows = self._pivot_lows(
            rows,
            window=normalized_pivot_window,
        )

        swing_highs = self._pivot_highs(
            rows,
            window=normalized_pivot_window,
        )

        support_line = (
            self._fit_pivot_line(
                swing_lows,
                total_bars=len(rows),
                source="swing_lows",
            )
        )

        resistance_line = (
            self._fit_pivot_line(
                swing_highs,
                total_bars=len(rows),
                source="swing_highs",
            )
        )

        fallback_support = False
        fallback_resistance = False

        if support_line is None:
            low_regression = (
                self._regression(
                    lows
                )
            )

            if low_regression is not None:
                support_line = (
                    self._fitted_line_from_series(
                        values=lows,
                        regression=low_regression,
                        source="low_regression",
                    )
                )

                fallback_support = True

        if resistance_line is None:
            high_regression = (
                self._regression(
                    highs
                )
            )

            if high_regression is not None:
                resistance_line = (
                    self._fitted_line_from_series(
                        values=highs,
                        regression=high_regression,
                        source="high_regression",
                    )
                )

                fallback_resistance = True

        median_range = (
            self._median_range(
                rows
            )
        )

        atr = self._atr(
            rows
        )

        tolerance = (
            self._touch_tolerance(
                current_price=current_price,
                atr=atr,
                median_range=median_range,
            )
        )

        if (
            support_line is not None
            and tolerance is not None
        ):
            support_line = (
                self._with_touch_count(
                    line=support_line,
                    rows=rows,
                    field="low",
                    tolerance=tolerance,
                )
            )

        if (
            resistance_line
            is not None
            and tolerance is not None
        ):
            resistance_line = (
                self._with_touch_count(
                    line=resistance_line,
                    rows=rows,
                    field="high",
                    tolerance=tolerance,
                )
            )

        channel = self._channel(
            support=support_line,
            resistance=resistance_line,
            current_price=current_price,
            total_bars=len(rows),
        )

        structural_trend = (
            self._structural_trend(
                swing_lows=swing_lows,
                swing_highs=swing_highs,
            )
        )

        regression_trend = (
            self._regression_trend(
                slope=close_slope,
                current_price=current_price,
                median_range=median_range,
            )
        )

        channel_trend = (
            self._channel_trend(
                support=support_line,
                resistance=resistance_line,
                current_price=current_price,
                median_range=median_range,
            )
        )

        trend = self._combine_trends(
            regression_trend=regression_trend,
            structural_trend=structural_trend,
            channel_trend=channel_trend,
        )

        support_payload = (
            self._line_payload(
                support_line
            )
            if support_line is not None
            else None
        )

        resistance_payload = (
            self._line_payload(
                resistance_line
            )
            if resistance_line
            is not None
            else None
        )

        close_payload = {
            "slope": close_slope,
            "intercept": (
                close_intercept
            ),
            "start": (
                close_start
            ),
            "current": (
                close_current
            ),
            "r_squared": (
                close_r_squared
            ),
        }

        breakout = (
            self._breakout_state(
                current_price=current_price,
                support=support_line,
                resistance=resistance_line,
                tolerance=tolerance,
            )
        )

        support_distance = (
            self._distance_to_line(
                current_price,
                support_line.current
                if support_line
                is not None
                else None,
            )
        )

        resistance_distance = (
            self._distance_to_line(
                current_price,
                resistance_line.current
                if resistance_line
                is not None
                else None,
            )
        )

        trend_consistency = (
            self._trend_consistency(
                regression_trend=regression_trend,
                structural_trend=structural_trend,
                channel_trend=channel_trend,
            )
        )

        return {
            "available": True,
            "price": current_price,
            "trend": trend,
            "regression_trend": (
                regression_trend
            ),
            "structural_trend": (
                structural_trend
            ),
            "channel_trend": (
                channel_trend
            ),
            "trend_consistency": (
                trend_consistency
            ),
            "slope_per_bar": (
                close_slope
            ),
            "slope_percent_per_bar": (
                slope_percent
            ),
            "total_change_percent": (
                total_change_percent
            ),
            "close_line": (
                close_payload
            ),
            "support_line": (
                support_payload
            ),
            "resistance_line": (
                resistance_payload
            ),
            "channel": channel,
            "breakout": breakout,
            "distance_to_support_line": (
                support_distance
            ),
            "distance_to_resistance_line": (
                resistance_distance
            ),
            "pivot_lows": [
                self._pivot_payload(
                    pivot
                )
                for pivot
                in swing_lows
            ],
            "pivot_highs": [
                self._pivot_payload(
                    pivot
                )
                for pivot
                in swing_highs
            ],
            "pivot_low_count": len(
                swing_lows
            ),
            "pivot_high_count": len(
                swing_highs
            ),
            "support_fallback": (
                fallback_support
            ),
            "resistance_fallback": (
                fallback_resistance
            ),
            "atr": atr,
            "median_bar_range": (
                median_range
            ),
            "touch_tolerance": (
                tolerance
            ),
            "bar_count": len(
                rows
            ),
            "lookback": (
                normalized_lookback
            ),
            "pivot_window": (
                normalized_pivot_window
            ),
            "method": (
                "pivot_trendlines_with_regression_fallback"
            ),
        }

    def trend(
        self,
        bars: list[dict[str, Any]],
        *,
        lookback: int = 80,
        pivot_window: int = 2,
    ) -> str:
        result = self.analyze(
            bars,
            lookback=lookback,
            pivot_window=pivot_window,
        )

        return str(
            result.get(
                "trend"
            )
            or "UNKNOWN"
        )

    def channel(
        self,
        bars: list[dict[str, Any]],
        *,
        lookback: int = 80,
        pivot_window: int = 2,
    ) -> dict[str, Any] | None:
        result = self.analyze(
            bars,
            lookback=lookback,
            pivot_window=pivot_window,
        )

        value = result.get(
            "channel"
        )

        if isinstance(
            value,
            dict,
        ):
            return value

        return None

    def pivot_points(
        self,
        bars: list[dict[str, Any]],
        *,
        lookback: int = 80,
        pivot_window: int = 2,
    ) -> dict[str, Any]:
        normalized_lookback = (
            self._positive_int(
                lookback,
                default=self.DEFAULT_LOOKBACK,
            )
        )

        normalized_window = (
            self._positive_int(
                pivot_window,
                default=self.DEFAULT_PIVOT_WINDOW,
            )
        )

        rows = self._normalize_bars(
            bars,
            lookback=normalized_lookback,
        )

        if len(rows) < self.MIN_BARS:
            return {
                "available": False,
                "pivot_lows": [],
                "pivot_highs": [],
                "reason": (
                    "Insufficient valid OHLC history"
                ),
            }

        lows = self._pivot_lows(
            rows,
            window=normalized_window,
        )

        highs = self._pivot_highs(
            rows,
            window=normalized_window,
        )

        return {
            "available": True,
            "pivot_lows": [
                self._pivot_payload(
                    pivot
                )
                for pivot in lows
            ],
            "pivot_highs": [
                self._pivot_payload(
                    pivot
                )
                for pivot in highs
            ],
            "bar_count": len(
                rows
            ),
            "pivot_window": (
                normalized_window
            ),
        }

    # ============================================================
    # BAR NORMALIZATION
    # ============================================================

    def _normalize_bars(
        self,
        bars: Any,
        *,
        lookback: int,
    ) -> list[dict[str, Any]]:
        if not isinstance(
            bars,
            Sequence,
        ) or isinstance(
            bars,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            return []

        selected = list(
            bars
        )[
            -max(
                self.MIN_BARS,
                lookback,
            ):
        ]

        output: list[
            dict[str, Any]
        ] = []

        for source_index, bar in enumerate(
            selected
        ):
            if not isinstance(
                bar,
                Mapping,
            ):
                continue

            normalized = (
                self._normalize_bar(
                    bar,
                    source_index=source_index,
                )
            )

            if normalized is None:
                continue

            output.append(
                normalized
            )

        for index, row in enumerate(
            output
        ):
            row["index"] = index

        return output

    def _normalize_bar(
        self,
        bar: Mapping[str, Any],
        *,
        source_index: int,
    ) -> dict[str, Any] | None:
        high = self._number(
            self._first(
                bar,
                "high",
                "h",
            )
        )

        low = self._number(
            self._first(
                bar,
                "low",
                "l",
            )
        )

        close = self._number(
            self._first(
                bar,
                "close",
                "c",
            )
        )

        open_price = self._number(
            self._first(
                bar,
                "open",
                "o",
            )
        )

        if (
            high is None
            or low is None
            or close is None
        ):
            return None

        if (
            high <= 0
            or low <= 0
            or close <= 0
        ):
            return None

        if high < low:
            return None

        if (
            close > high
            or close < low
        ):
            return None

        if open_price is not None:
            if (
                open_price <= 0
                or open_price > high
                or open_price < low
            ):
                open_price = None

        volume = self._number(
            self._first(
                bar,
                "volume",
                "v",
            )
        )

        if (
            volume is not None
            and volume < 0
        ):
            volume = None

        timestamp = self._timestamp(
            self._first(
                bar,
                "timestamp",
                "time",
                "datetime",
                "date",
                "t",
            )
        )

        return {
            "source_index": (
                source_index
            ),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "timestamp": timestamp,
        }

    # ============================================================
    # PIVOTS
    # ============================================================

    def _pivot_lows(
        self,
        rows: list[dict[str, Any]],
        *,
        window: int,
    ) -> list[TrendPivot]:
        if len(rows) < (
            window * 2
            + 1
        ):
            return []

        output: list[
            TrendPivot
        ] = []

        for index in range(
            window,
            len(rows) - window,
        ):
            price = rows[index][
                "low"
            ]

            before = [
                rows[position][
                    "low"
                ]
                for position in range(
                    index - window,
                    index,
                )
            ]

            after = [
                rows[position][
                    "low"
                ]
                for position in range(
                    index + 1,
                    index + window + 1,
                )
            ]

            if not before or not after:
                continue

            if (
                price <= min(
                    before
                )
                and price <= min(
                    after
                )
                and (
                    price < min(
                        before
                    )
                    or price < min(
                        after
                    )
                )
            ):
                output.append(
                    TrendPivot(
                        index=index,
                        price=price,
                        kind="LOW",
                        timestamp=rows[
                            index
                        ].get(
                            "timestamp"
                        ),
                    )
                )

        return output

    def _pivot_highs(
        self,
        rows: list[dict[str, Any]],
        *,
        window: int,
    ) -> list[TrendPivot]:
        if len(rows) < (
            window * 2
            + 1
        ):
            return []

        output: list[
            TrendPivot
        ] = []

        for index in range(
            window,
            len(rows) - window,
        ):
            price = rows[index][
                "high"
            ]

            before = [
                rows[position][
                    "high"
                ]
                for position in range(
                    index - window,
                    index,
                )
            ]

            after = [
                rows[position][
                    "high"
                ]
                for position in range(
                    index + 1,
                    index + window + 1,
                )
            ]

            if not before or not after:
                continue

            if (
                price >= max(
                    before
                )
                and price >= max(
                    after
                )
                and (
                    price > max(
                        before
                    )
                    or price > max(
                        after
                    )
                )
            ):
                output.append(
                    TrendPivot(
                        index=index,
                        price=price,
                        kind="HIGH",
                        timestamp=rows[
                            index
                        ].get(
                            "timestamp"
                        ),
                    )
                )

        return output

    # ============================================================
    # PIVOT LINE
    # ============================================================

    def _fit_pivot_line(
        self,
        pivots: list[TrendPivot],
        *,
        total_bars: int,
        source: str,
    ) -> FittedLine | None:
        if len(pivots) < (
            self.DEFAULT_MIN_PIVOTS
        ):
            return None

        x = [
            float(
                pivot.index
            )
            for pivot in pivots
        ]

        y = [
            pivot.price
            for pivot in pivots
        ]

        regression = (
            self._regression_xy(
                x,
                y,
            )
        )

        if regression is None:
            return None

        slope, intercept = (
            regression
        )

        current = (
            slope
            * (
                total_bars
                - 1
            )
            + intercept
        )

        start = intercept

        r_squared = (
            self._r_squared_xy(
                x,
                y,
                slope,
                intercept,
            )
        )

        return FittedLine(
            slope=slope,
            intercept=intercept,
            current=current,
            start=start,
            touches=len(
                pivots
            ),
            r_squared=r_squared,
            source=source,
            first_index=min(
                pivot.index
                for pivot in pivots
            ),
            last_index=max(
                pivot.index
                for pivot in pivots
            ),
        )

    def _fitted_line_from_series(
        self,
        *,
        values: list[float],
        regression: tuple[
            float,
            float,
        ],
        source: str,
    ) -> FittedLine:
        slope, intercept = (
            regression
        )

        current = (
            slope
            * (
                len(values)
                - 1
            )
            + intercept
        )

        r_squared = (
            self._r_squared(
                values,
                slope,
                intercept,
            )
        )

        return FittedLine(
            slope=slope,
            intercept=intercept,
            current=current,
            start=intercept,
            touches=0,
            r_squared=r_squared,
            source=source,
            first_index=0,
            last_index=(
                len(values)
                - 1
            ),
        )

    # ============================================================
    # TOUCH COUNT
    # ============================================================

    def _with_touch_count(
        self,
        *,
        line: FittedLine,
        rows: list[dict[str, Any]],
        field: str,
        tolerance: float,
    ) -> FittedLine:
        if tolerance <= 0:
            return line

        touches = 0

        first_index: int | None = None
        last_index: int | None = None

        for index, row in enumerate(
            rows
        ):
            price = self._number(
                row.get(
                    field
                )
            )

            if price is None:
                continue

            expected = (
                line.slope
                * index
                + line.intercept
            )

            if abs(
                price
                - expected
            ) <= tolerance:
                touches += 1

                if first_index is None:
                    first_index = (
                        index
                    )

                last_index = index

        return FittedLine(
            slope=line.slope,
            intercept=line.intercept,
            current=line.current,
            start=line.start,
            touches=touches,
            r_squared=line.r_squared,
            source=line.source,
            first_index=(
                first_index
                if first_index
                is not None
                else line.first_index
            ),
            last_index=(
                last_index
                if last_index
                is not None
                else line.last_index
            ),
        )

    # ============================================================
    # CHANNEL
    # ============================================================

    def _channel(
        self,
        *,
        support: FittedLine | None,
        resistance: FittedLine | None,
        current_price: float,
        total_bars: int,
    ) -> dict[str, Any] | None:
        if (
            support is None
            or resistance is None
        ):
            return None

        support_current = (
            support.current
        )

        resistance_current = (
            resistance.current
        )

        width = (
            resistance_current
            - support_current
        )

        start_width = (
            resistance.start
            - support.start
        )

        midpoint_current = (
            support_current
            + resistance_current
        ) / 2.0

        midpoint_start = (
            support.start
            + resistance.start
        ) / 2.0

        midpoint_slope = (
            support.slope
            + resistance.slope
        ) / 2.0

        width_percent = (
            (
                width
                / current_price
                * 100.0
            )
            if current_price > 0
            else None
        )

        parallelism = (
            self._parallelism(
                support.slope,
                resistance.slope,
                current_price=current_price,
            )
        )

        position = (
            self._channel_position(
                current_price=current_price,
                support=support_current,
                resistance=resistance_current,
            )
        )

        geometry_valid = (
            width >= 0
        )

        return {
            "valid": geometry_valid,
            "support_current": (
                support_current
            ),
            "resistance_current": (
                resistance_current
            ),
            "midpoint_current": (
                midpoint_current
            ),
            "midpoint_start": (
                midpoint_start
            ),
            "midpoint_slope": (
                midpoint_slope
            ),
            "width": (
                width
                if width >= 0
                else None
            ),
            "width_percent": (
                width_percent
                if width >= 0
                else None
            ),
            "start_width": (
                start_width
            ),
            "support_slope": (
                support.slope
            ),
            "resistance_slope": (
                resistance.slope
            ),
            "parallelism": (
                parallelism
            ),
            "price_position": (
                position
            ),
            "bar_count": (
                total_bars
            ),
        }

    # ============================================================
    # CHANNEL POSITION
    # ============================================================

    @staticmethod
    def _channel_position(
        *,
        current_price: float,
        support: float,
        resistance: float,
    ) -> float | None:
        width = (
            resistance
            - support
        )

        if (
            not isfinite(
                width
            )
            or width <= 0
        ):
            return None

        value = (
            current_price
            - support
        ) / width

        if not isfinite(
            value
        ):
            return None

        return value

    # ============================================================
    # PARALLELISM
    # ============================================================

    @staticmethod
    def _parallelism(
        support_slope: float,
        resistance_slope: float,
        *,
        current_price: float,
    ) -> dict[str, Any]:
        difference = abs(
            support_slope
            - resistance_slope
        )

        normalized_difference = (
            (
                difference
                / current_price
                * 100.0
            )
            if current_price > 0
            else None
        )

        return {
            "slope_difference": (
                difference
            ),
            "slope_difference_percent": (
                normalized_difference
            ),
        }

    # ============================================================
    # BREAKOUT
    # ============================================================

    @staticmethod
    def _breakout_state(
        *,
        current_price: float,
        support: FittedLine | None,
        resistance: FittedLine | None,
        tolerance: float | None,
    ) -> dict[str, Any]:
        effective_tolerance = (
            tolerance
            if (
                tolerance is not None
                and isfinite(
                    tolerance
                )
                and tolerance >= 0
            )
            else 0.0
        )

        above_resistance = False
        below_support = False

        if resistance is not None:
            above_resistance = (
                current_price
                > (
                    resistance.current
                    + effective_tolerance
                )
            )

        if support is not None:
            below_support = (
                current_price
                < (
                    support.current
                    - effective_tolerance
                )
            )

        state = "INSIDE_CHANNEL"

        if above_resistance:
            state = (
                "ABOVE_RESISTANCE"
            )

        elif below_support:
            state = (
                "BELOW_SUPPORT"
            )

        elif (
            support is None
            and resistance is None
        ):
            state = "UNAVAILABLE"

        return {
            "state": state,
            "above_resistance": (
                above_resistance
            ),
            "below_support": (
                below_support
            ),
            "tolerance": (
                effective_tolerance
            ),
        }

    # ============================================================
    # STRUCTURAL TREND
    # ============================================================

    def _structural_trend(
        self,
        *,
        swing_lows: list[TrendPivot],
        swing_highs: list[TrendPivot],
    ) -> str:
        low_structure = (
            self._pivot_structure(
                swing_lows
            )
        )

        high_structure = (
            self._pivot_structure(
                swing_highs
            )
        )

        if (
            low_structure
            == "RISING"
            and high_structure
            == "RISING"
        ):
            return "UPTREND"

        if (
            low_structure
            == "FALLING"
            and high_structure
            == "FALLING"
        ):
            return "DOWNTREND"

        if (
            low_structure
            == "FLAT"
            and high_structure
            == "FLAT"
        ):
            return "SIDEWAYS"

        if (
            low_structure
            == "RISING"
            and high_structure
            in {
                "RISING",
                "FLAT",
            }
        ):
            return "UPTREND"

        if (
            high_structure
            == "FALLING"
            and low_structure
            in {
                "FALLING",
                "FLAT",
            }
        ):
            return "DOWNTREND"

        return "MIXED"

    # ============================================================
    # PIVOT STRUCTURE
    # ============================================================

    @staticmethod
    def _pivot_structure(
        pivots: list[TrendPivot],
    ) -> str:
        if len(pivots) < 2:
            return "UNKNOWN"

        recent = pivots[
            -min(
                4,
                len(pivots),
            ):
        ]

        changes = [
            recent[index].price
            - recent[index - 1].price
            for index in range(
                1,
                len(recent),
            )
        ]

        if not changes:
            return "UNKNOWN"

        positive = sum(
            1
            for change in changes
            if change > 0
        )

        negative = sum(
            1
            for change in changes
            if change < 0
        )

        flat = sum(
            1
            for change in changes
            if change == 0
        )

        if (
            positive > negative
            and positive >= flat
        ):
            return "RISING"

        if (
            negative > positive
            and negative >= flat
        ):
            return "FALLING"

        if (
            flat == len(
                changes
            )
        ):
            return "FLAT"

        return "MIXED"

    # ============================================================
    # REGRESSION TREND
    # ============================================================

    @staticmethod
    def _regression_trend(
        *,
        slope: float,
        current_price: float,
        median_range: float | None,
    ) -> str:
        if (
            not isfinite(
                slope
            )
            or current_price <= 0
        ):
            return "UNKNOWN"

        normalized = (
            slope
            / current_price
        )

        if median_range is not None:
            noise_floor = (
                median_range
                / current_price
                * 0.02
            )
        else:
            noise_floor = 0.0

        if normalized > noise_floor:
            return "UPTREND"

        if normalized < -noise_floor:
            return "DOWNTREND"

        return "SIDEWAYS"

    # ============================================================
    # CHANNEL TREND
    # ============================================================

    def _channel_trend(
        self,
        *,
        support: FittedLine | None,
        resistance: FittedLine | None,
        current_price: float,
        median_range: float | None,
    ) -> str:
        slopes = [
            line.slope
            for line in (
                support,
                resistance,
            )
            if line is not None
        ]

        if not slopes:
            return "UNKNOWN"

        average_slope = (
            sum(slopes)
            / len(slopes)
        )

        return self._regression_trend(
            slope=average_slope,
            current_price=current_price,
            median_range=median_range,
        )

    # ============================================================
    # COMBINE TRENDS
    # ============================================================

    @staticmethod
    def _combine_trends(
        *,
        regression_trend: str,
        structural_trend: str,
        channel_trend: str,
    ) -> str:
        votes = [
            value
            for value in (
                regression_trend,
                structural_trend,
                channel_trend,
            )
            if value
            in {
                "UPTREND",
                "DOWNTREND",
                "SIDEWAYS",
            }
        ]

        if not votes:
            return "UNKNOWN"

        up = votes.count(
            "UPTREND"
        )

        down = votes.count(
            "DOWNTREND"
        )

        sideways = votes.count(
            "SIDEWAYS"
        )

        if (
            up > down
            and up > sideways
        ):
            return "UPTREND"

        if (
            down > up
            and down > sideways
        ):
            return "DOWNTREND"

        if (
            sideways > up
            and sideways > down
        ):
            return "SIDEWAYS"

        if (
            regression_trend
            in {
                "UPTREND",
                "DOWNTREND",
                "SIDEWAYS",
            }
        ):
            return regression_trend

        return "MIXED"

    # ============================================================
    # TREND CONSISTENCY
    # ============================================================

    @staticmethod
    def _trend_consistency(
        *,
        regression_trend: str,
        structural_trend: str,
        channel_trend: str,
    ) -> dict[str, Any]:
        values = [
            value
            for value in (
                regression_trend,
                structural_trend,
                channel_trend,
            )
            if value not in {
                "UNKNOWN",
                "MIXED",
            }
        ]

        if not values:
            return {
                "available": False,
                "agreement": None,
                "sources": 0,
            }

        counts = {
            "UPTREND": values.count(
                "UPTREND"
            ),
            "DOWNTREND": values.count(
                "DOWNTREND"
            ),
            "SIDEWAYS": values.count(
                "SIDEWAYS"
            ),
        }

        maximum = max(
            counts.values()
        )

        agreement = (
            maximum
            / len(values)
        )

        return {
            "available": True,
            "agreement": (
                agreement
            ),
            "sources": len(
                values
            ),
            "counts": counts,
        }

    # ============================================================
    # REGRESSION
    # ============================================================

    @staticmethod
    def _line(
        values: list[float],
    ) -> tuple[float, float]:
        """
        Backward-compatible regression helper.

        Unlike the previous implementation, malformed/non-finite input is
        rejected rather than silently participating in the regression.
        """

        clean: list[
            float
        ] = []

        for value in values:
            parsed = (
                TrendlineService._number(
                    value
                )
            )

            if parsed is None:
                continue

            clean.append(
                parsed
            )

        if not clean:
            return (
                0.0,
                0.0,
            )

        if len(clean) == 1:
            return (
                0.0,
                clean[0],
            )

        result = (
            TrendlineService._regression(
                clean
            )
        )

        if result is None:
            return (
                0.0,
                clean[-1],
            )

        return result

    @staticmethod
    def _regression(
        values: list[float],
    ) -> tuple[
        float,
        float,
    ] | None:
        if len(values) < 2:
            return None

        x = [
            float(index)
            for index in range(
                len(values)
            )
        ]

        return (
            TrendlineService._regression_xy(
                x,
                values,
            )
        )

    @staticmethod
    def _regression_xy(
        x: list[float],
        y: list[float],
    ) -> tuple[
        float,
        float,
    ] | None:
        if (
            len(x) != len(y)
            or len(x) < 2
        ):
            return None

        if any(
            not isfinite(
                value
            )
            for value in (
                x + y
            )
        ):
            return None

        n = float(
            len(x)
        )

        sx = sum(
            x
        )

        sy = sum(
            y
        )

        sxx = sum(
            value * value
            for value in x
        )

        sxy = sum(
            x_value
            * y_value
            for x_value, y_value
            in zip(
                x,
                y,
            )
        )

        denominator = (
            n
            * sxx
            - sx
            * sx
        )

        if (
            not isfinite(
                denominator
            )
            or abs(
                denominator
            )
            <= 1e-15
        ):
            return None

        slope = (
            (
                n
                * sxy
                - sx
                * sy
            )
            / denominator
        )

        intercept = (
            sy
            - slope
            * sx
        ) / n

        if (
            not isfinite(
                slope
            )
            or not isfinite(
                intercept
            )
        ):
            return None

        return (
            slope,
            intercept,
        )

    # ============================================================
    # R-SQUARED
    # ============================================================

    @staticmethod
    def _r_squared(
        values: list[float],
        slope: float,
        intercept: float,
    ) -> float | None:
        x = [
            float(index)
            for index in range(
                len(values)
            )
        ]

        return (
            TrendlineService._r_squared_xy(
                x,
                values,
                slope,
                intercept,
            )
        )

    @staticmethod
    def _r_squared_xy(
        x: list[float],
        y: list[float],
        slope: float,
        intercept: float,
    ) -> float | None:
        if (
            len(x) != len(y)
            or not y
        ):
            return None

        mean_y = (
            sum(y)
            / len(y)
        )

        total = sum(
            (
                value
                - mean_y
            )
            ** 2
            for value in y
        )

        residual = sum(
            (
                value
                - (
                    slope
                    * x_value
                    + intercept
                )
            )
            ** 2
            for x_value, value
            in zip(
                x,
                y,
            )
        )

        if total <= 0:
            return None

        result = (
            1.0
            - residual
            / total
        )

        if not isfinite(
            result
        ):
            return None

        return max(
            0.0,
            min(
                1.0,
                result,
            ),
        )

    # ============================================================
    # ATR
    # ============================================================

    def _atr(
        self,
        rows: list[dict[str, Any]],
        *,
        period: int = 14,
    ) -> float | None:
        if len(rows) < 2:
            return None

        true_ranges: list[
            float
        ] = []

        previous_close: float | None = None

        for row in rows:
            high = row[
                "high"
            ]

            low = row[
                "low"
            ]

            if previous_close is None:
                true_range = (
                    high
                    - low
                )

            else:
                true_range = max(
                    high - low,
                    abs(
                        high
                        - previous_close
                    ),
                    abs(
                        low
                        - previous_close
                    ),
                )

            if (
                isfinite(
                    true_range
                )
                and true_range >= 0
            ):
                true_ranges.append(
                    true_range
                )

            previous_close = row[
                "close"
            ]

        if not true_ranges:
            return None

        effective_period = min(
            self._positive_int(
                period,
                default=14,
            ),
            len(
                true_ranges
            ),
        )

        selected = true_ranges[
            -effective_period:
        ]

        if not selected:
            return None

        value = (
            sum(selected)
            / len(selected)
        )

        if (
            not isfinite(
                value
            )
            or value < 0
        ):
            return None

        return value

    # ============================================================
    # MEDIAN RANGE
    # ============================================================

    @staticmethod
    def _median_range(
        rows: list[dict[str, Any]],
    ) -> float | None:
        ranges = [
            row["high"]
            - row["low"]
            for row in rows
            if (
                row["high"]
                >= row["low"]
            )
        ]

        if not ranges:
            return None

        value = median(
            ranges
        )

        if (
            not isfinite(
                value
            )
            or value < 0
        ):
            return None

        return value

    # ============================================================
    # TOUCH TOLERANCE
    # ============================================================

    @staticmethod
    def _touch_tolerance(
        *,
        current_price: float,
        atr: float | None,
        median_range: float | None,
    ) -> float | None:
        candidates: list[
            float
        ] = []

        if (
            atr is not None
            and isfinite(
                atr
            )
            and atr > 0
        ):
            candidates.append(
                atr * 0.25
            )

        if (
            median_range is not None
            and isfinite(
                median_range
            )
            and median_range > 0
        ):
            candidates.append(
                median_range
                * 0.35
            )

        if (
            current_price > 0
            and isfinite(
                current_price
            )
        ):
            candidates.append(
                current_price
                * 0.0015
            )

        candidates = [
            value
            for value in candidates
            if (
                isfinite(
                    value
                )
                and value > 0
            )
        ]

        if not candidates:
            return None

        return max(
            candidates
        )

    # ============================================================
    # DISTANCE
    # ============================================================

    @staticmethod
    def _distance_to_line(
        current_price: float,
        line_price: float | None,
    ) -> dict[str, float] | None:
        if line_price is None:
            return None

        if (
            not isfinite(
                current_price
            )
            or not isfinite(
                line_price
            )
            or current_price <= 0
        ):
            return None

        signed = (
            current_price
            - line_price
        )

        absolute = abs(
            signed
        )

        percent = (
            signed
            / current_price
            * 100.0
        )

        return {
            "absolute": (
                absolute
            ),
            "signed": signed,
            "percent": percent,
        }

    # ============================================================
    # SLOPE
    # ============================================================

    @staticmethod
    def _slope_percent(
        slope: float,
        reference_price: float,
    ) -> float | None:
        if (
            not isfinite(
                slope
            )
            or not isfinite(
                reference_price
            )
            or reference_price <= 0
        ):
            return None

        value = (
            slope
            / reference_price
            * 100.0
        )

        if not isfinite(
            value
        ):
            return None

        return value

    # ============================================================
    # PERCENT CHANGE
    # ============================================================

    @staticmethod
    def _percent_change(
        start: float,
        end: float,
    ) -> float | None:
        if (
            not isfinite(
                start
            )
            or not isfinite(
                end
            )
            or start == 0
        ):
            return None

        value = (
            (
                end
                - start
            )
            / abs(
                start
            )
            * 100.0
        )

        if not isfinite(
            value
        ):
            return None

        return value

    # ============================================================
    # LINE PAYLOAD
    # ============================================================

    @staticmethod
    def _line_payload(
        line: FittedLine,
    ) -> dict[str, Any]:
        return {
            "slope": (
                line.slope
            ),
            "intercept": (
                line.intercept
            ),
            "start": (
                line.start
            ),
            "current": (
                line.current
            ),
            "touches": (
                line.touches
            ),
            "r_squared": (
                line.r_squared
            ),
            "source": (
                line.source
            ),
            "first_index": (
                line.first_index
            ),
            "last_index": (
                line.last_index
            ),
        }

    # ============================================================
    # PIVOT PAYLOAD
    # ============================================================

    @staticmethod
    def _pivot_payload(
        pivot: TrendPivot,
    ) -> dict[str, Any]:
        return {
            "index": (
                pivot.index
            ),
            "price": (
                pivot.price
            ),
            "kind": (
                pivot.kind
            ),
            "timestamp": (
                pivot.timestamp
            ),
        }

    # ============================================================
    # UNAVAILABLE
    # ============================================================

    @staticmethod
    def _unavailable(
        *,
        bar_count: int,
        lookback: int,
        pivot_window: int,
        reason: str,
        price: float | None = None,
    ) -> dict[str, Any]:
        return {
            "available": False,
            "price": price,
            "trend": "UNKNOWN",
            "regression_trend": (
                "UNKNOWN"
            ),
            "structural_trend": (
                "UNKNOWN"
            ),
            "channel_trend": (
                "UNKNOWN"
            ),
            "trend_consistency": {
                "available": False,
                "agreement": None,
                "sources": 0,
            },
            "slope_per_bar": None,
            "slope_percent_per_bar": (
                None
            ),
            "total_change_percent": (
                None
            ),
            "close_line": None,
            "support_line": None,
            "resistance_line": None,
            "channel": None,
            "breakout": {
                "state": "UNAVAILABLE",
                "above_resistance": False,
                "below_support": False,
                "tolerance": None,
            },
            "distance_to_support_line": (
                None
            ),
            "distance_to_resistance_line": (
                None
            ),
            "pivot_lows": [],
            "pivot_highs": [],
            "pivot_low_count": 0,
            "pivot_high_count": 0,
            "support_fallback": False,
            "resistance_fallback": (
                False
            ),
            "atr": None,
            "median_bar_range": None,
            "touch_tolerance": None,
            "bar_count": bar_count,
            "lookback": lookback,
            "pivot_window": (
                pivot_window
            ),
            "method": (
                "pivot_trendlines_with_regression_fallback"
            ),
            "reason": reason,
        }

    # ============================================================
    # VALUE HELPERS
    # ============================================================

    @staticmethod
    def _first(
        mapping: Mapping[str, Any],
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
            parsed = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(
            parsed
        ):
            return None

        return parsed

    @staticmethod
    def _positive_int(
        value: Any,
        *,
        default: int,
    ) -> int:
        if isinstance(
            value,
            bool,
        ):
            return default

        try:
            parsed = int(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return default

        if parsed <= 0:
            return default

        return parsed

    @staticmethod
    def _timestamp(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            return value.isoformat()

        text = str(
            value
        ).strip()

        if not text:
            return None

        return text


trendline_service = TrendlineService()


__all__ = [
    "FittedLine",
    "TrendPivot",
    "TrendlineService",
    "trendline_service",
]