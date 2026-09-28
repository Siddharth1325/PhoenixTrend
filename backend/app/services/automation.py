from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from ..broker import alpaca_broker
from ..db import AutomationAssetConfiguration, SessionLocal
from ..domain import AccountState, ExecutionMode
from ..engines.automatic_engine import AutomaticEngine
from ..engines.strategy_picker import StrategyPicker
from .audit import audit
from .live_market import live_market_service


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Automation:
    id: str
    name: str
    strategy: str | None = None
    symbols: list[str] = field(default_factory=list)
    mode: ExecutionMode = ExecutionMode.AUTOMATIC
    enabled: bool = False
    entries_paused: bool = False
    auto_select_strategy: bool = True
    max_position_value: float = 2500.0
    asset_class: str = "stocks"
    trading_style: str = "intraday"
    capital_allocation: float | None = None
    max_daily_loss: float | None = None
    max_open_positions: int | None = None
    allow_long: bool = True
    allow_short: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass
class AutomationRuntime:
    automation_id: str
    state: str = "STOPPED"
    started_at: str | None = None
    stopped_at: str | None = None
    last_cycle_at: str | None = None
    last_symbol: str | None = None
    last_action: str | None = None
    last_strategy: str | None = None
    last_execution_state: str | None = None
    last_error: str | None = None
    cycles: int = 0
    opportunities: int = 0
    orders_requested: int = 0
    live_symbols: dict[str, dict[str, Any]] = field(default_factory=dict)


class AutomationEngine:
    """
    PhoenixTrend automation orchestration service.

    IMPORTANT:
    Construction of this service must not access the database because the
    module-level singleton is created while Python imports application
    modules. Database initialization happens later through db.init_db().

    initialize_database_state() must therefore be called after init_db().

    Asset-section OFF semantics:

        * blocks discovery/new entries immediately
        * does not liquidate positions
        * does not represent existing positions as closed
        * existing positions remain the responsibility of the shared
          position-monitor/risk/execution infrastructure

    Automatic order path:

        live provider event
            -> AutomaticEngine
            -> DecisionEngine
            -> MarketSafety
            -> RiskEngine
            -> ExecutionService
            -> broker
    """

    LIVE_TIMEFRAME = "1M"
    LIVE_FEED = "iex"

    ASSET_SECTIONS = (
        "stocks",
        "options",
        "crypto",
        "etfs",
        "forex",
        "bonds",
    )

    def __init__(self) -> None:
        self.items: dict[str, Automation] = {}

        self.strategy_picker = StrategyPicker()

        self._lock = RLock()
        self._runtime_lock = RLock()

        self._runtimes: dict[str, AutomationRuntime] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._stop_events: dict[str, asyncio.Event] = {}
        self._symbol_tasks: dict[str, dict[str, asyncio.Task[Any]]] = {}

        # Never touch PostgreSQL/SQLite during module import.
        self._database_initialized = False

        # Master automation-engine state is independent from the number of
        # currently running automation tasks. This lets the UI keep the
        # engine armed/running even when no asset sections or automations are
        # enabled yet.
        self._master_enabled = False
        self._emergency_stop = False

    # ==================================================================
    # DATABASE INITIALIZATION
    # ==================================================================

    def initialize_database_state(self) -> None:
        """
        Initialize persistent automation section state.

        This must be invoked only after db.init_db() has created/migrated
        the PhoenixTrend schema.

        Safe to call repeatedly.
        """

        with self._lock:
            if self._database_initialized:
                return

            self._ensure_section_rows()
            self._database_initialized = True

    def _require_database_initialized(self) -> None:
        if not self._database_initialized:
            raise RuntimeError(
                "Automation database state has not been initialized. "
                "Call init_db() followed by "
                "automation_engine.initialize_database_state() during "
                "application startup."
            )

    # ==================================================================
    # CONFIGURATION
    # ==================================================================

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._dump(item)
                for item in self.items.values()
            ]

    def get(self, automation_id: str) -> Automation:
        automation_id = str(
            automation_id or ""
        ).strip()

        if not automation_id:
            raise ValueError(
                "Automation ID is required"
            )

        with self._lock:
            item = self.items.get(
                automation_id
            )

        if item is None:
            raise KeyError(
                automation_id
            )

        return item

    def create(
        self,
        name: str,
        symbols: list[str] | None = None,
        strategy: str | None = None,
        auto_select_strategy: bool = True,
        max_position_value: float = 2500.0,
        enabled: bool = False,
        asset_class: str = "stocks",
        trading_style: str = "intraday",
        capital_allocation: float | None = None,
        max_daily_loss: float | None = None,
        max_open_positions: int | None = None,
        allow_long: bool = True,
        allow_short: bool = False,
    ) -> dict[str, Any]:
        normalized_name = str(
            name or ""
        ).strip()

        if not normalized_name:
            raise ValueError(
                "Automation name is required"
            )

        asset = self._normalize_asset_class(
            asset_class
        )

        if asset not in self.ASSET_SECTIONS:
            raise ValueError(
                f"Unsupported automation asset class: {asset_class}"
            )

        selected_strategy = self._strategy(
            strategy
        )

        if (
            not auto_select_strategy
            and selected_strategy is None
        ):
            raise ValueError(
                "A strategy is required when automatic strategy "
                "selection is disabled"
            )

        position_value = self._required_positive(
            max_position_value,
            "max_position_value",
        )

        item = Automation(
            id=str(uuid4()),
            name=normalized_name,
            strategy=selected_strategy,
            symbols=self._symbols(
                symbols or []
            ),
            enabled=False,
            entries_paused=False,
            auto_select_strategy=bool(
                auto_select_strategy
            ),
            max_position_value=position_value,
            asset_class=asset,
            trading_style=self._normalize_trading_style(
                trading_style
            ),
            capital_allocation=self._optional_positive(
                capital_allocation
            ),
            max_daily_loss=self._optional_positive(
                max_daily_loss
            ),
            max_open_positions=self._optional_positive_int(
                max_open_positions
            ),
            allow_long=bool(
                allow_long
            ),
            allow_short=bool(
                allow_short
            ),
        )

        with self._lock:
            self.items[item.id] = item

        self._ensure_runtime(
            item.id
        )

        if enabled:
            return self.enable(
                item.id
            )

        return self._dump(
            item
        )

    def update(
        self,
        automation_id: str,
        *,
        name: str | None = None,
        symbols: list[str] | None = None,
        strategy: str | None = None,
        auto_select_strategy: bool | None = None,
        max_position_value: float | None = None,
        asset_class: str | None = None,
        trading_style: str | None = None,
        capital_allocation: float | None = None,
        max_daily_loss: float | None = None,
        max_open_positions: int | None = None,
        allow_long: bool | None = None,
        allow_short: bool | None = None,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        if self.is_running(
            item.id
        ):
            raise ValueError(
                "Stop the automation runtime before changing "
                "its configuration"
            )

        with self._lock:
            if name is not None:
                value = str(
                    name
                ).strip()

                if not value:
                    raise ValueError(
                        "Automation name cannot be empty"
                    )

                item.name = value

            if symbols is not None:
                item.symbols = self._symbols(
                    symbols
                )

            if strategy is not None:
                item.strategy = self._strategy(
                    strategy
                )

            if auto_select_strategy is not None:
                item.auto_select_strategy = bool(
                    auto_select_strategy
                )

            if (
                not item.auto_select_strategy
                and item.strategy is None
            ):
                raise ValueError(
                    "A strategy is required when automatic "
                    "strategy selection is disabled"
                )

            if max_position_value is not None:
                item.max_position_value = (
                    self._required_positive(
                        max_position_value,
                        "max_position_value",
                    )
                )

            if asset_class is not None:
                asset = self._normalize_asset_class(
                    asset_class
                )

                if asset not in self.ASSET_SECTIONS:
                    raise ValueError(
                        f"Unsupported automation asset class: "
                        f"{asset_class}"
                    )

                item.asset_class = asset

            if trading_style is not None:
                item.trading_style = (
                    self._normalize_trading_style(
                        trading_style
                    )
                )

            if capital_allocation is not None:
                item.capital_allocation = (
                    self._optional_positive(
                        capital_allocation
                    )
                )

            if max_daily_loss is not None:
                item.max_daily_loss = (
                    self._optional_positive(
                        max_daily_loss
                    )
                )

            if max_open_positions is not None:
                item.max_open_positions = (
                    self._optional_positive_int(
                        max_open_positions
                    )
                )

            if allow_long is not None:
                item.allow_long = bool(
                    allow_long
                )

            if allow_short is not None:
                item.allow_short = bool(
                    allow_short
                )

            item.updated_at = utc_now()

        return self._dump(
            item
        )

    def enable(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        self._validate_ready(
            item
        )

        with self._lock:
            item.enabled = True
            item.entries_paused = False
            item.updated_at = utc_now()

        self._set_runtime_state(
            item.id,
            "READY",
        )

        self._audit_sync(
            "AUTOMATION_ENABLED",
            item.id,
            {
                "automation_id": item.id,
                "asset_class": item.asset_class,
            },
        )

        return self._dump(
            item
        )

    def disable(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        with self._lock:
            item.enabled = False
            item.entries_paused = True
            item.updated_at = utc_now()

        self._audit_sync(
            "AUTOMATION_DISABLED",
            item.id,
            {
                "automation_id": item.id,
                "asset_class": item.asset_class,
                "new_entries_blocked": True,
            },
        )

        return self._dump(
            item
        )

    def pause_entries(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        if not item.enabled:
            raise ValueError(
                "Cannot pause entries for a disabled automation"
            )

        with self._lock:
            item.entries_paused = True
            item.updated_at = utc_now()

        if self.is_running(
            item.id
        ):
            self._set_runtime_state(
                item.id,
                "PAUSED",
            )

        return self._dump(
            item
        )

    def resume_entries(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        if not item.enabled:
            raise ValueError(
                "Cannot resume entries for a disabled automation"
            )

        if not self.section_enabled(
            item.asset_class
        ):
            raise ValueError(
                f"{item.asset_class} section is OFF"
            )

        with self._lock:
            item.entries_paused = False
            item.updated_at = utc_now()

        if self.is_running(
            item.id
        ):
            self._set_runtime_state(
                item.id,
                "RUNNING",
            )

        return self._dump(
            item
        )

    def delete(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        if self.is_running(
            item.id
        ):
            raise ValueError(
                "Stop automation before deleting it"
            )

        if item.enabled:
            raise ValueError(
                "Disable automation before deleting it"
            )

        with self._lock:
            removed = self.items.pop(
                item.id
            )

        with self._runtime_lock:
            self._runtimes.pop(
                item.id,
                None,
            )
            self._stop_events.pop(
                item.id,
                None,
            )
            self._symbol_tasks.pop(
                item.id,
                None,
            )
            self._tasks.pop(
                item.id,
                None,
            )

        return self._dump(
            removed
        )

    # ==================================================================
    # RUNTIME
    # ==================================================================

    async def start_runtime(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        self._validate_ready(
            item
        )

        if not item.enabled:
            raise ValueError(
                "Enable the automation before starting it"
            )

        if item.entries_paused:
            raise ValueError(
                "Resume automation entries before starting it"
            )

        if not self.section_enabled(
            item.asset_class
        ):
            raise ValueError(
                f"{item.asset_class} section is OFF"
            )

        if not item.symbols:
            raise ValueError(
                "Automation runtime requires at least one "
                "discovered or configured symbol"
            )

        if self.is_running(
            item.id
        ):
            return self.runtime_status(
                item.id
            )

        await self._validate_runtime_provider(
            item
        )

        stop_event = asyncio.Event()

        runtime = self._ensure_runtime(
            item.id
        )

        runtime.state = "STARTING"
        runtime.started_at = utc_now()
        runtime.stopped_at = None
        runtime.last_error = None

        task = asyncio.create_task(
            self._run_automation(
                item.id,
                stop_event,
            ),
            name=(
                f"phoenixtrend-automation-{item.id}"
            ),
        )

        with self._runtime_lock:
            self._stop_events[
                item.id
            ] = stop_event

            self._tasks[
                item.id
            ] = task

        await self._audit(
            "AUTOMATION_STARTED",
            {
                "automation_id": item.id,
                "name": item.name,
                "asset_class": item.asset_class,
                "symbols": list(
                    item.symbols
                ),
                "strategy": item.strategy,
                "auto_select_strategy": (
                    item.auto_select_strategy
                ),
            },
        )

        return self.runtime_status(
            item.id
        )

    async def stop_runtime(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        with self._runtime_lock:
            stop_event = self._stop_events.get(
                item.id
            )

            task = self._tasks.get(
                item.id
            )

        if stop_event is not None:
            stop_event.set()

        await self._cancel_symbol_tasks(
            item.id
        )

        if (
            task is not None
            and not task.done()
        ):
            task.cancel()

            try:
                await task

            except asyncio.CancelledError:
                pass

            except Exception as exc:
                self._set_runtime_error(
                    item.id,
                    str(exc),
                )

        with self._runtime_lock:
            self._tasks.pop(
                item.id,
                None,
            )

            self._stop_events.pop(
                item.id,
                None,
            )

        runtime = self._ensure_runtime(
            item.id
        )

        runtime.state = "STOPPED"
        runtime.stopped_at = utc_now()

        await self._audit(
            "AUTOMATION_STOPPED",
            {
                "automation_id": item.id,
                "name": item.name,
            },
        )

        return self.runtime_status(
            item.id
        )

    async def emergency_stop(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        with self._lock:
            item.entries_paused = True
            item.enabled = False
            item.updated_at = utc_now()

        await self.stop_runtime(
            item.id
        )

        runtime = self._ensure_runtime(
            item.id
        )

        runtime.state = "EMERGENCY_STOP"

        await self._audit(
            "EMERGENCY_STOP",
            {
                "automation_id": item.id,
                "name": item.name,
                "new_entries_blocked": True,
            },
        )

        return self.runtime_status(
            item.id
        )

    async def _run_automation(
        self,
        automation_id: str,
        stop_event: asyncio.Event,
    ) -> None:
        item = self.get(
            automation_id
        )

        runtime = self._ensure_runtime(
            item.id
        )

        engine = AutomaticEngine(
            strategy_picker=self.strategy_picker
        )

        engine.start(
            strategy_name=item.strategy,
            auto_select=item.auto_select_strategy,
        )

        runtime.state = "RUNNING"
        runtime.last_error = None

        tasks: dict[
            str,
            asyncio.Task[Any],
        ] = {}

        try:
            for symbol in item.symbols:
                tasks[
                    symbol
                ] = asyncio.create_task(
                    self._run_symbol(
                        automation_id=item.id,
                        symbol=symbol,
                        engine=engine,
                        stop_event=stop_event,
                    ),
                    name=(
                        f"phoenixtrend-"
                        f"{item.id}-{symbol}"
                    ),
                )

            with self._runtime_lock:
                self._symbol_tasks[
                    item.id
                ] = tasks

            results = await asyncio.gather(
                *tasks.values(),
                return_exceptions=True,
            )

            failures = [
                result
                for result in results
                if isinstance(
                    result,
                    Exception,
                )
                and not isinstance(
                    result,
                    asyncio.CancelledError,
                )
            ]

            if (
                failures
                and not stop_event.is_set()
            ):
                runtime.last_error = "; ".join(
                    str(error)
                    for error in failures
                )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            runtime.state = "ERROR"
            runtime.last_error = str(
                exc
            )

            await self._audit(
                "AUTOMATION_RUNTIME_FAILURE",
                {
                    "automation_id": item.id,
                    "error": str(exc),
                },
            )

        finally:
            engine.stop()

            await self._cancel_symbol_tasks(
                item.id,
                exclude_current=True,
            )

            if runtime.state not in {
                "ERROR",
                "EMERGENCY_STOP",
            }:
                runtime.state = "STOPPED"

            runtime.stopped_at = utc_now()

    async def _run_symbol(
        self,
        *,
        automation_id: str,
        symbol: str,
        engine: AutomaticEngine,
        stop_event: asyncio.Event,
    ) -> None:
        symbol = symbol.strip().upper()

        while not stop_event.is_set():
            item = self.get(
                automation_id
            )

            if (
                not item.enabled
                or item.entries_paused
                or not self.section_enabled(
                    item.asset_class
                )
            ):
                await asyncio.sleep(1)
                continue

            try:
                async for event in (
                    live_market_service.stream_candles(
                        symbol,
                        timeframe=self.LIVE_TIMEFRAME,
                        feed=self.LIVE_FEED,
                    )
                ):
                    if stop_event.is_set():
                        return

                    item = self.get(
                        automation_id
                    )

                    if (
                        not item.enabled
                        or item.entries_paused
                        or not self.section_enabled(
                            item.asset_class
                        )
                    ):
                        continue

                    if not isinstance(
                        event,
                        dict,
                    ):
                        continue

                    event_type = str(
                        event.get("type")
                        or ""
                    ).strip().lower()

                    if event_type == "live_status":
                        self._update_live_symbol(
                            item.id,
                            symbol,
                            {
                                "connected": bool(
                                    event.get(
                                        "connected",
                                        True,
                                    )
                                ),
                                "provider": event.get(
                                    "provider"
                                ),
                                "provider_mode": event.get(
                                    "provider_mode"
                                ),
                                "feed": event.get(
                                    "feed"
                                ),
                                "real_time_stream": bool(
                                    event.get(
                                        "real_time_stream"
                                    )
                                ),
                                "simulated": bool(
                                    event.get(
                                        "simulated",
                                        True,
                                    )
                                ),
                                "last_event_at": utc_now(),
                            },
                        )
                        continue

                    if event_type != "candle":
                        continue

                    candle = event.get(
                        "candle"
                    )

                    if not isinstance(
                        candle,
                        dict,
                    ):
                        continue

                    if (
                        event.get(
                            "real_time_stream"
                        )
                        is not True
                    ):
                        continue

                    if (
                        event.get(
                            "simulated"
                        )
                        is not False
                    ):
                        continue

                    provider = str(
                        event.get(
                            "provider"
                        )
                        or ""
                    ).strip().lower()

                    provider_mode = str(
                        event.get(
                            "provider_mode"
                        )
                        or ""
                    ).strip().lower()

                    if (
                        provider != "alpaca"
                        or provider_mode != "stream"
                    ):
                        continue

                    price = self._positive_number(
                        candle.get(
                            "close"
                        )
                    )

                    timestamp = (
                        candle.get(
                            "timestamp"
                        )
                        or candle.get(
                            "time"
                        )
                        or event.get(
                            "timestamp"
                        )
                    )

                    if not timestamp:
                        continue

                    self._update_live_symbol(
                        item.id,
                        symbol,
                        {
                            "connected": True,
                            "provider": provider,
                            "provider_mode": provider_mode,
                            "feed": event.get(
                                "feed"
                            ),
                            "real_time_stream": True,
                            "simulated": False,
                            "price": price,
                            "timestamp": timestamp,
                            "last_event_at": utc_now(),
                        },
                    )

                    await self._process_live_opportunity(
                        automation=item,
                        symbol=symbol,
                        live_event=event,
                        live_price=price,
                        engine=engine,
                    )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                self._update_live_symbol(
                    item.id,
                    symbol,
                    {
                        "connected": False,
                        "error": str(exc),
                        "last_event_at": utc_now(),
                    },
                )

                self._set_runtime_error(
                    item.id,
                    str(exc),
                )

                await self._audit(
                    "AUTOMATION_RUNTIME_FAILURE",
                    {
                        "automation_id": item.id,
                        "symbol": symbol,
                        "error": str(exc),
                    },
                )

                if stop_event.is_set():
                    return

                await asyncio.sleep(5)

    async def _process_live_opportunity(
        self,
        *,
        automation: Automation,
        symbol: str,
        live_event: dict[str, Any],
        live_price: float,
        engine: AutomaticEngine,
    ) -> None:
        if (
            not automation.enabled
            or automation.entries_paused
            or not self.section_enabled(
                automation.asset_class
            )
        ):
            return

        runtime = self._ensure_runtime(
            automation.id
        )

        runtime.cycles += 1
        runtime.opportunities += 1
        runtime.last_cycle_at = utc_now()
        runtime.last_symbol = symbol

        account = await self._account_state()

        candle_payload = live_event.get(
            "candle"
        )

        if not isinstance(
            candle_payload,
            dict,
        ):
            candle_payload = {}

        live_market_data = {
            "symbol": symbol,
            "asset_class": automation.asset_class,
            "asset_type": self._asset_type_for_section(
                automation.asset_class
            ),
            "price": live_price,
            "provider": str(
                live_event.get(
                    "provider"
                )
                or ""
            ).lower(),
            "provider_mode": str(
                live_event.get(
                    "provider_mode"
                )
                or ""
            ).lower(),
            "real_time_stream": (
                live_event.get(
                    "real_time_stream"
                )
                is True
            ),
            "simulated": (
                live_event.get(
                    "simulated"
                )
                is not False
            ),
            "automatic_execution_safe": True,
            "feed": live_event.get(
                "feed"
            ),
            "timeframe": live_event.get(
                "timeframe"
            ),
            "timestamp": (
                candle_payload.get(
                    "timestamp"
                )
                or candle_payload.get(
                    "time"
                )
                or live_event.get(
                    "timestamp"
                )
            ),
            "candle": live_event.get(
                "candle"
            ),
        }

        if (
            live_market_data[
                "provider"
            ] != "alpaca"
            or live_market_data[
                "provider_mode"
            ] != "stream"
            or live_market_data[
                "real_time_stream"
            ] is not True
            or live_market_data[
                "simulated"
            ] is not False
            or not live_market_data[
                "timestamp"
            ]
        ):
            await self._audit(
                "AUTOMATION_OPPORTUNITY_BLOCKED",
                {
                    "automation_id": automation.id,
                    "symbol": symbol,
                    "reason": (
                        "BLOCKED_LIVE_MARKET_DATA"
                    ),
                },
            )
            return

        try:
            result = await engine.process(
                symbol=symbol,
                market_data=live_market_data,
                quantity=self._quantity_for(
                    automation,
                    live_price,
                ),
                account=account,
                strategy_name=automation.strategy,
                strategy_config=None,
                automation_enabled=True,
                automation_id=automation.id,
                asset_class=automation.asset_class,
            )

        except RuntimeError as exc:
            runtime.last_error = str(
                exc
            )

            await self._audit(
                "AUTOMATION_OPPORTUNITY_BLOCKED",
                {
                    "automation_id": automation.id,
                    "symbol": symbol,
                    "reason": str(exc),
                },
            )
            return

        runtime.last_action = self._nested_text(
            result,
            "decision",
            "action",
        )

        runtime.last_strategy = self._nested_text(
            result,
            "decision",
            "strategy",
        )

        runtime.last_execution_state = (
            str(
                result.get(
                    "status"
                )
                or ""
            ).strip()
            or None
        )

        if result.get(
            "intent"
        ) is not None:
            runtime.orders_requested += 1

        await self._audit(
            "AUTOMATION_OPPORTUNITY",
            {
                "automation_id": automation.id,
                "symbol": symbol,
                "result": result,
            },
        )

    # ==================================================================
    # PROVIDER / ACCOUNT
    # ==================================================================

    async def _validate_runtime_provider(
        self,
        automation: Automation,
    ) -> None:
        broker_status = alpaca_broker.status()

        if not isinstance(
            broker_status,
            dict,
        ):
            raise RuntimeError(
                "Broker status is unavailable"
            )

        if not broker_status.get(
            "connected",
            False,
        ):
            raise RuntimeError(
                "Connect Alpaca before starting automation"
            )

        feed_status = (
            await live_market_service.check_feed(
                self.LIVE_FEED
            )
        )

        if (
            not isinstance(
                feed_status,
                dict,
            )
            or not feed_status.get(
                "available",
                False,
            )
        ):
            message = (
                feed_status.get(
                    "message"
                )
                if isinstance(
                    feed_status,
                    dict,
                )
                else None
            )

            raise RuntimeError(
                "Alpaca live market-data feed is unavailable: "
                f"{message or 'unknown error'}"
            )

    async def _account_state(
        self,
    ) -> AccountState:
        account_payload = (
            await alpaca_broker.account()
        )

        positions_payload = (
            await alpaca_broker.positions()
        )

        if not isinstance(
            account_payload,
            dict,
        ):
            raise RuntimeError(
                "Broker account state is unavailable"
            )

        if not isinstance(
            positions_payload,
            list,
        ):
            raise RuntimeError(
                "Broker position state is unavailable"
            )

        buying_power = self._optional_number(
            account_payload.get(
                "buying_power"
            )
        )

        if buying_power is None:
            buying_power = self._optional_number(
                account_payload.get(
                    "cash"
                )
            )

        if buying_power is None:
            raise RuntimeError(
                "Broker buying power is unavailable"
            )

        gross_exposure = 0.0

        for position in positions_payload:
            if not isinstance(
                position,
                dict,
            ):
                continue

            market_value = self._optional_number(
                position.get(
                    "market_value"
                )
            )

            if market_value is not None:
                gross_exposure += abs(
                    market_value
                )

        daily_pnl = self._optional_number(
            account_payload.get(
                "daily_pnl"
            )
        )

        weekly_pnl = self._optional_number(
            account_payload.get(
                "weekly_pnl"
            )
        )

        if (
            daily_pnl is None
            or weekly_pnl is None
        ):
            raise RuntimeError(
                "Confirmed daily/weekly account P&L is "
                "unavailable; automatic risk evaluation "
                "cannot continue safely"
            )

        return AccountState(
            buying_power=buying_power,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            open_positions=len(
                positions_payload
            ),
            gross_exposure=gross_exposure,
        )

    # ==================================================================
    # SECTION CONTROL
    # ==================================================================

    def _ensure_section_rows(
        self,
    ) -> None:
        with SessionLocal() as session:
            changed = False

            for asset in self.ASSET_SECTIONS:
                row = self._section_row(
                    session,
                    asset,
                )

                if row is None:
                    session.add(
                        AutomationAssetConfiguration(
                            asset_class=asset,
                            enabled=False,
                        )
                    )
                    changed = True

            if changed:
                session.commit()

    @staticmethod
    def _section_row(
        session: Any,
        asset_class: str,
    ) -> AutomationAssetConfiguration | None:
        return session.execute(
            select(
                AutomationAssetConfiguration
            ).where(
                AutomationAssetConfiguration.asset_class
                == asset_class
            )
        ).scalar_one_or_none()

    def section_enabled(
        self,
        asset_class: str,
    ) -> bool:
        self._require_database_initialized()

        asset = self._normalize_asset_class(
            asset_class
        )

        if asset not in self.ASSET_SECTIONS:
            return False

        with SessionLocal() as session:
            row = self._section_row(
                session,
                asset,
            )

            return bool(
                row is not None
                and row.enabled
            )

    def set_section_enabled(
        self,
        asset_class: str,
        enabled: bool,
    ) -> dict[str, Any]:
        self._require_database_initialized()

        asset = self._normalize_asset_class(
            asset_class
        )

        if asset not in self.ASSET_SECTIONS:
            raise ValueError(
                f"Unsupported automation section: {asset_class}"
            )

        with SessionLocal() as session:
            row = self._section_row(
                session,
                asset,
            )

            if row is None:
                row = AutomationAssetConfiguration(
                    asset_class=asset,
                    enabled=bool(
                        enabled
                    ),
                )
                session.add(
                    row
                )

            else:
                row.enabled = bool(
                    enabled
                )

                if hasattr(
                    row,
                    "updated_at",
                ):
                    row.updated_at = datetime.now(
                        timezone.utc
                    )

            session.commit()

        self._audit_sync(
            (
                "AUTOMATION_ENABLED"
                if enabled
                else "AUTOMATION_DISABLED"
            ),
            asset,
            {
                "asset_class": asset,
                "section": True,
                "enabled": bool(
                    enabled
                ),
                "new_entries_blocked": (
                    not bool(enabled)
                ),
            },
        )

        return self.section_state(
            asset
        )

    async def enable_section(
        self,
        asset_class: str,
    ) -> dict[str, Any]:
        return self.set_section_enabled(
            asset_class,
            True,
        )

    async def disable_section(
        self,
        asset_class: str,
    ) -> dict[str, Any]:
        asset = self._normalize_asset_class(
            asset_class
        )

        if asset not in self.ASSET_SECTIONS:
            raise ValueError(
                f"Unsupported automation section: {asset_class}"
            )

        self.set_section_enabled(
            asset,
            False,
        )

        affected: list[str] = []

        for item in list(
            self.items.values()
        ):
            if (
                self._normalize_asset_class(
                    item.asset_class
                )
                != asset
            ):
                continue

            item.entries_paused = True
            item.updated_at = utc_now()

            affected.append(
                item.id
            )

            if self.is_running(
                item.id
            ):
                await self.stop_runtime(
                    item.id
                )

        state = self.section_state(
            asset
        )

        state[
            "affected_automations"
        ] = affected

        state[
            "new_entries_blocked"
        ] = True

        state[
            "positions_liquidated"
        ] = False

        return state

    def section_state(
        self,
        asset_class: str,
    ) -> dict[str, Any]:
        self._require_database_initialized()

        asset = self._normalize_asset_class(
            asset_class
        )

        if asset not in self.ASSET_SECTIONS:
            raise ValueError(
                f"Unsupported automation section: {asset_class}"
            )

        with self._lock:
            items = [
                item
                for item in self.items.values()
                if (
                    self._normalize_asset_class(
                        item.asset_class
                    )
                    == asset
                )
            ]

        return {
            "asset_class": asset,
            "enabled": self.section_enabled(
                asset
            ),
            "automation_count": len(
                items
            ),
            "enabled_automations": sum(
                1
                for item in items
                if item.enabled
            ),
            "running_automations": sum(
                1
                for item in items
                if self.is_running(
                    item.id
                )
            ),
        }

    def section_list(
        self,
    ) -> list[dict[str, Any]]:
        self._require_database_initialized()

        return [
            self.section_state(
                asset
            )
            for asset in self.ASSET_SECTIONS
        ]

    async def start_enabled_sections(
        self,
    ) -> dict[str, Any]:
        self._require_database_initialized()

        if self._emergency_stop:
            raise RuntimeError(
                "Emergency Stop is active"
            )

        # Arm the master engine first. Running automations may legitimately be
        # zero until a section/automation is enabled.
        self._master_enabled = True

        started: list[str] = []
        skipped: list[
            dict[str, str]
        ] = []

        for item in list(
            self.items.values()
        ):
            if not item.enabled:
                continue

            if not self.section_enabled(
                item.asset_class
            ):
                continue

            if self.is_running(
                item.id
            ):
                continue

            try:
                await self.start_runtime(
                    item.id
                )

                started.append(
                    item.id
                )

            except Exception as exc:
                skipped.append(
                    {
                        "automation_id": item.id,
                        "reason": str(exc),
                    }
                )

        return {
            "state": "RUNNING",
            "master_enabled": True,
            "running_automations": self.running_count(),
            "started": started,
            "skipped": skipped,
            "sections": self.section_list(),
        }

    async def stop_all_runtimes(
        self,
    ) -> dict[str, Any]:
        self._master_enabled = False

        stopped: list[str] = []

        for automation_id in list(
            self.items.keys()
        ):
            if not self.is_running(
                automation_id
            ):
                continue

            await self.stop_runtime(
                automation_id
            )

            stopped.append(
                automation_id
            )

        return {
            "state": (
                "EMERGENCY_STOP"
                if self._emergency_stop
                else "STOPPED"
            ),
            "master_enabled": False,
            "running_automations": self.running_count(),
            "stopped": stopped,
            "sections": (
                self.section_list()
                if self._database_initialized
                else []
            ),
        }

    def activate_master_emergency_stop(
        self,
    ) -> None:
        self._emergency_stop = True
        self._master_enabled = False

    def clear_master_emergency_stop(
        self,
    ) -> dict[str, Any]:
        self._emergency_stop = False
        self._master_enabled = False
        return self.engine_status()

    # ==================================================================
    # STATUS
    # ==================================================================

    def runtime_status(
        self,
        automation_id: str,
    ) -> dict[str, Any]:
        item = self.get(
            automation_id
        )

        runtime = self._ensure_runtime(
            item.id
        )

        with self._runtime_lock:
            task = self._tasks.get(
                item.id
            )

        data = asdict(
            runtime
        )

        data[
            "task_running"
        ] = bool(
            task is not None
            and not task.done()
        )

        data[
            "automation"
        ] = self._dump(
            item
        )

        return data

    def runtime_list(
        self,
    ) -> list[dict[str, Any]]:
        with self._lock:
            ids = list(
                self.items
            )

        return [
            self.runtime_status(
                item_id
            )
            for item_id in ids
        ]

    def is_running(
        self,
        automation_id: str,
    ) -> bool:
        with self._runtime_lock:
            task = self._tasks.get(
                automation_id
            )

        return bool(
            task is not None
            and not task.done()
        )

    def running_count(
        self,
    ) -> int:
        with self._lock:
            ids = list(
                self.items
            )

        return sum(
            1
            for item_id in ids
            if self.is_running(
                item_id
            )
        )

    def engine_status(
        self,
    ) -> dict[str, Any]:
        running = self.running_count()

        state = (
            "EMERGENCY_STOP"
            if self._emergency_stop
            else (
                "RUNNING"
                if self._master_enabled
                else "STOPPED"
            )
        )

        return {
            "state": state,
            "master_enabled": self._master_enabled,
            "emergency_stop": self._emergency_stop,
            "running_automations": running,
            "enabled_automations": sum(
                1
                for item in self.items.values()
                if item.enabled
            ),
            "sections": (
                self.section_list()
                if self._database_initialized
                else []
            ),
            "database_initialized": (
                self._database_initialized
            ),
        }

    # ==================================================================
    # INTERNAL RUNTIME STATE
    # ==================================================================

    def _ensure_runtime(
        self,
        automation_id: str,
    ) -> AutomationRuntime:
        with self._runtime_lock:
            runtime = self._runtimes.get(
                automation_id
            )

            if runtime is None:
                runtime = AutomationRuntime(
                    automation_id=automation_id
                )

                self._runtimes[
                    automation_id
                ] = runtime

            return runtime

    def _set_runtime_state(
        self,
        automation_id: str,
        state: str,
    ) -> None:
        self._ensure_runtime(
            automation_id
        ).state = state

    def _set_runtime_error(
        self,
        automation_id: str,
        error: str,
    ) -> None:
        self._ensure_runtime(
            automation_id
        ).last_error = str(
            error
        )

    def _update_live_symbol(
        self,
        automation_id: str,
        symbol: str,
        data: dict[str, Any],
    ) -> None:
        runtime = self._ensure_runtime(
            automation_id
        )

        current = runtime.live_symbols.get(
            symbol,
            {},
        )

        current.update(
            data
        )

        runtime.live_symbols[
            symbol
        ] = current

    async def _cancel_symbol_tasks(
        self,
        automation_id: str,
        *,
        exclude_current: bool = False,
    ) -> None:
        with self._runtime_lock:
            tasks = dict(
                self._symbol_tasks.pop(
                    automation_id,
                    {},
                )
            )

        current = asyncio.current_task()

        pending: list[
            asyncio.Task[Any]
        ] = []

        for task in tasks.values():
            if (
                exclude_current
                and task is current
            ):
                continue

            if task.done():
                continue

            task.cancel()
            pending.append(
                task
            )

        if pending:
            await asyncio.gather(
                *pending,
                return_exceptions=True,
            )

    # ==================================================================
    # VALIDATION / NORMALIZATION
    # ==================================================================

    def _validate_ready(
        self,
        automation: Automation,
    ) -> None:
        if (
            automation.asset_class
            not in self.ASSET_SECTIONS
        ):
            raise ValueError(
                "Automation has unsupported asset class"
            )

        if (
            automation.max_position_value
            <= 0
        ):
            raise ValueError(
                "Automation has invalid position limit"
            )

        if (
            not automation.auto_select_strategy
            and automation.strategy is None
        ):
            raise ValueError(
                "Automation requires a selected strategy"
            )

        if (
            automation.strategy is not None
            and not self.strategy_picker.exists(
                automation.strategy
            )
        ):
            raise ValueError(
                "Automation references an unknown strategy"
            )

    def _strategy(
        self,
        strategy: str | None,
    ) -> str | None:
        if strategy is None:
            return None

        normalized = str(
            strategy
        ).strip()

        if not normalized:
            return None

        if not self.strategy_picker.exists(
            normalized
        ):
            raise ValueError(
                f"Unknown strategy: {strategy}"
            )

        return self.strategy_picker.resolve_name(
            normalized
        )

    @staticmethod
    def _symbols(
        symbols: list[str],
    ) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()

        for symbol in symbols:
            value = str(
                symbol or ""
            ).strip().upper()

            if (
                not value
                or value in seen
            ):
                continue

            seen.add(
                value
            )

            output.append(
                value
            )

        return output

    @staticmethod
    def _normalize_asset_class(
        value: str | None,
    ) -> str:
        raw = str(
            value or "stocks"
        ).strip().lower().replace(
            "-",
            "_",
        ).replace(
            " ",
            "_",
        )

        aliases = {
            "stock": "stocks",
            "equity": "stocks",
            "equities": "stocks",
            "option": "options",
            "cryptocurrency": "crypto",
            "etf": "etfs",
            "fx": "forex",
            "bond": "bonds",
            "fixed_income": "bonds",
        }

        return aliases.get(
            raw,
            raw,
        )

    @staticmethod
    def _normalize_trading_style(
        value: str | None,
    ) -> str:
        raw = str(
            value or "intraday"
        ).strip().lower().replace(
            "-",
            "_",
        ).replace(
            " ",
            "_",
        )

        aliases = {
            "day": "intraday",
            "day_trading": "intraday",
            "longterm": "long_term",
        }

        return aliases.get(
            raw,
            raw,
        )

    @staticmethod
    def _required_positive(
        value: Any,
        field_name: str,
    ) -> float:
        try:
            number = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                f"{field_name} must be numeric"
            ) from exc

        if number <= 0:
            raise ValueError(
                f"{field_name} must be greater than zero"
            )

        return number

    @staticmethod
    def _optional_positive(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            number = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Value must be numeric"
            ) from exc

        if number <= 0:
            raise ValueError(
                "Value must be greater than zero"
            )

        return number

    @staticmethod
    def _optional_positive_int(
        value: Any,
    ) -> int | None:
        if value is None:
            return None

        try:
            number = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(
                "Value must be an integer"
            ) from exc

        if number <= 0:
            raise ValueError(
                "Value must be greater than zero"
            )

        return number

    @staticmethod
    def _optional_number(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            number = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return None

        if number != number:
            return None

        if number in {
            float("inf"),
            float("-inf"),
        }:
            return None

        return number

    @classmethod
    def _positive_number(
        cls,
        value: Any,
    ) -> float:
        number = cls._optional_number(
            value
        )

        if (
            number is None
            or number <= 0
        ):
            raise ValueError(
                "Live market price must be greater than zero"
            )

        return number

    @staticmethod
    def _asset_type_for_section(
        asset_class: str,
    ) -> str:
        mapping = {
            "stocks": "EQUITY",
            "options": "OPTION",
            "crypto": "CRYPTO",
            "etfs": "ETF",
            "forex": "FOREX",
            "bonds": "BOND",
        }

        asset = str(
            asset_class
        ).strip().lower()

        if asset not in mapping:
            raise ValueError(
                f"Unsupported asset class: {asset_class}"
            )

        return mapping[
            asset
        ]

    @staticmethod
    def _quantity_for(
        automation: Automation,
        price: float,
    ) -> float:
        if price <= 0:
            raise ValueError(
                "Live price must be greater than zero"
            )

        if (
            automation.max_position_value
            <= 0
        ):
            raise ValueError(
                "Automation max_position_value is invalid"
            )

        quantity = (
            automation.max_position_value
            / price
        )

        if quantity <= 0:
            raise RuntimeError(
                "Calculated quantity is invalid"
            )

        return quantity

    @staticmethod
    def _nested_text(
        payload: dict[str, Any],
        parent: str,
        key: str,
    ) -> str | None:
        nested = payload.get(
            parent
        )

        if not isinstance(
            nested,
            dict,
        ):
            return None

        value = nested.get(
            key
        )

        if value is None:
            return None

        value = str(
            value
        ).strip()

        return value or None

    @staticmethod
    def _dump(
        automation: Automation,
    ) -> dict[str, Any]:
        data = asdict(
            automation
        )

        data[
            "mode"
        ] = automation.mode.value

        return data

    # ==================================================================
    # AUDIT
    # ==================================================================

    @staticmethod
    def _audit_sync(
        event_type: str,
        entity_id: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            audit.log(
                event_type,
                entity_id,
                payload,
            )

        except Exception:
            pass

    @staticmethod
    async def _audit(
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        try:
            entity_id = str(
                payload.get(
                    "automation_id"
                )
                or payload.get(
                    "intent_id"
                )
                or payload.get(
                    "symbol"
                )
                or "automation"
            )

            audit.log(
                event_type,
                entity_id,
                payload,
            )

        except Exception:
            pass


# Safe to construct during module import because __init__ no longer
# queries the database. main.py must call:
#
#     init_db()
#     automation_engine.initialize_database_state()
#
# in that order during application startup.
automation_engine = AutomationEngine()


__all__ = [
    "Automation",
    "AutomationRuntime",
    "AutomationEngine",
    "automation_engine",
]