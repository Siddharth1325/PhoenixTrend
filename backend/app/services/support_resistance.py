from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from statistics import median
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class PriceLevel:
    price: float
    touches: int
    first_index: int
    last_index: int
    source: str
    strength: float | None = None
    distance: float | None = None
    distance_percent: float | None = None


@dataclass(frozen=True)
class PivotPoint:
    index: int
    price: float
    kind: str
    timestamp: str | None = None


class SupportResistanceService:
    """
    PhoenixTrend support/resistance analysis service.

    The service derives price levels only from supplied OHLC bars.

    It does not:
        - fabricate missing OHLC values
        - fabricate ATR
        - fabricate volume
        - fabricate timestamps
        - fabricate support/resistance when history is insufficient
        - generate BUY/SELL decisions
        - authorize execution

    Analysis includes:
        - normalized OHLC validation
        - swing-high / swing-low detection
        - clustered pivot levels
        - touch counting
        - recency metadata
        - nearest support/resistance
        - broken-level detection
        - role-reversal detection
        - distance from current price
        - optional ATR-aware clustering when genuine ATR can be derived
    """

    DEFAULT_LOOKBACK = 120
    DEFAULT_LEVELS = 3
    DEFAULT_PIVOT_WINDOW = 2

    MIN_BARS = 5

    def analyze(
        self,
        bars: list[dict[str, Any]],
        *,
        lookback: int = 120,
        pivots: int = 3,
        pivot_window: int = 2,
    ) -> dict[str, Any]:
        normalized_lookback = self._positive_int(
            lookback,
            default=self.DEFAULT_LOOKBACK,
        )

        level_limit = self._positive_int(
            pivots,
            default=self.DEFAULT_LEVELS,
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

        current = rows[-1]["close"]

        atr = self._atr(
            rows
        )

        median_range = self._median_range(
            rows
        )

        tolerance = self._cluster_tolerance(
            current=current,
            atr=atr,
            median_range=median_range,
        )

        if tolerance is None or tolerance <= 0:
            return self._unavailable(
                bar_count=len(rows),
                lookback=normalized_lookback,
                pivot_window=normalized_pivot_window,
                reason="Unable to derive a valid clustering tolerance",
                price=current,
            )

        swing_lows = self._pivot_lows(
            rows,
            window=normalized_pivot_window,
        )

        swing_highs = self._pivot_highs(
            rows,
            window=normalized_pivot_window,
        )

        support_candidates = [
            pivot
            for pivot in swing_lows
            if pivot.price <= current
        ]

        resistance_candidates = [
            pivot
            for pivot in swing_highs
            if pivot.price >= current
        ]

        support_levels = self._cluster_pivots(
            support_candidates,
            tolerance=tolerance,
            current=current,
            side="support",
            limit=level_limit,
            total_bars=len(rows),
        )

        resistance_levels = self._cluster_pivots(
            resistance_candidates,
            tolerance=tolerance,
            current=current,
            side="resistance",
            limit=level_limit,
            total_bars=len(rows),
        )

        historical_support = self._cluster_pivots(
            swing_lows,
            tolerance=tolerance,
            current=current,
            side="support",
            limit=None,
            total_bars=len(rows),
        )

        historical_resistance = self._cluster_pivots(
            swing_highs,
            tolerance=tolerance,
            current=current,
            side="resistance",
            limit=None,
            total_bars=len(rows),
        )

        role_reversals = self._role_reversals(
            current=current,
            support_levels=historical_support,
            resistance_levels=historical_resistance,
            tolerance=tolerance,
        )

        nearest_support = (
            support_levels[0]["price"]
            if support_levels
            else None
        )

        nearest_resistance = (
            resistance_levels[0]["price"]
            if resistance_levels
            else None
        )

        support_prices = [
            level["price"]
            for level in support_levels
        ]

        resistance_prices = [
            level["price"]
            for level in resistance_levels
        ]

        return {
            "available": True,
            "price": current,
            "support": support_prices,
            "resistance": resistance_prices,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "pivot_lows": [
                self._pivot_payload(
                    pivot
                )
                for pivot in swing_lows
            ],
            "pivot_highs": [
                self._pivot_payload(
                    pivot
                )
                for pivot in swing_highs
            ],
            "role_reversals": role_reversals,
            "distance_to_support": self._distance_payload(
                current,
                nearest_support,
            ),
            "distance_to_resistance": self._distance_payload(
                current,
                nearest_resistance,
            ),
            "bar_count": len(rows),
            "lookback": normalized_lookback,
            "pivot_window": normalized_pivot_window,
            "cluster_tolerance": tolerance,
            "atr": atr,
            "median_bar_range": median_range,
            "method": "clustered_swing_pivots",
        }

    def levels(
        self,
        bars: list[dict[str, Any]],
        *,
        lookback: int = 120,
        pivots: int = 3,
        pivot_window: int = 2,
    ) -> dict[str, Any]:
        return self.analyze(
            bars,
            lookback=lookback,
            pivots=pivots,
            pivot_window=pivot_window,
        )

    def nearest(
        self,
        bars: list[dict[str, Any]],
        *,
        lookback: int = 120,
        pivot_window: int = 2,
    ) -> dict[str, Any]:
        result = self.analyze(
            bars,
            lookback=lookback,
            pivots=1,
            pivot_window=pivot_window,
        )

        return {
            "available": result.get(
                "available",
                False,
            ),
            "price": result.get(
                "price"
            ),
            "nearest_support": result.get(
                "nearest_support"
            ),
            "nearest_resistance": result.get(
                "nearest_resistance"
            ),
            "distance_to_support": result.get(
                "distance_to_support"
            ),
            "distance_to_resistance": result.get(
                "distance_to_resistance"
            ),
            "reason": result.get(
                "reason"
            ),
        }

    def pivot_points(
        self,
        bars: list[dict[str, Any]],
        *,
        lookback: int = 120,
        pivot_window: int = 2,
    ) -> dict[str, Any]:
        rows = self._normalize_bars(
            bars,
            lookback=self._positive_int(
                lookback,
                default=self.DEFAULT_LOOKBACK,
            ),
        )

        if len(rows) < self.MIN_BARS:
            return {
                "available": False,
                "pivot_lows": [],
                "pivot_highs": [],
                "reason": "Insufficient valid OHLC history",
            }

        window = self._positive_int(
            pivot_window,
            default=self.DEFAULT_PIVOT_WINDOW,
        )

        lows = self._pivot_lows(
            rows,
            window=window,
        )

        highs = self._pivot_highs(
            rows,
            window=window,
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
            "bar_count": len(rows),
            "pivot_window": window,
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
        )[-max(
            self.MIN_BARS,
            lookback,
        ):]

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

            normalized = self._normalize_bar(
                bar,
                source_index=source_index,
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

        if close > high or close < low:
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
            "source_index": source_index,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "timestamp": timestamp,
        }

    # ============================================================
    # PIVOT DETECTION
    # ============================================================

    def _pivot_lows(
        self,
        rows: list[dict[str, Any]],
        *,
        window: int,
    ) -> list[PivotPoint]:
        if len(rows) < (
            window * 2
            + 1
        ):
            return []

        output: list[
            PivotPoint
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
                price <= min(before)
                and price <= min(after)
                and (
                    price < min(before)
                    or price < min(after)
                )
            ):
                output.append(
                    PivotPoint(
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
    ) -> list[PivotPoint]:
        if len(rows) < (
            window * 2
            + 1
        ):
            return []

        output: list[
            PivotPoint
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
                price >= max(before)
                and price >= max(after)
                and (
                    price > max(before)
                    or price > max(after)
                )
            ):
                output.append(
                    PivotPoint(
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
    # CLUSTERING
    # ============================================================

    def _cluster_pivots(
        self,
        pivots: list[PivotPoint],
        *,
        tolerance: float,
        current: float,
        side: str,
        limit: int | None,
        total_bars: int,
    ) -> list[dict[str, Any]]:
        if not pivots:
            return []

        if not isfinite(
            tolerance
        ) or tolerance <= 0:
            return []

        ordered = sorted(
            pivots,
            key=lambda item: (
                item.price,
                item.index,
            ),
        )

        groups: list[
            list[PivotPoint]
        ] = []

        for pivot in ordered:
            best_group: list[
                PivotPoint
            ] | None = None

            best_distance: float | None = None

            for group in groups:
                center = self._pivot_group_center(
                    group
                )

                distance = abs(
                    pivot.price
                    - center
                )

                if distance > tolerance:
                    continue

                if (
                    best_distance is None
                    or distance
                    < best_distance
                ):
                    best_group = group
                    best_distance = distance

            if best_group is None:
                groups.append(
                    [pivot]
                )
            else:
                best_group.append(
                    pivot
                )

        levels: list[
            dict[str, Any]
        ] = []

        for group in groups:
            center = self._pivot_group_center(
                group
            )

            if side == "support":
                if center > current:
                    continue

            elif side == "resistance":
                if center < current:
                    continue

            else:
                continue

            indexes = [
                pivot.index
                for pivot in group
            ]

            prices = [
                pivot.price
                for pivot in group
            ]

            touches = len(
                group
            )

            first_index = min(
                indexes
            )

            last_index = max(
                indexes
            )

            distance = abs(
                current
                - center
            )

            distance_percent = (
                distance
                / current
                * 100.0
                if current > 0
                else None
            )

            strength = (
                self._level_strength(
                    touches=touches,
                    last_index=last_index,
                    total_bars=total_bars,
                )
            )

            levels.append(
                {
                    "price": round(
                        center,
                        6,
                    ),
                    "touches": touches,
                    "first_index": (
                        first_index
                    ),
                    "last_index": (
                        last_index
                    ),
                    "first_timestamp": (
                        self._first_group_timestamp(
                            group
                        )
                    ),
                    "last_timestamp": (
                        self._last_group_timestamp(
                            group
                        )
                    ),
                    "minimum": round(
                        min(prices),
                        6,
                    ),
                    "maximum": round(
                        max(prices),
                        6,
                    ),
                    "width": round(
                        max(prices)
                        - min(prices),
                        6,
                    ),
                    "distance": round(
                        distance,
                        6,
                    ),
                    "distance_percent": (
                        round(
                            distance_percent,
                            6,
                        )
                        if distance_percent
                        is not None
                        else None
                    ),
                    "strength": strength,
                    "source": (
                        "swing_lows"
                        if side
                        == "support"
                        else "swing_highs"
                    ),
                }
            )

        if side == "support":
            levels.sort(
                key=lambda level: (
                    level[
                        "distance"
                    ],
                    -level[
                        "touches"
                    ],
                    -level[
                        "last_index"
                    ],
                )
            )

        else:
            levels.sort(
                key=lambda level: (
                    level[
                        "distance"
                    ],
                    -level[
                        "touches"
                    ],
                    -level[
                        "last_index"
                    ],
                )
            )

        if limit is not None:
            return levels[
                :limit
            ]

        return levels

    # ============================================================
    # BACKWARD-COMPATIBLE CLUSTER
    # ============================================================

    @staticmethod
    def _cluster(
        values: list[float],
        tolerance: float,
        limit: int,
    ) -> list[float]:
        clean_values = [
            value
            for value in (
                SupportResistanceService._number(
                    item
                )
                for item in values
            )
            if value is not None
        ]

        if not clean_values:
            return []

        if (
            not isfinite(
                tolerance
            )
            or tolerance <= 0
        ):
            return []

        normalized_limit = (
            SupportResistanceService._positive_int(
                limit,
                default=3,
            )
        )

        groups: list[
            list[float]
        ] = []

        for value in sorted(
            clean_values
        ):
            best_group: list[
                float
            ] | None = None

            best_distance: float | None = None

            for group in groups:
                center = sum(
                    group
                ) / len(
                    group
                )

                distance = abs(
                    value
                    - center
                )

                if distance > tolerance:
                    continue

                if (
                    best_distance is None
                    or distance
                    < best_distance
                ):
                    best_group = group
                    best_distance = distance

            if best_group is None:
                groups.append(
                    [value]
                )
            else:
                best_group.append(
                    value
                )

        groups.sort(
            key=lambda group: (
                -len(
                    group
                ),
                (
                    max(group)
                    - min(group)
                ),
                -max(
                    group
                ),
            )
        )

        return [
            round(
                sum(group)
                / len(group),
                6,
            )
            for group in groups[
                :normalized_limit
            ]
        ]

    # ============================================================
    # LEVEL STRENGTH
    # ============================================================

    @staticmethod
    def _level_strength(
        *,
        touches: int,
        last_index: int,
        total_bars: int,
    ) -> float | None:
        if (
            touches <= 0
            or total_bars <= 0
            or last_index < 0
        ):
            return None

        touch_component = min(
            1.0,
            touches / 5.0,
        )

        recency_component = (
            (
                last_index
                + 1
            )
            / total_bars
        )

        strength = (
            touch_component
            * 0.7
            + recency_component
            * 0.3
        )

        if not isfinite(
            strength
        ):
            return None

        return round(
            max(
                0.0,
                min(
                    1.0,
                    strength,
                ),
            ),
            6,
        )

    # ============================================================
    # ROLE REVERSAL
    # ============================================================

    def _role_reversals(
        self,
        *,
        current: float,
        support_levels: list[dict[str, Any]],
        resistance_levels: list[dict[str, Any]],
        tolerance: float,
    ) -> list[dict[str, Any]]:
        output: list[
            dict[str, Any]
        ] = []

        seen: set[
            tuple[str, float]
        ] = set()

        for level in resistance_levels:
            price = self._number(
                level.get(
                    "price"
                )
            )

            if price is None:
                continue

            if current <= (
                price
                + tolerance
            ):
                continue

            key = (
                "RESISTANCE_TO_SUPPORT",
                round(
                    price,
                    6,
                ),
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            output.append(
                {
                    "price": round(
                        price,
                        6,
                    ),
                    "type": (
                        "RESISTANCE_TO_SUPPORT"
                    ),
                    "previous_role": (
                        "RESISTANCE"
                    ),
                    "current_role": (
                        "POTENTIAL_SUPPORT"
                    ),
                    "touches": (
                        level.get(
                            "touches"
                        )
                    ),
                }
            )

        for level in support_levels:
            price = self._number(
                level.get(
                    "price"
                )
            )

            if price is None:
                continue

            if current >= (
                price
                - tolerance
            ):
                continue

            key = (
                "SUPPORT_TO_RESISTANCE",
                round(
                    price,
                    6,
                ),
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            output.append(
                {
                    "price": round(
                        price,
                        6,
                    ),
                    "type": (
                        "SUPPORT_TO_RESISTANCE"
                    ),
                    "previous_role": (
                        "SUPPORT"
                    ),
                    "current_role": (
                        "POTENTIAL_RESISTANCE"
                    ),
                    "touches": (
                        level.get(
                            "touches"
                        )
                    ),
                }
            )

        output.sort(
            key=lambda item: abs(
                current
                - float(
                    item[
                        "price"
                    ]
                )
            )
        )

        return output

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

        value = sum(
            selected
        ) / len(
            selected
        )

        if (
            not isfinite(
                value
            )
            or value < 0
        ):
            return None

        return round(
            value,
            6,
        )

    # ============================================================
    # MEDIAN RANGE
    # ============================================================

    @staticmethod
    def _median_range(
        rows: list[dict[str, Any]],
    ) -> float | None:
        ranges = [
            row[
                "high"
            ]
            - row[
                "low"
            ]
            for row in rows
            if (
                isfinite(
                    row[
                        "high"
                    ]
                )
                and isfinite(
                    row[
                        "low"
                    ]
                )
                and row[
                    "high"
                ]
                >= row[
                    "low"
                ]
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

        return round(
            value,
            6,
        )

    # ============================================================
    # CLUSTER TOLERANCE
    # ============================================================

    @staticmethod
    def _cluster_tolerance(
        *,
        current: float,
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
                atr * 0.35
            )

        if (
            median_range is not None
            and isfinite(
                median_range
            )
            and median_range > 0
        ):
            candidates.append(
                median_range * 0.5
            )

        if (
            isfinite(
                current
            )
            and current > 0
        ):
            candidates.append(
                current * 0.0025
            )

        candidates = [
            candidate
            for candidate
            in candidates
            if (
                isfinite(
                    candidate
                )
                and candidate > 0
            )
        ]

        if not candidates:
            return None

        return round(
            max(
                candidates
            ),
            6,
        )

    # ============================================================
    # DISTANCE
    # ============================================================

    @staticmethod
    def _distance_payload(
        current: float,
        level: float | None,
    ) -> dict[str, float] | None:
        if level is None:
            return None

        if (
            not isfinite(
                current
            )
            or not isfinite(
                level
            )
            or current <= 0
        ):
            return None

        signed = (
            level
            - current
        )

        absolute = abs(
            signed
        )

        percent = (
            signed
            / current
            * 100.0
        )

        return {
            "absolute": round(
                absolute,
                6,
            ),
            "signed": round(
                signed,
                6,
            ),
            "percent": round(
                percent,
                6,
            ),
        }

    # ============================================================
    # GROUP HELPERS
    # ============================================================

    @staticmethod
    def _pivot_group_center(
        group: list[PivotPoint],
    ) -> float:
        return sum(
            pivot.price
            for pivot in group
        ) / len(
            group
        )

    @staticmethod
    def _first_group_timestamp(
        group: list[PivotPoint],
    ) -> str | None:
        ordered = sorted(
            group,
            key=lambda item: (
                item.index
            ),
        )

        for pivot in ordered:
            if pivot.timestamp:
                return pivot.timestamp

        return None

    @staticmethod
    def _last_group_timestamp(
        group: list[PivotPoint],
    ) -> str | None:
        ordered = sorted(
            group,
            key=lambda item: (
                item.index
            ),
            reverse=True,
        )

        for pivot in ordered:
            if pivot.timestamp:
                return pivot.timestamp

        return None

    @staticmethod
    def _pivot_payload(
        pivot: PivotPoint,
    ) -> dict[str, Any]:
        return {
            "index": pivot.index,
            "price": round(
                pivot.price,
                6,
            ),
            "kind": pivot.kind,
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
            "support": [],
            "resistance": [],
            "nearest_support": None,
            "nearest_resistance": None,
            "support_levels": [],
            "resistance_levels": [],
            "pivot_lows": [],
            "pivot_highs": [],
            "role_reversals": [],
            "distance_to_support": None,
            "distance_to_resistance": None,
            "bar_count": bar_count,
            "lookback": lookback,
            "pivot_window": (
                pivot_window
            ),
            "cluster_tolerance": None,
            "atr": None,
            "median_bar_range": None,
            "method": (
                "clustered_swing_pivots"
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


support_resistance_service = SupportResistanceService()


__all__ = [
    "PivotPoint",
    "PriceLevel",
    "SupportResistanceService",
    "support_resistance_service",
]