from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class PatternEvidence:
    name: str
    direction: str | None
    category: str | None
    confidence: float | None
    strength: float | None
    timeframe: str | None
    confirmed: bool | None


class StrategyPatternMapper:
    """
    PhoenixTrend strategy/pattern compatibility mapper.

    This service provides contextual compatibility metadata only.

    It does NOT:
        - generate BUY/SELL/HOLD decisions
        - replace StrategyRegistry implementations
        - replace StrategyPicker
        - override DecisionEngine
        - fabricate strategy scores
        - fabricate pattern confidence
        - fabricate market regime
        - authorize execution
        - bypass MarketSafety or RiskEngine

    Compatibility is derived only from:
        - the supplied strategy name
        - verified pattern metadata
        - supplied market-regime metadata

    Missing information remains missing rather than receiving a synthetic
    neutral score.

    The DecisionEngine and the actual strategy implementation remain
    authoritative.
    """

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

    TREND = "TREND"
    REVERSAL = "REVERSAL"
    BREAKOUT = "BREAKOUT"
    MOMENTUM = "MOMENTUM"
    MEAN_REVERSION = "MEAN_REVERSION"
    VOLATILITY = "VOLATILITY"
    RANGE = "RANGE"
    VOLUME = "VOLUME"
    SUPPORT_RESISTANCE = "SUPPORT_RESISTANCE"
    CANDLESTICK = "CANDLESTICK"
    STRUCTURAL = "STRUCTURAL"
    UNKNOWN = "UNKNOWN"

    TREND_STRATEGY_WORDS = (
        "trend",
        "ema",
        "sma",
        "moving average",
        "moving_average",
        "macd",
        "supertrend",
        "ichimoku",
        "adx",
        "trend following",
        "trend_following",
        "trendfollowing",
    )

    BREAKOUT_STRATEGY_WORDS = (
        "breakout",
        "break out",
        "orb",
        "opening range",
        "opening_range",
        "donchian",
        "channel breakout",
        "channel_breakout",
        "range breakout",
        "range_breakout",
        "volatility breakout",
        "volatility_breakout",
    )

    MOMENTUM_STRATEGY_WORDS = (
        "momentum",
        "roc",
        "rate of change",
        "rate_of_change",
        "relative strength",
        "relative_strength",
        "macd",
        "rsi momentum",
        "rsi_momentum",
    )

    REVERSAL_STRATEGY_WORDS = (
        "reversal",
        "reverse",
        "turnaround",
        "countertrend",
        "counter trend",
        "counter_trend",
    )

    MEAN_REVERSION_STRATEGY_WORDS = (
        "mean reversion",
        "mean_reversion",
        "meanreversion",
        "bollinger",
        "rsi",
        "stochastic",
        "oversold",
        "overbought",
        "zscore",
        "z-score",
        "z score",
    )

    VOLATILITY_STRATEGY_WORDS = (
        "volatility",
        "atr",
        "bollinger",
        "keltner",
        "squeeze",
    )

    VOLUME_STRATEGY_WORDS = (
        "volume",
        "obv",
        "vwap",
        "money flow",
        "money_flow",
        "mfi",
        "accumulation",
        "distribution",
    )

    SUPPORT_RESISTANCE_STRATEGY_WORDS = (
        "support",
        "resistance",
        "pivot",
        "vwap",
        "supply",
        "demand",
    )

    RANGE_STRATEGY_WORDS = (
        "range",
        "sideways",
        "mean reversion",
        "mean_reversion",
        "bollinger",
        "stochastic",
    )

    BULLISH_PATTERN_NAMES = (
        "double bottom",
        "triple bottom",
        "inverse head and shoulders",
        "inverse head & shoulders",
        "inverse h&s",
        "bull flag",
        "bullish flag",
        "bull pennant",
        "bullish pennant",
        "ascending triangle",
        "falling wedge",
        "cup and handle",
        "cup & handle",
        "bullish rectangle",
        "bullish channel",
        "bullish breakout",
        "bullish engulfing",
        "bullish harami",
        "morning star",
        "hammer",
        "inverted hammer",
        "piercing",
        "piercing line",
        "three white soldiers",
        "tweezer bottom",
        "dragonfly doji",
        "bullish marubozu",
        "bullish kicker",
        "bullish belt hold",
        "bullish abandoned baby",
        "bullish three line strike",
        "three inside up",
        "three outside up",
        "rising three methods",
        "ladder bottom",
        "matching low",
        "homing pigeon",
        "concealing baby swallow",
        "breakaway bullish",
        "upside tasuki gap",
        "bullish gap",
        "v bottom",
        "rounded bottom",
        "rounding bottom",
        "bump and run bullish",
        "quasimodo bullish",
        "scallop bullish",
    )

    BEARISH_PATTERN_NAMES = (
        "double top",
        "triple top",
        "head and shoulders",
        "head & shoulders",
        "h&s",
        "bear flag",
        "bearish flag",
        "bear pennant",
        "bearish pennant",
        "descending triangle",
        "rising wedge",
        "bearish rectangle",
        "bearish channel",
        "bearish breakout",
        "bearish engulfing",
        "bearish harami",
        "evening star",
        "hanging man",
        "shooting star",
        "dark cloud",
        "dark cloud cover",
        "three black crows",
        "tweezer top",
        "gravestone doji",
        "bearish marubozu",
        "bearish kicker",
        "bearish belt hold",
        "bearish abandoned baby",
        "bearish three line strike",
        "three inside down",
        "three outside down",
        "falling three methods",
        "advance block",
        "deliberation",
        "breakaway bearish",
        "downside tasuki gap",
        "bearish gap",
        "v top",
        "rounded top",
        "rounding top",
        "bump and run bearish",
        "quasimodo bearish",
        "scallop bearish",
    )

    REVERSAL_PATTERN_WORDS = (
        "double top",
        "double bottom",
        "triple top",
        "triple bottom",
        "head and shoulders",
        "head & shoulders",
        "inverse head",
        "rounding top",
        "rounding bottom",
        "rounded top",
        "rounded bottom",
        "diamond top",
        "diamond bottom",
        "island reversal",
        "quasimodo",
        "v top",
        "v bottom",
        "spike top",
        "spike bottom",
        "bump and run",
        "dead cat bounce",
        "three drives",
        "harmonic",
        "gartley",
        "bat pattern",
        "butterfly",
        "crab pattern",
        "shark pattern",
        "cypher",
        "engulfing",
        "harami",
        "morning star",
        "evening star",
        "hammer",
        "hanging man",
        "shooting star",
        "inverted hammer",
        "piercing",
        "dark cloud",
        "tweezer",
        "abandoned baby",
        "kicker",
    )

    CONTINUATION_PATTERN_WORDS = (
        "flag",
        "pennant",
        "rectangle",
        "channel",
        "rising three",
        "falling three",
        "tasuki",
        "staircase",
        "scallop",
    )

    BREAKOUT_PATTERN_WORDS = (
        "breakout",
        "break out",
        "triangle",
        "wedge",
        "flag",
        "pennant",
        "rectangle",
        "channel",
        "cup and handle",
        "cup & handle",
        "broadening",
        "megaphone",
        "diamond",
        "gap",
        "opening range",
    )

    TREND_PATTERN_WORDS = (
        "channel",
        "trend",
        "staircase",
        "flag",
        "pennant",
        "elliott",
        "wave",
        "three drives",
        "scallop",
    )

    RANGE_PATTERN_WORDS = (
        "rectangle",
        "range",
        "sideways",
        "consolidation",
        "box",
    )

    VOLATILITY_PATTERN_WORDS = (
        "broadening",
        "megaphone",
        "wedge",
        "triangle",
        "squeeze",
        "expansion",
        "gap",
        "spike",
    )

    CANDLESTICK_WORDS = (
        "doji",
        "hammer",
        "hanging man",
        "shooting star",
        "inverted hammer",
        "engulfing",
        "harami",
        "morning star",
        "evening star",
        "marubozu",
        "three white soldiers",
        "three black crows",
        "tweezer",
        "piercing",
        "dark cloud",
        "kicker",
        "belt hold",
        "abandoned baby",
        "three line strike",
        "three inside",
        "three outside",
        "rising three methods",
        "falling three methods",
        "dragonfly",
        "gravestone",
        "spinning top",
        "inside bar",
        "outside bar",
        "pin bar",
    )

    BULLISH_REGIME_WORDS = (
        "bull",
        "bullish",
        "uptrend",
        "up trend",
        "strong bull",
        "strong_bull",
        "strong bullish",
        "strong_bullish",
    )

    BEARISH_REGIME_WORDS = (
        "bear",
        "bearish",
        "downtrend",
        "down trend",
        "strong bear",
        "strong_bear",
        "strong bearish",
        "strong_bearish",
    )

    RANGE_REGIME_WORDS = (
        "range",
        "ranging",
        "sideways",
        "neutral",
        "consolidation",
        "consolidating",
        "choppy",
    )

    TREND_REGIME_WORDS = (
        "trend",
        "trending",
        "bull",
        "bear",
        "uptrend",
        "downtrend",
        "directional",
    )

    HIGH_VOLATILITY_REGIME_WORDS = (
        "high volatility",
        "high_volatility",
        "volatile",
        "volatility expansion",
        "volatility_expansion",
    )

    LOW_VOLATILITY_REGIME_WORDS = (
        "low volatility",
        "low_volatility",
        "compression",
        "squeeze",
    )

    def compatibility(
        self,
        strategy_name: str,
        patterns: list[dict[str, Any]],
        regime: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Describe compatibility between a strategy, verified pattern evidence,
        and the supplied market regime.

        No compatibility number is emitted unless there is actual contextual
        evidence from patterns or regime. This prevents a synthetic default
        score such as 0.5 from being mistaken for model evidence.
        """

        clean_strategy = self._strategy_name(
            strategy_name
        )

        normalized_patterns = self._patterns(
            patterns
        )

        normalized_regime = self._regime(
            regime
        )

        profile = self.strategy_profile(
            clean_strategy
        )

        evidence: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []

        pattern_matches = 0
        pattern_conflicts = 0
        regime_matches = 0
        regime_conflicts = 0

        strategy_categories = set(
            profile["categories"]
        )

        strategy_direction = profile.get(
            "direction"
        )

        for pattern in normalized_patterns:
            assessment = self._assess_pattern(
                pattern=pattern,
                strategy_categories=strategy_categories,
                strategy_direction=strategy_direction,
            )

            if assessment["compatible"]:
                pattern_matches += 1
                evidence.append(
                    assessment
                )

            if assessment["conflict"]:
                pattern_conflicts += 1
                conflicts.append(
                    assessment
                )

        regime_assessment = self._assess_regime(
            profile=profile,
            regime=normalized_regime,
        )

        if regime_assessment is not None:
            if regime_assessment[
                "compatible"
            ]:
                regime_matches += 1
                evidence.append(
                    regime_assessment
                )

            if regime_assessment[
                "conflict"
            ]:
                regime_conflicts += 1
                conflicts.append(
                    regime_assessment
                )

        directional_pattern_summary = (
            self._directional_pattern_summary(
                normalized_patterns
            )
        )

        directional_assessment = (
            self._directional_alignment(
                strategy_direction=(
                    strategy_direction
                ),
                pattern_summary=(
                    directional_pattern_summary
                ),
                regime=normalized_regime,
            )
        )

        if directional_assessment is not None:
            if directional_assessment[
                "compatible"
            ]:
                evidence.append(
                    directional_assessment
                )

            if directional_assessment[
                "conflict"
            ]:
                conflicts.append(
                    directional_assessment
                )

        compatibility = (
            self._compatibility_value(
                evidence=evidence,
                conflicts=conflicts,
            )
        )

        reasons = [
            str(item["reason"])
            for item in evidence
            if item.get("reason")
        ]

        conflict_reasons = [
            str(item["reason"])
            for item in conflicts
            if item.get("reason")
        ]

        return {
            "strategy": clean_strategy,
            "strategy_profile": profile,
            "compatibility": compatibility,
            "has_context": bool(
                normalized_patterns
                or normalized_regime
            ),
            "pattern_count": len(
                normalized_patterns
            ),
            "pattern_matches": (
                pattern_matches
            ),
            "pattern_conflicts": (
                pattern_conflicts
            ),
            "regime_matches": (
                regime_matches
            ),
            "regime_conflicts": (
                regime_conflicts
            ),
            "pattern_direction": (
                directional_pattern_summary
            ),
            "regime": normalized_regime,
            "evidence": evidence,
            "conflicts": conflicts,
            "reasons": self._dedupe(
                reasons
            ),
            "conflict_reasons": self._dedupe(
                conflict_reasons
            ),
        }

    def map(
        self,
        strategy_names: Iterable[str],
        patterns: list[dict[str, Any]],
        regime: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Evaluate compatibility for multiple strategies.

        This method preserves caller order. It intentionally does not rank
        strategies because strategy ranking belongs to StrategyPicker /
        DecisionEngine.
        """

        output: list[
            dict[str, Any]
        ] = []

        seen: set[str] = set()

        for strategy_name in (
            strategy_names
        ):
            clean = self._strategy_name(
                strategy_name
            )

            key = clean.casefold()

            if key in seen:
                continue

            seen.add(key)

            output.append(
                self.compatibility(
                    clean,
                    patterns,
                    regime,
                )
            )

        return output

    def compatible_patterns(
        self,
        strategy_name: str,
        patterns: list[dict[str, Any]],
        regime: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = self.compatibility(
            strategy_name,
            patterns,
            regime,
        )

        return [
            dict(item)
            for item in result[
                "evidence"
            ]
            if item.get(
                "source"
            )
            == "pattern"
        ]

    def conflicts(
        self,
        strategy_name: str,
        patterns: list[dict[str, Any]],
        regime: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = self.compatibility(
            strategy_name,
            patterns,
            regime,
        )

        return [
            dict(item)
            for item in result[
                "conflicts"
            ]
        ]

    def strategy_profile(
        self,
        strategy_name: str,
    ) -> dict[str, Any]:
        """
        Infer broad compatibility categories from a strategy's registered
        human-readable name.

        This is descriptive metadata only. It does not claim how the strategy
        implementation actually calculates its signal.
        """

        clean = self._strategy_name(
            strategy_name
        )

        normalized = self._normalize_text(
            clean
        )

        categories: list[str] = []

        self._append_category_if_matching(
            categories,
            normalized,
            self.TREND_STRATEGY_WORDS,
            self.TREND,
        )

        self._append_category_if_matching(
            categories,
            normalized,
            self.BREAKOUT_STRATEGY_WORDS,
            self.BREAKOUT,
        )

        self._append_category_if_matching(
            categories,
            normalized,
            self.MOMENTUM_STRATEGY_WORDS,
            self.MOMENTUM,
        )

        self._append_category_if_matching(
            categories,
            normalized,
            self.REVERSAL_STRATEGY_WORDS,
            self.REVERSAL,
        )

        self._append_category_if_matching(
            categories,
            normalized,
            self.MEAN_REVERSION_STRATEGY_WORDS,
            self.MEAN_REVERSION,
        )

        self._append_category_if_matching(
            categories,
            normalized,
            self.VOLATILITY_STRATEGY_WORDS,
            self.VOLATILITY,
        )

        self._append_category_if_matching(
            categories,
            normalized,
            self.VOLUME_STRATEGY_WORDS,
            self.VOLUME,
        )

        self._append_category_if_matching(
            categories,
            normalized,
            self.SUPPORT_RESISTANCE_STRATEGY_WORDS,
            self.SUPPORT_RESISTANCE,
        )

        self._append_category_if_matching(
            categories,
            normalized,
            self.RANGE_STRATEGY_WORDS,
            self.RANGE,
        )

        direction = (
            self._direction_from_text(
                normalized
            )
        )

        return {
            "name": clean,
            "categories": categories,
            "direction": direction,
            "classified": bool(
                categories
                or direction
            ),
        }

    def pattern_profile(
        self,
        pattern: Mapping[str, Any],
    ) -> dict[str, Any]:
        evidence = self._pattern(
            pattern
        )

        if evidence is None:
            raise ValueError(
                "Pattern must contain usable pattern metadata"
            )

        categories = (
            self._pattern_categories(
                evidence
            )
        )

        return {
            "name": evidence.name,
            "direction": (
                evidence.direction
            ),
            "category": (
                evidence.category
            ),
            "categories": categories,
            "confidence": (
                evidence.confidence
            ),
            "strength": (
                evidence.strength
            ),
            "timeframe": (
                evidence.timeframe
            ),
            "confirmed": (
                evidence.confirmed
            ),
        }

    def _assess_pattern(
        self,
        *,
        pattern: PatternEvidence,
        strategy_categories: set[str],
        strategy_direction: str | None,
    ) -> dict[str, Any]:
        pattern_categories = set(
            self._pattern_categories(
                pattern
            )
        )

        shared_categories = sorted(
            strategy_categories
            & pattern_categories
        )

        category_match = bool(
            shared_categories
        )

        direction_match = False
        direction_conflict = False

        if (
            strategy_direction
            in {
                self.BULLISH,
                self.BEARISH,
            }
            and pattern.direction
            in {
                self.BULLISH,
                self.BEARISH,
            }
        ):
            direction_match = (
                strategy_direction
                == pattern.direction
            )

            direction_conflict = (
                strategy_direction
                != pattern.direction
            )

        compatible = bool(
            category_match
            or direction_match
        )

        conflict = bool(
            direction_conflict
        )

        reason_parts: list[str] = []

        if category_match:
            reason_parts.append(
                "shared context "
                + ", ".join(
                    shared_categories
                )
            )

        if direction_match:
            reason_parts.append(
                (
                    f"{pattern.direction.lower()} "
                    "direction aligns"
                )
            )

        if direction_conflict:
            reason_parts.append(
                (
                    f"{pattern.direction.lower()} "
                    "pattern conflicts with "
                    f"{strategy_direction.lower()} "
                    "strategy direction"
                )
            )

        if not reason_parts:
            reason_parts.append(
                "no explicit strategy-pattern compatibility identified"
            )

        return {
            "source": "pattern",
            "pattern": pattern.name,
            "pattern_direction": (
                pattern.direction
            ),
            "pattern_categories": sorted(
                pattern_categories
            ),
            "shared_categories": (
                shared_categories
            ),
            "confidence": (
                pattern.confidence
            ),
            "strength": (
                pattern.strength
            ),
            "confirmed": (
                pattern.confirmed
            ),
            "timeframe": (
                pattern.timeframe
            ),
            "compatible": compatible,
            "conflict": conflict,
            "reason": (
                f"{pattern.name}: "
                + "; ".join(
                    reason_parts
                )
            ),
        }

    def _assess_regime(
        self,
        *,
        profile: Mapping[str, Any],
        regime: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        if not regime:
            return None

        regime_name = str(
            regime.get(
                "regime"
            )
            or regime.get(
                "name"
            )
            or regime.get(
                "market_regime"
            )
            or ""
        ).strip()

        if not regime_name:
            return None

        regime_normalized = (
            self._normalize_text(
                regime_name
            )
        )

        categories = set(
            profile.get(
                "categories"
            )
            or []
        )

        compatible = False
        conflict = False

        reasons: list[str] = []

        regime_direction = (
            self._direction_from_regime(
                regime_normalized
            )
        )

        strategy_direction = (
            profile.get(
                "direction"
            )
        )

        if (
            self.TREND in categories
            or self.MOMENTUM
            in categories
            or self.BREAKOUT
            in categories
        ):
            if self._contains_any(
                regime_normalized,
                self.TREND_REGIME_WORDS,
            ):
                compatible = True
                reasons.append(
                    "directional/trending regime supports trend, momentum or breakout context"
                )

            if self._contains_any(
                regime_normalized,
                self.RANGE_REGIME_WORDS,
            ):
                conflict = True
                reasons.append(
                    "range/choppy regime conflicts with directional trend context"
                )

        if (
            self.MEAN_REVERSION
            in categories
            or self.RANGE
            in categories
        ):
            if self._contains_any(
                regime_normalized,
                self.RANGE_REGIME_WORDS,
            ):
                compatible = True
                reasons.append(
                    "range/sideways regime supports mean-reversion context"
                )

            if self._contains_any(
                regime_normalized,
                self.TREND_REGIME_WORDS,
            ) and regime_direction in {
                self.BULLISH,
                self.BEARISH,
            }:
                conflict = True
                reasons.append(
                    "directional trend can conflict with mean-reversion context"
                )

        if (
            self.VOLATILITY
            in categories
        ):
            if (
                self._contains_any(
                    regime_normalized,
                    self.HIGH_VOLATILITY_REGIME_WORDS,
                )
                or self._contains_any(
                    regime_normalized,
                    self.LOW_VOLATILITY_REGIME_WORDS,
                )
            ):
                compatible = True
                reasons.append(
                    "volatility regime provides relevant volatility context"
                )

        if (
            strategy_direction
            in {
                self.BULLISH,
                self.BEARISH,
            }
            and regime_direction
            in {
                self.BULLISH,
                self.BEARISH,
            }
        ):
            if (
                strategy_direction
                == regime_direction
            ):
                compatible = True
                reasons.append(
                    "strategy direction aligns with regime direction"
                )

            else:
                conflict = True
                reasons.append(
                    "strategy direction conflicts with regime direction"
                )

        if not reasons:
            reasons.append(
                "regime is available but no explicit compatibility rule applies"
            )

        return {
            "source": "regime",
            "regime": regime_name,
            "regime_direction": (
                regime_direction
            ),
            "compatible": compatible,
            "conflict": conflict,
            "reason": "; ".join(
                reasons
            ),
        }

    def _directional_alignment(
        self,
        *,
        strategy_direction: str | None,
        pattern_summary: Mapping[str, Any],
        regime: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        pattern_direction = (
            pattern_summary.get(
                "dominant_direction"
            )
        )

        regime_name = str(
            regime.get(
                "regime"
            )
            or regime.get(
                "name"
            )
            or regime.get(
                "market_regime"
            )
            or ""
        )

        regime_direction = (
            self._direction_from_regime(
                self._normalize_text(
                    regime_name
                )
            )
            if regime_name
            else None
        )

        directions = [
            direction
            for direction in (
                pattern_direction,
                regime_direction,
            )
            if direction
            in {
                self.BULLISH,
                self.BEARISH,
            }
        ]

        if not directions:
            return None

        if (
            pattern_direction
            and regime_direction
            and pattern_direction
            != regime_direction
        ):
            return {
                "source": (
                    "directional_context"
                ),
                "pattern_direction": (
                    pattern_direction
                ),
                "regime_direction": (
                    regime_direction
                ),
                "compatible": False,
                "conflict": True,
                "reason": (
                    "pattern direction and market-regime direction disagree"
                ),
            }

        context_direction = (
            directions[0]
        )

        if strategy_direction in {
            self.BULLISH,
            self.BEARISH,
        }:
            compatible = (
                strategy_direction
                == context_direction
            )

            return {
                "source": (
                    "directional_context"
                ),
                "strategy_direction": (
                    strategy_direction
                ),
                "context_direction": (
                    context_direction
                ),
                "pattern_direction": (
                    pattern_direction
                ),
                "regime_direction": (
                    regime_direction
                ),
                "compatible": compatible,
                "conflict": (
                    not compatible
                ),
                "reason": (
                    "strategy direction aligns with combined pattern/regime context"
                    if compatible
                    else
                    "strategy direction conflicts with combined pattern/regime context"
                ),
            }

        return {
            "source": (
                "directional_context"
            ),
            "context_direction": (
                context_direction
            ),
            "pattern_direction": (
                pattern_direction
            ),
            "regime_direction": (
                regime_direction
            ),
            "compatible": False,
            "conflict": False,
            "reason": (
                "directional context is available; strategy name does not declare a direction"
            ),
        }

    def _compatibility_value(
        self,
        *,
        evidence: Sequence[
            Mapping[str, Any]
        ],
        conflicts: Sequence[
            Mapping[str, Any]
        ],
    ) -> float | None:
        """
        Return a descriptive compatibility ratio based only on identified
        compatibility/conflict assessments.

        No default is emitted when there is no usable evidence.
        """

        positive = 0.0
        negative = 0.0

        for item in evidence:
            if not item.get(
                "compatible"
            ):
                continue

            positive += (
                self._evidence_weight(
                    item
                )
            )

        for item in conflicts:
            if not item.get(
                "conflict"
            ):
                continue

            negative += (
                self._evidence_weight(
                    item
                )
            )

        total = (
            positive
            + negative
        )

        if total <= 0:
            return None

        value = (
            positive
            / total
        )

        if not isfinite(
            value
        ):
            return None

        return round(
            max(
                0.0,
                min(
                    1.0,
                    value,
                ),
            ),
            6,
        )

    def _evidence_weight(
        self,
        item: Mapping[str, Any],
    ) -> float:
        """
        Weight evidence only when the originating detector supplied a real
        confidence/strength value.

        If neither exists, one unit represents one observed compatibility
        relation. This is a count, not fabricated detector confidence.
        """

        confidence = (
            self._normalized_score(
                item.get(
                    "confidence"
                )
            )
        )

        strength = (
            self._normalized_score(
                item.get(
                    "strength"
                )
            )
        )

        if (
            confidence is not None
            and strength is not None
        ):
            return (
                confidence
                + strength
            ) / 2.0

        if confidence is not None:
            return confidence

        if strength is not None:
            return strength

        return 1.0

    def _patterns(
        self,
        patterns: Any,
    ) -> list[PatternEvidence]:
        if patterns is None:
            return []

        if not isinstance(
            patterns,
            Sequence,
        ) or isinstance(
            patterns,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            raise TypeError(
                "patterns must be a list of pattern objects"
            )

        output: list[
            PatternEvidence
        ] = []

        for item in patterns:
            if not isinstance(
                item,
                Mapping,
            ):
                continue

            pattern = self._pattern(
                item
            )

            if pattern is not None:
                output.append(
                    pattern
                )

        return output

    def _pattern(
        self,
        item: Mapping[str, Any],
    ) -> PatternEvidence | None:
        name = self._first_text(
            item,
            (
                "pattern",
                "name",
                "pattern_name",
                "type",
            ),
        )

        raw_direction = (
            self._first_text(
                item,
                (
                    "direction",
                    "bias",
                    "signal",
                    "side",
                ),
            )
        )

        direction = (
            self._normalize_direction(
                raw_direction
            )
        )

        if direction is None and name:
            direction = (
                self._direction_from_pattern_name(
                    name
                )
            )

        category = self._first_text(
            item,
            (
                "category",
                "pattern_category",
                "family",
                "kind",
            ),
        )

        confidence = (
            self._first_score(
                item,
                (
                    "confidence",
                    "probability",
                    "quality",
                ),
            )
        )

        strength = (
            self._first_score(
                item,
                (
                    "strength",
                    "score",
                ),
            )
        )

        timeframe = self._first_text(
            item,
            (
                "timeframe",
                "interval",
            ),
        )

        confirmed = (
            self._first_bool(
                item,
                (
                    "confirmed",
                    "is_confirmed",
                    "validated",
                ),
            )
        )

        if not name:
            if (
                direction is None
                and category is None
            ):
                return None

            name = (
                category
                or direction
                or "Pattern"
            )

        return PatternEvidence(
            name=name,
            direction=direction,
            category=category,
            confidence=confidence,
            strength=strength,
            timeframe=timeframe,
            confirmed=confirmed,
        )

    def _pattern_categories(
        self,
        pattern: PatternEvidence,
    ) -> list[str]:
        categories: list[str] = []

        explicit = self._normalize_category(
            pattern.category
        )

        if explicit is not None:
            categories.append(
                explicit
            )

        name = self._normalize_text(
            pattern.name
        )

        if self._contains_any(
            name,
            self.REVERSAL_PATTERN_WORDS,
        ):
            self._append_unique(
                categories,
                self.REVERSAL,
            )

        if self._contains_any(
            name,
            self.CONTINUATION_PATTERN_WORDS,
        ):
            self._append_unique(
                categories,
                self.TREND,
            )

        if self._contains_any(
            name,
            self.BREAKOUT_PATTERN_WORDS,
        ):
            self._append_unique(
                categories,
                self.BREAKOUT,
            )

        if self._contains_any(
            name,
            self.TREND_PATTERN_WORDS,
        ):
            self._append_unique(
                categories,
                self.TREND,
            )

        if self._contains_any(
            name,
            self.RANGE_PATTERN_WORDS,
        ):
            self._append_unique(
                categories,
                self.RANGE,
            )

        if self._contains_any(
            name,
            self.VOLATILITY_PATTERN_WORDS,
        ):
            self._append_unique(
                categories,
                self.VOLATILITY,
            )

        if self._contains_any(
            name,
            self.CANDLESTICK_WORDS,
        ):
            self._append_unique(
                categories,
                self.CANDLESTICK,
            )

        if (
            self.CANDLESTICK
            not in categories
            and name
        ):
            self._append_unique(
                categories,
                self.STRUCTURAL,
            )

        return categories

    def _directional_pattern_summary(
        self,
        patterns: Sequence[
            PatternEvidence
        ],
    ) -> dict[str, Any]:
        bullish = 0.0
        bearish = 0.0
        neutral = 0.0

        bullish_count = 0
        bearish_count = 0
        neutral_count = 0

        for pattern in patterns:
            weight = (
                self._pattern_weight(
                    pattern
                )
            )

            if (
                pattern.direction
                == self.BULLISH
            ):
                bullish += weight
                bullish_count += 1

            elif (
                pattern.direction
                == self.BEARISH
            ):
                bearish += weight
                bearish_count += 1

            elif (
                pattern.direction
                == self.NEUTRAL
            ):
                neutral += weight
                neutral_count += 1

        dominant: str | None = None

        if (
            bullish > bearish
            and bullish > 0
        ):
            dominant = self.BULLISH

        elif (
            bearish > bullish
            and bearish > 0
        ):
            dominant = self.BEARISH

        elif (
            bullish == bearish
            and bullish > 0
        ):
            dominant = self.NEUTRAL

        elif (
            neutral > 0
        ):
            dominant = self.NEUTRAL

        return {
            "dominant_direction": (
                dominant
            ),
            "bullish_count": (
                bullish_count
            ),
            "bearish_count": (
                bearish_count
            ),
            "neutral_count": (
                neutral_count
            ),
            "bullish_weight": round(
                bullish,
                6,
            ),
            "bearish_weight": round(
                bearish,
                6,
            ),
            "neutral_weight": round(
                neutral,
                6,
            ),
        }

    def _pattern_weight(
        self,
        pattern: PatternEvidence,
    ) -> float:
        if (
            pattern.confidence
            is not None
            and pattern.strength
            is not None
        ):
            return (
                pattern.confidence
                + pattern.strength
            ) / 2.0

        if pattern.confidence is not None:
            return pattern.confidence

        if pattern.strength is not None:
            return pattern.strength

        return 1.0

    def _regime(
        self,
        regime: Any,
    ) -> dict[str, Any]:
        if regime is None:
            return {}

        if isinstance(
            regime,
            Mapping,
        ):
            return dict(
                regime
            )

        if isinstance(
            regime,
            str,
        ):
            clean = regime.strip()

            return (
                {
                    "regime": clean
                }
                if clean
                else {}
            )

        raise TypeError(
            "regime must be a mapping, string, or None"
        )

    def _direction_from_pattern_name(
        self,
        name: str,
    ) -> str | None:
        normalized = self._normalize_text(
            name
        )

        bullish = self._contains_any(
            normalized,
            self.BULLISH_PATTERN_NAMES,
        )

        bearish = self._contains_any(
            normalized,
            self.BEARISH_PATTERN_NAMES,
        )

        if bullish and not bearish:
            return self.BULLISH

        if bearish and not bullish:
            return self.BEARISH

        if (
            "bullish" in normalized
            and "bearish"
            not in normalized
        ):
            return self.BULLISH

        if (
            "bearish" in normalized
            and "bullish"
            not in normalized
        ):
            return self.BEARISH

        return None

    def _direction_from_text(
        self,
        text: str,
    ) -> str | None:
        normalized = self._normalize_text(
            text
        )

        bullish_tokens = (
            "long only",
            "long_only",
            "bullish",
            "bull ",
            "buy only",
            "buy_only",
        )

        bearish_tokens = (
            "short only",
            "short_only",
            "bearish",
            "bear ",
            "sell only",
            "sell_only",
        )

        bullish = self._contains_any(
            normalized,
            bullish_tokens,
        )

        bearish = self._contains_any(
            normalized,
            bearish_tokens,
        )

        if bullish and not bearish:
            return self.BULLISH

        if bearish and not bullish:
            return self.BEARISH

        return None

    def _direction_from_regime(
        self,
        regime: str,
    ) -> str | None:
        normalized = self._normalize_text(
            regime
        )

        if self._contains_any(
            normalized,
            self.BULLISH_REGIME_WORDS,
        ):
            return self.BULLISH

        if self._contains_any(
            normalized,
            self.BEARISH_REGIME_WORDS,
        ):
            return self.BEARISH

        if self._contains_any(
            normalized,
            self.RANGE_REGIME_WORDS,
        ):
            return self.NEUTRAL

        return None

    def _normalize_direction(
        self,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = (
            str(value)
            .strip()
            .upper()
        )

        aliases = {
            "BUY": self.BULLISH,
            "LONG": self.BULLISH,
            "UP": self.BULLISH,
            "UPWARD": self.BULLISH,
            "BULL": self.BULLISH,
            "BULLISH": self.BULLISH,
            "SELL": self.BEARISH,
            "SHORT": self.BEARISH,
            "DOWN": self.BEARISH,
            "DOWNWARD": self.BEARISH,
            "BEAR": self.BEARISH,
            "BEARISH": self.BEARISH,
            "NEUTRAL": self.NEUTRAL,
            "SIDEWAYS": self.NEUTRAL,
            "RANGE": self.NEUTRAL,
            "RANGING": self.NEUTRAL,
            "NONE": self.NEUTRAL,
        }

        return aliases.get(
            normalized
        )

    def _normalize_category(
        self,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = (
            str(value)
            .strip()
            .upper()
            .replace("-", "_")
            .replace(" ", "_")
        )

        aliases = {
            "TREND": self.TREND,
            "TRENDING": self.TREND,
            "CONTINUATION": self.TREND,
            "REVERSAL": self.REVERSAL,
            "BREAKOUT": self.BREAKOUT,
            "MOMENTUM": self.MOMENTUM,
            "MEAN_REVERSION": (
                self.MEAN_REVERSION
            ),
            "MEANREVERSION": (
                self.MEAN_REVERSION
            ),
            "VOLATILITY": (
                self.VOLATILITY
            ),
            "RANGE": self.RANGE,
            "RANGING": self.RANGE,
            "VOLUME": self.VOLUME,
            "SUPPORT_RESISTANCE": (
                self.SUPPORT_RESISTANCE
            ),
            "SUPPORT_AND_RESISTANCE": (
                self.SUPPORT_RESISTANCE
            ),
            "CANDLESTICK": (
                self.CANDLESTICK
            ),
            "CANDLE": self.CANDLESTICK,
            "STRUCTURAL": self.STRUCTURAL,
            "CHART": self.STRUCTURAL,
            "CHART_PATTERN": (
                self.STRUCTURAL
            ),
        }

        return aliases.get(
            normalized,
            normalized
            if normalized
            else None,
        )

    @classmethod
    def _first_score(
        cls,
        item: Mapping[str, Any],
        keys: Sequence[str],
    ) -> float | None:
        for key in keys:
            if key not in item:
                continue

            score = cls._normalized_score(
                item.get(
                    key
                )
            )

            if score is not None:
                return score

        return None

    @staticmethod
    def _normalized_score(
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

        if (
            number > 1.0
            and number <= 100.0
        ):
            number /= 100.0

        if not (
            0.0
            <= number
            <= 1.0
        ):
            return None

        return number

    @staticmethod
    def _first_text(
        item: Mapping[str, Any],
        keys: Sequence[str],
    ) -> str | None:
        for key in keys:
            value = item.get(
                key
            )

            if value is None:
                continue

            text = str(
                value
            ).strip()

            if text:
                return text

        return None

    @staticmethod
    def _first_bool(
        item: Mapping[str, Any],
        keys: Sequence[str],
    ) -> bool | None:
        for key in keys:
            value = item.get(
                key
            )

            if isinstance(
                value,
                bool,
            ):
                return value

            if isinstance(
                value,
                int,
            ) and value in {
                0,
                1,
            }:
                return bool(
                    value
                )

            if isinstance(
                value,
                str,
            ):
                normalized = (
                    value
                    .strip()
                    .lower()
                )

                if normalized in {
                    "true",
                    "yes",
                    "1",
                    "confirmed",
                }:
                    return True

                if normalized in {
                    "false",
                    "no",
                    "0",
                    "unconfirmed",
                }:
                    return False

        return None

    @staticmethod
    def _strategy_name(
        value: Any,
    ) -> str:
        if value is None:
            raise ValueError(
                "strategy_name is required"
            )

        name = str(
            value
        ).strip()

        if not name:
            raise ValueError(
                "strategy_name is required"
            )

        if len(name) > 256:
            raise ValueError(
                "strategy_name is invalid"
            )

        return name

    @staticmethod
    def _normalize_text(
        value: Any,
    ) -> str:
        if value is None:
            return ""

        text = (
            str(value)
            .strip()
            .lower()
        )

        return " ".join(
            text.split()
        )

    @classmethod
    def _contains_any(
        cls,
        text: str,
        words: Sequence[str],
    ) -> bool:
        normalized = cls._normalize_text(
            text
        )

        return any(
            cls._normalize_text(
                word
            )
            in normalized
            for word in words
            if cls._normalize_text(
                word
            )
        )

    @staticmethod
    def _append_unique(
        values: list[str],
        value: str,
    ) -> None:
        if value not in values:
            values.append(
                value
            )

    @classmethod
    def _append_category_if_matching(
        cls,
        categories: list[str],
        normalized_name: str,
        words: Sequence[str],
        category: str,
    ) -> None:
        if cls._contains_any(
            normalized_name,
            words,
        ):
            cls._append_unique(
                categories,
                category,
            )

    @staticmethod
    def _dedupe(
        values: Sequence[str],
    ) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()

        for value in values:
            clean = str(
                value
            ).strip()

            if not clean:
                continue

            key = clean.casefold()

            if key in seen:
                continue

            seen.add(
                key
            )

            output.append(
                clean
            )

        return output


strategy_pattern_mapper = StrategyPatternMapper()


__all__ = [
    "PatternEvidence",
    "StrategyPatternMapper",
    "strategy_pattern_mapper",
]