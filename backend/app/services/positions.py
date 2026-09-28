from __future__ import annotations

from math import isfinite
from threading import RLock
from typing import Any

from ..domain import Position, Side


class PositionEngine:
    """
    PhoenixTrend position monitoring service.

    Responsibilities:
        - track currently known positions
        - synchronize broker-confirmed positions
        - update market prices
        - evaluate stop loss
        - evaluate profit target
        - evaluate trailing stop
        - preserve favorable-price state across position refreshes
        - calculate unrealized P&L
        - calculate gross exposure
        - calculate long/short exposure
        - expose normalized position summaries

    PositionEngine does NOT:
        - create strategy signals
        - make trading decisions
        - submit broker orders
        - fabricate broker positions
        - fabricate market prices
        - assume missing stop/target values
        - close positions directly

    When an exit condition is triggered, the caller must create the
    appropriate TradeIntent and send it through the normal pipeline:

        Risk
          ↓
        Safety / Capability
          ↓
        Execution
          ↓
        Broker

    All monetary/exposure calculations are derived only from the supplied
    PhoenixTrend Position model.
    """

    EXIT_STOP = "STOP"
    EXIT_TARGET = "TARGET"
    EXIT_TRAILING_STOP = "TRAILING_STOP"
    EXIT_HOLD = "HOLD"

    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}

        # Most favorable observed price since monitoring began.
        #
        # LONG  -> highest observed price
        # SHORT -> lowest observed price
        self._favorable_prices: dict[str, float] = {}

        self._lock = RLock()

    # ============================================================
    # ADD
    # ============================================================

    def add(
        self,
        position: Position,
    ) -> Position:
        """
        Add a position to the in-memory monitor.

        This method is intended for a newly observed position. If a position
        with the same ID already exists, use ``upsert`` so favorable-price
        state is not accidentally reset.
        """

        validated = self._validate_position(
            position
        )

        position_id = self._position_id(
            validated
        )

        current_price = self._positive_price(
            validated.current_price
        )

        with self._lock:
            existing = self.positions.get(
                position_id
            )

            self.positions[
                position_id
            ] = validated

            if existing is None:
                self._favorable_prices[
                    position_id
                ] = current_price

            else:
                previous_favorable = (
                    self._favorable_prices.get(
                        position_id
                    )
                )

                self._favorable_prices[
                    position_id
                ] = self._preserve_favorable_price(
                    validated,
                    current_price=current_price,
                    previous_favorable=(
                        previous_favorable
                    ),
                )

        return validated

    # ============================================================
    # UPSERT
    # ============================================================

    def upsert(
        self,
        position: Position,
    ) -> Position:
        """
        Add or replace a position using broker-confirmed data.

        Favorable-price state is preserved when refreshing an existing
        position so repeated broker synchronization does not reset an active
        trailing stop.

        If the broker reports a materially different entry/side/quantity under
        the same position ID, the existing favorable price is retained only
        when it is still directionally valid for the refreshed position.
        """

        validated = self._validate_position(
            position
        )

        position_id = self._position_id(
            validated
        )

        current_price = self._positive_price(
            validated.current_price
        )

        with self._lock:
            previous = self.positions.get(
                position_id
            )

            previous_favorable = (
                self._favorable_prices.get(
                    position_id
                )
            )

            self.positions[
                position_id
            ] = validated

            if previous is None:
                favorable = current_price

            elif (
                previous.side
                != validated.side
            ):
                # A side reversal represents a new directional position.
                favorable = current_price

            else:
                favorable = (
                    self._preserve_favorable_price(
                        validated,
                        current_price=(
                            current_price
                        ),
                        previous_favorable=(
                            previous_favorable
                        ),
                    )
                )

            self._favorable_prices[
                position_id
            ] = favorable

        return validated

    # ============================================================
    # GET
    # ============================================================

    def get(
        self,
        position_id: str,
    ) -> Position:
        normalized_id = (
            self._normalize_position_id(
                position_id
            )
        )

        with self._lock:
            position = self.positions.get(
                normalized_id
            )

            if position is None:
                raise KeyError(
                    normalized_id
                )

            return position

    # ============================================================
    # EXISTS
    # ============================================================

    def exists(
        self,
        position_id: str,
    ) -> bool:
        normalized_id = (
            self._normalize_position_id(
                position_id
            )
        )

        with self._lock:
            return (
                normalized_id
                in self.positions
            )

    # ============================================================
    # FIND BY SYMBOL
    # ============================================================

    def find_by_symbol(
        self,
        symbol: str,
    ) -> list[Position]:
        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        with self._lock:
            return [
                position
                for position
                in self.positions.values()
                if self._normalize_symbol(
                    position.symbol
                )
                == normalized_symbol
            ]

    # ============================================================
    # REMOVE
    # ============================================================

    def remove(
        self,
        position_id: str,
    ) -> Position:
        normalized_id = (
            self._normalize_position_id(
                position_id
            )
        )

        with self._lock:
            position = self.positions.pop(
                normalized_id,
                None,
            )

            self._favorable_prices.pop(
                normalized_id,
                None,
            )

            if position is None:
                raise KeyError(
                    normalized_id
                )

            return position

    # ============================================================
    # DISCARD
    # ============================================================

    def discard(
        self,
        position_id: str,
    ) -> Position | None:
        normalized_id = (
            self._normalize_position_id(
                position_id
            )
        )

        with self._lock:
            position = self.positions.pop(
                normalized_id,
                None,
            )

            self._favorable_prices.pop(
                normalized_id,
                None,
            )

            return position

    # ============================================================
    # CLEAR
    # ============================================================

    def clear(
        self,
    ) -> None:
        """
        Clear the in-memory position monitor.

        This does NOT close broker positions and does NOT submit orders.
        """

        with self._lock:
            self.positions.clear()
            self._favorable_prices.clear()

    # ============================================================
    # LIST
    # ============================================================

    def list(
        self,
    ) -> list[dict[str, Any]]:
        with self._lock:
            positions = list(
                self.positions.values()
            )

            favorable_prices = dict(
                self._favorable_prices
            )

            return [
                self._view_locked_snapshot(
                    position,
                    favorable_prices.get(
                        self._position_id(
                            position
                        )
                    ),
                )
                for position
                in positions
            ]

    # ============================================================
    # COUNT
    # ============================================================

    def count(
        self,
    ) -> int:
        with self._lock:
            return len(
                self.positions
            )

    # ============================================================
    # UPDATE PRICE
    # ============================================================

    def update_price(
        self,
        position_id: str,
        new_price: float,
    ) -> dict[str, Any]:
        normalized_id = (
            self._normalize_position_id(
                position_id
            )
        )

        price = self._positive_price(
            new_price
        )

        with self._lock:
            position = self.positions.get(
                normalized_id
            )

            if position is None:
                raise KeyError(
                    normalized_id
                )

            position.current_price = price

            self._update_favorable_price(
                position,
                price,
            )

            return self._view(
                position
            )

    # ============================================================
    # UPDATE PRICE BY SYMBOL
    # ============================================================

    def update_symbol_price(
        self,
        symbol: str,
        new_price: float,
    ) -> list[dict[str, Any]]:
        """
        Update every monitored position matching a symbol.
        """

        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        price = self._positive_price(
            new_price
        )

        output: list[
            dict[str, Any]
        ] = []

        with self._lock:
            positions = [
                position
                for position
                in self.positions.values()
                if self._normalize_symbol(
                    position.symbol
                )
                == normalized_symbol
            ]

            for position in positions:
                position.current_price = (
                    price
                )

                self._update_favorable_price(
                    position,
                    price,
                )

                output.append(
                    self._view(
                        position
                    )
                )

        return output

    # ============================================================
    # UPDATE PRICES
    # ============================================================

    def update_prices(
        self,
        prices: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Update monitored positions from a symbol -> price mapping.

        Only supplied symbols are touched. Missing symbols are not assigned a
        fallback price.
        """

        if not isinstance(
            prices,
            dict,
        ):
            raise TypeError(
                "prices must be a dictionary"
            )

        normalized_prices: dict[
            str,
            float,
        ] = {}

        for symbol, value in (
            prices.items()
        ):
            normalized_symbol = (
                self._normalize_symbol(
                    symbol
                )
            )

            normalized_prices[
                normalized_symbol
            ] = self._positive_price(
                value
            )

        updated: list[
            dict[str, Any]
        ] = []

        with self._lock:
            for position in (
                self.positions.values()
            ):
                symbol = (
                    self._normalize_symbol(
                        position.symbol
                    )
                )

                price = (
                    normalized_prices.get(
                        symbol
                    )
                )

                if price is None:
                    continue

                position.current_price = (
                    price
                )

                self._update_favorable_price(
                    position,
                    price,
                )

                updated.append(
                    self._view(
                        position
                    )
                )

        return updated

    # ============================================================
    # EXIT EVALUATION
    # ============================================================

    def evaluate_exit(
        self,
        position: Position,
        new_price: float,
    ) -> str:
        """
        Evaluate whether a position has reached an exit condition.

        Returns:
            STOP
            TARGET
            TRAILING_STOP
            HOLD

        This method does NOT place an order.

        Static stop/target levels are evaluated before the trailing stop.
        Favorable-price state is updated using the newly observed price before
        trailing-stop evaluation.
        """

        validated = self._validate_position(
            position
        )

        price = self._positive_price(
            new_price
        )

        position_id = self._position_id(
            validated
        )

        with self._lock:
            side = validated.side

            stop = self._optional_positive_price(
                getattr(
                    validated,
                    "stop",
                    None,
                ),
                field_name="stop",
            )

            target = self._optional_positive_price(
                getattr(
                    validated,
                    "target",
                    None,
                ),
                field_name="target",
            )

            # ====================================================
            # STATIC STOP / TARGET — LONG
            # ====================================================

            if side == Side.BUY:
                if (
                    stop is not None
                    and price <= stop
                ):
                    validated.current_price = (
                        price
                    )

                    self._update_favorable_price(
                        validated,
                        price,
                    )

                    return self.EXIT_STOP

                if (
                    target is not None
                    and price >= target
                ):
                    validated.current_price = (
                        price
                    )

                    self._update_favorable_price(
                        validated,
                        price,
                    )

                    return self.EXIT_TARGET

            # ====================================================
            # STATIC STOP / TARGET — SHORT
            # ====================================================

            elif side == Side.SELL:
                if (
                    stop is not None
                    and price >= stop
                ):
                    validated.current_price = (
                        price
                    )

                    self._update_favorable_price(
                        validated,
                        price,
                    )

                    return self.EXIT_STOP

                if (
                    target is not None
                    and price <= target
                ):
                    validated.current_price = (
                        price
                    )

                    self._update_favorable_price(
                        validated,
                        price,
                    )

                    return self.EXIT_TARGET

            else:
                raise ValueError(
                    "Position side must be BUY or SELL"
                )

            # ====================================================
            # UPDATE FAVORABLE PRICE
            # ====================================================

            self._update_favorable_price(
                validated,
                price,
            )

            favorable_price = (
                self._favorable_prices.get(
                    position_id
                )
            )

            if favorable_price is None:
                favorable_price = price

                self._favorable_prices[
                    position_id
                ] = price

            # ====================================================
            # TRAILING STOP
            # ====================================================

            trailing_pct = (
                self._trailing_percent(
                    getattr(
                        validated,
                        "trailing_pct",
                        None,
                    )
                )
            )

            if trailing_pct is not None:
                if side == Side.BUY:
                    trailing_stop = (
                        favorable_price
                        * (
                            1.0
                            - trailing_pct
                        )
                    )

                    if (
                        price
                        <= trailing_stop
                    ):
                        validated.current_price = (
                            price
                        )

                        return (
                            self.EXIT_TRAILING_STOP
                        )

                elif side == Side.SELL:
                    trailing_stop = (
                        favorable_price
                        * (
                            1.0
                            + trailing_pct
                        )
                    )

                    if (
                        price
                        >= trailing_stop
                    ):
                        validated.current_price = (
                            price
                        )

                        return (
                            self.EXIT_TRAILING_STOP
                        )

            validated.current_price = price

            return self.EXIT_HOLD

    # ============================================================
    # EVALUATE POSITION BY ID
    # ============================================================

    def evaluate_position(
        self,
        position_id: str,
        new_price: float,
    ) -> dict[str, Any]:
        """
        Evaluate one monitored position and return both the resulting action
        and current normalized position view.
        """

        normalized_id = (
            self._normalize_position_id(
                position_id
            )
        )

        price = self._positive_price(
            new_price
        )

        with self._lock:
            position = self.positions.get(
                normalized_id
            )

            if position is None:
                raise KeyError(
                    normalized_id
                )

            action = self.evaluate_exit(
                position,
                price,
            )

            return {
                "position_id": (
                    normalized_id
                ),
                "symbol": (
                    self._normalize_symbol(
                        position.symbol
                    )
                ),
                "exit_action": action,
                "position": (
                    self._view(
                        position
                    )
                ),
            }

    # ============================================================
    # EVALUATE SYMBOL
    # ============================================================

    def evaluate_symbol(
        self,
        symbol: str,
        new_price: float,
    ) -> list[dict[str, Any]]:
        normalized_symbol = (
            self._normalize_symbol(
                symbol
            )
        )

        price = self._positive_price(
            new_price
        )

        output: list[
            dict[str, Any]
        ] = []

        with self._lock:
            matching = [
                position
                for position
                in self.positions.values()
                if self._normalize_symbol(
                    position.symbol
                )
                == normalized_symbol
            ]

            for position in matching:
                action = (
                    self.evaluate_exit(
                        position,
                        price,
                    )
                )

                output.append(
                    {
                        "position_id": (
                            self._position_id(
                                position
                            )
                        ),
                        "symbol": (
                            normalized_symbol
                        ),
                        "exit_action": (
                            action
                        ),
                        "position": (
                            self._view(
                                position
                            )
                        ),
                    }
                )

        return output

    # ============================================================
    # FAVORABLE PRICE
    # ============================================================

    def favorable_price(
        self,
        position_id: str,
    ) -> float | None:
        normalized_id = (
            self._normalize_position_id(
                position_id
            )
        )

        with self._lock:
            return self._favorable_prices.get(
                normalized_id
            )

    # ============================================================
    # UPDATE FAVORABLE PRICE
    # ============================================================

    def _update_favorable_price(
        self,
        position: Position,
        price: float,
    ) -> None:
        position_id = self._position_id(
            position
        )

        current = (
            self._favorable_prices.get(
                position_id
            )
        )

        if current is None:
            current = self._positive_price(
                position.current_price
            )

        price = self._positive_price(
            price
        )

        if position.side == Side.BUY:
            self._favorable_prices[
                position_id
            ] = max(
                current,
                price,
            )

        elif position.side == Side.SELL:
            self._favorable_prices[
                position_id
            ] = min(
                current,
                price,
            )

        else:
            raise ValueError(
                "Position side must be BUY or SELL"
            )

    # ============================================================
    # PRESERVE FAVORABLE PRICE
    # ============================================================

    def _preserve_favorable_price(
        self,
        position: Position,
        *,
        current_price: float,
        previous_favorable: float | None,
    ) -> float:
        current_price = self._positive_price(
            current_price
        )

        if previous_favorable is None:
            return current_price

        previous = self._positive_price(
            previous_favorable
        )

        if position.side == Side.BUY:
            return max(
                previous,
                current_price,
            )

        if position.side == Side.SELL:
            return min(
                previous,
                current_price,
            )

        raise ValueError(
            "Position side must be BUY or SELL"
        )

    # ============================================================
    # TRAILING STOP PRICE
    # ============================================================

    def trailing_stop_price(
        self,
        position: Position,
    ) -> float | None:
        validated = self._validate_position(
            position
        )

        trailing_pct = (
            self._trailing_percent(
                getattr(
                    validated,
                    "trailing_pct",
                    None,
                )
            )
        )

        if trailing_pct is None:
            return None

        position_id = self._position_id(
            validated
        )

        with self._lock:
            favorable = (
                self._favorable_prices.get(
                    position_id
                )
            )

            if favorable is None:
                favorable = (
                    self._positive_price(
                        validated.current_price
                    )
                )

            if validated.side == Side.BUY:
                return (
                    favorable
                    * (
                        1.0
                        - trailing_pct
                    )
                )

            if validated.side == Side.SELL:
                return (
                    favorable
                    * (
                        1.0
                        + trailing_pct
                    )
                )

        raise ValueError(
            "Position side must be BUY or SELL"
        )

    # ============================================================
    # UNREALIZED P&L
    # ============================================================

    @classmethod
    def unrealized_pnl(
        cls,
        position: Position,
    ) -> float:
        """
        Calculate unrealized P&L from PhoenixTrend's normalized Position model.

        Position uses ``avg_entry`` rather than ``entry_price``.
        """

        if position is None:
            raise ValueError(
                "Position is required"
            )

        entry_price = cls._positive_price(
            position.avg_entry
        )

        current_price = (
            cls._positive_price(
                position.current_price
            )
        )

        quantity = cls._positive_quantity(
            position.qty
        )

        if position.side == Side.BUY:
            value = (
                current_price
                - entry_price
            ) * quantity

        elif position.side == Side.SELL:
            value = (
                entry_price
                - current_price
            ) * quantity

        else:
            raise ValueError(
                "Position side must be BUY or SELL"
            )

        if not isfinite(
            value
        ):
            raise ValueError(
                "Calculated unrealized P&L is not finite"
            )

        return value

    # ============================================================
    # UNREALIZED P&L PERCENT
    # ============================================================

    @classmethod
    def unrealized_pnl_percent(
        cls,
        position: Position,
    ) -> float:
        entry_price = cls._positive_price(
            position.avg_entry
        )

        current_price = (
            cls._positive_price(
                position.current_price
            )
        )

        if position.side == Side.BUY:
            value = (
                (
                    current_price
                    - entry_price
                )
                / entry_price
            )

        elif position.side == Side.SELL:
            value = (
                (
                    entry_price
                    - current_price
                )
                / entry_price
            )

        else:
            raise ValueError(
                "Position side must be BUY or SELL"
            )

        if not isfinite(
            value
        ):
            raise ValueError(
                "Calculated unrealized P&L percent is not finite"
            )

        return value

    # ============================================================
    # POSITION MARKET VALUE
    # ============================================================

    @classmethod
    def market_value(
        cls,
        position: Position,
    ) -> float:
        if position is None:
            raise ValueError(
                "Position is required"
            )

        current_price = (
            cls._positive_price(
                position.current_price
            )
        )

        quantity = cls._positive_quantity(
            position.qty
        )

        value = abs(
            current_price
            * quantity
        )

        if not isfinite(
            value
        ):
            raise ValueError(
                "Calculated market value is not finite"
            )

        return value

    # ============================================================
    # POSITION COST BASIS
    # ============================================================

    @classmethod
    def cost_basis(
        cls,
        position: Position,
    ) -> float:
        if position is None:
            raise ValueError(
                "Position is required"
            )

        entry = cls._positive_price(
            position.avg_entry
        )

        quantity = cls._positive_quantity(
            position.qty
        )

        value = abs(
            entry
            * quantity
        )

        if not isfinite(
            value
        ):
            raise ValueError(
                "Calculated cost basis is not finite"
            )

        return value

    # ============================================================
    # TOTAL UNREALIZED P&L
    # ============================================================

    def total_unrealized_pnl(
        self,
    ) -> float:
        with self._lock:
            positions = list(
                self.positions.values()
            )

            total = sum(
                self.unrealized_pnl(
                    position
                )
                for position
                in positions
            )

        if not isfinite(
            total
        ):
            raise ValueError(
                "Total unrealized P&L is not finite"
            )

        return total

    # ============================================================
    # GROSS EXPOSURE
    # ============================================================

    def gross_exposure(
        self,
    ) -> float:
        """
        Absolute market exposure of monitored positions.
        """

        with self._lock:
            positions = list(
                self.positions.values()
            )

            total = sum(
                self.market_value(
                    position
                )
                for position
                in positions
            )

        if not isfinite(
            total
        ):
            raise ValueError(
                "Gross exposure is not finite"
            )

        return total

    # ============================================================
    # LONG EXPOSURE
    # ============================================================

    def long_exposure(
        self,
    ) -> float:
        with self._lock:
            positions = list(
                self.positions.values()
            )

            total = sum(
                self.market_value(
                    position
                )
                for position
                in positions
                if position.side
                == Side.BUY
            )

        if not isfinite(
            total
        ):
            raise ValueError(
                "Long exposure is not finite"
            )

        return total

    # ============================================================
    # SHORT EXPOSURE
    # ============================================================

    def short_exposure(
        self,
    ) -> float:
        with self._lock:
            positions = list(
                self.positions.values()
            )

            total = sum(
                self.market_value(
                    position
                )
                for position
                in positions
                if position.side
                == Side.SELL
            )

        if not isfinite(
            total
        ):
            raise ValueError(
                "Short exposure is not finite"
            )

        return total

    # ============================================================
    # NET EXPOSURE
    # ============================================================

    def net_exposure(
        self,
    ) -> float:
        with self._lock:
            positions = list(
                self.positions.values()
            )

            total = 0.0

            for position in positions:
                value = self.market_value(
                    position
                )

                if position.side == Side.BUY:
                    total += value

                elif position.side == Side.SELL:
                    total -= value

                else:
                    raise ValueError(
                        "Position side must be BUY or SELL"
                    )

        if not isfinite(
            total
        ):
            raise ValueError(
                "Net exposure is not finite"
            )

        return total

    # ============================================================
    # SUMMARY
    # ============================================================

    def summary(
        self,
    ) -> dict[str, Any]:
        """
        Return values derived only from currently monitored PhoenixTrend
        positions.

        These values are not a substitute for broker account data.
        """

        with self._lock:
            positions = list(
                self.positions.values()
            )

            open_positions = len(
                positions
            )

            gross_exposure = 0.0
            long_exposure = 0.0
            short_exposure = 0.0
            unrealized_pnl = 0.0

            for position in positions:
                market_value = (
                    self.market_value(
                        position
                    )
                )

                pnl = self.unrealized_pnl(
                    position
                )

                gross_exposure += (
                    market_value
                )

                unrealized_pnl += pnl

                if position.side == Side.BUY:
                    long_exposure += (
                        market_value
                    )

                elif position.side == Side.SELL:
                    short_exposure += (
                        market_value
                    )

                else:
                    raise ValueError(
                        "Position side must be BUY or SELL"
                    )

            net_exposure = (
                long_exposure
                - short_exposure
            )

            values = (
                gross_exposure,
                long_exposure,
                short_exposure,
                net_exposure,
                unrealized_pnl,
            )

            if not all(
                isfinite(value)
                for value
                in values
            ):
                raise ValueError(
                    "Position summary contains non-finite values"
                )

            return {
                "open_positions": (
                    open_positions
                ),
                "gross_exposure": (
                    gross_exposure
                ),
                "long_exposure": (
                    long_exposure
                ),
                "short_exposure": (
                    short_exposure
                ),
                "net_exposure": (
                    net_exposure
                ),
                "unrealized_pnl": (
                    unrealized_pnl
                ),
            }

    # ============================================================
    # VIEW
    # ============================================================

    def _view(
        self,
        position: Position,
    ) -> dict[str, Any]:
        position_id = self._position_id(
            position
        )

        favorable_price = (
            self._favorable_prices.get(
                position_id
            )
        )

        return self._view_locked_snapshot(
            position,
            favorable_price,
        )

    # ============================================================
    # VIEW SNAPSHOT
    # ============================================================

    def _view_locked_snapshot(
        self,
        position: Position,
        favorable_price: float | None,
    ) -> dict[str, Any]:
        data = self._model_dump(
            position
        )

        data[
            "unrealized_pnl"
        ] = self.unrealized_pnl(
            position
        )

        data[
            "unrealized_pnl_percent"
        ] = self.unrealized_pnl_percent(
            position
        )

        data[
            "market_value"
        ] = self.market_value(
            position
        )

        data[
            "cost_basis"
        ] = self.cost_basis(
            position
        )

        current_price = (
            self._positive_price(
                position.current_price
            )
        )

        if favorable_price is None:
            favorable_price = current_price

        else:
            favorable_price = (
                self._positive_price(
                    favorable_price
                )
            )

        data[
            "favorable_price"
        ] = favorable_price

        trailing_price = None

        trailing_pct = (
            self._trailing_percent(
                getattr(
                    position,
                    "trailing_pct",
                    None,
                )
            )
        )

        if trailing_pct is not None:
            if position.side == Side.BUY:
                trailing_price = (
                    favorable_price
                    * (
                        1.0
                        - trailing_pct
                    )
                )

            elif position.side == Side.SELL:
                trailing_price = (
                    favorable_price
                    * (
                        1.0
                        + trailing_pct
                    )
                )

            else:
                raise ValueError(
                    "Position side must be BUY or SELL"
                )

        data[
            "trailing_stop_price"
        ] = trailing_price

        return data

    # ============================================================
    # MODEL DUMP
    # ============================================================

    @staticmethod
    def _model_dump(
        position: Position,
    ) -> dict[str, Any]:
        model_dump = getattr(
            position,
            "model_dump",
            None,
        )

        if callable(
            model_dump
        ):
            try:
                data = model_dump(
                    mode="json"
                )

            except TypeError:
                data = model_dump()

            if isinstance(
                data,
                dict,
            ):
                return dict(
                    data
                )

        dict_method = getattr(
            position,
            "dict",
            None,
        )

        if callable(
            dict_method
        ):
            data = dict_method()

            if isinstance(
                data,
                dict,
            ):
                return dict(
                    data
                )

        raw = getattr(
            position,
            "__dict__",
            None,
        )

        if isinstance(
            raw,
            dict,
        ):
            return {
                key: value
                for key, value
                in raw.items()
                if not str(
                    key
                ).startswith("_")
            }

        raise TypeError(
            "Position does not expose a serializable representation"
        )

    # ============================================================
    # POSITION VALIDATION
    # ============================================================

    @classmethod
    def _validate_position(
        cls,
        position: Position,
    ) -> Position:
        if position is None:
            raise ValueError(
                "Position is required"
            )

        cls._position_id(
            position
        )

        cls._normalize_symbol(
            position.symbol
        )

        cls._positive_quantity(
            position.qty
        )

        cls._positive_price(
            position.avg_entry
        )

        cls._positive_price(
            position.current_price
        )

        if position.side not in {
            Side.BUY,
            Side.SELL,
        }:
            raise ValueError(
                "Position side must be BUY or SELL"
            )

        cls._optional_positive_price(
            getattr(
                position,
                "stop",
                None,
            ),
            field_name="stop",
        )

        cls._optional_positive_price(
            getattr(
                position,
                "target",
                None,
            ),
            field_name="target",
        )

        cls._trailing_percent(
            getattr(
                position,
                "trailing_pct",
                None,
            )
        )

        return position

    # ============================================================
    # POSITION ID
    # ============================================================

    @classmethod
    def _position_id(
        cls,
        position: Position,
    ) -> str:
        if position is None:
            raise ValueError(
                "Position is required"
            )

        value = getattr(
            position,
            "position_id",
            None,
        )

        return cls._normalize_position_id(
            value
        )

    # ============================================================
    # POSITION ID NORMALIZATION
    # ============================================================

    @staticmethod
    def _normalize_position_id(
        value: Any,
    ) -> str:
        if value is None:
            raise ValueError(
                "Position ID is required"
            )

        normalized = str(
            value
        ).strip()

        if not normalized:
            raise ValueError(
                "Position ID is required"
            )

        if len(
            normalized
        ) > 256:
            raise ValueError(
                "Position ID is invalid"
            )

        return normalized

    # ============================================================
    # SYMBOL NORMALIZATION
    # ============================================================

    @staticmethod
    def _normalize_symbol(
        value: Any,
    ) -> str:
        if value is None:
            raise ValueError(
                "Symbol is required"
            )

        normalized = str(
            value
        ).strip().upper()

        if not normalized:
            raise ValueError(
                "Symbol is required"
            )

        if len(
            normalized
        ) > 64:
            raise ValueError(
                "Symbol is invalid"
            )

        allowed = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "0123456789"
            ".-/_:"
        )

        if any(
            character not in allowed
            for character
            in normalized
        ):
            raise ValueError(
                "Symbol is invalid"
            )

        return normalized

    # ============================================================
    # POSITIVE PRICE
    # ============================================================

    @staticmethod
    def _positive_price(
        value: Any,
    ) -> float:
        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "Price must be numeric"
            )

        try:
            price = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                "Price must be numeric"
            ) from exc

        if not isfinite(
            price
        ):
            raise ValueError(
                "Price must be finite"
            )

        if price <= 0:
            raise ValueError(
                "Price must be greater than zero"
            )

        return price

    # ============================================================
    # OPTIONAL POSITIVE PRICE
    # ============================================================

    @classmethod
    def _optional_positive_price(
        cls,
        value: Any,
        *,
        field_name: str,
    ) -> float | None:
        if value is None:
            return None

        try:
            return cls._positive_price(
                value
            )

        except ValueError as exc:
            raise ValueError(
                f"{field_name} must be a finite value greater than zero"
            ) from exc

    # ============================================================
    # POSITIVE QUANTITY
    # ============================================================

    @staticmethod
    def _positive_quantity(
        value: Any,
    ) -> float:
        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "Position quantity must be numeric"
            )

        try:
            quantity = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                "Position quantity must be numeric"
            ) from exc

        if not isfinite(
            quantity
        ):
            raise ValueError(
                "Position quantity must be finite"
            )

        if quantity <= 0:
            raise ValueError(
                "Position quantity must be greater than zero"
            )

        return quantity

    # ============================================================
    # TRAILING PERCENT
    # ============================================================

    @staticmethod
    def _trailing_percent(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(
            value,
            bool,
        ):
            raise ValueError(
                "trailing_pct must be numeric"
            )

        try:
            trailing_pct = float(
                value
            )

        except (
            TypeError,
            ValueError,
            OverflowError,
        ) as exc:
            raise ValueError(
                "trailing_pct must be numeric"
            ) from exc

        if not isfinite(
            trailing_pct
        ):
            raise ValueError(
                "trailing_pct must be finite"
            )

        if not (
            0.0
            < trailing_pct
            < 1.0
        ):
            raise ValueError(
                "trailing_pct must be between 0 and 1"
            )

        return trailing_pct


position_engine = PositionEngine()


__all__ = [
    "PositionEngine",
    "position_engine",
]