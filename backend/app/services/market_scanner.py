from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from math import isfinite
from time import monotonic
from typing import Any, Iterable, Mapping, Sequence

from .candidate_ranker import candidate_ranker
from .decision_engine import decision_engine
from .universe import universe_service


class MarketScanner:
    """
    PhoenixTrend broad market scanner.

    Pipeline responsibility:

        Universe
            -> Decision Engine
            -> market/indicator/pattern/strategy observations
            -> normalized candidate
            -> Candidate Ranker

    This service is discovery/read-only infrastructure.

    It does not:
        - place orders
        - authorize automatic execution
        - fabricate missing market values
        - convert missing confidence into a positive signal
        - treat safety approval as ranking alpha
        - silently turn analysis failures into HOLD candidates

    Missing observations remain None.

    A candidate's ``automatic_execution_safe`` value is informational only.
    Final unattended execution must still pass PhoenixTrend's Market Safety,
    Risk, Capability and Execution pipeline.
    """

    DEFAULT_LIMIT = 25
    MAX_LIMIT = 250

    DEFAULT_WORKERS = 8
    MAX_WORKERS = 16

    MAX_UNIVERSE_SIZE = 1000

    ACTION_BUY = "BUY"
    ACTION_SELL = "SELL"
    ACTION_HOLD = "HOLD"

    STATUS_OK = "ok"
    STATUS_ERROR = "error"

    def scan(
        self,
        asset_class: str,
        *,
        symbols: list[str] | None = None,
        limit: int = DEFAULT_LIMIT,
        force: bool = False,
        workers: int | None = None,
    ) -> dict[str, Any]:
        asset = universe_service.normalize_asset_class(
            asset_class
        )

        universe = self._resolve_universe(
            asset,
            symbols,
        )

        safe_limit = self._normalize_limit(
            limit
        )

        started_at = datetime.now(
            timezone.utc
        )

        started_monotonic = monotonic()

        if not universe:
            return {
                "asset_class": asset,
                "scanned_at": started_at.isoformat(),
                "completed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "duration_ms": 0.0,
                "universe_count": 0,
                "successful_count": 0,
                "failure_count": 0,
                "candidate_count": 0,
                "actionable_count": 0,
                "candidates": [],
                "failures": [],
            }

        safe_workers = self._normalize_workers(
            workers,
            len(universe),
        )

        successful: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        if safe_workers <= 1:
            for symbol in universe:
                candidate, failure = self._scan_symbol(
                    symbol=symbol,
                    asset_class=asset,
                    force=force,
                )

                if candidate is not None:
                    successful.append(
                        candidate
                    )

                if failure is not None:
                    failures.append(
                        failure
                    )

        else:
            with ThreadPoolExecutor(
                max_workers=safe_workers,
                thread_name_prefix="phoenix-market-scanner",
            ) as executor:
                future_map = {
                    executor.submit(
                        self._scan_symbol,
                        symbol=symbol,
                        asset_class=asset,
                        force=force,
                    ): symbol
                    for symbol in universe
                }

                for future in as_completed(
                    future_map
                ):
                    symbol = future_map[
                        future
                    ]

                    try:
                        candidate, failure = (
                            future.result()
                        )
                    except Exception as exc:
                        candidate = None
                        failure = self._failure(
                            symbol=symbol,
                            asset_class=asset,
                            exc=exc,
                        )

                    if candidate is not None:
                        successful.append(
                            candidate
                        )

                    if failure is not None:
                        failures.append(
                            failure
                        )

        ranked = self._rank(
            successful,
            limit=safe_limit,
        )

        failures.sort(
            key=lambda item: str(
                item.get("symbol")
                or ""
            )
        )

        completed_at = datetime.now(
            timezone.utc
        )

        actionable_count = sum(
            1
            for candidate in ranked
            if self._normalize_action(
                candidate.get("action")
            )
            in {
                self.ACTION_BUY,
                self.ACTION_SELL,
            }
        )

        return {
            "asset_class": asset,
            "scanned_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_ms": round(
                (
                    monotonic()
                    - started_monotonic
                )
                * 1000.0,
                3,
            ),
            "universe_count": len(
                universe
            ),
            "successful_count": len(
                successful
            ),
            "failure_count": len(
                failures
            ),
            "candidate_count": len(
                ranked
            ),
            "actionable_count": actionable_count,
            "candidates": ranked,
            "failures": failures,
        }

    def scan_symbols(
        self,
        asset_class: str,
        symbols: Sequence[str],
        *,
        limit: int = DEFAULT_LIMIT,
        force: bool = False,
        workers: int | None = None,
    ) -> dict[str, Any]:
        return self.scan(
            asset_class,
            symbols=list(
                symbols
            ),
            limit=limit,
            force=force,
            workers=workers,
        )

    def scan_one(
        self,
        asset_class: str,
        symbol: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        asset = universe_service.normalize_asset_class(
            asset_class
        )

        normalized_symbol = self._normalize_symbol(
            symbol
        )

        if not normalized_symbol:
            raise ValueError(
                "symbol is required"
            )

        candidate, failure = self._scan_symbol(
            symbol=normalized_symbol,
            asset_class=asset,
            force=force,
        )

        if failure is not None:
            return {
                "asset_class": asset,
                "symbol": normalized_symbol,
                "status": self.STATUS_ERROR,
                "candidate": None,
                "failure": failure,
            }

        return {
            "asset_class": asset,
            "symbol": normalized_symbol,
            "status": self.STATUS_OK,
            "candidate": candidate,
            "failure": None,
        }

    def _resolve_universe(
        self,
        asset_class: str,
        symbols: Sequence[str] | None,
    ) -> list[str]:
        if symbols is None:
            raw_universe = universe_service.symbols(
                asset_class
            )
        else:
            raw_universe = symbols

        if raw_universe is None:
            return []

        if isinstance(
            raw_universe,
            str,
        ):
            raw_universe = [
                raw_universe
            ]

        try:
            deduped = universe_service._dedupe(
                list(
                    raw_universe
                )
            )
        except Exception:
            deduped = self._dedupe_symbols(
                raw_universe
            )

        normalized: list[str] = []
        seen: set[str] = set()

        for raw_symbol in deduped:
            symbol = self._normalize_symbol(
                raw_symbol
            )

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(
                symbol
            )

            normalized.append(
                symbol
            )

            if (
                len(normalized)
                >= self.MAX_UNIVERSE_SIZE
            ):
                break

        return normalized

    def _scan_symbol(
        self,
        *,
        symbol: str,
        asset_class: str,
        force: bool,
    ) -> tuple[
        dict[str, Any] | None,
        dict[str, Any] | None,
    ]:
        started = monotonic()

        try:
            decision = decision_engine.analyze(
                symbol,
                force=force,
            )

            if not isinstance(
                decision,
                Mapping,
            ):
                raise RuntimeError(
                    "DecisionEngine returned an invalid payload"
                )

            candidate = self._candidate_from_decision(
                symbol=symbol,
                asset_class=asset_class,
                decision=decision,
            )

            candidate[
                "scan_duration_ms"
            ] = round(
                (
                    monotonic()
                    - started
                )
                * 1000.0,
                3,
            )

            return (
                candidate,
                None,
            )

        except Exception as exc:
            return (
                None,
                self._failure(
                    symbol=symbol,
                    asset_class=asset_class,
                    exc=exc,
                    duration_ms=(
                        monotonic()
                        - started
                    )
                    * 1000.0,
                ),
            )

    def _candidate_from_decision(
        self,
        *,
        symbol: str,
        asset_class: str,
        decision: Mapping[str, Any],
    ) -> dict[str, Any]:
        decision_dict = dict(
            decision
        )

        market = self._mapping(
            decision_dict.get(
                "market"
            )
        )

        selected = self._mapping(
            decision_dict.get(
                "selected"
            )
        )

        selection = self._mapping(
            decision_dict.get(
                "selection"
            )
        )

        indicators = self._mapping(
            market.get(
                "indicators"
            )
        )

        if not indicators:
            indicators = self._mapping(
                decision_dict.get(
                    "indicators"
                )
            )

        patterns = self._sequence(
            decision_dict.get(
                "patterns"
            )
        )

        evaluations = self._sequence(
            decision_dict.get(
                "evaluations"
            )
        )

        normalized_symbol = (
            self._normalize_symbol(
                decision_dict.get(
                    "symbol"
                )
            )
            or symbol
        )

        action = self._normalize_action(
            self._first_nonempty(
                decision_dict.get(
                    "action"
                ),
                decision_dict.get(
                    "decision"
                ),
                selected.get(
                    "action"
                ),
                selected.get(
                    "signal"
                ),
                self.ACTION_HOLD,
            )
        )

        confidence = self._extract_confidence(
            decision_dict,
            selected,
            selection,
        )

        strategy = self._first_nonempty(
            decision_dict.get(
                "strategy"
            ),
            selected.get(
                "strategy"
            ),
            selected.get(
                "name"
            ),
            selection.get(
                "selected_strategy"
            ),
            selection.get(
                "strategy"
            ),
        )

        price = self._first_number(
            market,
            "price",
            "regular_market_price",
            "close",
            "last",
            "last_price",
        )

        previous_close = self._first_number(
            market,
            "previous_close",
            "regular_market_previous_close",
            "prev_close",
        )

        change_percent = self._first_number(
            market,
            "change_percent",
            "change_pct",
            "regular_market_change_percent",
            "percent_change",
        )

        if (
            change_percent is None
            and price is not None
            and previous_close is not None
            and previous_close != 0
        ):
            change_percent = (
                (
                    price
                    - previous_close
                )
                / previous_close
            ) * 100.0

        volume = self._first_number(
            market,
            "volume",
            "regular_market_volume",
        )

        average_volume = self._first_number(
            market,
            "average_volume",
            "avg_volume",
            "average_daily_volume",
        )

        volume_ratio = self._first_number(
            market,
            "volume_ratio",
            "relative_volume",
            "relative_volume_ratio",
            "rvol",
        )

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

        dollar_volume = self._first_number(
            market,
            "dollar_volume",
            "notional_volume",
        )

        if (
            dollar_volume is None
            and price is not None
            and volume is not None
            and price >= 0
            and volume >= 0
        ):
            dollar_volume = (
                price
                * volume
            )

        bid = self._first_number(
            market,
            "bid",
            "bid_price",
        )

        ask = self._first_number(
            market,
            "ask",
            "ask_price",
        )

        spread = self._first_number(
            market,
            "spread",
        )

        if (
            spread is None
            and bid is not None
            and ask is not None
            and ask >= bid
        ):
            spread = ask - bid

        spread_percent = self._first_number(
            market,
            "spread_percent",
            "spread_pct",
        )

        if (
            spread_percent is None
            and spread is not None
            and bid is not None
            and ask is not None
        ):
            midpoint = (
                bid
                + ask
            ) / 2.0

            if midpoint > 0:
                spread_percent = (
                    spread
                    / midpoint
                ) * 100.0

        atr = self._first_number(
            indicators,
            "atr",
            "atr14",
            "atr_14",
        )

        if atr is None:
            atr = self._first_number(
                market,
                "atr",
                "atr14",
                "atr_14",
            )

        atr_percent = self._first_number(
            indicators,
            "atr_percent",
            "atr_pct",
            "atr_percentage",
        )

        if atr_percent is None:
            atr_percent = self._first_number(
                market,
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
            atr_percent = (
                atr
                / price
            ) * 100.0

        rsi = self._first_number(
            indicators,
            "rsi",
            "rsi14",
            "rsi_14",
        )

        if rsi is None:
            rsi = self._first_number(
                market,
                "rsi",
                "rsi14",
                "rsi_14",
            )

        adx = self._first_number(
            indicators,
            "adx",
            "adx14",
            "adx_14",
        )

        if adx is None:
            adx = self._first_number(
                market,
                "adx",
                "adx14",
                "adx_14",
            )

        momentum_score = self._first_number(
            market,
            "momentum_score",
        )

        if momentum_score is None:
            momentum_score = self._first_number(
                indicators,
                "momentum_score",
            )

        liquidity_score = self._first_number(
            market,
            "liquidity_score",
        )

        volatility_score = self._first_number(
            market,
            "volatility_score",
        )

        pattern_name = self._pattern_name(
            patterns
        )

        pattern_confidence = self._pattern_confidence(
            patterns
        )

        market_source = self._first_nonempty(
            market.get(
                "source"
            ),
            market.get(
                "provider"
            ),
            market.get(
                "market_provider"
            ),
        )

        as_of = self._first_nonempty(
            market.get(
                "as_of"
            ),
            market.get(
                "timestamp"
            ),
            market.get(
                "market_timestamp"
            ),
            market.get(
                "quote_timestamp"
            ),
            market.get(
                "bar_timestamp"
            ),
        )

        automatic_execution_safe = (
            self._execution_safety(
                decision_dict,
                market,
            )
        )

        regime = self._first_nonempty(
            decision_dict.get(
                "regime"
            ),
            market.get(
                "regime"
            ),
            market.get(
                "market_regime"
            ),
        )

        candidate: dict[str, Any] = {
            "symbol": normalized_symbol,
            "asset_class": asset_class,
            "action": action,
            "signal": action,
            "confidence": confidence,
            "strategy": (
                str(strategy)
                if strategy is not None
                else None
            ),
            "pattern": pattern_name,
            "pattern_confidence": pattern_confidence,
            "price": price,
            "previous_close": previous_close,
            "change_percent": change_percent,
            "volume": volume,
            "average_volume": average_volume,
            "volume_ratio": volume_ratio,
            "relative_volume": volume_ratio,
            "dollar_volume": dollar_volume,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "spread_percent": spread_percent,
            "atr": atr,
            "atr_percent": atr_percent,
            "rsi": rsi,
            "adx": adx,
            "momentum_score": momentum_score,
            "liquidity_score": liquidity_score,
            "volatility_score": volatility_score,
            "automatic_execution_safe": automatic_execution_safe,
            "market_source": (
                str(market_source)
                if market_source is not None
                else None
            ),
            "as_of": (
                str(as_of)
                if as_of is not None
                else None
            ),
            "regime": regime,
            "patterns": patterns,
            "evaluation_count": len(
                evaluations
            ),
            "status": self.STATUS_OK,
            "decision": decision_dict,
        }

        return candidate

    def _rank(
        self,
        candidates: list[dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        try:
            ranked = candidate_ranker.rank(
                candidates,
                limit=limit,
            )

            if not isinstance(
                ranked,
                list,
            ):
                raise RuntimeError(
                    "CandidateRanker returned an invalid payload"
                )

            return ranked

        except TypeError:
            ranked = candidate_ranker.rank(
                candidates
            )

            if not isinstance(
                ranked,
                list,
            ):
                raise RuntimeError(
                    "CandidateRanker returned an invalid payload"
                )

            return ranked[
                :limit
            ]

    @classmethod
    def _extract_confidence(
        cls,
        decision: Mapping[str, Any],
        selected: Mapping[str, Any],
        selection: Mapping[str, Any],
    ) -> float | None:
        values = (
            selected.get(
                "confidence"
            ),
            decision.get(
                "confidence"
            ),
            selection.get(
                "confidence"
            ),
            selection.get(
                "base_confidence"
            ),
            selected.get(
                "score"
            ),
        )

        for raw in values:
            number = cls._number(
                raw
            )

            if number is None:
                continue

            if (
                number > 1.0
                and number <= 100.0
            ):
                number /= 100.0

            if number < 0:
                return 0.0

            if number > 1:
                return 1.0

            return number

        return None

    @staticmethod
    def _execution_safety(
        decision: Mapping[str, Any],
        market: Mapping[str, Any],
    ) -> bool:
        decision_value = decision.get(
            "automatic_execution_safe"
        )

        if isinstance(
            decision_value,
            bool,
        ):
            return decision_value

        market_value = market.get(
            "automatic_execution_safe"
        )

        if isinstance(
            market_value,
            bool,
        ):
            return market_value

        return False

    @classmethod
    def _pattern_name(
        cls,
        patterns: Any,
    ) -> str | None:
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
            return None

        best_name: str | None = None
        best_confidence: float | None = None

        for pattern in patterns:
            if isinstance(
                pattern,
                Mapping,
            ):
                name = cls._first_nonempty(
                    pattern.get(
                        "name"
                    ),
                    pattern.get(
                        "pattern"
                    ),
                    pattern.get(
                        "label"
                    ),
                    pattern.get(
                        "type"
                    ),
                )

                if name is None:
                    continue

                confidence = cls._number(
                    pattern.get(
                        "confidence"
                    )
                )

                if confidence is None:
                    if best_name is None:
                        best_name = str(
                            name
                        )
                    continue

                if (
                    confidence > 1.0
                    and confidence <= 100.0
                ):
                    confidence /= 100.0

                if (
                    best_confidence is None
                    or confidence
                    > best_confidence
                ):
                    best_confidence = (
                        confidence
                    )
                    best_name = str(
                        name
                    )

            elif (
                pattern
                and best_name is None
            ):
                best_name = str(
                    pattern
                )

        return best_name

    @classmethod
    def _pattern_confidence(
        cls,
        patterns: Any,
    ) -> float | None:
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
            return None

        best: float | None = None

        for pattern in patterns:
            if not isinstance(
                pattern,
                Mapping,
            ):
                continue

            confidence = cls._number(
                pattern.get(
                    "confidence"
                )
            )

            if confidence is None:
                continue

            if (
                confidence > 1.0
                and confidence <= 100.0
            ):
                confidence /= 100.0

            confidence = max(
                0.0,
                min(
                    confidence,
                    1.0,
                ),
            )

            if (
                best is None
                or confidence > best
            ):
                best = confidence

        return best

    @classmethod
    def _first_number(
        cls,
        source: Mapping[str, Any],
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

            number = cls._number(
                source.get(
                    key
                )
            )

            if number is not None:
                return number

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
    def _mapping(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(
            value,
            Mapping,
        ):
            return dict(
                value
            )

        return {}

    @staticmethod
    def _sequence(
        value: Any,
    ) -> list[Any]:
        if isinstance(
            value,
            list,
        ):
            return list(
                value
            )

        if isinstance(
            value,
            tuple,
        ):
            return list(
                value
            )

        return []

    @staticmethod
    def _first_nonempty(
        *values: Any,
    ) -> Any:
        for value in values:
            if value is None:
                continue

            if isinstance(
                value,
                str,
            ):
                value = value.strip()

                if not value:
                    continue

            return value

        return None

    @classmethod
    def _normalize_action(
        cls,
        value: Any,
    ) -> str:
        action = str(
            value
            or cls.ACTION_HOLD
        ).strip().upper()

        if action in {
            cls.ACTION_BUY,
            cls.ACTION_SELL,
            cls.ACTION_HOLD,
        }:
            return action

        return cls.ACTION_HOLD

    @staticmethod
    def _normalize_symbol(
        value: Any,
    ) -> str:
        if value is None:
            return ""

        symbol = str(
            value
        ).strip().upper()

        if not symbol:
            return ""

        if len(symbol) > 64:
            return ""

        allowed = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789"
            ".-/_:"
        )

        if any(
            character not in allowed
            for character in symbol
        ):
            return ""

        return symbol

    @classmethod
    def _dedupe_symbols(
        cls,
        symbols: Iterable[Any],
    ) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()

        for raw in symbols:
            symbol = cls._normalize_symbol(
                raw
            )

            if not symbol:
                continue

            if symbol in seen:
                continue

            seen.add(
                symbol
            )
            output.append(
                symbol
            )

        return output

    @classmethod
    def _normalize_limit(
        cls,
        value: Any,
    ) -> int:
        try:
            parsed = int(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            parsed = cls.DEFAULT_LIMIT

        return max(
            1,
            min(
                parsed,
                cls.MAX_LIMIT,
            ),
        )

    @classmethod
    def _normalize_workers(
        cls,
        workers: int | None,
        universe_count: int,
    ) -> int:
        if universe_count <= 1:
            return 1

        if workers is None:
            workers = cls.DEFAULT_WORKERS

        try:
            parsed = int(
                workers
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            parsed = cls.DEFAULT_WORKERS

        return max(
            1,
            min(
                parsed,
                cls.MAX_WORKERS,
                universe_count,
            ),
        )

    @staticmethod
    def _failure(
        *,
        symbol: str,
        asset_class: str,
        exc: Exception,
        duration_ms: float | None = None,
    ) -> dict[str, Any]:
        message = str(
            exc
        ).strip()

        if not message:
            message = (
                exc.__class__.__name__
            )

        if len(message) > 500:
            message = (
                message[:497]
                + "..."
            )

        result: dict[str, Any] = {
            "symbol": symbol,
            "asset_class": asset_class,
            "status": MarketScanner.STATUS_ERROR,
            "error": message,
            "error_type": exc.__class__.__name__,
        }

        if duration_ms is not None:
            result[
                "scan_duration_ms"
            ] = round(
                duration_ms,
                3,
            )

        return result


market_scanner = MarketScanner()


__all__ = [
    "MarketScanner",
    "market_scanner",
]