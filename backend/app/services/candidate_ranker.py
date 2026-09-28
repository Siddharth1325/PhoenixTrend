from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence


# =============================================================================
# RESULT MODEL
# =============================================================================


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    """
    Ranked representation of one scanner candidate.

    Ranking is descriptive only.

    CandidateRanker does NOT:

        - create market data
        - invent missing metrics
        - convert HOLD into BUY/SELL
        - declare data safe
        - approve automatic execution
        - size an order
        - perform risk approval
        - submit an order

    automatic_execution_safe is preserved from the upstream candidate only.
    It is never inferred by this service.
    """

    symbol: str
    score: float
    rank: int
    action: str
    confidence: float | None
    automatic_execution_safe: bool
    reasons: tuple[str, ...]
    available_metrics: tuple[str, ...]
    missing_metrics: tuple[str, ...]
    payload: dict[str, Any]

    def dump(self) -> dict[str, Any]:
        return {
            **self.payload,
            "symbol": self.symbol,
            "rank": self.rank,
            "rank_score": self.score,
            "action": self.action,
            "confidence": self.confidence,
            "automatic_execution_safe": self.automatic_execution_safe,
            "ranking_reasons": list(self.reasons),
            "ranking_available_metrics": list(self.available_metrics),
            "ranking_missing_metrics": list(self.missing_metrics),
        }


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    """
    Normalized real metrics available on one scanner candidate.

    None always means unavailable.

    Missing values are intentionally NOT replaced with neutral or average
    values because doing so would fabricate evidence for the ranking.
    """

    confidence: float | None = None

    price: float | None = None

    change_percent: float | None = None
    momentum_percent: float | None = None

    volume: float | None = None
    average_volume: float | None = None
    volume_ratio: float | None = None
    dollar_volume: float | None = None

    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    spread_percent: float | None = None

    volatility: float | None = None
    atr: float | None = None
    atr_percent: float | None = None

    pattern_confidence: float | None = None
    strategy_confidence: float | None = None

    liquidity_score: float | None = None
    momentum_score: float | None = None
    volatility_score: float | None = None

    def available(self) -> tuple[str, ...]:
        output: list[str] = []

        for field_name in self.__dataclass_fields__:
            if getattr(self, field_name) is not None:
                output.append(field_name)

        return tuple(output)


# =============================================================================
# RANKER
# =============================================================================


class CandidateRanker:
    """
    PhoenixTrend scanner candidate ranker.

    Purpose
    -------
    Rank already-discovered candidates using only metrics actually returned
    by upstream scanners/providers.

    Expected broad scanner flow:

        tradable universe
            -> scanner
            -> candidate metrics
            -> CandidateRanker
            -> deeper PhoenixTrend analysis
            -> patterns / indicators / regime
            -> strategy evaluations
            -> DecisionEngine
            -> BUY / SELL / HOLD
            -> Market Safety
            -> Risk
            -> Execution

    This service can also rank candidates that have already received deeper
    analysis, but it does not manufacture analysis when those fields are absent.

    Safety
    ------
    A high ranking score is NEVER execution approval.

    automatic_execution_safe remains an upstream fact and receives no ranking
    bonus. A candidate must still pass the authoritative live-market,
    MarketSafety, RiskEngine, broker-capability and execution checks.
    """

    DEFAULT_LIMIT = 50
    MAX_LIMIT = 1000

    ACTION_BUY = "BUY"
    ACTION_SELL = "SELL"
    ACTION_HOLD = "HOLD"

    ACTIONS = frozenset(
        {
            ACTION_BUY,
            ACTION_SELL,
            ACTION_HOLD,
        }
    )

    # Ranking weights intentionally total approximately 100 when all broad
    # scanner metrics are present. Deep-analysis evidence can provide a modest
    # additional differentiation without becoming execution authority.
    WEIGHT_CONFIDENCE = 24.0
    WEIGHT_RELATIVE_VOLUME = 16.0
    WEIGHT_DOLLAR_VOLUME = 12.0
    WEIGHT_SPREAD = 12.0
    WEIGHT_MOMENTUM = 12.0
    WEIGHT_VOLATILITY = 8.0
    WEIGHT_LIQUIDITY_SCORE = 8.0
    WEIGHT_MOMENTUM_SCORE = 4.0
    WEIGHT_VOLATILITY_SCORE = 4.0

    DEEP_PATTERN_WEIGHT = 4.0
    DEEP_STRATEGY_WEIGHT = 4.0
    ACTIONABLE_WEIGHT = 2.0

    # Used only for bounded normalization of values that are genuinely
    # available. They are not substituted for missing metrics.
    RELATIVE_VOLUME_FULL_SCORE = 3.0
    MOMENTUM_FULL_SCORE_PERCENT = 5.0
    ATR_PERCENT_FULL_SCORE = 5.0
    VOLATILITY_FULL_SCORE = 0.05

    # A tighter spread receives more points.
    SPREAD_EXCELLENT_PERCENT = 0.05
    SPREAD_POOR_PERCENT = 1.00

    # Dollar-volume normalization is deliberately logarithmic because real
    # market liquidity spans several orders of magnitude.
    DOLLAR_VOLUME_REFERENCE = 1_000_000.0
    DOLLAR_VOLUME_FULL_SCORE = 100_000_000.0

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def score(
        self,
        item: Mapping[str, Any],
    ) -> tuple[float, list[str]]:
        """
        Compatibility scoring API.

        Returns:

            (score, reasons)

        No missing metric receives a default contribution.
        """

        normalized = self._normalize_candidate(item)

        if normalized is None:
            return 0.0, []

        metrics = self._metrics(normalized)

        score, reasons, _available, _missing = self._score_metrics(
            normalized,
            metrics,
        )

        return score, reasons

    def rank(
        self,
        candidates: Iterable[dict[str, Any]],
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Rank scanner candidates deterministically.

        Duplicate symbols are consolidated rather than appearing repeatedly.
        The most informative candidate for each symbol is retained.

        Ties are resolved deterministically by symbol.
        """

        safe_limit = self._limit(limit)

        if safe_limit == 0:
            return []

        deduplicated: dict[
            str,
            tuple[
                float,
                dict[str, Any],
                CandidateMetrics,
                list[str],
                tuple[str, ...],
                tuple[str, ...],
            ],
        ] = {}

        for raw in candidates:
            if not isinstance(raw, dict):
                continue

            normalized = self._normalize_candidate(raw)

            if normalized is None:
                continue

            symbol = normalized["symbol"]

            metrics = self._metrics(normalized)

            (
                score,
                reasons,
                available,
                missing,
            ) = self._score_metrics(
                normalized,
                metrics,
            )

            current = deduplicated.get(symbol)

            candidate_record = (
                score,
                normalized,
                metrics,
                reasons,
                available,
                missing,
            )

            if current is None:
                deduplicated[symbol] = candidate_record
                continue

            if self._prefer_candidate(
                candidate_record,
                current,
            ):
                deduplicated[symbol] = candidate_record

        prepared = list(
            deduplicated.values()
        )

        prepared.sort(
            key=lambda row: (
                -row[0],
                row[1]["symbol"],
            )
        )

        if safe_limit is not None:
            prepared = prepared[:safe_limit]

        output: list[dict[str, Any]] = []

        for index, (
            score,
            payload,
            metrics,
            reasons,
            available,
            missing,
        ) in enumerate(
            prepared,
            start=1,
        ):
            output.append(
                RankedCandidate(
                    symbol=payload["symbol"],
                    score=score,
                    rank=index,
                    action=self._action(payload),
                    confidence=metrics.confidence,
                    automatic_execution_safe=(
                        payload.get(
                            "automatic_execution_safe"
                        )
                        is True
                    ),
                    reasons=tuple(reasons),
                    available_metrics=available,
                    missing_metrics=missing,
                    payload=dict(payload),
                ).dump()
            )

        return output

    def rank_models(
        self,
        candidates: Iterable[dict[str, Any]],
        *,
        limit: int | None = None,
    ) -> list[RankedCandidate]:
        """
        Typed equivalent of rank().
        """

        ranked = self.rank(
            candidates,
            limit=limit,
        )

        output: list[RankedCandidate] = []

        for item in ranked:
            output.append(
                RankedCandidate(
                    symbol=str(
                        item["symbol"]
                    ),
                    score=float(
                        item["rank_score"]
                    ),
                    rank=int(
                        item["rank"]
                    ),
                    action=str(
                        item["action"]
                    ),
                    confidence=self._optional_unit(
                        item.get(
                            "confidence"
                        )
                    ),
                    automatic_execution_safe=(
                        item.get(
                            "automatic_execution_safe"
                        )
                        is True
                    ),
                    reasons=tuple(
                        str(value)
                        for value in item.get(
                            "ranking_reasons",
                            [],
                        )
                    ),
                    available_metrics=tuple(
                        str(value)
                        for value in item.get(
                            "ranking_available_metrics",
                            [],
                        )
                    ),
                    missing_metrics=tuple(
                        str(value)
                        for value in item.get(
                            "ranking_missing_metrics",
                            [],
                        )
                    ),
                    payload={
                        key: value
                        for key, value in item.items()
                        if key
                        not in {
                            "rank",
                            "rank_score",
                            "ranking_reasons",
                            "ranking_available_metrics",
                            "ranking_missing_metrics",
                        }
                    },
                )
            )

        return output

    # =========================================================================
    # CANDIDATE NORMALIZATION
    # =========================================================================

    def _normalize_candidate(
        self,
        raw: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        symbol = self._symbol(
            raw.get("symbol")
        )

        if symbol is None:
            return None

        output = dict(raw)
        output["symbol"] = symbol

        # Normalize action only when one was actually supplied.
        action_value = (
            raw.get("action")
            if raw.get("action") is not None
            else raw.get("decision")
        )

        if action_value is not None:
            output["action"] = self._normalize_action(
                action_value
            )

        return output

    @staticmethod
    def _symbol(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        symbol = str(value).strip().upper()

        return symbol or None

    # =========================================================================
    # METRIC EXTRACTION
    # =========================================================================

    def _metrics(
        self,
        item: Mapping[str, Any],
    ) -> CandidateMetrics:
        price = self._positive(
            self._first(
                item,
                "price",
                "last_price",
                "current_price",
                "close",
            )
        )

        volume = self._nonnegative(
            self._first(
                item,
                "volume",
                "current_volume",
            )
        )

        average_volume = self._positive(
            self._first(
                item,
                "average_volume",
                "avg_volume",
            )
        )

        explicit_volume_ratio = self._nonnegative(
            self._first(
                item,
                "volume_ratio",
                "relative_volume",
                "relative_volume_ratio",
                "rvol",
            )
        )

        volume_ratio = explicit_volume_ratio

        if (
            volume_ratio is None
            and volume is not None
            and average_volume is not None
            and average_volume > 0
        ):
            volume_ratio = (
                volume
                / average_volume
            )

        explicit_dollar_volume = self._nonnegative(
            self._first(
                item,
                "dollar_volume",
                "notional_volume",
            )
        )

        dollar_volume = explicit_dollar_volume

        if (
            dollar_volume is None
            and price is not None
            and volume is not None
        ):
            dollar_volume = (
                price
                * volume
            )

        bid = self._positive(
            self._first(
                item,
                "bid",
                "bid_price",
            )
        )

        ask = self._positive(
            self._first(
                item,
                "ask",
                "ask_price",
            )
        )

        explicit_spread = self._nonnegative(
            self._first(
                item,
                "spread",
                "bid_ask_spread",
            )
        )

        spread = explicit_spread

        if (
            spread is None
            and bid is not None
            and ask is not None
            and ask >= bid
        ):
            spread = ask - bid

        explicit_spread_percent = self._nonnegative(
            self._first(
                item,
                "spread_percent",
                "spread_pct",
                "bid_ask_spread_percent",
            )
        )

        spread_percent = explicit_spread_percent

        if (
            spread_percent is None
            and spread is not None
        ):
            midpoint: float | None = None

            if (
                bid is not None
                and ask is not None
                and ask >= bid
            ):
                midpoint = (
                    bid + ask
                ) / 2.0

            elif price is not None:
                midpoint = price

            if (
                midpoint is not None
                and midpoint > 0
            ):
                spread_percent = (
                    spread
                    / midpoint
                    * 100.0
                )

        change_percent = self._number(
            self._first(
                item,
                "change_percent",
                "change_pct",
                "percent_change",
            )
        )

        momentum_percent = self._number(
            self._first(
                item,
                "momentum_percent",
                "momentum_pct",
            )
        )

        if momentum_percent is None:
            momentum_percent = change_percent

        atr = self._nonnegative(
            self._first(
                item,
                "atr",
                "average_true_range",
            )
        )

        explicit_atr_percent = self._nonnegative(
            self._first(
                item,
                "atr_percent",
                "atr_pct",
            )
        )

        atr_percent = explicit_atr_percent

        if (
            atr_percent is None
            and atr is not None
            and price is not None
            and price > 0
        ):
            atr_percent = (
                atr
                / price
                * 100.0
            )

        return CandidateMetrics(
            confidence=self._optional_unit(
                self._first(
                    item,
                    "confidence",
                    "decision_confidence",
                )
            ),
            price=price,
            change_percent=change_percent,
            momentum_percent=momentum_percent,
            volume=volume,
            average_volume=average_volume,
            volume_ratio=volume_ratio,
            dollar_volume=dollar_volume,
            bid=bid,
            ask=ask,
            spread=spread,
            spread_percent=spread_percent,
            volatility=self._nonnegative(
                self._first(
                    item,
                    "volatility",
                    "realized_volatility",
                )
            ),
            atr=atr,
            atr_percent=atr_percent,
            pattern_confidence=self._optional_unit(
                self._first(
                    item,
                    "pattern_confidence",
                    "chart_pattern_confidence",
                )
            ),
            strategy_confidence=self._optional_unit(
                self._first(
                    item,
                    "strategy_confidence",
                    "selected_strategy_confidence",
                )
            ),
            liquidity_score=self._optional_unit(
                self._first(
                    item,
                    "liquidity_score",
                )
            ),
            momentum_score=self._optional_unit(
                self._first(
                    item,
                    "momentum_score",
                )
            ),
            volatility_score=self._optional_unit(
                self._first(
                    item,
                    "volatility_score",
                )
            ),
        )

    # =========================================================================
    # SCORING
    # =========================================================================

    def _score_metrics(
        self,
        item: Mapping[str, Any],
        metrics: CandidateMetrics,
    ) -> tuple[
        float,
        list[str],
        tuple[str, ...],
        tuple[str, ...],
    ]:
        score = 0.0
        reasons: list[str] = []

        available = set(
            metrics.available()
        )

        expected = {
            "confidence",
            "volume_ratio",
            "dollar_volume",
            "spread_percent",
            "momentum_percent",
            "volatility",
            "atr_percent",
            "liquidity_score",
            "momentum_score",
            "volatility_score",
        }

        # ---------------------------------------------------------------------
        # CONFIDENCE
        # ---------------------------------------------------------------------

        if metrics.confidence is not None:
            contribution = (
                metrics.confidence
                * self.WEIGHT_CONFIDENCE
            )

            score += contribution

            reasons.append(
                f"decision confidence {metrics.confidence:.2f}"
            )

        # ---------------------------------------------------------------------
        # RELATIVE VOLUME
        # ---------------------------------------------------------------------

        if metrics.volume_ratio is not None:
            normalized = self._clamp01(
                metrics.volume_ratio
                / self.RELATIVE_VOLUME_FULL_SCORE
            )

            contribution = (
                normalized
                * self.WEIGHT_RELATIVE_VOLUME
            )

            score += contribution

            reasons.append(
                f"relative volume {metrics.volume_ratio:.2f}x"
            )

        # ---------------------------------------------------------------------
        # DOLLAR VOLUME
        # ---------------------------------------------------------------------

        if metrics.dollar_volume is not None:
            normalized = self._log_scale(
                metrics.dollar_volume,
                low=self.DOLLAR_VOLUME_REFERENCE,
                high=self.DOLLAR_VOLUME_FULL_SCORE,
            )

            contribution = (
                normalized
                * self.WEIGHT_DOLLAR_VOLUME
            )

            score += contribution

            reasons.append(
                f"dollar volume {metrics.dollar_volume:.2f}"
            )

        # ---------------------------------------------------------------------
        # SPREAD
        # ---------------------------------------------------------------------

        if metrics.spread_percent is not None:
            normalized = self._inverse_range(
                metrics.spread_percent,
                best=self.SPREAD_EXCELLENT_PERCENT,
                worst=self.SPREAD_POOR_PERCENT,
            )

            contribution = (
                normalized
                * self.WEIGHT_SPREAD
            )

            score += contribution

            reasons.append(
                f"spread {metrics.spread_percent:.4f}%"
            )

        # ---------------------------------------------------------------------
        # MOMENTUM
        # ---------------------------------------------------------------------

        if metrics.momentum_percent is not None:
            absolute_momentum = abs(
                metrics.momentum_percent
            )

            normalized = self._clamp01(
                absolute_momentum
                / self.MOMENTUM_FULL_SCORE_PERCENT
            )

            contribution = (
                normalized
                * self.WEIGHT_MOMENTUM
            )

            score += contribution

            reasons.append(
                f"absolute move {absolute_momentum:.2f}%"
            )

        # ---------------------------------------------------------------------
        # VOLATILITY
        # ---------------------------------------------------------------------

        volatility_normalized: float | None = None

        if metrics.atr_percent is not None:
            volatility_normalized = self._clamp01(
                metrics.atr_percent
                / self.ATR_PERCENT_FULL_SCORE
            )

            reasons.append(
                f"ATR {metrics.atr_percent:.2f}% of price"
            )

        elif metrics.volatility is not None:
            volatility_normalized = self._clamp01(
                metrics.volatility
                / self.VOLATILITY_FULL_SCORE
            )

            reasons.append(
                f"volatility {metrics.volatility:.6f}"
            )

        if volatility_normalized is not None:
            score += (
                volatility_normalized
                * self.WEIGHT_VOLATILITY
            )

        # ---------------------------------------------------------------------
        # PRECOMPUTED REAL SCANNER SCORES
        # ---------------------------------------------------------------------

        if metrics.liquidity_score is not None:
            score += (
                metrics.liquidity_score
                * self.WEIGHT_LIQUIDITY_SCORE
            )

            reasons.append(
                f"liquidity score {metrics.liquidity_score:.2f}"
            )

        if metrics.momentum_score is not None:
            score += (
                metrics.momentum_score
                * self.WEIGHT_MOMENTUM_SCORE
            )

            reasons.append(
                f"momentum score {metrics.momentum_score:.2f}"
            )

        if metrics.volatility_score is not None:
            score += (
                metrics.volatility_score
                * self.WEIGHT_VOLATILITY_SCORE
            )

            reasons.append(
                f"volatility score {metrics.volatility_score:.2f}"
            )

        # ---------------------------------------------------------------------
        # DEEP ANALYSIS EVIDENCE
        # ---------------------------------------------------------------------

        pattern = self._text(
            self._first(
                item,
                "pattern",
                "pattern_name",
                "selected_pattern",
            )
        )

        if pattern:
            if metrics.pattern_confidence is not None:
                score += (
                    metrics.pattern_confidence
                    * self.DEEP_PATTERN_WEIGHT
                )

                reasons.append(
                    (
                        f"pattern {pattern} "
                        f"({metrics.pattern_confidence:.2f})"
                    )
                )
            else:
                # Presence is recorded but receives no fabricated confidence.
                reasons.append(
                    f"pattern {pattern}"
                )

        strategy = self._text(
            self._first(
                item,
                "strategy",
                "selected_strategy",
            )
        )

        if strategy:
            if metrics.strategy_confidence is not None:
                score += (
                    metrics.strategy_confidence
                    * self.DEEP_STRATEGY_WEIGHT
                )

                reasons.append(
                    (
                        f"strategy {strategy} "
                        f"({metrics.strategy_confidence:.2f})"
                    )
                )
            else:
                reasons.append(
                    f"strategy {strategy}"
                )

        # ---------------------------------------------------------------------
        # ACTION
        # ---------------------------------------------------------------------

        action = self._action(
            item
        )

        if action in {
            self.ACTION_BUY,
            self.ACTION_SELL,
        }:
            score += self.ACTIONABLE_WEIGHT

            reasons.append(
                f"actionable {action} analysis"
            )

        elif action == self.ACTION_HOLD:
            reasons.append(
                "current decision HOLD"
            )

        # ---------------------------------------------------------------------
        # EXECUTION SAFETY
        # ---------------------------------------------------------------------

        if (
            item.get(
                "automatic_execution_safe"
            )
            is True
        ):
            # Intentionally no score contribution.
            #
            # Market safety is a gate, not an attractiveness metric.
            reasons.append(
                "upstream market snapshot marked automatic-execution safe"
            )

        # ---------------------------------------------------------------------
        # DATA COMPLETENESS
        # ---------------------------------------------------------------------

        missing = tuple(
            sorted(
                expected
                - available
            )
        )

        available_tuple = tuple(
            sorted(
                available
            )
        )

        if missing:
            reasons.append(
                (
                    "ranking omitted unavailable metrics: "
                    + ", ".join(
                        missing
                    )
                )
            )

        return (
            round(
                max(
                    0.0,
                    score,
                ),
                6,
            ),
            reasons,
            available_tuple,
            missing,
        )

    # =========================================================================
    # DUPLICATE RESOLUTION
    # =========================================================================

    @staticmethod
    def _prefer_candidate(
        candidate: tuple[
            float,
            dict[str, Any],
            CandidateMetrics,
            list[str],
            tuple[str, ...],
            tuple[str, ...],
        ],
        current: tuple[
            float,
            dict[str, Any],
            CandidateMetrics,
            list[str],
            tuple[str, ...],
            tuple[str, ...],
        ],
    ) -> bool:
        candidate_score = candidate[0]
        current_score = current[0]

        if candidate_score != current_score:
            return candidate_score > current_score

        candidate_available = len(
            candidate[4]
        )

        current_available = len(
            current[4]
        )

        if candidate_available != current_available:
            return (
                candidate_available
                > current_available
            )

        candidate_safe = (
            candidate[1].get(
                "automatic_execution_safe"
            )
            is True
        )

        current_safe = (
            current[1].get(
                "automatic_execution_safe"
            )
            is True
        )

        # Safety is used only as deterministic duplicate preference when two
        # records have the same ranking score and completeness. It still does
        # not increase the rank score or authorize execution.
        if candidate_safe != current_safe:
            return candidate_safe

        return False

    # =========================================================================
    # ACTION NORMALIZATION
    # =========================================================================

    def _action(
        self,
        item: Mapping[str, Any],
    ) -> str:
        raw = (
            item.get("action")
            if item.get("action") is not None
            else item.get("decision")
        )

        return self._normalize_action(
            raw
        )

    def _normalize_action(
        self,
        value: Any,
    ) -> str:
        if value is None:
            return self.ACTION_HOLD

        action = str(
            getattr(
                value,
                "value",
                value,
            )
        ).strip().upper()

        aliases = {
            "LONG": self.ACTION_BUY,
            "SHORT": self.ACTION_SELL,
            "NO_TRADE": self.ACTION_HOLD,
            "NO TRADE": self.ACTION_HOLD,
            "NONE": self.ACTION_HOLD,
            "WAIT": self.ACTION_HOLD,
            "NEUTRAL": self.ACTION_HOLD,
        }

        action = aliases.get(
            action,
            action,
        )

        if action not in self.ACTIONS:
            return self.ACTION_HOLD

        return action

    # =========================================================================
    # LIMIT
    # =========================================================================

    def _limit(
        self,
        limit: int | None,
    ) -> int | None:
        if limit is None:
            return None

        try:
            safe_limit = int(
                limit
            )
        except (
            TypeError,
            ValueError,
        ):
            raise ValueError(
                "limit must be an integer"
            )

        if safe_limit < 0:
            raise ValueError(
                "limit cannot be negative"
            )

        return min(
            safe_limit,
            self.MAX_LIMIT,
        )

    # =========================================================================
    # VALUE EXTRACTION
    # =========================================================================

    @staticmethod
    def _first(
        item: Mapping[str, Any],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key not in item:
                continue

            value = item.get(
                key
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _text(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        text = str(
            getattr(
                value,
                "value",
                value,
            )
        ).strip()

        return text or None

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

    @classmethod
    def _positive(
        cls,
        value: Any,
    ) -> float | None:
        number = cls._number(
            value
        )

        if (
            number is None
            or number <= 0
        ):
            return None

        return number

    @classmethod
    def _nonnegative(
        cls,
        value: Any,
    ) -> float | None:
        number = cls._number(
            value
        )

        if (
            number is None
            or number < 0
        ):
            return None

        return number

    @classmethod
    def _optional_unit(
        cls,
        value: Any,
    ) -> float | None:
        number = cls._number(
            value
        )

        if number is None:
            return None

        # Confidence/normalized scanner scores must already be supplied in
        # [0, 1]. Values outside the documented range are treated as invalid
        # rather than silently clamped into believable evidence.
        if (
            number < 0
            or number > 1
        ):
            return None

        return number

    # =========================================================================
    # NORMALIZATION HELPERS
    # =========================================================================

    @staticmethod
    def _clamp01(
        value: float,
    ) -> float:
        return max(
            0.0,
            min(
                1.0,
                value,
            ),
        )

    @classmethod
    def _inverse_range(
        cls,
        value: float,
        *,
        best: float,
        worst: float,
    ) -> float:
        if worst <= best:
            return 0.0

        if value <= best:
            return 1.0

        if value >= worst:
            return 0.0

        return cls._clamp01(
            1.0
            - (
                (value - best)
                / (worst - best)
            )
        )

    @classmethod
    def _log_scale(
        cls,
        value: float,
        *,
        low: float,
        high: float,
    ) -> float:
        """
        Bounded logarithmic normalization without inventing a missing value.
        """

        if (
            value <= 0
            or low <= 0
            or high <= low
        ):
            return 0.0

        if value <= low:
            return 0.0

        if value >= high:
            return 1.0

        # Avoid importing a broader numerical dependency for a small,
        # deterministic ranker.
        from math import log

        numerator = (
            log(value)
            - log(low)
        )

        denominator = (
            log(high)
            - log(low)
        )

        if denominator <= 0:
            return 0.0

        return cls._clamp01(
            numerator
            / denominator
        )


candidate_ranker = CandidateRanker()


__all__ = [
    "RankedCandidate",
    "CandidateMetrics",
    "CandidateRanker",
    "candidate_ranker",
]