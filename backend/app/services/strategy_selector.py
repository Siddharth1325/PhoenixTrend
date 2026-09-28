from __future__ import annotations

from math import isfinite
from typing import Any

from ..config import settings
from ..strategies.registry import StrategyRegistry


class StrategySelector:
    """
    PhoenixTrend strategy ranking and selection service.

    Strategy implementations remain authoritative for their own signals,
    confidence, stops, targets, rationale, and setup rules.

    This selector is responsible only for:

        - validating strategy-evaluation output
        - excluding disabled strategies
        - preserving HOLD evaluations for diagnostics
        - ranking genuine actionable evaluations
        - applying bounded confirmation from verified chart-pattern metadata
        - detecting conflicting pattern evidence
        - returning deterministic selection metadata
        - deciding whether the adaptive-strategy workflow should be considered

    It does NOT:

        - generate BUY/SELL signals
        - convert HOLD into BUY/SELL
        - execute trades
        - perform broker capability checks
        - perform market-safety checks
        - perform account-risk checks
        - fabricate strategy confidence
        - fabricate pattern confidence
        - fabricate stops or targets
        - replace StrategyRegistry
        - replace StrategyManagementService
        - replace DecisionEngine
    """

    PATTERN_CONFIRMATION_MAX = 0.08

    VALID_SIGNALS = frozenset(
        {
            "BUY",
            "SELL",
            "HOLD",
        }
    )

    ACTIONABLE_SIGNALS = frozenset(
        {
            "BUY",
            "SELL",
        }
    )

    def __init__(self) -> None:
        self.registry = StrategyRegistry()

    # ============================================================
    # MANAGEMENT
    # ============================================================

    @staticmethod
    def _management():
        """
        Lazy import avoids an initialization cycle between strategy
        management and strategy selection.
        """

        from .strategy_management import (
            strategy_management_service,
        )

        return strategy_management_service

    # ============================================================
    # ENABLED
    # ============================================================

    def _strategy_is_enabled(
        self,
        strategy_name: str,
    ) -> bool:
        try:
            return bool(
                self._management().enabled_for(
                    strategy_name
                )
            )

        except ValueError:
            return False

    # ============================================================
    # SELECT
    # ============================================================

    def select(
        self,
        evaluations: list[dict[str, Any]],
        patterns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Rank actual strategy evaluations.

        The strategy's own confidence remains authoritative.

        Pattern evidence can provide a bounded confirmation adjustment only
        when:

            - the strategy already emitted BUY or SELL
            - the pattern direction agrees with that signal
            - the pattern explicitly lists the strategy as preferred
            - the pattern contains a valid confidence value

        Pattern evidence cannot create an actionable signal from HOLD.

        Disabled strategies are excluded from automatic selection.
        """

        normalized_evaluations = (
            self._normalize_evaluations(
                evaluations
            )
        )

        normalized_patterns = (
            self._normalize_patterns(
                patterns
            )
        )

        candidates: list[
            dict[str, Any]
        ] = []

        excluded: list[
            dict[str, Any]
        ] = []

        for index, evaluation in enumerate(
            normalized_evaluations
        ):
            strategy_name = (
                self._strategy_name(
                    evaluation.get(
                        "strategy"
                    )
                )
            )

            if strategy_name is None:
                excluded.append(
                    {
                        "index": index,
                        "reason": (
                            "strategy name is missing"
                        ),
                    }
                )
                continue

            canonical_strategy = (
                self._canonical_strategy_name(
                    strategy_name
                )
            )

            if canonical_strategy is None:
                excluded.append(
                    {
                        "index": index,
                        "strategy": strategy_name,
                        "reason": (
                            "strategy is not registered"
                        ),
                    }
                )
                continue

            if not self._strategy_is_enabled(
                canonical_strategy
            ):
                excluded.append(
                    {
                        "index": index,
                        "strategy": (
                            canonical_strategy
                        ),
                        "reason": (
                            "strategy is disabled"
                        ),
                    }
                )
                continue

            signal = self._signal(
                evaluation.get(
                    "signal"
                )
            )

            if signal is None:
                excluded.append(
                    {
                        "index": index,
                        "strategy": (
                            canonical_strategy
                        ),
                        "reason": (
                            "strategy evaluation contains an invalid signal"
                        ),
                    }
                )
                continue

            raw_confidence = (
                evaluation.get(
                    "confidence"
                )
            )

            base_confidence = (
                self._confidence(
                    raw_confidence
                )
            )

            evaluation_error = (
                evaluation.get(
                    "error"
                )
            )

            if (
                signal
                in self.ACTIONABLE_SIGNALS
                and base_confidence is None
            ):
                excluded.append(
                    {
                        "index": index,
                        "strategy": (
                            canonical_strategy
                        ),
                        "signal": signal,
                        "reason": (
                            "actionable strategy evaluation is missing a valid confidence"
                        ),
                    }
                )
                continue

            pattern_result = (
                self._pattern_confirmation(
                    canonical_strategy,
                    signal,
                    normalized_patterns,
                )
            )

            pattern_bonus = (
                pattern_result[
                    "bonus"
                ]
            )

            pattern_penalty = (
                pattern_result[
                    "penalty"
                ]
            )

            if (
                signal
                in self.ACTIONABLE_SIGNALS
                and base_confidence is not None
            ):
                final_score = max(
                    0.0,
                    min(
                        1.0,
                        (
                            base_confidence
                            + pattern_bonus
                            - pattern_penalty
                        ),
                    ),
                )

            else:
                final_score = (
                    base_confidence
                )

            rationale = (
                self._rationale(
                    evaluation.get(
                        "rationale"
                    )
                )
            )

            reasons = list(
                rationale
            )

            reasons.extend(
                pattern_result[
                    "confirmation_reasons"
                ]
            )

            conflict_reasons = list(
                pattern_result[
                    "conflict_reasons"
                ]
            )

            candidate = {
                "strategy": (
                    canonical_strategy
                ),
                "signal": signal,
                "base_confidence": (
                    base_confidence
                ),
                "pattern_bonus": (
                    pattern_bonus
                    if signal
                    in self.ACTIONABLE_SIGNALS
                    else 0.0
                ),
                "pattern_penalty": (
                    pattern_penalty
                    if signal
                    in self.ACTIONABLE_SIGNALS
                    else 0.0
                ),
                "score": final_score,
                "reasons": reasons,
                "conflict_reasons": (
                    conflict_reasons
                ),
                "pattern_confirmations": (
                    pattern_result[
                        "confirmations"
                    ]
                ),
                "pattern_conflicts": (
                    pattern_result[
                        "conflicts"
                    ]
                ),
                "stop": evaluation.get(
                    "stop"
                ),
                "target": evaluation.get(
                    "target"
                ),
                "error": evaluation_error,
                "evaluation_index": index,
            }

            candidates.append(
                candidate
            )

        actionable = [
            candidate
            for candidate in candidates
            if (
                candidate[
                    "signal"
                ]
                in self.ACTIONABLE_SIGNALS
                and candidate[
                    "score"
                ]
                is not None
                and not candidate[
                    "error"
                ]
            )
        ]

        actionable.sort(
            key=self._actionable_sort_key
        )

        top_count = (
            self._decision_top_strategies()
        )

        # ========================================================
        # NO ACTIONABLE STRATEGY
        # ========================================================

        if not actionable:
            hold_ranked = [
                candidate
                for candidate
                in candidates
                if candidate[
                    "signal"
                ]
                == "HOLD"
            ]

            hold_ranked.sort(
                key=self._hold_sort_key
            )

            return {
                "selected_strategy": None,
                "selected_signal": "HOLD",
                "score": None,
                "base_confidence": None,
                "pattern_bonus": 0.0,
                "pattern_penalty": 0.0,
                "reasons": [
                    (
                        "No enabled registered strategy "
                        "produced an actionable signal."
                    )
                ],
                "conflict_reasons": [],
                "ranked": (
                    hold_ranked[
                        :top_count
                    ]
                ),
                "excluded": excluded,
                "evaluated_count": len(
                    normalized_evaluations
                ),
                "eligible_count": len(
                    candidates
                ),
                "actionable_count": 0,
                "create_adaptive": (
                    self._adaptive_enabled()
                ),
            }

        # ========================================================
        # BEST ACTIONABLE STRATEGY
        # ========================================================

        best = actionable[0]

        create_adaptive = (
            self._should_create_adaptive(
                best
            )
        )

        return {
            "selected_strategy": (
                best[
                    "strategy"
                ]
            ),
            "selected_signal": (
                best[
                    "signal"
                ]
            ),
            "score": (
                best[
                    "score"
                ]
            ),
            "base_confidence": (
                best[
                    "base_confidence"
                ]
            ),
            "pattern_bonus": (
                best[
                    "pattern_bonus"
                ]
            ),
            "pattern_penalty": (
                best[
                    "pattern_penalty"
                ]
            ),
            "reasons": (
                best[
                    "reasons"
                ]
            ),
            "conflict_reasons": (
                best[
                    "conflict_reasons"
                ]
            ),
            "stop": (
                best[
                    "stop"
                ]
            ),
            "target": (
                best[
                    "target"
                ]
            ),
            "ranked": (
                actionable[
                    :top_count
                ]
            ),
            "excluded": excluded,
            "evaluated_count": len(
                normalized_evaluations
            ),
            "eligible_count": len(
                candidates
            ),
            "actionable_count": len(
                actionable
            ),
            "create_adaptive": (
                create_adaptive
            ),
        }

    # ============================================================
    # PATTERN CONFIRMATION
    # ============================================================

    def _pattern_confirmation(
        self,
        strategy_name: str,
        signal: str,
        patterns: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Calculate bounded pattern confirmation.

        Pattern evidence may only adjust an existing actionable signal.

        A pattern contributes when it explicitly identifies the selected
        strategy as preferred and its direction agrees with the strategy
        signal.

        Opposite-direction evidence can produce a bounded penalty when it
        explicitly identifies the strategy as preferred.

        Missing pattern confidence contributes nothing.
        """

        if signal not in (
            self.ACTIONABLE_SIGNALS
        ):
            return {
                "bonus": 0.0,
                "penalty": 0.0,
                "confirmations": [],
                "conflicts": [],
                "confirmation_reasons": [],
                "conflict_reasons": [],
            }

        expected_direction = (
            "BULLISH"
            if signal == "BUY"
            else "BEARISH"
        )

        opposite_direction = (
            "BEARISH"
            if expected_direction
            == "BULLISH"
            else "BULLISH"
        )

        confirmations: list[
            dict[str, Any]
        ] = []

        conflicts: list[
            dict[str, Any]
        ] = []

        raw_confirmation_weight = 0.0
        raw_conflict_weight = 0.0

        for pattern in patterns:
            direction = (
                self._pattern_direction(
                    pattern
                )
            )

            if direction not in {
                expected_direction,
                opposite_direction,
            }:
                continue

            preferred = (
                self._preferred_strategies(
                    pattern
                )
            )

            if not preferred:
                continue

            if not self._strategy_is_preferred(
                strategy_name,
                preferred,
            ):
                continue

            confidence = (
                self._pattern_confidence(
                    pattern
                )
            )

            if confidence is None:
                continue

            label = (
                self._pattern_label(
                    pattern
                )
            )

            evidence = {
                "pattern": label,
                "direction": direction,
                "confidence": confidence,
                "preferred_strategy": (
                    strategy_name
                ),
            }

            if (
                direction
                == expected_direction
            ):
                confirmations.append(
                    evidence
                )

                raw_confirmation_weight += (
                    confidence
                )

            elif (
                direction
                == opposite_direction
            ):
                conflicts.append(
                    evidence
                )

                raw_conflict_weight += (
                    confidence
                )

        bonus = (
            self._bounded_pattern_adjustment(
                raw_confirmation_weight
            )
        )

        penalty = (
            self._bounded_pattern_adjustment(
                raw_conflict_weight
            )
        )

        confirmation_reasons = [
            (
                f"{item['pattern']} confirms "
                f"{signal.lower()} setup "
                f"({item['confidence']:.2f})"
            )
            for item in confirmations
        ]

        conflict_reasons = [
            (
                f"{item['pattern']} conflicts with "
                f"{signal.lower()} setup "
                f"({item['confidence']:.2f})"
            )
            for item in conflicts
        ]

        return {
            "bonus": bonus,
            "penalty": penalty,
            "confirmations": (
                confirmations
            ),
            "conflicts": conflicts,
            "confirmation_reasons": (
                confirmation_reasons
            ),
            "conflict_reasons": (
                conflict_reasons
            ),
        }

    # ============================================================
    # BOUNDED PATTERN ADJUSTMENT
    # ============================================================

    def _bounded_pattern_adjustment(
        self,
        evidence_weight: float,
    ) -> float:
        """
        Preserve the existing PhoenixTrend maximum confirmation influence.

        The original selector allowed each fully confident confirming pattern
        to contribute 0.04 and capped total pattern influence at 0.08.

        This method retains that contract while ensuring only real, finite
        pattern confidence contributes.
        """

        if not isfinite(
            evidence_weight
        ):
            return 0.0

        if evidence_weight <= 0:
            return 0.0

        contribution = (
            evidence_weight
            * 0.04
        )

        return min(
            contribution,
            self.PATTERN_CONFIRMATION_MAX,
        )

    # ============================================================
    # STRATEGY NAME MATCHING
    # ============================================================

    def _strategy_is_preferred(
        self,
        strategy_name: str,
        preferred: list[Any],
    ) -> bool:
        canonical_strategy = (
            self._canonical_strategy_name(
                strategy_name
            )
        )

        if canonical_strategy is None:
            return False

        canonical_key = (
            canonical_strategy.casefold()
        )

        for preferred_name in preferred:
            name = self._strategy_name(
                preferred_name
            )

            if name is None:
                continue

            canonical_preferred = (
                self._canonical_strategy_name(
                    name
                )
            )

            if canonical_preferred is None:
                continue

            if (
                canonical_preferred.casefold()
                == canonical_key
            ):
                return True

        return False

    # ============================================================
    # CANONICAL STRATEGY NAME
    # ============================================================

    def _canonical_strategy_name(
        self,
        strategy_name: str,
    ) -> str | None:
        name = self._strategy_name(
            strategy_name
        )

        if name is None:
            return None

        try:
            resolved = (
                self.registry.resolve_name(
                    name
                )
            )

        except (
            ValueError,
            KeyError,
            TypeError,
        ):
            return None

        resolved_name = (
            self._strategy_name(
                resolved
            )
        )

        return resolved_name

    # ============================================================
    # NORMALIZE EVALUATIONS
    # ============================================================

    @staticmethod
    def _normalize_evaluations(
        evaluations: Any,
    ) -> list[dict[str, Any]]:
        if evaluations is None:
            return []

        if not isinstance(
            evaluations,
            list,
        ):
            raise TypeError(
                "evaluations must be a list"
            )

        output: list[
            dict[str, Any]
        ] = []

        for evaluation in evaluations:
            if not isinstance(
                evaluation,
                dict,
            ):
                continue

            output.append(
                dict(
                    evaluation
                )
            )

        return output

    # ============================================================
    # NORMALIZE PATTERNS
    # ============================================================

    @staticmethod
    def _normalize_patterns(
        patterns: Any,
    ) -> list[dict[str, Any]]:
        if patterns is None:
            return []

        if not isinstance(
            patterns,
            list,
        ):
            raise TypeError(
                "patterns must be a list"
            )

        output: list[
            dict[str, Any]
        ] = []

        for pattern in patterns:
            if not isinstance(
                pattern,
                dict,
            ):
                continue

            output.append(
                dict(
                    pattern
                )
            )

        return output

    # ============================================================
    # SIGNAL
    # ============================================================

    @classmethod
    def _signal(
        cls,
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        signal = str(
            value
        ).strip().upper()

        if signal not in (
            cls.VALID_SIGNALS
        ):
            return None

        return signal

    # ============================================================
    # CONFIDENCE
    # ============================================================

    @staticmethod
    def _confidence(
        value: Any,
    ) -> float | None:
        """
        Normalize genuine strategy confidence.

        Missing, malformed, NaN, infinity, or out-of-range confidence is not
        silently converted to zero.
        """

        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            return None

        try:
            confidence = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(
            confidence
        ):
            return None

        if (
            confidence > 1.0
            and confidence <= 100.0
        ):
            confidence /= 100.0

        if not (
            0.0
            <= confidence
            <= 1.0
        ):
            return None

        return confidence

    # ============================================================
    # PATTERN CONFIDENCE
    # ============================================================

    @classmethod
    def _pattern_confidence(
        cls,
        pattern: dict[str, Any],
    ) -> float | None:
        for key in (
            "confidence",
            "pattern_confidence",
            "quality",
            "probability",
        ):
            if key not in pattern:
                continue

            confidence = (
                cls._confidence(
                    pattern.get(
                        key
                    )
                )
            )

            if confidence is not None:
                return confidence

        return None

    # ============================================================
    # PATTERN DIRECTION
    # ============================================================

    @staticmethod
    def _pattern_direction(
        pattern: dict[str, Any],
    ) -> str | None:
        raw = None

        for key in (
            "direction",
            "bias",
            "signal",
            "side",
        ):
            value = pattern.get(
                key
            )

            if value is not None:
                raw = str(
                    value
                ).strip().upper()

                if raw:
                    break

        if not raw:
            return None

        aliases = {
            "BUY": "BULLISH",
            "LONG": "BULLISH",
            "UP": "BULLISH",
            "UPWARD": "BULLISH",
            "BULL": "BULLISH",
            "BULLISH": "BULLISH",
            "SELL": "BEARISH",
            "SHORT": "BEARISH",
            "DOWN": "BEARISH",
            "DOWNWARD": "BEARISH",
            "BEAR": "BEARISH",
            "BEARISH": "BEARISH",
            "NEUTRAL": "NEUTRAL",
            "SIDEWAYS": "NEUTRAL",
            "RANGE": "NEUTRAL",
            "RANGING": "NEUTRAL",
        }

        return aliases.get(
            raw
        )

    # ============================================================
    # PREFERRED STRATEGIES
    # ============================================================

    @staticmethod
    def _preferred_strategies(
        pattern: dict[str, Any],
    ) -> list[Any]:
        value = pattern.get(
            "preferred_strategies"
        )

        if value is None:
            value = pattern.get(
                "strategies"
            )

        if value is None:
            value = pattern.get(
                "compatible_strategies"
            )

        if value is None:
            return []

        if isinstance(
            value,
            str,
        ):
            clean = value.strip()

            return (
                [clean]
                if clean
                else []
            )

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            return [
                item
                for item in value
                if item is not None
            ]

        return []

    # ============================================================
    # PATTERN LABEL
    # ============================================================

    @staticmethod
    def _pattern_label(
        pattern: dict[str, Any],
    ) -> str:
        for key in (
            "label",
            "name",
            "pattern",
            "pattern_name",
            "type",
        ):
            value = pattern.get(
                key
            )

            if value is None:
                continue

            label = str(
                value
            ).strip()

            if label:
                return label

        return "chart pattern"

    # ============================================================
    # RATIONALE
    # ============================================================

    @staticmethod
    def _rationale(
        value: Any,
    ) -> list[str]:
        if value is None:
            return []

        if isinstance(
            value,
            str,
        ):
            clean = value.strip()

            return (
                [clean]
                if clean
                else []
            )

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            output: list[
                str
            ] = []

            for item in value:
                if item is None:
                    continue

                clean = str(
                    item
                ).strip()

                if clean:
                    output.append(
                        clean
                    )

            return output

        clean = str(
            value
        ).strip()

        return (
            [clean]
            if clean
            else []
        )

    # ============================================================
    # STRATEGY NAME
    # ============================================================

    @staticmethod
    def _strategy_name(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        name = str(
            value
        ).strip()

        if not name:
            return None

        if len(name) > 256:
            return None

        return name

    # ============================================================
    # ACTIONABLE SORT
    # ============================================================

    @staticmethod
    def _actionable_sort_key(
        candidate: dict[str, Any],
    ) -> tuple[
        float,
        float,
        float,
        str,
    ]:
        score = candidate.get(
            "score"
        )

        base_confidence = (
            candidate.get(
                "base_confidence"
            )
        )

        pattern_bonus = (
            candidate.get(
                "pattern_bonus"
            )
        )

        strategy = str(
            candidate.get(
                "strategy"
            )
            or ""
        ).casefold()

        return (
            -float(
                score
                if score is not None
                else -1.0
            ),
            -float(
                base_confidence
                if base_confidence
                is not None
                else -1.0
            ),
            -float(
                pattern_bonus
                if pattern_bonus
                is not None
                else 0.0
            ),
            strategy,
        )

    # ============================================================
    # HOLD SORT
    # ============================================================

    @staticmethod
    def _hold_sort_key(
        candidate: dict[str, Any],
    ) -> tuple[
        float,
        str,
    ]:
        confidence = (
            candidate.get(
                "base_confidence"
            )
        )

        strategy = str(
            candidate.get(
                "strategy"
            )
            or ""
        ).casefold()

        return (
            -float(
                confidence
                if confidence
                is not None
                else -1.0
            ),
            strategy,
        )

    # ============================================================
    # DECISION TOP STRATEGIES
    # ============================================================

    @staticmethod
    def _decision_top_strategies() -> int:
        value = getattr(
            settings,
            "decision_top_strategies",
            None,
        )

        if isinstance(
            value,
            bool,
        ):
            return 1

        try:
            parsed = int(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return 1

        return max(
            1,
            parsed,
        )

    # ============================================================
    # ADAPTIVE ENABLED
    # ============================================================

    @staticmethod
    def _adaptive_enabled() -> bool:
        value = getattr(
            settings,
            "adaptive_strategy_enabled",
            False,
        )

        return StrategySelector._bool(
            value,
            default=False,
        )

    # ============================================================
    # ADAPTIVE MIN CONFIDENCE
    # ============================================================

    @classmethod
    def _adaptive_min_confidence(
        cls,
    ) -> float | None:
        value = getattr(
            settings,
            "adaptive_strategy_min_confidence",
            None,
        )

        return cls._confidence(
            value
        )

    # ============================================================
    # SHOULD CREATE ADAPTIVE
    # ============================================================

    @classmethod
    def _should_create_adaptive(
        cls,
        best: dict[str, Any],
    ) -> bool:
        if not cls._adaptive_enabled():
            return False

        score = best.get(
            "score"
        )

        if score is None:
            return False

        minimum = (
            cls._adaptive_min_confidence()
        )

        if minimum is None:
            return False

        return float(
            score
        ) < minimum

    # ============================================================
    # BOOLEAN
    # ============================================================

    @staticmethod
    def _bool(
        value: Any,
        *,
        default: bool,
    ) -> bool:
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
                value.strip().lower()
            )

            if normalized in {
                "true",
                "1",
                "yes",
                "on",
                "enabled",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "off",
                "disabled",
            }:
                return False

        return default


strategy_selector = StrategySelector()


__all__ = [
    "StrategySelector",
    "strategy_selector",
]