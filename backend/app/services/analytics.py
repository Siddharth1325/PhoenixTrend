from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Mapping

from sqlalchemy import select

from ..db import SessionLocal, TradeRecord


class AnalyticsService:
    """
    PhoenixTrend persisted trading analytics.

    AnalyticsService is READ-ONLY.

    Authoritative data source
    -------------------------
    Persisted TradeRecord rows.

    Realized trading metrics are calculated only from records that contain
    persisted realized P&L. Missing P&L is never estimated.

    The service does not:

        - generate signals
        - select strategies
        - modify trades
        - execute orders
        - fabricate P&L
        - fabricate account equity
        - fabricate percentage returns
        - fabricate unrealized P&L
        - infer missing entry/exit prices
        - infer missing execution modes
        - infer missing asset classes

    Percentage portfolio return, Sharpe ratio and capital-normalized metrics
    require genuine account-equity/capital history and therefore remain
    unavailable from TradeRecord-only analytics.
    """

    MAX_RECENT_TRADES = 500
    MAX_EQUITY_POINTS = 5000

    # =========================================================================
    # SUMMARY
    # =========================================================================

    def summary(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        rows = self._filtered_trades(
            start=start,
            end=end,
            strategy=strategy,
            asset_type=asset_type,
            execution_mode=execution_mode,
            symbol=symbol,
        )

        realized = self._realized_rows(
            rows
        )

        metrics = self._metrics(
            realized
        )

        return {
            "total_trade_records": len(
                rows
            ),
            **metrics,
            "open_trade_records": sum(
                1
                for trade in rows
                if self._is_open_trade(
                    trade
                )
            ),
            "realized_trade_records": len(
                realized
            ),
            "unrealized_pnl": None,
            "total_return": None,
            "return_denominator_available": False,
            "source": "persisted trade_records",
            "filters": self._filter_view(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
        }

    # =========================================================================
    # STRATEGY PERFORMANCE
    # =========================================================================

    def by_strategy(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        return self._group_performance(
            rows,
            key_getter=lambda trade: (
                self._text(
                    getattr(
                        trade,
                        "strategy",
                        None,
                    )
                )
                or "Unknown"
            ),
            key_name="strategy",
        )

    def strategy(
        self,
        strategy_name: str,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any] | None:
        wanted = self._normalize_strategy_name(
            strategy_name
        )

        if not wanted:
            return None

        rows = self.by_strategy(
            start=start,
            end=end,
            asset_type=asset_type,
            execution_mode=execution_mode,
            symbol=symbol,
        )

        for row in rows:
            current = self._normalize_strategy_name(
                str(
                    row.get(
                        "strategy"
                    )
                    or ""
                )
            )

            if current == wanted:
                return row

        return None

    # =========================================================================
    # ASSET PERFORMANCE
    # =========================================================================

    def by_asset_type(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        return self._group_performance(
            rows,
            key_getter=lambda trade: (
                self._text(
                    getattr(
                        trade,
                        "asset_type",
                        None,
                    )
                )
                or "Unknown"
            ),
            key_name="asset_type",
        )

    # =========================================================================
    # SYMBOL PERFORMANCE
    # =========================================================================

    def by_symbol(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
            )
        )

        return self._group_performance(
            rows,
            key_getter=lambda trade: (
                self._text(
                    getattr(
                        trade,
                        "symbol",
                        None,
                    )
                )
                or "Unknown"
            ).upper(),
            key_name="symbol",
        )

    # =========================================================================
    # EXECUTION MODE PERFORMANCE
    # =========================================================================

    def by_execution_mode(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                symbol=symbol,
            )
        )

        return self._group_performance(
            rows,
            key_getter=lambda trade: (
                self._text(
                    getattr(
                        trade,
                        "execution_mode",
                        None,
                    )
                )
                or "Unknown"
            ),
            key_name="execution_mode",
        )

    # =========================================================================
    # AUTOMATION VS MANUAL
    # =========================================================================

    def automation_vs_manual(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        rows = self.by_execution_mode(
            start=start,
            end=end,
            strategy=strategy,
            asset_type=asset_type,
            symbol=symbol,
        )

        automatic = None
        manual = None
        other: list[dict[str, Any]] = []

        for row in rows:
            normalized = self._normalize_execution_mode(
                row.get(
                    "execution_mode"
                )
            )

            if normalized in {
                "automatic",
                "auto",
                "automation",
            }:
                automatic = row

            elif normalized in {
                "manual",
            }:
                manual = row

            else:
                other.append(
                    row
                )

        return {
            "automatic": automatic,
            "manual": manual,
            "other": other,
            "source": "persisted trade_records",
        }

    # =========================================================================
    # DAILY PERFORMANCE
    # =========================================================================

    def by_day(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        grouped: dict[
            str,
            list[TradeRecord],
        ] = defaultdict(
            list
        )

        for trade in rows:
            timestamp = self._performance_timestamp(
                trade
            )

            if timestamp is None:
                continue

            key = timestamp.date().isoformat()

            grouped[
                key
            ].append(
                trade
            )

        output: list[
            dict[str, Any]
        ] = []

        for day in sorted(
            grouped
        ):
            metrics = self._metrics(
                grouped[
                    day
                ]
            )

            output.append(
                {
                    "date": day,
                    **metrics,
                    "source": (
                        "persisted trade_records"
                    ),
                }
            )

        return output

    # =========================================================================
    # MONTHLY PERFORMANCE
    # =========================================================================

    def by_month(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        grouped: dict[
            str,
            list[TradeRecord],
        ] = defaultdict(
            list
        )

        for trade in rows:
            timestamp = self._performance_timestamp(
                trade
            )

            if timestamp is None:
                continue

            key = (
                f"{timestamp.year:04d}-"
                f"{timestamp.month:02d}"
            )

            grouped[
                key
            ].append(
                trade
            )

        output: list[
            dict[str, Any]
        ] = []

        for month in sorted(
            grouped
        ):
            metrics = self._metrics(
                grouped[
                    month
                ]
            )

            output.append(
                {
                    "month": month,
                    **metrics,
                    "source": (
                        "persisted trade_records"
                    ),
                }
            )

        return output

    # =========================================================================
    # EQUITY / CUMULATIVE REALIZED P&L CURVE
    # =========================================================================

    def equity_curve(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
        limit: int = MAX_EQUITY_POINTS,
    ) -> list[dict[str, Any]]:
        """
        Return a cumulative REALIZED-P&L curve.

        This is intentionally not named account-equity history because
        TradeRecord does not contain complete account equity history.
        """
        safe_limit = max(
            1,
            min(
                int(
                    limit
                ),
                self.MAX_EQUITY_POINTS,
            ),
        )

        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        rows = sorted(
            rows,
            key=lambda trade: (
                self._performance_timestamp(
                    trade
                )
                or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            ),
        )

        cumulative = 0.0

        output: list[
            dict[str, Any]
        ] = []

        for trade in rows[
            :safe_limit
        ]:
            pnl = self._pnl(
                trade
            )

            if pnl is None:
                continue

            cumulative += pnl

            timestamp = self._performance_timestamp(
                trade
            )

            output.append(
                {
                    "trade_id": getattr(
                        trade,
                        "id",
                        None,
                    ),
                    "symbol": getattr(
                        trade,
                        "symbol",
                        None,
                    ),
                    "strategy": getattr(
                        trade,
                        "strategy",
                        None,
                    ),
                    "execution_mode": getattr(
                        trade,
                        "execution_mode",
                        None,
                    ),
                    "timestamp": (
                        timestamp.isoformat()
                        if timestamp
                        else None
                    ),
                    "trade_pnl": round(
                        pnl,
                        2,
                    ),
                    "cumulative_realized_pnl": round(
                        cumulative,
                        2,
                    ),
                    "source": (
                        "persisted trade_records"
                    ),
                }
            )

        return output

    # =========================================================================
    # DRAWDOWN
    # =========================================================================

    def drawdown(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """
        Calculate drawdown on cumulative realized trade P&L.

        This is not account-equity drawdown. A genuine account-equity
        drawdown requires persisted account-equity history.
        """
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        rows = sorted(
            rows,
            key=lambda trade: (
                self._performance_timestamp(
                    trade
                )
                or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            ),
        )

        cumulative = 0.0
        peak = 0.0
        max_drawdown = 0.0

        current_drawdown = 0.0
        max_drawdown_start = None
        max_drawdown_end = None
        current_peak_time = None

        for trade in rows:
            pnl = self._pnl(
                trade
            )

            if pnl is None:
                continue

            timestamp = self._performance_timestamp(
                trade
            )

            cumulative += pnl

            if cumulative > peak:
                peak = cumulative
                current_peak_time = timestamp

            drawdown_value = (
                peak
                - cumulative
            )

            current_drawdown = drawdown_value

            if drawdown_value > max_drawdown:
                max_drawdown = drawdown_value
                max_drawdown_start = (
                    current_peak_time
                )
                max_drawdown_end = timestamp

        return {
            "max_realized_pnl_drawdown": round(
                max_drawdown,
                2,
            ),
            "current_realized_pnl_drawdown": round(
                current_drawdown,
                2,
            ),
            "max_drawdown_start": (
                max_drawdown_start.isoformat()
                if max_drawdown_start
                else None
            ),
            "max_drawdown_end": (
                max_drawdown_end.isoformat()
                if max_drawdown_end
                else None
            ),
            "account_equity_drawdown": None,
            "drawdown_percent": None,
            "source": (
                "cumulative persisted realized trade P&L"
            ),
        }

    # =========================================================================
    # STREAKS
    # =========================================================================

    def streaks(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        rows = sorted(
            rows,
            key=lambda trade: (
                self._performance_timestamp(
                    trade
                )
                or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            ),
        )

        longest_win = 0
        longest_loss = 0

        current_win = 0
        current_loss = 0

        for trade in rows:
            pnl = self._pnl(
                trade
            )

            if pnl is None:
                continue

            if pnl > 0:
                current_win += 1
                current_loss = 0

                longest_win = max(
                    longest_win,
                    current_win,
                )

            elif pnl < 0:
                current_loss += 1
                current_win = 0

                longest_loss = max(
                    longest_loss,
                    current_loss,
                )

            else:
                current_win = 0
                current_loss = 0

        return {
            "longest_win_streak": (
                longest_win
            ),
            "longest_loss_streak": (
                longest_loss
            ),
            "current_win_streak": (
                current_win
            ),
            "current_loss_streak": (
                current_loss
            ),
            "source": (
                "persisted trade_records"
            ),
        }

    # =========================================================================
    # DURATION ANALYTICS
    # =========================================================================

    def duration_stats(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        durations: list[
            tuple[TradeRecord, float]
        ] = []

        for trade in rows:
            opened_at = self._datetime(
                getattr(
                    trade,
                    "opened_at",
                    None,
                )
            )

            closed_at = self._datetime(
                getattr(
                    trade,
                    "closed_at",
                    None,
                )
            )

            if (
                opened_at is None
                or closed_at is None
                or closed_at < opened_at
            ):
                continue

            seconds = (
                closed_at
                - opened_at
            ).total_seconds()

            durations.append(
                (
                    trade,
                    seconds,
                )
            )

        if not durations:
            return {
                "trades_with_duration": 0,
                "average_seconds": None,
                "average_minutes": None,
                "average_hours": None,
                "median_seconds": None,
                "shortest_seconds": None,
                "longest_seconds": None,
                "average_winner_seconds": None,
                "average_loser_seconds": None,
                "source": (
                    "persisted opened_at/closed_at"
                ),
            }

        values = [
            seconds
            for _trade, seconds
            in durations
        ]

        sorted_values = sorted(
            values
        )

        median = self._median(
            sorted_values
        )

        winners = [
            seconds
            for trade, seconds
            in durations
            if (
                self._pnl(
                    trade
                )
                or 0.0
            )
            > 0
        ]

        losers = [
            seconds
            for trade, seconds
            in durations
            if (
                self._pnl(
                    trade
                )
                or 0.0
            )
            < 0
        ]

        average = (
            sum(
                values
            )
            / len(
                values
            )
        )

        return {
            "trades_with_duration": len(
                durations
            ),
            "average_seconds": round(
                average,
                2,
            ),
            "average_minutes": round(
                average / 60.0,
                2,
            ),
            "average_hours": round(
                average / 3600.0,
                2,
            ),
            "median_seconds": round(
                median,
                2,
            ),
            "shortest_seconds": round(
                min(
                    values
                ),
                2,
            ),
            "longest_seconds": round(
                max(
                    values
                ),
                2,
            ),
            "average_winner_seconds": (
                round(
                    sum(
                        winners
                    )
                    / len(
                        winners
                    ),
                    2,
                )
                if winners
                else None
            ),
            "average_loser_seconds": (
                round(
                    sum(
                        losers
                    )
                    / len(
                        losers
                    ),
                    2,
                )
                if losers
                else None
            ),
            "source": (
                "persisted opened_at/closed_at"
            ),
        }

    # =========================================================================
    # TIME ANALYTICS
    # =========================================================================

    def by_weekday(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        grouped: dict[
            int,
            list[TradeRecord],
        ] = defaultdict(
            list
        )

        for trade in rows:
            timestamp = self._performance_timestamp(
                trade
            )

            if timestamp is None:
                continue

            grouped[
                timestamp.weekday()
            ].append(
                trade
            )

        names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        output: list[
            dict[str, Any]
        ] = []

        for weekday in range(
            7
        ):
            trades = grouped.get(
                weekday
            )

            if not trades:
                continue

            output.append(
                {
                    "weekday": names[
                        weekday
                    ],
                    "weekday_index": weekday,
                    **self._metrics(
                        trades
                    ),
                    "source": (
                        "persisted trade_records"
                    ),
                }
            )

        return output

    def by_hour(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._realized_rows(
            self._filtered_trades(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            )
        )

        grouped: dict[
            int,
            list[TradeRecord],
        ] = defaultdict(
            list
        )

        for trade in rows:
            timestamp = self._performance_timestamp(
                trade
            )

            if timestamp is None:
                continue

            grouped[
                timestamp.hour
            ].append(
                trade
            )

        output: list[
            dict[str, Any]
        ] = []

        for hour in sorted(
            grouped
        ):
            output.append(
                {
                    "hour": hour,
                    "timezone": "UTC",
                    **self._metrics(
                        grouped[
                            hour
                        ]
                    ),
                    "source": (
                        "persisted trade_records"
                    ),
                }
            )

        return output

    # =========================================================================
    # RECENT TRADES
    # =========================================================================

    def recent_trades(
        self,
        limit: int = 50,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        safe_limit = max(
            1,
            min(
                int(
                    limit
                ),
                self.MAX_RECENT_TRADES,
            ),
        )

        rows = self._filtered_trades(
            start=start,
            end=end,
            strategy=strategy,
            asset_type=asset_type,
            execution_mode=execution_mode,
            symbol=symbol,
            status=status,
        )

        rows.sort(
            key=lambda trade: (
                self._datetime(
                    getattr(
                        trade,
                        "created_at",
                        None,
                    )
                )
                or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            ),
            reverse=True,
        )

        return [
            self._trade_view(
                trade
            )
            for trade
            in rows[
                :safe_limit
            ]
        ]

    # =========================================================================
    # COMPLETE DASHBOARD PAYLOAD
    # =========================================================================

    def dashboard(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
        recent_limit: int = 50,
    ) -> dict[str, Any]:
        return {
            "summary": self.summary(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "drawdown": self.drawdown(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "streaks": self.streaks(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "duration": self.duration_stats(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "by_strategy": self.by_strategy(
                start=start,
                end=end,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "by_asset_type": self.by_asset_type(
                start=start,
                end=end,
                strategy=strategy,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "by_execution_mode": (
                self.by_execution_mode(
                    start=start,
                    end=end,
                    strategy=strategy,
                    asset_type=asset_type,
                    symbol=symbol,
                )
            ),
            "automation_vs_manual": (
                self.automation_vs_manual(
                    start=start,
                    end=end,
                    strategy=strategy,
                    asset_type=asset_type,
                    symbol=symbol,
                )
            ),
            "daily": self.by_day(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "monthly": self.by_month(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "weekday": self.by_weekday(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "hourly": self.by_hour(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "equity_curve": self.equity_curve(
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "recent_trades": self.recent_trades(
                recent_limit,
                start=start,
                end=end,
                strategy=strategy,
                asset_type=asset_type,
                execution_mode=execution_mode,
                symbol=symbol,
            ),
            "source": "persisted trade_records",
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

    # =========================================================================
    # GROUP PERFORMANCE
    # =========================================================================

    def _group_performance(
        self,
        rows: Iterable[TradeRecord],
        *,
        key_getter: Callable[
            [TradeRecord],
            str,
        ],
        key_name: str,
    ) -> list[dict[str, Any]]:
        grouped: dict[
            str,
            list[TradeRecord],
        ] = defaultdict(
            list
        )

        for trade in rows:
            key = self._text(
                key_getter(
                    trade
                )
            )

            if not key:
                key = "Unknown"

            grouped[
                key
            ].append(
                trade
            )

        output: list[
            dict[str, Any]
        ] = []

        for key, trades in grouped.items():
            metrics = self._metrics(
                trades
            )

            output.append(
                {
                    key_name: key,
                    **metrics,
                    "total_return": None,
                    "source": (
                        "persisted trade_records"
                    ),
                }
            )

        output.sort(
            key=lambda item: (
                item.get(
                    "realized_pnl",
                    0.0,
                )
            ),
            reverse=True,
        )

        return output

    # =========================================================================
    # METRICS
    # =========================================================================

    def _metrics(
        self,
        trades: Iterable[TradeRecord],
    ) -> dict[str, Any]:
        rows = list(
            trades
        )

        pnl_values = [
            pnl
            for pnl in (
                self._pnl(
                    trade
                )
                for trade in rows
            )
            if pnl is not None
        ]

        wins = [
            pnl
            for pnl in pnl_values
            if pnl > 0
        ]

        losses = [
            pnl
            for pnl in pnl_values
            if pnl < 0
        ]

        breakeven = [
            pnl
            for pnl in pnl_values
            if pnl == 0
        ]

        realized_pnl = sum(
            pnl_values
        )

        gross_profit = sum(
            wins
        )

        gross_loss = abs(
            sum(
                losses
            )
        )

        win_rate = (
            len(
                wins
            )
            / len(
                pnl_values
            )
            * 100.0
            if pnl_values
            else 0.0
        )

        loss_rate = (
            len(
                losses
            )
            / len(
                pnl_values
            )
            * 100.0
            if pnl_values
            else 0.0
        )

        breakeven_rate = (
            len(
                breakeven
            )
            / len(
                pnl_values
            )
            * 100.0
            if pnl_values
            else 0.0
        )

        profit_factor = (
            gross_profit
            / gross_loss
            if gross_loss > 0
            else None
        )

        average_trade = (
            realized_pnl
            / len(
                pnl_values
            )
            if pnl_values
            else 0.0
        )

        average_win = (
            gross_profit
            / len(
                wins
            )
            if wins
            else 0.0
        )

        average_loss = (
            -gross_loss
            / len(
                losses
            )
            if losses
            else 0.0
        )

        largest_win = (
            max(
                wins
            )
            if wins
            else 0.0
        )

        largest_loss = (
            min(
                losses
            )
            if losses
            else 0.0
        )

        payoff_ratio = (
            average_win
            / abs(
                average_loss
            )
            if (
                wins
                and losses
                and average_loss != 0
            )
            else None
        )

        expectancy = (
            (
                (
                    len(
                        wins
                    )
                    / len(
                        pnl_values
                    )
                )
                * average_win
            )
            + (
                (
                    len(
                        losses
                    )
                    / len(
                        pnl_values
                    )
                )
                * average_loss
            )
            if pnl_values
            else 0.0
        )

        return {
            "trades": len(
                pnl_values
            ),
            "closed_trades": len(
                pnl_values
            ),
            "wins": len(
                wins
            ),
            "losses": len(
                losses
            ),
            "breakeven": len(
                breakeven
            ),
            "realized_pnl": round(
                realized_pnl,
                2,
            ),
            "gross_profit": round(
                gross_profit,
                2,
            ),
            "gross_loss": round(
                gross_loss,
                2,
            ),
            "win_rate": round(
                win_rate,
                2,
            ),
            "loss_rate": round(
                loss_rate,
                2,
            ),
            "breakeven_rate": round(
                breakeven_rate,
                2,
            ),
            "profit_factor": (
                round(
                    profit_factor,
                    4,
                )
                if profit_factor
                is not None
                else None
            ),
            "average_trade": round(
                average_trade,
                2,
            ),
            "average_win": round(
                average_win,
                2,
            ),
            "average_loss": round(
                average_loss,
                2,
            ),
            "largest_win": round(
                largest_win,
                2,
            ),
            "largest_loss": round(
                largest_loss,
                2,
            ),
            "payoff_ratio": (
                round(
                    payoff_ratio,
                    4,
                )
                if payoff_ratio
                is not None
                else None
            ),
            "expectancy": round(
                expectancy,
                2,
            ),
            "total_return": None,
        }

    # =========================================================================
    # DATABASE
    # =========================================================================

    @staticmethod
    def _trades() -> list[TradeRecord]:
        with SessionLocal() as session:
            return list(
                session.scalars(
                    select(
                        TradeRecord
                    )
                ).all()
            )

    # =========================================================================
    # FILTERING
    # =========================================================================

    def _filtered_trades(
        self,
        *,
        start: datetime | date | str | None = None,
        end: datetime | date | str | None = None,
        strategy: str | None = None,
        asset_type: str | None = None,
        execution_mode: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[TradeRecord]:
        rows = self._trades()

        start_dt = self._parse_boundary(
            start,
            end_of_day=False,
        )

        end_dt = self._parse_boundary(
            end,
            end_of_day=True,
        )

        wanted_strategy = (
            self._normalize_strategy_name(
                strategy
            )
            if strategy
            else None
        )

        wanted_asset = (
            self._normalize_text(
                asset_type
            )
            if asset_type
            else None
        )

        wanted_mode = (
            self._normalize_execution_mode(
                execution_mode
            )
            if execution_mode
            else None
        )

        wanted_symbol = (
            str(
                symbol
            )
            .strip()
            .upper()
            if symbol
            else None
        )

        wanted_status = (
            self._normalize_text(
                status
            )
            if status
            else None
        )

        output: list[
            TradeRecord
        ] = []

        for trade in rows:
            if wanted_strategy:
                current = (
                    self._normalize_strategy_name(
                        self._text(
                            getattr(
                                trade,
                                "strategy",
                                None,
                            )
                        )
                    )
                )

                if current != wanted_strategy:
                    continue

            if wanted_asset:
                current = self._normalize_text(
                    getattr(
                        trade,
                        "asset_type",
                        None,
                    )
                )

                if current != wanted_asset:
                    continue

            if wanted_mode:
                current = (
                    self._normalize_execution_mode(
                        getattr(
                            trade,
                            "execution_mode",
                            None,
                        )
                    )
                )

                if current != wanted_mode:
                    continue

            if wanted_symbol:
                current = str(
                    getattr(
                        trade,
                        "symbol",
                        None,
                    )
                    or ""
                ).strip().upper()

                if current != wanted_symbol:
                    continue

            if wanted_status:
                current = self._normalize_text(
                    getattr(
                        trade,
                        "status",
                        None,
                    )
                )

                if current != wanted_status:
                    continue

            timestamp = self._performance_timestamp(
                trade
            )

            if start_dt is not None:
                if (
                    timestamp is None
                    or timestamp < start_dt
                ):
                    continue

            if end_dt is not None:
                if (
                    timestamp is None
                    or timestamp > end_dt
                ):
                    continue

            output.append(
                trade
            )

        return output

    # =========================================================================
    # REALIZED ROWS
    # =========================================================================

    @classmethod
    def _realized_rows(
        cls,
        rows: Iterable[TradeRecord],
    ) -> list[TradeRecord]:
        return [
            trade
            for trade in rows
            if cls._pnl(
                trade
            )
            is not None
        ]

    # =========================================================================
    # TRADE CLASSIFICATION
    # =========================================================================

    @staticmethod
    def _is_open_trade(
        trade: TradeRecord,
    ) -> bool:
        if getattr(
            trade,
            "pnl",
            None,
        ) is not None:
            return False

        status = str(
            getattr(
                trade,
                "status",
                None,
            )
            or ""
        ).strip().lower()

        return status in {
            "open",
            "opened",
            "filled",
            "partially_filled",
            "partially-filled",
            "active",
        }

    # =========================================================================
    # TIMESTAMPS
    # =========================================================================

    @classmethod
    def _performance_timestamp(
        cls,
        trade: TradeRecord,
    ) -> datetime | None:
        for field in (
            "closed_at",
            "updated_at",
            "opened_at",
            "created_at",
        ):
            value = cls._datetime(
                getattr(
                    trade,
                    field,
                    None,
                )
            )

            if value is not None:
                return value

        return None

    @staticmethod
    def _datetime(
        value: Any,
    ) -> datetime | None:
        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            if value.tzinfo is None:
                return value.replace(
                    tzinfo=timezone.utc
                )

            return value.astimezone(
                timezone.utc
            )

        if isinstance(
            value,
            date,
        ):
            return datetime(
                value.year,
                value.month,
                value.day,
                tzinfo=timezone.utc,
            )

        if isinstance(
            value,
            str,
        ):
            text = value.strip()

            if not text:
                return None

            if text.endswith(
                "Z"
            ):
                text = (
                    text[:-1]
                    + "+00:00"
                )

            try:
                parsed = datetime.fromisoformat(
                    text
                )

            except ValueError:
                try:
                    parsed_date = date.fromisoformat(
                        text
                    )

                except ValueError:
                    return None

                return datetime(
                    parsed_date.year,
                    parsed_date.month,
                    parsed_date.day,
                    tzinfo=timezone.utc,
                )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        return None

    @classmethod
    def _parse_boundary(
        cls,
        value: datetime | date | str | None,
        *,
        end_of_day: bool,
    ) -> datetime | None:
        if value is None:
            return None

        if isinstance(
            value,
            datetime,
        ):
            parsed = cls._datetime(
                value
            )

            return parsed

        if isinstance(
            value,
            date,
        ):
            if end_of_day:
                return datetime(
                    value.year,
                    value.month,
                    value.day,
                    23,
                    59,
                    59,
                    999999,
                    tzinfo=timezone.utc,
                )

            return datetime(
                value.year,
                value.month,
                value.day,
                tzinfo=timezone.utc,
            )

        text = str(
            value
        ).strip()

        if not text:
            return None

        try:
            parsed_date = date.fromisoformat(
                text
            )

            if (
                len(
                    text
                )
                == 10
            ):
                if end_of_day:
                    return datetime(
                        parsed_date.year,
                        parsed_date.month,
                        parsed_date.day,
                        23,
                        59,
                        59,
                        999999,
                        tzinfo=timezone.utc,
                    )

                return datetime(
                    parsed_date.year,
                    parsed_date.month,
                    parsed_date.day,
                    tzinfo=timezone.utc,
                )

        except ValueError:
            pass

        return cls._datetime(
            text
        )

    # =========================================================================
    # PNL
    # =========================================================================

    @staticmethod
    def _pnl(
        trade: TradeRecord,
    ) -> float | None:
        value = getattr(
            trade,
            "pnl",
            None,
        )

        if value is None:
            return None

        try:
            result = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if result != result:
            return None

        if result in {
            float(
                "inf"
            ),
            float(
                "-inf"
            ),
        }:
            return None

        return result

    # =========================================================================
    # NORMALIZATION
    # =========================================================================

    @staticmethod
    def _text(
        value: Any,
    ) -> str:
        if value is None:
            return ""

        return str(
            value
        ).strip()

    @staticmethod
    def _normalize_text(
        value: Any,
    ) -> str:
        return (
            str(
                value
                or ""
            )
            .strip()
            .lower()
            .replace(
                "-",
                "_",
            )
            .replace(
                " ",
                "_",
            )
        )

    @staticmethod
    def _normalize_strategy_name(
        value: Any,
    ) -> str:
        """
        Normalize strategy names for matching only.

        Persisted strategy names are never changed.
        """
        return (
            str(
                value
                or ""
            )
            .strip()
            .lower()
            .replace(
                "-",
                "",
            )
            .replace(
                "_",
                "",
            )
            .replace(
                " ",
                "",
            )
        )

    @classmethod
    def _normalize_execution_mode(
        cls,
        value: Any,
    ) -> str:
        normalized = cls._normalize_text(
            value
        )

        aliases = {
            "auto": "automatic",
            "automation": "automatic",
            "automated": "automatic",
            "automatic": "automatic",
            "manual": "manual",
        }

        return aliases.get(
            normalized,
            normalized,
        )

    # =========================================================================
    # FILTER VIEW
    # =========================================================================

    @classmethod
    def _filter_view(
        cls,
        *,
        start: datetime | date | str | None,
        end: datetime | date | str | None,
        strategy: str | None,
        asset_type: str | None,
        execution_mode: str | None,
        symbol: str | None,
    ) -> dict[str, Any]:
        start_dt = cls._parse_boundary(
            start,
            end_of_day=False,
        )

        end_dt = cls._parse_boundary(
            end,
            end_of_day=True,
        )

        return {
            "start": (
                start_dt.isoformat()
                if start_dt
                else None
            ),
            "end": (
                end_dt.isoformat()
                if end_dt
                else None
            ),
            "strategy": strategy,
            "asset_type": asset_type,
            "execution_mode": (
                execution_mode
            ),
            "symbol": (
                str(
                    symbol
                ).strip().upper()
                if symbol
                else None
            ),
        }

    # =========================================================================
    # MEDIAN
    # =========================================================================

    @staticmethod
    def _median(
        values: list[float],
    ) -> float:
        if not values:
            return 0.0

        size = len(
            values
        )

        midpoint = (
            size
            // 2
        )

        if size % 2:
            return float(
                values[
                    midpoint
                ]
            )

        return (
            float(
                values[
                    midpoint - 1
                ]
            )
            + float(
                values[
                    midpoint
                ]
            )
        ) / 2.0

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    @staticmethod
    def _trade_view(
        trade: TradeRecord,
    ) -> dict[str, Any]:
        def iso(
            value: Any,
        ) -> str | None:
            if value is None:
                return None

            if isinstance(
                value,
                datetime,
            ):
                return value.isoformat()

            return str(
                value
            )

        return {
            "id": getattr(
                trade,
                "id",
                None,
            ),
            "intent_id": getattr(
                trade,
                "intent_id",
                None,
            ),
            "automation_id": getattr(
                trade,
                "automation_id",
                None,
            ),
            "broker": getattr(
                trade,
                "broker",
                None,
            ),
            "broker_order_id": getattr(
                trade,
                "broker_order_id",
                None,
            ),
            "exit_broker_order_id": getattr(
                trade,
                "exit_broker_order_id",
                None,
            ),
            "symbol": getattr(
                trade,
                "symbol",
                None,
            ),
            "asset_type": getattr(
                trade,
                "asset_type",
                None,
            ),
            "strategy": getattr(
                trade,
                "strategy",
                None,
            ),
            "execution_mode": getattr(
                trade,
                "execution_mode",
                None,
            ),
            "side": getattr(
                trade,
                "side",
                None,
            ),
            "qty": getattr(
                trade,
                "qty",
                None,
            ),
            "order_type": getattr(
                trade,
                "order_type",
                None,
            ),
            "time_in_force": getattr(
                trade,
                "time_in_force",
                None,
            ),
            "reference_price": getattr(
                trade,
                "reference_price",
                None,
            ),
            "entry_price": getattr(
                trade,
                "entry_price",
                None,
            ),
            "exit_price": getattr(
                trade,
                "exit_price",
                None,
            ),
            "stop": getattr(
                trade,
                "stop",
                None,
            ),
            "target": getattr(
                trade,
                "target",
                None,
            ),
            "max_loss": getattr(
                trade,
                "max_loss",
                None,
            ),
            "pnl": getattr(
                trade,
                "pnl",
                None,
            ),
            "status": getattr(
                trade,
                "status",
                None,
            ),
            "created_at": iso(
                getattr(
                    trade,
                    "created_at",
                    None,
                )
            ),
            "updated_at": iso(
                getattr(
                    trade,
                    "updated_at",
                    None,
                )
            ),
            "opened_at": iso(
                getattr(
                    trade,
                    "opened_at",
                    None,
                )
            ),
            "closed_at": iso(
                getattr(
                    trade,
                    "closed_at",
                    None,
                )
            ),
        }


analytics_service = AnalyticsService()