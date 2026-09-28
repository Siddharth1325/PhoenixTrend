from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from math import isfinite
from time import monotonic
from typing import Any, Mapping, Sequence

from ..broker import alpaca_broker
from .decision_engine import decision_engine


class PositionMonitorService:
    """
    PhoenixTrend shared live-position intelligence service.

    This service is read-only. It reads real broker positions and optionally
    enriches each position with a fresh DecisionEngine analysis.

    It does not:
        - fabricate positions
        - fabricate broker connectivity
        - fabricate P&L
        - fabricate market prices
        - fabricate DecisionEngine confidence
        - fabricate execution-safety approval
        - convert an analysis failure into HOLD
        - submit, modify, cancel, or close orders
        - authorize automatic exits

    Position exit/risk execution belongs to the dedicated risk, safety,
    capability and execution pipeline.
    """

    DEFAULT_WORKERS = 6
    MAX_WORKERS = 12
    MAX_FAILURE_MESSAGE = 500

    def snapshot(
        self,
        *,
        analyze: bool = True,
        force_analysis: bool = False,
        workers: int | None = None,
    ) -> dict[str, Any]:
        started_at = datetime.now(
            timezone.utc
        )
        started_monotonic = monotonic()

        connection = self._connection_state()

        if connection is False:
            return {
                "available": False,
                "connected": False,
                "source": "broker:alpaca",
                "as_of": started_at.isoformat(),
                "completed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "duration_ms": round(
                    (
                        monotonic()
                        - started_monotonic
                    )
                    * 1000.0,
                    3,
                ),
                "count": 0,
                "analyzed_count": 0,
                "analysis_failure_count": 0,
                "positions": [],
                "analysis_failures": [],
                "reason": "Broker is not connected",
            }

        try:
            raw = self._broker_positions()
        except Exception as exc:
            return {
                "available": False,
                "connected": connection,
                "source": "broker:alpaca",
                "as_of": started_at.isoformat(),
                "completed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "duration_ms": round(
                    (
                        monotonic()
                        - started_monotonic
                    )
                    * 1000.0,
                    3,
                ),
                "count": 0,
                "analyzed_count": 0,
                "analysis_failure_count": 0,
                "positions": [],
                "analysis_failures": [],
                "reason": self._error_message(
                    exc
                ),
                "error_type": (
                    exc.__class__.__name__
                ),
            }

        try:
            positions, broker_metadata = (
                self._extract_positions(
                    raw
                )
            )
        except Exception as exc:
            return {
                "available": False,
                "connected": connection,
                "source": "broker:alpaca",
                "as_of": started_at.isoformat(),
                "completed_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "duration_ms": round(
                    (
                        monotonic()
                        - started_monotonic
                    )
                    * 1000.0,
                    3,
                ),
                "count": 0,
                "analyzed_count": 0,
                "analysis_failure_count": 0,
                "positions": [],
                "analysis_failures": [],
                "reason": self._error_message(
                    exc
                ),
                "error_type": (
                    exc.__class__.__name__
                ),
            }

        normalized_positions: list[
            dict[str, Any]
        ] = []

        invalid_positions: list[
            dict[str, Any]
        ] = []

        for index, item in enumerate(
            positions
        ):
            normalized = (
                self._normalize_position(
                    item
                )
            )

            if normalized is None:
                invalid_positions.append(
                    {
                        "index": index,
                        "reason": (
                            "Broker position payload "
                            "is not a valid position object"
                        ),
                    }
                )
                continue

            normalized_positions.append(
                normalized
            )

        analysis_failures: list[
            dict[str, Any]
        ] = []

        analyzed_count = 0

        if (
            analyze
            and normalized_positions
        ):
            analyzed_count, analysis_failures = (
                self._enrich_positions(
                    normalized_positions,
                    force=force_analysis,
                    workers=workers,
                )
            )

        completed_at = datetime.now(
            timezone.utc
        )

        response: dict[str, Any] = {
            "available": True,
            "connected": connection,
            "source": "broker:alpaca",
            "as_of": self._broker_as_of(
                broker_metadata
            )
            or started_at.isoformat(),
            "completed_at": (
                completed_at.isoformat()
            ),
            "duration_ms": round(
                (
                    monotonic()
                    - started_monotonic
                )
                * 1000.0,
                3,
            ),
            "count": len(
                normalized_positions
            ),
            "analyzed_count": analyzed_count,
            "analysis_failure_count": len(
                analysis_failures
            ),
            "invalid_position_count": len(
                invalid_positions
            ),
            "positions": normalized_positions,
            "analysis_failures": (
                analysis_failures
            ),
        }

        if invalid_positions:
            response[
                "invalid_positions"
            ] = invalid_positions

        if broker_metadata:
            response[
                "broker_metadata"
            ] = broker_metadata

        return response

    def positions(
        self,
        *,
        analyze: bool = True,
        force_analysis: bool = False,
        workers: int | None = None,
    ) -> list[dict[str, Any]]:
        result = self.snapshot(
            analyze=analyze,
            force_analysis=force_analysis,
            workers=workers,
        )

        positions = result.get(
            "positions"
        )

        if isinstance(
            positions,
            list,
        ):
            return positions

        return []

    def position(
        self,
        symbol: str,
        *,
        analyze: bool = True,
        force_analysis: bool = False,
    ) -> dict[str, Any] | None:
        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        if not normalized_symbol:
            raise ValueError(
                "symbol is required"
            )

        connection = self._connection_state()

        if connection is False:
            return None

        direct = self._direct_position(
            normalized_symbol
        )

        if direct is not None:
            normalized = (
                self._normalize_position(
                    direct
                )
            )

            if normalized is None:
                return None

            if analyze:
                try:
                    analysis = (
                        self._analyze_symbol(
                            normalized_symbol,
                            force=force_analysis,
                        )
                    )

                    normalized[
                        "phoenixtrend"
                    ] = analysis

                except Exception as exc:
                    normalized[
                        "phoenixtrend_error"
                    ] = {
                        "error": (
                            self._error_message(
                                exc
                            )
                        ),
                        "error_type": (
                            exc.__class__.__name__
                        ),
                    }

            return normalized

        snapshot = self.snapshot(
            analyze=analyze,
            force_analysis=force_analysis,
            workers=1,
        )

        for item in snapshot.get(
            "positions",
            [],
        ):
            if not isinstance(
                item,
                Mapping,
            ):
                continue

            if (
                self._normalize_symbol(
                    item.get("symbol")
                )
                == normalized_symbol
            ):
                return dict(item)

        return None

    def symbols(
        self,
    ) -> list[str]:
        snapshot = self.snapshot(
            analyze=False
        )

        symbols: list[str] = []

        seen: set[str] = set()

        for position in snapshot.get(
            "positions",
            [],
        ):
            if not isinstance(
                position,
                Mapping,
            ):
                continue

            symbol = self._normalize_symbol(
                position.get(
                    "symbol"
                )
            )

            if (
                not symbol
                or symbol in seen
            ):
                continue

            seen.add(symbol)
            symbols.append(symbol)

        return symbols

    def _enrich_positions(
        self,
        positions: list[dict[str, Any]],
        *,
        force: bool,
        workers: int | None,
    ) -> tuple[
        int,
        list[dict[str, Any]],
    ]:
        symbol_indexes: dict[
            str,
            list[int],
        ] = {}

        failures: list[
            dict[str, Any]
        ] = []

        for index, position in enumerate(
            positions
        ):
            symbol = self._normalize_symbol(
                position.get(
                    "symbol"
                )
            )

            if not symbol:
                failures.append(
                    {
                        "symbol": None,
                        "index": index,
                        "error": (
                            "Position has no valid symbol"
                        ),
                        "error_type": (
                            "InvalidPositionSymbol"
                        ),
                    }
                )
                continue

            symbol_indexes.setdefault(
                symbol,
                [],
            ).append(index)

        symbols = list(
            symbol_indexes
        )

        if not symbols:
            return (
                0,
                failures,
            )

        safe_workers = (
            self._normalize_workers(
                workers,
                len(symbols),
            )
        )

        analyses: dict[
            str,
            dict[str, Any],
        ] = {}

        if safe_workers <= 1:
            for symbol in symbols:
                try:
                    analyses[
                        symbol
                    ] = self._analyze_symbol(
                        symbol,
                        force=force,
                    )

                except Exception as exc:
                    failures.append(
                        self._analysis_failure(
                            symbol,
                            exc,
                        )
                    )

        else:
            with ThreadPoolExecutor(
                max_workers=safe_workers,
                thread_name_prefix=(
                    "phoenix-position-monitor"
                ),
            ) as executor:
                future_map = {
                    executor.submit(
                        self._analyze_symbol,
                        symbol,
                        force=force,
                    ): symbol
                    for symbol in symbols
                }

                for future in as_completed(
                    future_map
                ):
                    symbol = future_map[
                        future
                    ]

                    try:
                        analyses[
                            symbol
                        ] = future.result()

                    except Exception as exc:
                        failures.append(
                            self._analysis_failure(
                                symbol,
                                exc,
                            )
                        )

        analyzed_count = 0

        for symbol, analysis in (
            analyses.items()
        ):
            indexes = symbol_indexes.get(
                symbol,
                [],
            )

            for index in indexes:
                positions[
                    index
                ][
                    "phoenixtrend"
                ] = dict(
                    analysis
                )

                analyzed_count += 1

        failures.sort(
            key=lambda item: str(
                item.get(
                    "symbol"
                )
                or ""
            )
        )

        return (
            analyzed_count,
            failures,
        )

    def _analyze_symbol(
        self,
        symbol: str,
        *,
        force: bool,
    ) -> dict[str, Any]:
        started = monotonic()

        try:
            decision = (
                decision_engine.analyze(
                    symbol,
                    force=force,
                )
            )
        except TypeError:
            decision = (
                decision_engine.analyze(
                    symbol
                )
            )

        if not isinstance(
            decision,
            Mapping,
        ):
            raise RuntimeError(
                "DecisionEngine returned an "
                "invalid payload"
            )

        decision_dict = dict(
            decision
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
            )
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

        confidence = (
            self._confidence(
                decision_dict,
                selected,
                selection,
            )
        )

        patterns = (
            self._patterns(
                decision_dict.get(
                    "patterns"
                )
            )
        )

        automatic_execution_safe = (
            self._strict_bool(
                decision_dict.get(
                    "automatic_execution_safe"
                )
            )
        )

        market = self._mapping(
            decision_dict.get(
                "market"
            )
        )

        if (
            automatic_execution_safe
            is None
        ):
            automatic_execution_safe = (
                self._strict_bool(
                    market.get(
                        "automatic_execution_safe"
                    )
                )
            )

        as_of = self._first_nonempty(
            decision_dict.get(
                "as_of"
            ),
            decision_dict.get(
                "timestamp"
            ),
            market.get(
                "as_of"
            ),
            market.get(
                "timestamp"
            ),
        )

        result: dict[str, Any] = {
            "action": action,
            "strategy": (
                str(strategy)
                if strategy is not None
                else None
            ),
            "confidence": confidence,
            "patterns": patterns,
            "automatic_execution_safe": (
                automatic_execution_safe
            ),
            "as_of": (
                str(as_of)
                if as_of is not None
                else None
            ),
            "analysis_duration_ms": round(
                (
                    monotonic()
                    - started
                )
                * 1000.0,
                3,
            ),
        }

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

        if regime is not None:
            result["regime"] = regime

        return result

    def _normalize_position(
        self,
        raw: Any,
    ) -> dict[str, Any] | None:
        item = self._object_to_mapping(
            raw
        )

        if not item:
            return None

        symbol = self._normalize_symbol(
            self._first_nonempty(
                item.get(
                    "symbol"
                ),
                item.get(
                    "asset_symbol"
                ),
            )
        )

        if not symbol:
            return None

        row = dict(item)

        row["symbol"] = symbol

        self._normalize_numeric_field(
            row,
            item,
            "qty",
            "qty",
            "quantity",
        )

        self._normalize_numeric_field(
            row,
            item,
            "available_qty",
            "available_qty",
        )

        self._normalize_numeric_field(
            row,
            item,
            "avg_entry_price",
            "avg_entry_price",
            "average_entry_price",
            "entry_price",
        )

        self._normalize_numeric_field(
            row,
            item,
            "current_price",
            "current_price",
            "market_price",
            "last_price",
        )

        self._normalize_numeric_field(
            row,
            item,
            "market_value",
            "market_value",
        )

        self._normalize_numeric_field(
            row,
            item,
            "cost_basis",
            "cost_basis",
        )

        self._normalize_numeric_field(
            row,
            item,
            "unrealized_pl",
            "unrealized_pl",
            "unrealized_pnl",
        )

        self._normalize_numeric_field(
            row,
            item,
            "unrealized_plpc",
            "unrealized_plpc",
            "unrealized_pnl_percent",
        )

        self._normalize_numeric_field(
            row,
            item,
            "change_today",
            "change_today",
        )

        side = self._normalize_side(
            item.get(
                "side"
            )
        )

        if side is not None:
            row["side"] = side

        asset_class = self._first_nonempty(
            item.get(
                "asset_class"
            ),
            item.get(
                "class"
            ),
        )

        if asset_class is not None:
            row[
                "asset_class"
            ] = str(
                asset_class
            )

        asset_id = self._first_nonempty(
            item.get(
                "asset_id"
            ),
            item.get(
                "id"
            ),
        )

        if asset_id is not None:
            row["asset_id"] = str(
                asset_id
            )

        exchange = self._first_nonempty(
            item.get(
                "exchange"
            ),
        )

        if exchange is not None:
            row["exchange"] = str(
                exchange
            )

        return row

    @classmethod
    def _normalize_numeric_field(
        cls,
        target: dict[str, Any],
        source: Mapping[str, Any],
        target_key: str,
        *source_keys: str,
    ) -> None:
        value = cls._first_number(
            source,
            *source_keys,
        )

        if value is not None:
            target[
                target_key
            ] = value

    def _broker_positions(
        self,
    ) -> Any:
        method = getattr(
            alpaca_broker,
            "positions",
            None,
        )

        if not callable(method):
            method = getattr(
                alpaca_broker,
                "get_positions",
                None,
            )

        if not callable(method):
            method = getattr(
                alpaca_broker,
                "list_positions",
                None,
            )

        if not callable(method):
            raise RuntimeError(
                "Broker adapter does not expose "
                "a positions API"
            )

        return method()

    def _direct_position(
        self,
        symbol: str,
    ) -> Any | None:
        for name in (
            "position",
            "get_position",
            "position_for_symbol",
        ):
            method = getattr(
                alpaca_broker,
                name,
                None,
            )

            if not callable(method):
                continue

            try:
                return method(
                    symbol
                )

            except TypeError:
                continue

            except Exception:
                return None

        return None

    def _connection_state(
        self,
    ) -> bool | None:
        method = getattr(
            alpaca_broker,
            "is_connected",
            None,
        )

        if not callable(method):
            return None

        try:
            value = method()
        except Exception:
            return None

        if isinstance(
            value,
            bool,
        ):
            return value

        return None

    def _extract_positions(
        self,
        raw: Any,
    ) -> tuple[
        list[Any],
        dict[str, Any],
    ]:
        if raw is None:
            return (
                [],
                {},
            )

        if isinstance(
            raw,
            Mapping,
        ):
            payload = dict(raw)

            for key in (
                "positions",
                "data",
                "items",
                "results",
            ):
                if key not in payload:
                    continue

                value = payload.get(
                    key
                )

                positions = (
                    self._coerce_sequence(
                        value
                    )
                )

                if positions is None:
                    raise RuntimeError(
                        "Broker positions payload "
                        "contains an invalid "
                        f"{key} collection"
                    )

                metadata = {
                    metadata_key: metadata_value
                    for metadata_key, metadata_value
                    in payload.items()
                    if metadata_key != key
                }

                return (
                    positions,
                    metadata,
                )

            if self._looks_like_position(
                payload
            ):
                return (
                    [payload],
                    {},
                )

            if not payload:
                return (
                    [],
                    {},
                )

            raise RuntimeError(
                "Broker positions payload does "
                "not contain a recognized "
                "positions collection"
            )

        positions = self._coerce_sequence(
            raw
        )

        if positions is None:
            raise RuntimeError(
                "Broker positions response "
                "has an unsupported type"
            )

        return (
            positions,
            {},
        )

    @staticmethod
    def _coerce_sequence(
        value: Any,
    ) -> list[Any] | None:
        if value is None:
            return []

        if isinstance(
            value,
            Sequence,
        ) and not isinstance(
            value,
            (
                str,
                bytes,
                bytearray,
            ),
        ):
            return list(value)

        try:
            if (
                not isinstance(
                    value,
                    (
                        str,
                        bytes,
                        bytearray,
                        Mapping,
                    ),
                )
                and hasattr(
                    value,
                    "__iter__",
                )
            ):
                return list(value)

        except TypeError:
            return None

        return None

    @staticmethod
    def _looks_like_position(
        value: Mapping[str, Any],
    ) -> bool:
        return bool(
            value.get("symbol")
            or value.get(
                "asset_symbol"
            )
        )

    @staticmethod
    def _object_to_mapping(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(
            value,
            Mapping,
        ):
            return dict(value)

        model_dump = getattr(
            value,
            "model_dump",
            None,
        )

        if callable(model_dump):
            dumped = model_dump()

            if isinstance(
                dumped,
                Mapping,
            ):
                return dict(dumped)

        dict_method = getattr(
            value,
            "dict",
            None,
        )

        if callable(dict_method):
            dumped = dict_method()

            if isinstance(
                dumped,
                Mapping,
            ):
                return dict(dumped)

        raw_dict = getattr(
            value,
            "__dict__",
            None,
        )

        if isinstance(
            raw_dict,
            Mapping,
        ):
            return {
                key: item
                for key, item
                in raw_dict.items()
                if not str(
                    key
                ).startswith("_")
            }

        return {}

    @classmethod
    def _confidence(
        cls,
        decision: Mapping[str, Any],
        selected: Mapping[str, Any],
        selection: Mapping[str, Any],
    ) -> float | None:
        for raw in (
            decision.get(
                "confidence"
            ),
            selected.get(
                "confidence"
            ),
            selection.get(
                "confidence"
            ),
        ):
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

            if (
                number < 0
                or number > 1
            ):
                continue

            return number

        return None

    @staticmethod
    def _patterns(
        value: Any,
    ) -> list[Any]:
        if isinstance(
            value,
            list,
        ):
            return list(value)

        if isinstance(
            value,
            tuple,
        ):
            return list(value)

        return []

    @staticmethod
    def _normalize_action(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        action = str(
            value
        ).strip().upper()

        if action in {
            "BUY",
            "SELL",
            "HOLD",
        }:
            return action

        return None

    @staticmethod
    def _normalize_side(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        side = str(
            value
        ).strip().upper()

        if side in {
            "LONG",
            "SHORT",
        }:
            return side

        return side or None

    @staticmethod
    def _strict_bool(
        value: Any,
    ) -> bool | None:
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
            return bool(value)

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
                "1",
                "yes",
                "y",
            }:
                return True

            if normalized in {
                "false",
                "0",
                "no",
                "n",
            }:
                return False

        return None

    @classmethod
    def _first_number(
        cls,
        source: Mapping[str, Any],
        *keys: str,
    ) -> float | None:
        for key in keys:
            if key not in source:
                continue

            number = cls._number(
                source.get(key)
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
            number = float(value)

        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            return None

        if not isfinite(number):
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
            return dict(value)

        return {}

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
    def _normalize_workers(
        cls,
        workers: int | None,
        symbol_count: int,
    ) -> int:
        if symbol_count <= 1:
            return 1

        if workers is None:
            workers = cls.DEFAULT_WORKERS

        if isinstance(
            workers,
            bool,
        ):
            workers = cls.DEFAULT_WORKERS

        try:
            parsed = int(workers)

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
                symbol_count,
            ),
        )

    @classmethod
    def _analysis_failure(
        cls,
        symbol: str,
        exc: Exception,
    ) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "error": cls._error_message(
                exc
            ),
            "error_type": (
                exc.__class__.__name__
            ),
        }

    @classmethod
    def _error_message(
        cls,
        exc: Exception,
    ) -> str:
        message = str(exc).strip()

        if not message:
            message = (
                exc.__class__.__name__
            )

        if (
            len(message)
            > cls.MAX_FAILURE_MESSAGE
        ):
            message = (
                message[
                    : cls.MAX_FAILURE_MESSAGE
                    - 3
                ]
                + "..."
            )

        return message

    @staticmethod
    def _broker_as_of(
        metadata: Mapping[str, Any],
    ) -> str | None:
        for key in (
            "as_of",
            "timestamp",
            "updated_at",
        ):
            value = metadata.get(key)

            if value is None:
                continue

            if isinstance(
                value,
                datetime,
            ):
                timestamp = value

                if timestamp.tzinfo is None:
                    timestamp = (
                        timestamp.replace(
                            tzinfo=timezone.utc
                        )
                    )

                return (
                    timestamp.isoformat()
                )

            text = str(value).strip()

            if text:
                return text

        return None


position_monitor_service = PositionMonitorService()


__all__ = [
    "PositionMonitorService",
    "position_monitor_service",
]