from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Any

from ..config import settings
from ..domain import AssetType
from ..strategies.base import Context
from ..strategies.registry import StrategyRegistry

from .adaptive_strategy import adaptive_strategy_service
from .chart_patterns import chart_pattern_service
from .market import market_service
from .strategy_selector import strategy_selector
from .strategy_management import strategy_management_service


class DecisionEngine:
    """PhoenixTrend deterministic decision pipeline."""

    def __init__(self) -> None:
        self.registry = StrategyRegistry()
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = RLock()

    # ============================================================
    # NUMBER HELPERS
    # ============================================================

    @staticmethod
    def _float(
        value: Any,
        default: float = 0.0,
    ) -> float:
        try:
            if value is None:
                return default

            return float(value)

        except (TypeError, ValueError):
            return default

    @staticmethod
    def _optional_float(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            return float(value)

        except (TypeError, ValueError):
            return None

    # ============================================================
    # ASSET TYPE
    # ============================================================

    @staticmethod
    def _asset_type(
        market: dict[str, Any],
    ) -> AssetType:
        """
        Resolve the normalized PhoenixTrend asset type.

        Automatic execution must never silently classify an
        unknown instrument as EQUITY.
        """

        raw = (
            market.get("asset_type")
            or market.get("asset_class")
            or market.get("type")
        )

        if raw is None:
            raise RuntimeError(
                "Market provider did not identify the asset type"
            )

        if isinstance(raw, AssetType):
            return raw

        normalized = str(raw).strip().upper()

        aliases = {
            "STOCK": AssetType.EQUITY,
            "STOCKS": AssetType.EQUITY,
            "EQUITY": AssetType.EQUITY,
            "EQUITIES": AssetType.EQUITY,

            "ETF": AssetType.ETF,
            "ETFS": AssetType.ETF,

            "OPTION": AssetType.OPTION,
            "OPTIONS": AssetType.OPTION,

            "CRYPTO": AssetType.CRYPTO,
            "CRYPTOCURRENCY": AssetType.CRYPTO,
            "CRYPTOCURRENCIES": AssetType.CRYPTO,

            "FOREX": AssetType.FOREX,
            "FX": AssetType.FOREX,

            "COMMODITY": AssetType.COMMODITY,
            "COMMODITIES": AssetType.COMMODITY,
        }

        asset_type = aliases.get(normalized)

        if asset_type is None:
            raise RuntimeError(
                f"Unsupported market asset type: {raw}"
            )

        return asset_type

    # ============================================================
    # CONTEXT
    # ============================================================

    @classmethod
    def _context(
        cls,
        market: dict[str, Any],
        patterns: list[dict[str, Any]],
    ) -> Context:
        return Context(
            symbol=str(market["symbol"]),
            asset_type=cls._asset_type(market),
            price=cls._float(market.get("price")),
            open_price=cls._optional_float(
                market.get("open_price")
            ),
            previous_close=cls._optional_float(
                market.get("previous_close")
            ),
            ema9=cls._optional_float(
                market.get("ema9")
            ),
            ema20=cls._float(
                market.get("ema20")
            ),
            ema50=cls._float(
                market.get("ema50")
            ),
            ema200=cls._optional_float(
                market.get("ema200")
            ),
            vwap=cls._float(
                market.get("vwap")
            ),
            rsi=cls._float(
                market.get("rsi"),
                50.0,
            ),
            macd=cls._optional_float(
                market.get("macd")
            ),
            macd_signal=cls._optional_float(
                market.get("macd_signal")
            ),
            macd_histogram=cls._optional_float(
                market.get("macd_histogram")
            ),
            atr=cls._float(
                market.get("atr")
            ),
            atr_pct=cls._float(
                market.get("atr_pct")
            ),
            bb_lower=cls._optional_float(
                market.get("bb_lower")
            ),
            bb_middle=cls._optional_float(
                market.get("bb_middle")
            ),
            bb_upper=cls._optional_float(
                market.get("bb_upper")
            ),
            volume=cls._float(
                market.get("volume")
            ),
            average_volume=cls._float(
                market.get("average_volume")
            ),
            volume_ratio=cls._float(
                market.get("volume_ratio"),
                1.0,
            ),
            day_high=cls._float(
                market.get("day_high")
            ),
            day_low=cls._float(
                market.get("day_low")
            ),
            opening_range_high=cls._optional_float(
                market.get("opening_range_high")
            ),
            opening_range_low=cls._optional_float(
                market.get("opening_range_low")
            ),
            market_regime=str(
                market.get(
                    "market_regime",
                    "NEUTRAL",
                )
            ).upper(),
            trend_strength=cls._float(
                market.get("trend_strength")
            ),
            sma20=cls._optional_float(market.get("sma20")),
            sma50=cls._optional_float(market.get("sma50")),
            adx=cls._optional_float(market.get("adx")),
            plus_di=cls._optional_float(market.get("plus_di")),
            minus_di=cls._optional_float(market.get("minus_di")),
            stochastic_k=cls._optional_float(market.get("stochastic_k")),
            stochastic_d=cls._optional_float(market.get("stochastic_d")),
            cci=cls._optional_float(market.get("cci")),
            williams_r=cls._optional_float(market.get("williams_r")),
            roc=cls._optional_float(market.get("roc")),
            donchian_high=cls._optional_float(market.get("donchian_high")),
            donchian_low=cls._optional_float(market.get("donchian_low")),
            keltner_middle=cls._optional_float(market.get("keltner_middle")),
            keltner_upper=cls._optional_float(market.get("keltner_upper")),
            keltner_lower=cls._optional_float(market.get("keltner_lower")),
            ichimoku_conversion=cls._optional_float(market.get("ichimoku_conversion")),
            ichimoku_base=cls._optional_float(market.get("ichimoku_base")),
            ichimoku_span_a=cls._optional_float(market.get("ichimoku_span_a")),
            ichimoku_span_b=cls._optional_float(market.get("ichimoku_span_b")),
            supertrend=cls._optional_float(market.get("supertrend")),
            psar=cls._optional_float(market.get("psar")),
            patterns=patterns,
            source=str(
                market.get(
                    "source",
                    "unknown",
                )
            ),
            as_of=market.get("as_of"),
            simulated=bool(
                market.get(
                    "simulated",
                    False,
                )
            ),
            automatic_execution_safe=bool(
                market.get(
                    "automatic_execution_safe",
                    False,
                )
            ),
        )

    # ============================================================
    # STRATEGY EVALUATION
    # ============================================================

    def _evaluate_strategies(
        self,
        context: Context,
    ) -> list[dict[str, Any]]:
        evaluations: list[dict[str, Any]] = []

        for name in strategy_management_service.all_names():
            try:
                strategy = strategy_management_service.create_instance(name)

                signal = strategy.signal(context)

                raw_score = strategy.score(context)

                score = max(
                    0.0,
                    min(
                        self._float(raw_score),
                        1.0,
                    ),
                )

                if signal is None:
                    evaluations.append(
                        {
                            "strategy": strategy.name,
                            "signal": "HOLD",
                            "confidence": score,
                            "rationale": [],
                            "stop": None,
                            "target": None,
                            "source": "registered-strategy",
                        }
                    )

                    continue

                evaluations.append(
                    {
                        "strategy": strategy.name,
                        "signal": signal.side.value,
                        "confidence": max(
                            0.0,
                            min(
                                float(signal.confidence),
                                1.0,
                            ),
                        ),
                        "rationale": signal.rationale,
                        "stop": signal.stop,
                        "target": signal.target,
                        "source": "registered-strategy",
                    }
                )

            except Exception as exc:
                evaluations.append(
                    {
                        "strategy": name,
                        "signal": "HOLD",
                        "confidence": 0.0,
                        "rationale": [],
                        "stop": None,
                        "target": None,
                        "source": "registered-strategy",
                        "error": str(exc),
                    }
                )

        return evaluations

    # ============================================================
    # FIND STRATEGY EVALUATION
    # ============================================================

    @staticmethod
    def _find_evaluation(
        evaluations: list[dict[str, Any]],
        strategy_name: str | None,
    ) -> dict[str, Any] | None:
        if not strategy_name:
            return None

        wanted = strategy_name.strip().lower()

        return next(
            (
                evaluation
                for evaluation in evaluations
                if str(
                    evaluation.get(
                        "strategy",
                        "",
                    )
                ).strip().lower()
                == wanted
            ),
            None,
        )

    # ============================================================
    # ANALYZE
    # ============================================================

    def analyze(
        self,
        symbol: str,
        force: bool = False,
    ) -> dict[str, Any]:
        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError(
                "Symbol is required"
            )

        now = monotonic()

        # ========================================================
        # CACHE
        # ========================================================

        with self._lock:
            cached = self._cache.get(
                normalized_symbol
            )

        if (
            not force
            and cached is not None
            and now - cached[0]
            <= settings.decision_cache_seconds
        ):
            return {
                **cached[1],
                "cache_hit": True,
            }

        # ========================================================
        # MARKET CONTEXT
        # ========================================================

        market = market_service.context(
            normalized_symbol
        )

        bars = market.get("bars") or []

        if not bars:
            raise RuntimeError(
                "Market context contains no bars "
                f"for {normalized_symbol}"
            )

        # ========================================================
        # PATTERNS
        # ========================================================

        patterns = chart_pattern_service.analyze(
            bars
        )

        # ========================================================
        # NORMALIZED STRATEGY CONTEXT
        # ========================================================

        context = self._context(
            market,
            patterns,
        )

        # ========================================================
        # REGISTERED STRATEGIES
        # ========================================================

        evaluations = self._evaluate_strategies(
            context
        )

        # ========================================================
        # STRATEGY SELECTION
        # ========================================================

        # StrategySelector ranks evaluated strategies,
        # not raw market data.
        selection = strategy_selector.select(
            evaluations,
            patterns,
        )

        selected_name = selection.get(
            "selected_strategy"
        )

        selected = self._find_evaluation(
            evaluations,
            selected_name,
        )

        # ========================================================
        # ADAPTIVE STRATEGY
        # ========================================================

        adaptive = None

        should_try_adaptive = (
            settings.adaptive_strategy_enabled
            and (
                bool(
                    selection.get(
                        "create_adaptive"
                    )
                )
                or selected is None
                or selected.get(
                    "signal"
                )
                == "HOLD"
            )
        )

        if should_try_adaptive:
            adaptive = (
                adaptive_strategy_service.evaluate(
                    normalized_symbol,
                    market,
                    patterns,
                )
            )

            adaptive_signal = (
                adaptive.get("signal")
                if adaptive
                else None
            )

            if adaptive_signal is not None:
                adaptive_view = {
                    "strategy": (
                        adaptive_signal.strategy
                    ),
                    "signal": (
                        adaptive_signal.side.value
                    ),
                    "confidence": float(
                        adaptive_signal.confidence
                    ),
                    "rationale": (
                        adaptive_signal.rationale
                    ),
                    "stop": (
                        adaptive_signal.stop
                    ),
                    "target": (
                        adaptive_signal.target
                    ),
                    "rules": adaptive.get(
                        "rules",
                        [],
                    ),
                    "source": (
                        "adaptive-composite"
                    ),
                }

                selected_confidence = (
                    self._float(
                        selected.get(
                            "confidence"
                        )
                    )
                    if selected
                    else 0.0
                )

                if (
                    selected is None
                    or selected.get(
                        "signal"
                    )
                    == "HOLD"
                    or adaptive_view[
                        "confidence"
                    ]
                    > selected_confidence
                ):
                    selected = adaptive_view

                    selected_name = (
                        adaptive_view[
                            "strategy"
                        ]
                    )

        # ========================================================
        # FINAL ACTION
        # ========================================================

        action = "HOLD"
        confidence = 0.0

        if selected:
            confidence = self._float(
                selected.get(
                    "confidence"
                )
            )

            selected_signal = str(
                selected.get(
                    "signal",
                    "HOLD",
                )
            ).upper()

            if (
                selected_signal
                in {
                    "BUY",
                    "SELL",
                }
                and confidence
                >= settings.decision_min_confidence
            ):
                action = selected_signal

        # ========================================================
        # ADAPTIVE RESPONSE
        # ========================================================

        adaptive_result = None

        if adaptive is not None:
            adaptive_signal = adaptive.get(
                "signal"
            )

            adaptive_result = {
                "name": adaptive.get(
                    "name"
                ),
                "confidence": adaptive.get(
                    "confidence",
                    0.0,
                ),
                "bullish_score": adaptive.get(
                    "bullish_score",
                    0.0,
                ),
                "bearish_score": adaptive.get(
                    "bearish_score",
                    0.0,
                ),
                "evidence": adaptive.get(
                    "evidence",
                    [],
                ),
                "rules": adaptive.get(
                    "rules",
                    {},
                ),
                "signal": (
                    {
                        "symbol": (
                            adaptive_signal.symbol
                        ),
                        "side": (
                            adaptive_signal.side.value
                        ),
                        "strategy": (
                            adaptive_signal.strategy
                        ),
                        "confidence": (
                            adaptive_signal.confidence
                        ),
                        "rationale": (
                            adaptive_signal.rationale
                        ),
                        "stop": (
                            adaptive_signal.stop
                        ),
                        "target": (
                            adaptive_signal.target
                        ),
                    }
                    if adaptive_signal
                    is not None
                    else None
                ),
            }

        # ========================================================
        # MARKET VIEW
        # ========================================================

        # Bars are intentionally excluded from the decision
        # response because they can be large. The normalized asset
        # type is explicitly included so downstream execution does
        # not need to guess the instrument class.
        market_view = {
            key: value
            for key, value
            in market.items()
            if key != "bars"
        }

        market_view[
            "asset_type"
        ] = context.asset_type.value

        # ========================================================
        # RESULT
        # ========================================================

        result = {
            "symbol": normalized_symbol,
            "action": action,
            "confidence": round(
                confidence,
                4,
            ),
            "strategy": (
                selected_name
                if selected is not None
                else None
            ),
            "selected": selected,
            "selection": selection,
            "patterns": patterns,
            "evaluations": evaluations,
            "adaptive": adaptive_result,
            "market": market_view,
            "automatic_execution_safe": bool(
                market.get(
                    "automatic_execution_safe",
                    False,
                )
            ),
            "created_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "cache_hit": False,
        }

        # ========================================================
        # STORE CACHE
        # ========================================================

        with self._lock:
            self._cache[
                normalized_symbol
            ] = (
                now,
                result,
            )

        return result

    # ============================================================
    # CLEAR CACHE
    # ============================================================

    def clear_cache(
        self,
        symbol: str | None = None,
    ) -> None:
        with self._lock:
            if symbol is None:
                self._cache.clear()
                return

            self._cache.pop(
                symbol.strip().upper(),
                None,
            )


decision_engine = DecisionEngine()