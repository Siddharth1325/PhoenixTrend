from __future__ import annotations

from datetime import date, datetime, timezone
from math import isfinite
from typing import Any, Mapping, Sequence

from .analytics import analytics_service


class PerformanceService:
    """
    PhoenixTrend shared performance adapter.

    Provides one normalized performance source for Automation and Manual Trade
    while preserving the existing AnalyticsService as the authority for
    calculated trading performance.

    The adapter never invents:
        - P&L
        - win rate
        - trade counts
        - balances
        - returns
        - drawdown
        - Sharpe/Sortino values
        - position values
        - equity curves
        - strategy statistics

    Missing metrics remain None or absent.

    AnalyticsService method discovery is intentionally conservative. A method is
    used only when it can be invoked with the supplied arguments. Provider or
    analytics failures are surfaced instead of being replaced by fake zeros.
    """

    SUMMARY_METHODS: tuple[str, ...] = (
        "summary",
        "performance",
        "dashboard",
        "overview",
    )

    HISTORY_METHODS: tuple[str, ...] = (
        "performance_history",
        "history",
        "equity_curve",
        "timeline",
    )

    TRADES_METHODS: tuple[str, ...] = (
        "trades",
        "trade_history",
        "recent_trades",
    )

    STRATEGY_METHODS: tuple[str, ...] = (
        "strategy_performance",
        "strategies",
        "strategy_stats",
    )

    ASSET_METHODS: tuple[str, ...] = (
        "asset_performance",
        "asset_class_performance",
        "performance_by_asset",
    )

    DEFAULT_RECENT_LIMIT = 50
    MAX_RECENT_LIMIT = 500

    def snapshot(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        source: str | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        """
        Return the primary PhoenixTrend performance snapshot.

        AnalyticsService remains authoritative. This method discovers a
        compatible summary method and normalizes only fields actually present
        in the returned payload.
        """

        context = self._context(
            user_id=user_id,
            account_id=account_id,
            source=source,
            start=start,
            end=end,
        )

        result = self._call_first(
            self.SUMMARY_METHODS,
            context=context,
        )

        if not result["available"]:
            return {
                **result,
                "generated_at": self._utc_now(),
                "context": self._public_context(
                    context
                ),
            }

        payload = result.get("data")

        normalized = self._normalize_snapshot(
            payload
        )

        return {
            "available": True,
            "source": result.get("source"),
            "generated_at": self._utc_now(),
            "context": self._public_context(
                context
            ),
            "data": payload,
            "performance": normalized,
        }

    def performance(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        source: str | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        return self.snapshot(
            user_id=user_id,
            account_id=account_id,
            source=source,
            start=start,
            end=end,
        )

    def overview(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        source: str | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        return self.snapshot(
            user_id=user_id,
            account_id=account_id,
            source=source,
            start=start,
            end=end,
        )

    def dashboard(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        source: str | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        return self.snapshot(
            user_id=user_id,
            account_id=account_id,
            source=source,
            start=start,
            end=end,
        )

    def history(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        source: str | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        context = self._context(
            user_id=user_id,
            account_id=account_id,
            source=source,
            start=start,
            end=end,
        )

        result = self._call_first(
            self.HISTORY_METHODS,
            context=context,
        )

        if not result["available"]:
            return {
                **result,
                "generated_at": self._utc_now(),
                "context": self._public_context(
                    context
                ),
            }

        return {
            "available": True,
            "source": result.get("source"),
            "generated_at": self._utc_now(),
            "context": self._public_context(
                context
            ),
            "data": result.get("data"),
        }

    def recent_trades(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        source: str | None = None,
        limit: int = DEFAULT_RECENT_LIMIT,
    ) -> dict[str, Any]:
        safe_limit = self._normalize_limit(
            limit
        )

        context = self._context(
            user_id=user_id,
            account_id=account_id,
            source=source,
            limit=safe_limit,
        )

        result = self._call_first(
            self.TRADES_METHODS,
            context=context,
        )

        if not result["available"]:
            return {
                **result,
                "generated_at": self._utc_now(),
                "context": self._public_context(
                    context
                ),
            }

        payload = result.get("data")

        if isinstance(payload, list):
            payload = payload[:safe_limit]

        elif isinstance(payload, Mapping):
            payload = dict(payload)

            for key in (
                "trades",
                "items",
                "results",
                "data",
            ):
                collection = payload.get(key)

                if isinstance(collection, list):
                    payload[key] = collection[
                        :safe_limit
                    ]
                    break

        return {
            "available": True,
            "source": result.get("source"),
            "generated_at": self._utc_now(),
            "context": self._public_context(
                context
            ),
            "data": payload,
        }

    def strategy_performance(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        source: str | None = None,
        strategy: str | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        context = self._context(
            user_id=user_id,
            account_id=account_id,
            source=source,
            strategy=strategy,
            start=start,
            end=end,
        )

        result = self._call_first(
            self.STRATEGY_METHODS,
            context=context,
        )

        if not result["available"]:
            return {
                **result,
                "generated_at": self._utc_now(),
                "context": self._public_context(
                    context
                ),
            }

        return {
            "available": True,
            "source": result.get("source"),
            "generated_at": self._utc_now(),
            "context": self._public_context(
                context
            ),
            "data": result.get("data"),
        }

    def asset_performance(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        source: str | None = None,
        asset_class: str | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        context = self._context(
            user_id=user_id,
            account_id=account_id,
            source=source,
            asset_class=asset_class,
            start=start,
            end=end,
        )

        result = self._call_first(
            self.ASSET_METHODS,
            context=context,
        )

        if not result["available"]:
            return {
                **result,
                "generated_at": self._utc_now(),
                "context": self._public_context(
                    context
                ),
            }

        return {
            "available": True,
            "source": result.get("source"),
            "generated_at": self._utc_now(),
            "context": self._public_context(
                context
            ),
            "data": result.get("data"),
        }

    def automation(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        return self.snapshot(
            user_id=user_id,
            account_id=account_id,
            source="AUTOMATION",
            start=start,
            end=end,
        )

    def manual(
        self,
        *,
        user_id: Any | None = None,
        account_id: Any | None = None,
        start: date | datetime | str | None = None,
        end: date | datetime | str | None = None,
    ) -> dict[str, Any]:
        return self.snapshot(
            user_id=user_id,
            account_id=account_id,
            source="MANUAL",
            start=start,
            end=end,
        )

    def _call_first(
        self,
        methods: Sequence[str],
        *,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        found_method = False
        invocation_failures: list[str] = []

        for name in methods:
            method = getattr(
                analytics_service,
                name,
                None,
            )

            if not callable(method):
                continue

            found_method = True

            kwargs = self._supported_kwargs(
                method,
                context,
            )

            try:
                payload = method(
                    **kwargs
                )

                return {
                    "available": True,
                    "source": (
                        f"analytics_service.{name}"
                    ),
                    "data": payload,
                    "reason": None,
                }

            except TypeError as exc:
                if kwargs:
                    try:
                        payload = method()

                        return {
                            "available": True,
                            "source": (
                                f"analytics_service.{name}"
                            ),
                            "data": payload,
                            "reason": None,
                        }

                    except TypeError:
                        invocation_failures.append(
                            f"{name}: incompatible method signature"
                        )
                        continue

                    except Exception as fallback_exc:
                        return self._failure(
                            source=(
                                f"analytics_service.{name}"
                            ),
                            exc=fallback_exc,
                        )

                invocation_failures.append(
                    f"{name}: incompatible method signature"
                )
                continue

            except Exception as exc:
                return self._failure(
                    source=(
                        f"analytics_service.{name}"
                    ),
                    exc=exc,
                )

        if not found_method:
            return {
                "available": False,
                "source": None,
                "data": None,
                "reason": (
                    "Existing analytics service exposes no "
                    "compatible performance method"
                ),
            }

        return {
            "available": False,
            "source": None,
            "data": None,
            "reason": (
                "; ".join(
                    invocation_failures
                )
                if invocation_failures
                else (
                    "No compatible analytics performance "
                    "method could be invoked"
                )
            ),
        }

    def _supported_kwargs(
        self,
        method: Any,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        """
        Pass only arguments supported by the analytics method.

        This preserves compatibility with older AnalyticsService versions
        without guessing positional argument order.
        """

        try:
            from inspect import Parameter, signature

            method_signature = signature(
                method
            )

        except (
            TypeError,
            ValueError,
        ):
            return {}

        parameters = method_signature.parameters

        accepts_kwargs = any(
            parameter.kind
            == Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )

        kwargs: dict[str, Any] = {}

        for key, value in context.items():
            if value is None:
                continue

            if accepts_kwargs:
                kwargs[key] = value
                continue

            parameter = parameters.get(
                key
            )

            if parameter is None:
                continue

            if parameter.kind in (
                Parameter.POSITIONAL_OR_KEYWORD,
                Parameter.KEYWORD_ONLY,
            ):
                kwargs[key] = value

        return kwargs

    def _normalize_snapshot(
        self,
        payload: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(
            payload,
            Mapping,
        ):
            return None

        source = dict(payload)

        normalized: dict[str, Any] = {}

        self._copy_number(
            normalized,
            "total_pnl",
            source,
            "total_pnl",
            "net_pnl",
            "realized_pnl",
            "pnl",
        )

        self._copy_number(
            normalized,
            "realized_pnl",
            source,
            "realized_pnl",
            "closed_pnl",
        )

        self._copy_number(
            normalized,
            "unrealized_pnl",
            source,
            "unrealized_pnl",
            "open_pnl",
        )

        self._copy_number(
            normalized,
            "gross_profit",
            source,
            "gross_profit",
            "total_profit",
        )

        self._copy_number(
            normalized,
            "gross_loss",
            source,
            "gross_loss",
            "total_loss",
        )

        self._copy_number(
            normalized,
            "return_percent",
            source,
            "return_percent",
            "return_pct",
            "total_return_percent",
            "total_return_pct",
        )

        self._copy_number(
            normalized,
            "win_rate",
            source,
            "win_rate",
            "win_rate_percent",
            "winning_percentage",
        )

        self._copy_number(
            normalized,
            "profit_factor",
            source,
            "profit_factor",
        )

        self._copy_number(
            normalized,
            "average_win",
            source,
            "average_win",
            "avg_win",
        )

        self._copy_number(
            normalized,
            "average_loss",
            source,
            "average_loss",
            "avg_loss",
        )

        self._copy_number(
            normalized,
            "average_trade",
            source,
            "average_trade",
            "avg_trade",
            "average_pnl",
        )

        self._copy_number(
            normalized,
            "largest_win",
            source,
            "largest_win",
            "best_trade",
        )

        self._copy_number(
            normalized,
            "largest_loss",
            source,
            "largest_loss",
            "worst_trade",
        )

        self._copy_number(
            normalized,
            "max_drawdown",
            source,
            "max_drawdown",
            "maximum_drawdown",
        )

        self._copy_number(
            normalized,
            "max_drawdown_percent",
            source,
            "max_drawdown_percent",
            "max_drawdown_pct",
            "maximum_drawdown_percent",
        )

        self._copy_number(
            normalized,
            "sharpe_ratio",
            source,
            "sharpe_ratio",
            "sharpe",
        )

        self._copy_number(
            normalized,
            "sortino_ratio",
            source,
            "sortino_ratio",
            "sortino",
        )

        self._copy_number(
            normalized,
            "expectancy",
            source,
            "expectancy",
        )

        self._copy_number(
            normalized,
            "equity",
            source,
            "equity",
            "account_equity",
        )

        self._copy_number(
            normalized,
            "cash",
            source,
            "cash",
            "cash_balance",
        )

        self._copy_number(
            normalized,
            "buying_power",
            source,
            "buying_power",
        )

        self._copy_integer(
            normalized,
            "trade_count",
            source,
            "trade_count",
            "total_trades",
            "trades",
        )

        self._copy_integer(
            normalized,
            "winning_trades",
            source,
            "winning_trades",
            "wins",
        )

        self._copy_integer(
            normalized,
            "losing_trades",
            source,
            "losing_trades",
            "losses",
        )

        self._copy_integer(
            normalized,
            "open_positions",
            source,
            "open_positions",
            "position_count",
        )

        self._copy_value(
            normalized,
            "period_start",
            source,
            "period_start",
            "start",
            "start_date",
        )

        self._copy_value(
            normalized,
            "period_end",
            source,
            "period_end",
            "end",
            "end_date",
        )

        self._copy_value(
            normalized,
            "as_of",
            source,
            "as_of",
            "timestamp",
            "updated_at",
        )

        return normalized

    @classmethod
    def _copy_number(
        cls,
        target: dict[str, Any],
        target_key: str,
        source: Mapping[str, Any],
        *source_keys: str,
    ) -> None:
        value = cls._first_number(
            source,
            *source_keys,
        )

        if value is not None:
            target[target_key] = value

    @classmethod
    def _copy_integer(
        cls,
        target: dict[str, Any],
        target_key: str,
        source: Mapping[str, Any],
        *source_keys: str,
    ) -> None:
        for key in source_keys:
            if key not in source:
                continue

            raw = source.get(key)

            if isinstance(
                raw,
                bool,
            ):
                continue

            try:
                number = float(raw)
            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                continue

            if (
                not isfinite(number)
                or not number.is_integer()
            ):
                continue

            target[target_key] = int(
                number
            )
            return

    @staticmethod
    def _copy_value(
        target: dict[str, Any],
        target_key: str,
        source: Mapping[str, Any],
        *source_keys: str,
    ) -> None:
        for key in source_keys:
            if key not in source:
                continue

            value = source.get(key)

            if value is None:
                continue

            target[target_key] = value
            return

    @classmethod
    def _first_number(
        cls,
        source: Mapping[str, Any],
        *keys: str,
    ) -> float | None:
        for key in keys:
            if key not in source:
                continue

            value = cls._number(
                source.get(key)
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

    @classmethod
    def _context(
        cls,
        **values: Any,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}

        for key, value in values.items():
            if value is None:
                continue

            if key in {
                "start",
                "end",
            }:
                normalized = cls._normalize_datetime_input(
                    value
                )

                if normalized is not None:
                    context[key] = normalized

                continue

            if key == "source":
                normalized_source = str(
                    value
                ).strip().upper()

                if normalized_source:
                    context[key] = normalized_source

                continue

            if key in {
                "strategy",
                "asset_class",
            }:
                text = str(
                    value
                ).strip()

                if text:
                    context[key] = text

                continue

            context[key] = value

        return context

    @staticmethod
    def _normalize_datetime_input(
        value: Any,
    ) -> Any:
        if isinstance(
            value,
            datetime,
        ):
            return value

        if isinstance(
            value,
            date,
        ):
            return value

        if isinstance(
            value,
            str,
        ):
            text = value.strip()

            return text or None

        return value

    @staticmethod
    def _public_context(
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        output: dict[str, Any] = {}

        for key, value in context.items():
            if isinstance(
                value,
                datetime,
            ):
                output[key] = value.isoformat()

            elif isinstance(
                value,
                date,
            ):
                output[key] = value.isoformat()

            else:
                output[key] = value

        return output

    @staticmethod
    def _normalize_limit(
        value: Any,
    ) -> int:
        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "limit must be an integer"
            )

        try:
            parsed = int(
                value
            )
        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                "limit must be an integer"
            ) from exc

        if parsed <= 0:
            raise ValueError(
                "limit must be greater than zero"
            )

        return min(
            parsed,
            PerformanceService.MAX_RECENT_LIMIT,
        )

    @staticmethod
    def _failure(
        *,
        source: str,
        exc: Exception,
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

        return {
            "available": False,
            "source": source,
            "data": None,
            "reason": message,
            "error_type": (
                exc.__class__.__name__
            ),
        }

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()


performance_service = PerformanceService()


__all__ = [
    "PerformanceService",
    "performance_service",
]